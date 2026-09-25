"""Medical-data privacy: nothing sensitive may reach the logs.

This service handles PHI. Report text, extracted values, patient identifiers
and the API key must never appear in log output.
"""

from __future__ import annotations

import io
import logging

from app.core.logging import safe_meta
from tests.conftest import WELL_FORMED_PAGE_PAYLOAD, FakeGeminiClient

URL = "/api/v1/ocr/extract"

# Distinctive strings planted in the mocked model response. If any of these
# turn up in the logs, something is logging report content.
CANARIES = [
    "CANARY-PATIENT-NAME",
    "CANARY-RAW-TEXT",
    "CANARY-TEST-NAME",
    "CANARY-LAB-NAME",
]


def test_safe_meta_drops_content_bearing_keys():
    out = safe_meta(
        page_number=2,
        size_bytes=100,
        raw_text="HbA1c 6.8",
        extracted_parameters=[{"a": 1}],
        patient_name="Jordan Sample",
        api_key="secret-key",
        prompt="the full prompt",
    )
    assert out == {"page_number": 2, "size_bytes": 100}


def test_safe_meta_truncates_unexpectedly_long_strings():
    out = safe_meta(error_code="X" * 500)
    assert len(out["error_code"]) <= 120


def test_safe_meta_summarises_non_scalars_by_type():
    out = safe_meta(payload={"a": 1}, items=[1, 2, 3])
    assert out == {"payload": "dict", "items": "list"}


def test_no_report_content_reaches_the_logs(
    client_factory, synthetic_pdf, caplog
):
    fake = FakeGeminiClient(
        payload={
            **WELL_FORMED_PAGE_PAYLOAD,
            "raw_text": "CANARY-RAW-TEXT\nPatient: CANARY-PATIENT-NAME",
            "lab_name": "CANARY-LAB-NAME",
            "parameters": [
                {
                    "test_name": "CANARY-TEST-NAME",
                    "value_raw": "6.8",
                    "value_numeric": 6.8,
                }
            ],
        }
    )
    client = client_factory(fake)

    with caplog.at_level(logging.DEBUG):
        response = client.post(
            URL,
            files={
                "file": (
                    "report.pdf",
                    io.BytesIO(synthetic_pdf),
                    "application/pdf",
                )
            },
        )
    assert response.status_code == 200
    # The canaries must be in the RESPONSE...
    assert "CANARY-TEST-NAME" in response.text
    # ...and absent from the LOGS.
    logged = caplog.text
    for canary in CANARIES:
        assert canary not in logged, f"{canary} leaked into logs"


def test_api_key_never_reaches_the_logs(client_factory, synthetic_pdf, caplog):
    secret = "super-secret-key-value-12345"
    fake = FakeGeminiClient()
    client = client_factory(fake, gemini_api_key=secret)

    with caplog.at_level(logging.DEBUG):
        client.post(
            URL,
            files={
                "file": (
                    "report.pdf",
                    io.BytesIO(synthetic_pdf),
                    "application/pdf",
                )
            },
        )
    assert secret not in caplog.text


def test_failure_paths_do_not_log_document_content(
    client_factory, synthetic_pdf, caplog
):
    fake = FakeGeminiClient(payloads=[RuntimeError("CANARY-RAW-TEXT in exception")])
    client = client_factory(fake)

    with caplog.at_level(logging.DEBUG):
        response = client.post(
            URL,
            files={
                "file": (
                    "report.pdf",
                    io.BytesIO(synthetic_pdf),
                    "application/pdf",
                )
            },
        )
    assert response.status_code == 500
    # The exception message itself must not be logged -- only its type.
    assert "CANARY-RAW-TEXT" not in caplog.text


def test_settings_repr_redacts_the_key():
    from app.config import Settings

    s = Settings(_env_file=None, gemini_api_key="do-not-print-me")
    assert "do-not-print-me" not in repr(s)
    assert "do-not-print-me" not in str(s)
    assert s.gemini_api_key.get_secret_value() == "do-not-print-me"


def test_patient_name_is_never_extracted_only_its_presence(
    client_factory, synthetic_pdf
):
    """The contract reports patient_name_present, never the name itself."""
    client = client_factory()
    metadata = client.post(
        URL,
        files={"file": ("r.pdf", io.BytesIO(synthetic_pdf), "application/pdf")},
    ).json()["data"]["report_metadata"]

    # Printed sex and age were added 2026-09-24, deliberately and alone: the
    # analysis depends on them and not on a name. No key may carry a name.
    assert set(metadata) == {
        "lab_name", "report_date", "patient_name_present", "patient_sex", "patient_age",
    }
    assert metadata["patient_name_present"] is True
    assert {key for key in metadata if "name" in key} == {"lab_name", "patient_name_present"}
