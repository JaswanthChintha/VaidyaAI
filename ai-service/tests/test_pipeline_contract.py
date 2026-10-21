from __future__ import annotations

import io
import logging

import pytest

from app.core.auth import SERVICE_KEY_HEADER
from app.core.request_context import REQUEST_ID_HEADER, sanitize_request_id
from app.services.feature_engineer import engineer_features, engineer_from_extraction
from tests.conftest import TEST_SERVICE_KEY
from tests.test_feature_engineer import OBSERVED_MODULE_4_PARAMETERS

ENGINEER = "/api/v1/features/engineer"
EXTRACT = "/api/v1/ocr/extract"

REPAIR_WARNING = "page 1 was recovered by the PDF repairer"

SKIPPED_PAGE_WARNING = (
    "Page 2 could not be processed by the extraction model "
    "(MODEL_RESPONSE_MALFORMED); it was skipped."
)


def module_4_payload(**overrides) -> dict:
    payload = {
        "source": {
            "filename": "report.pdf",
            "mime_type": "application/pdf",
            "page_count": 2,
            "size_bytes": 20481,
        },
        "raw_text": "NORTHFIELD DIAGNOSTIC LABORATORY ...",
        "pages": [
            {"page_number": 1, "raw_text": "HbA1c 6.8 % H 4.0 - 5.6"},
            {"page_number": 2, "raw_text": None},
        ],
        "extracted_parameters": OBSERVED_MODULE_4_PARAMETERS,
        "report_metadata": {
            "lab_name": "Northfield Diagnostic Laboratory",
            "report_date": "12/03/2024",
            "patient_name_present": True,
        },
        "extraction_confidence": 0.87,
        "warnings": [REPAIR_WARNING, SKIPPED_PAGE_WARNING],
    }
    payload.update(overrides)
    return payload


def test_module_4_warnings_reach_module_5_output(client):
    body = client.post(ENGINEER, json={"extraction": module_4_payload()}).json()
    data = body["data"]

    messages = [w["message"] for w in data["upstream_warnings"]]
    assert REPAIR_WARNING in messages
    assert SKIPPED_PAGE_WARNING in messages
    assert len(data["upstream_warnings"]) == 2


def test_every_warning_records_the_stage_that_raised_it(client):
    payload = module_4_payload(
        extracted_parameters=[
            {"test_name": "HbA1c", "value_raw": "6.8", "value_numeric": 6.8},
        ]
    )
    data = client.post(ENGINEER, json={"extraction": payload}).json()["data"]

    by_stage: dict = {}
    for warning in data["all_warnings"]:
        assert set(warning) == {"stage", "module", "message"}
        by_stage.setdefault(warning["stage"], []).append(warning["message"])

    assert set(by_stage) == {"extraction", "feature_engineering"}
    assert REPAIR_WARNING in by_stage["extraction"]
    assert any("no printed unit" in m for m in by_stage["feature_engineering"])

    modules = {w["stage"]: w["module"] for w in data["all_warnings"]}
    assert modules == {"extraction": 4, "feature_engineering": 5}


def test_upstream_warnings_are_not_merged_into_module_5s_own_list(client):
    data = client.post(ENGINEER, json={"extraction": module_4_payload()}).json()["data"]
    assert data["warnings"] == []
    assert len(data["upstream_warnings"]) == 2
    assert data["upstream_warnings"][0]["stage"] == "extraction"


def test_all_warnings_lists_upstream_first(client):
    payload = module_4_payload(
        extracted_parameters=[{"test_name": "HbA1c", "value_raw": "6.8"}]
    )
    data = client.post(ENGINEER, json={"extraction": payload}).json()["data"]
    stages = [w["stage"] for w in data["all_warnings"]]
    assert stages == sorted(stages, key=lambda s: s != "extraction")
    assert stages[0] == "extraction"
    assert stages[-1] == "feature_engineering"
    assert len(data["all_warnings"]) == len(data["upstream_warnings"]) + len(
        data["warnings"]
    )


def test_upstream_warnings_are_relayed_verbatim_never_edited(client):
    odd = "  page 3 :: unreadable -- 50% coverage  "
    payload = module_4_payload(warnings=[odd])
    data = client.post(ENGINEER, json={"extraction": payload}).json()["data"]
    assert data["upstream_warnings"][0]["message"] == odd


def test_no_upstream_warnings_yields_empty_lists_not_nulls(client):
    payload = module_4_payload(warnings=[])
    data = client.post(ENGINEER, json={"extraction": payload}).json()["data"]
    assert data["upstream_warnings"] == []
    assert data["all_warnings"] == []
    assert data["summary"]["upstream_warning_count"] == 0


def test_a_bare_string_warning_is_accepted(client):
    payload = module_4_payload(warnings=REPAIR_WARNING)
    data = client.post(ENGINEER, json={"extraction": payload}).json()["data"]
    assert [w["message"] for w in data["upstream_warnings"]] == [REPAIR_WARNING]


def test_extraction_confidence_survives_the_boundary(client):
    data = client.post(ENGINEER, json={"extraction": module_4_payload()}).json()["data"]
    assert data["upstream"]["extraction_confidence"] == pytest.approx(0.87)


def test_report_metadata_survives_the_boundary(client):
    data = client.post(ENGINEER, json={"extraction": module_4_payload()}).json()["data"]
    metadata = data["upstream"]["report_metadata"]
    assert metadata["lab_name"] == "Northfield Diagnostic Laboratory"
    assert metadata["report_date"] == "12/03/2024"
    assert metadata["patient_name_present"] is True
    assert set(metadata) == {
        "lab_name", "report_date", "patient_name_present", "patient_sex", "patient_age",
    }


def test_source_information_survives_the_boundary(client):
    data = client.post(ENGINEER, json={"extraction": module_4_payload()}).json()["data"]
    source = data["upstream"]["source"]
    assert source["filename"] == "report.pdf"
    assert source["mime_type"] == "application/pdf"
    assert source["page_count"] == 2
    assert source["size_bytes"] == 20481


def test_per_page_readability_survives_so_a_gap_is_not_read_as_absence(client):
    data = client.post(ENGINEER, json={"extraction": module_4_payload()}).json()["data"]
    upstream = data["upstream"]
    assert upstream["pages"] == [
        {"page_number": 1, "raw_text_available": True},
        {"page_number": 2, "raw_text_available": False},
    ]
    assert upstream["pages_unreadable"] == [2]
    assert data["summary"]["pages_unreadable_count"] == 1


def test_page_text_itself_is_not_carried_forward(client):
    payload = module_4_payload(
        raw_text="CANARY-BULK-REPORT-TEXT",
        pages=[{"page_number": 1, "raw_text": "CANARY-PAGE-TEXT"}],
    )
    response = client.post(ENGINEER, json={"extraction": payload})
    assert "CANARY-BULK-REPORT-TEXT" not in response.text
    assert "CANARY-PAGE-TEXT" not in response.text
    assert response.json()["data"]["upstream"]["pages"] == [
        {"page_number": 1, "raw_text_available": True}
    ]


def test_upstream_block_reports_when_no_extraction_context_was_given(client):
    body = client.post(
        ENGINEER,
        json={"extraction": {"extracted_parameters": OBSERVED_MODULE_4_PARAMETERS}},
    ).json()
    upstream = body["data"]["upstream"]
    assert upstream["provided"] is True
    assert upstream["source"] is None
    assert upstream["extraction_confidence"] is None
    assert upstream["pages"] == []
    assert upstream["pages_unreadable"] == []


def test_direct_import_carries_upstream_context_too(client):
    data = engineer_from_extraction(module_4_payload())
    assert [w.message for w in data.upstream_warnings] == [
        REPAIR_WARNING,
        SKIPPED_PAGE_WARNING,
    ]
    assert data.upstream.pages_unreadable == [2]
    assert data.upstream.extraction_confidence == pytest.approx(0.87)
    del client


def test_engineer_features_without_an_extraction_stays_backwards_compatible():
    data = engineer_features(OBSERVED_MODULE_4_PARAMETERS)
    assert data.upstream.provided is False
    assert data.upstream_warnings == []
    assert data.all_warnings == []
    assert data.warnings == []


def test_engineer_features_derives_rows_from_the_extraction_when_omitted():
    data = engineer_features(extraction=module_4_payload())
    assert data.summary.parameters_received == len(OBSERVED_MODULE_4_PARAMETERS)
    assert "hba1c" in data.features


def test_canonical_form_extraction_key(client):
    body = client.post(
        ENGINEER,
        json={"extraction": module_4_payload(), "profile": {"age": 45}},
    ).json()
    assert body["success"] is True
    assert "hba1c" in body["data"]["features"]
    assert body["data"]["features"]["age"]["value"] == 45
    assert len(body["data"]["upstream_warnings"]) == 2


def test_module_4_response_envelope_is_accepted_verbatim(client):
    body = client.post(
        ENGINEER,
        json={"success": True, "data": module_4_payload(), "profile": {"age": 45}},
    ).json()
    assert body["success"] is True
    assert "hba1c" in body["data"]["features"]
    assert body["data"]["features"]["age"]["value"] == 45
    assert len(body["data"]["upstream_warnings"]) == 2


def test_a_bare_module_4_data_object_is_accepted(client):
    body = client.post(ENGINEER, json=module_4_payload()).json()
    assert body["success"] is True
    assert "hba1c" in body["data"]["features"]
    assert len(body["data"]["upstream_warnings"]) == 2


def test_an_explicit_extraction_key_wins_over_an_envelope(client):
    body = client.post(
        ENGINEER,
        json={
            "extraction": {
                "extracted_parameters": [{"test_name": "HbA1c", "value_raw": "6.8"}]
            },
            "data": module_4_payload(),
        },
    ).json()
    assert body["data"]["summary"]["parameters_received"] == 1
    assert body["data"]["upstream_warnings"] == []


def test_an_ambiguous_body_is_rejected_not_guessed_at(client):
    response = client.post(
        ENGINEER,
        json={
            "data": module_4_payload(),
            "extracted_parameters": OBSERVED_MODULE_4_PARAMETERS,
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_tolerance_does_not_weaken_validation(client):
    for body in (
        {"extraction": {"extracted_parameters": [{"value_raw": "6.8"}]}},
        {"success": True, "data": {"extracted_parameters": [{"value_raw": "6.8"}]}},
        {"extracted_parameters": [{"value_raw": "6.8"}]},
    ):
        response = client.post(ENGINEER, json=body)
        assert response.status_code == 422, body
        assert response.json()["success"] is False


def test_a_non_dict_data_key_is_not_mistaken_for_an_extraction(client):
    body = client.post(ENGINEER, json={"success": True, "data": "not-an-object"}).json()
    assert body["success"] is True
    assert body["data"]["features"] == {}


def test_end_to_end_extract_then_engineer(client, synthetic_pdf):
    extraction = client.post(
        EXTRACT,
        files={"file": ("report.pdf", io.BytesIO(synthetic_pdf), "application/pdf")},
    )
    assert extraction.status_code == 200
    envelope = extraction.json()
    assert set(envelope) == {"success", "data"}

    for body in (envelope, {"extraction": envelope["data"]}):
        engineered = client.post(ENGINEER, json=body)
        assert engineered.status_code == 200, engineered.text
        data = engineered.json()["data"]
        assert "hba1c" in data["features"]
        assert data["upstream"]["provided"] is True
        assert data["upstream"]["source"]["filename"] == "report.pdf"
        assert data["upstream"]["extraction_confidence"] is not None


def test_extract_warnings_flow_end_to_end(client_factory, synthetic_pdf):
    from tests.conftest import WELL_FORMED_PAGE_PAYLOAD, FakeGeminiClient

    fake = FakeGeminiClient(
        payload={**WELL_FORMED_PAGE_PAYLOAD, "page_confidence": 0.1}
    )
    api = client_factory(fake)
    envelope = api.post(
        EXTRACT,
        files={"file": ("r.pdf", io.BytesIO(synthetic_pdf), "application/pdf")},
    ).json()
    assert envelope["data"]["warnings"], "expected Module 4 to warn"

    data = api.post(ENGINEER, json=envelope).json()["data"]
    assert [w["message"] for w in data["upstream_warnings"]] == envelope["data"][
        "warnings"
    ]
    assert all(w["stage"] == "extraction" for w in data["upstream_warnings"])


@pytest.mark.parametrize("path", [ENGINEER, "/api/v1/health", "/api/v1/features/catalog"])
def test_request_id_is_echoed(client, path):
    supplied = "68b1f0c2a4d9e7b3c1a2f4d6"
    if path == ENGINEER:
        response = client.post(
            path, json={}, headers={REQUEST_ID_HEADER: supplied}
        )
    else:
        response = client.get(path, headers={REQUEST_ID_HEADER: supplied})
    assert response.headers[REQUEST_ID_HEADER] == supplied


def test_a_request_id_is_generated_when_absent(client):
    response = client.get("/api/v1/health")
    generated = response.headers[REQUEST_ID_HEADER]
    assert generated
    assert sanitize_request_id(generated) == generated


def test_generated_ids_differ_between_requests(client):
    first = client.get("/api/v1/health").headers[REQUEST_ID_HEADER]
    second = client.get("/api/v1/health").headers[REQUEST_ID_HEADER]
    assert first != second


def test_request_id_is_echoed_on_error_responses(client):
    supplied = "trace-abc-123"
    response = client.post(
        ENGINEER,
        json={"extraction": {"extracted_parameters": [{"value_raw": "x"}]}},
        headers={REQUEST_ID_HEADER: supplied},
    )
    assert response.status_code == 422
    assert response.headers[REQUEST_ID_HEADER] == supplied


def test_request_id_is_echoed_on_a_401(authed_client):
    supplied = "trace-401-xyz"
    response = authed_client.get(
        "/api/v1/features/catalog", headers={REQUEST_ID_HEADER: supplied}
    )
    assert response.status_code == 401
    assert response.headers[REQUEST_ID_HEADER] == supplied


def test_request_id_appears_in_log_lines(authed_client, caplog):
    supplied = "trace-log-canary-001"
    with caplog.at_level(logging.DEBUG):
        authed_client.get("/api/v1/features/catalog")
        authed_client.get(
            "/api/v1/features/catalog", headers={REQUEST_ID_HEADER: supplied}
        )
    assert supplied in caplog.text
    assert "service_auth_rejected" in caplog.text


def test_request_id_survives_extraction_log_lines(client_factory, synthetic_pdf, caplog):
    supplied = "trace-extract-canary"
    api = client_factory()
    with caplog.at_level(logging.DEBUG):
        api.post(
            EXTRACT,
            files={"file": ("r.pdf", io.BytesIO(synthetic_pdf), "application/pdf")},
            headers={REQUEST_ID_HEADER: supplied},
        )
    assert supplied in caplog.text


@pytest.mark.parametrize(
    "hostile",
    [
        "Jordan Sample",
        "patient@example.com",
        "abc\ninjected log line",
        "abc\r\nSet-Cookie: x=1",
        "\x1b[31mred",
        "x" * 129,
        "",
        "   ",
        "../../etc/passwd",
    ],
)
def test_an_unusable_request_id_is_discarded_not_echoed(client, hostile, caplog):
    with caplog.at_level(logging.DEBUG):
        response = client.get("/api/v1/health", headers={REQUEST_ID_HEADER: hostile})
    echoed = response.headers[REQUEST_ID_HEADER]
    assert echoed != hostile
    assert sanitize_request_id(echoed) == echoed
    assert hostile.strip() not in caplog.text or not hostile.strip()


def test_sanitizer_accepts_the_opaque_ids_the_backend_will_send():
    for good in (
        "68b1f0c2a4d9e7b3c1a2f4d6",
        "3f2504e0-4f89-11d3-9a0c-0305e82c3301",
        "report:68b1f0c2a4d9e7b3c1a2f4d6",
        "req_2024.08.29-0001",
    ):
        assert sanitize_request_id(good) == good


def test_request_id_is_never_reflected_into_the_response_body(client):
    supplied = "trace-body-check-001"
    body = client.get("/api/v1/health", headers={REQUEST_ID_HEADER: supplied}).text
    assert supplied not in body


def test_the_gemini_call_is_bounded(settings):
    assert settings.gemini_timeout_seconds > 0
    assert settings.gemini_max_retries >= 1


def test_worst_case_duration_matches_the_documented_formula(settings):
    per_page = 3 * 120.0 + (1.0 * 1.25 + 2.0 * 1.25)
    expected = (2 * per_page + 20.0) * 10
    assert settings.worst_case_extraction_seconds == pytest.approx(expected)
    assert settings.worst_case_extraction_seconds == pytest.approx(7475.0)


def test_worst_case_shrinks_with_a_tighter_configuration():
    from app.config import Settings

    tuned = Settings(
        _env_file=None,
        gemini_timeout_seconds=45.0,
        gemini_max_retries=2,
        gemini_retry_base_delay_seconds=1.0,
        max_page_count=10,
    )
    assert tuned.worst_case_extraction_seconds == pytest.approx(2025.0)


def test_upstream_carry_forward_leaks_nothing_to_the_logs(client, caplog):
    payload = module_4_payload(
        raw_text="CANARY-RAW-TEXT",
        pages=[{"page_number": 1, "raw_text": "CANARY-PAGE-TEXT"}],
        report_metadata={
            "lab_name": "CANARY-LAB-NAME",
            "report_date": "12/03/2024",
            "patient_name_present": True,
        },
        warnings=["CANARY-UPSTREAM-WARNING"],
    )
    with caplog.at_level(logging.DEBUG):
        response = client.post(
            ENGINEER, json={"extraction": payload}, headers={SERVICE_KEY_HEADER: "x"}
        )
    assert response.status_code == 200
    assert "CANARY-LAB-NAME" in response.text
    assert "CANARY-UPSTREAM-WARNING" in response.text
    for canary in (
        "CANARY-RAW-TEXT",
        "CANARY-PAGE-TEXT",
        "CANARY-LAB-NAME",
        "CANARY-UPSTREAM-WARNING",
    ):
        assert canary not in caplog.text, f"{canary} leaked into logs"
