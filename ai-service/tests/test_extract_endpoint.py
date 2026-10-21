from __future__ import annotations

import io

import pytest
from PIL import Image

from app.core.errors import ErrorCode, ModelError, ModelTimeoutError
from tests.conftest import (
    WELL_FORMED_PAGE_PAYLOAD,
    FakeGeminiClient,
    make_synthetic_pdf,
)

URL = "/api/v1/ocr/extract"


def upload(client, data: bytes, name: str = "report.pdf", mime: str = "application/pdf"):
    return client.post(URL, files={"file": (name, io.BytesIO(data), mime)})


def test_pdf_extraction_returns_the_full_contract(client, synthetic_pdf):
    response = upload(client, synthetic_pdf)
    assert response.status_code == 200

    body = response.json()
    assert body["success"] is True
    data = body["data"]

    assert set(data) == {
        "source",
        "raw_text",
        "pages",
        "extracted_parameters",
        "report_metadata",
        "extraction_confidence",
        "warnings",
    }

    assert data["source"] == {
        "filename": "report.pdf",
        "mime_type": "application/pdf",
        "page_count": 1,
        "size_bytes": len(synthetic_pdf),
    }
    assert data["raw_text"]
    assert data["pages"][0]["page_number"] == 1
    assert data["report_metadata"]["patient_name_present"] is True
    assert 0.0 <= data["extraction_confidence"] <= 1.0
    assert isinstance(data["warnings"], list)


def test_extracted_parameters_match_the_contract_per_row(client, synthetic_pdf):
    data = upload(client, synthetic_pdf).json()["data"]
    params = data["extracted_parameters"]
    assert len(params) == 2

    hba1c = params[0]
    assert hba1c["test_name"] == "HbA1c"
    assert hba1c["value_raw"] == "6.8"
    assert hba1c["value_numeric"] == 6.8
    assert hba1c["unit"] == "%"
    assert hba1c["reference_range_raw"] == "4.0 - 5.6"
    assert hba1c["reference_low"] == 4.0
    assert hba1c["reference_high"] == 5.6
    assert hba1c["flag"] == "high"
    assert hba1c["page_number"] == 1
    assert hba1c["confidence"] == 0.94


def test_non_numeric_result_keeps_raw_value_and_nulls_numeric(client, synthetic_pdf):
    params = upload(client, synthetic_pdf).json()["data"]["extracted_parameters"]
    ketones = params[1]
    assert ketones["test_name"] == "Urine Ketones"
    assert ketones["value_raw"] == "Negative"
    assert ketones["value_numeric"] is None
    assert ketones["unit"] is None
    assert ketones["flag"] is None


def test_png_upload_is_accepted(client, synthetic_png):
    response = upload(client, synthetic_png, "scan.png", "image/png")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["source"]["mime_type"] == "image/png"
    assert data["source"]["page_count"] == 1


def test_jpeg_upload_is_accepted(client, synthetic_jpeg):
    response = upload(client, synthetic_jpeg, "scan.jpg", "image/jpeg")
    assert response.status_code == 200
    assert response.json()["data"]["source"]["mime_type"] == "image/jpeg"


def test_multipage_pdf_calls_the_model_per_page_and_stamps_page_numbers(
    client_factory, synthetic_pdf_2pages
):
    fake = FakeGeminiClient()
    client = client_factory(fake)
    data = upload(client, synthetic_pdf_2pages).json()["data"]

    assert len(fake.calls) == 2
    assert data["source"]["page_count"] == 2
    assert [p["page_number"] for p in data["pages"]] == [1, 2]
    assert {p["page_number"] for p in data["extracted_parameters"]} == {1, 2}
    assert len(data["extracted_parameters"]) == 4


def test_document_raw_text_concatenates_pages_in_order(
    client_factory, synthetic_pdf_2pages
):
    fake = FakeGeminiClient(
        payloads=[
            {**WELL_FORMED_PAGE_PAYLOAD, "raw_text": "PAGE ONE TEXT"},
            {**WELL_FORMED_PAGE_PAYLOAD, "raw_text": "PAGE TWO TEXT"},
        ]
    )
    client = client_factory(fake)
    raw = upload(client, synthetic_pdf_2pages).json()["data"]["raw_text"]
    assert raw.index("PAGE ONE TEXT") < raw.index("PAGE TWO TEXT")


def test_page_prompt_mentions_page_position(client_factory, synthetic_pdf_2pages):
    fake = FakeGeminiClient()
    client = client_factory(fake)
    upload(client, synthetic_pdf_2pages)
    assert "page 1 of 2" in fake.calls[0]["prompt"]
    assert "page 2 of 2" in fake.calls[1]["prompt"]


def test_model_receives_a_png_image_of_a_reasonable_size(
    client_factory, synthetic_pdf
):
    fake = FakeGeminiClient()
    client = client_factory(fake)
    upload(client, synthetic_pdf)
    assert fake.calls[0]["mime_type"] == "image/png"
    assert fake.calls[0]["size"] > 1000


def test_filename_path_components_are_stripped(client, synthetic_pdf):
    response = client.post(
        URL,
        files={
            "file": (
                "../../etc/passwd/report.pdf",
                io.BytesIO(synthetic_pdf),
                "application/pdf",
            )
        },
    )
    assert response.status_code == 200
    assert response.json()["data"]["source"]["filename"] == "report.pdf"


def test_low_confidence_produces_a_warning(client_factory, synthetic_pdf):
    fake = FakeGeminiClient(
        payload={
            **WELL_FORMED_PAGE_PAYLOAD,
            "page_confidence": 0.2,
            "parameters": [
                {"test_name": "HbA1c", "value_raw": "6.8", "confidence": 0.2}
            ],
        }
    )
    client = client_factory(fake)
    data = upload(client, synthetic_pdf).json()["data"]
    assert data["extraction_confidence"] <= 0.6
    assert any("confidence is low" in w for w in data["warnings"])


def test_model_warnings_are_forwarded_with_page_attribution(
    client_factory, synthetic_pdf
):
    fake = FakeGeminiClient(
        payload={
            **WELL_FORMED_PAGE_PAYLOAD,
            "warnings": ["Bottom-right region is blurred and unreadable."],
        }
    )
    client = client_factory(fake)
    warnings = upload(client, synthetic_pdf).json()["data"]["warnings"]
    assert any("Page 1: Bottom-right region is blurred" in w for w in warnings)


def test_no_parameters_found_is_warned_about(client_factory, synthetic_pdf):
    fake = FakeGeminiClient(
        payload={"raw_text": "Cover page. No results.", "parameters": []}
    )
    client = client_factory(fake)
    data = upload(client, synthetic_pdf).json()["data"]
    assert data["extracted_parameters"] == []
    assert any("No laboratory parameters" in w for w in data["warnings"])
    assert data["source"]["page_count"] == 1


def test_declared_type_mismatch_is_warned_about(client, synthetic_png):
    response = upload(client, synthetic_png, "report.pdf", "application/pdf")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["source"]["mime_type"] == "image/png"
    assert any("did not match" in w for w in data["warnings"])


def test_inverted_reference_range_is_flagged_but_preserved(
    client_factory, synthetic_pdf
):
    fake = FakeGeminiClient(
        payload={
            "raw_text": "t",
            "parameters": [
                {
                    "test_name": "Sodium",
                    "value_raw": "140",
                    "reference_low": 145,
                    "reference_high": 135,
                }
            ],
        }
    )
    client = client_factory(fake)
    data = upload(client, synthetic_pdf).json()["data"]
    param = data["extracted_parameters"][0]
    assert param["reference_low"] == 145
    assert param["reference_high"] == 135
    assert any("inverted" in w for w in data["warnings"])


def test_warnings_are_deduplicated(client_factory, synthetic_pdf_2pages):
    fake = FakeGeminiClient(
        payload={**WELL_FORMED_PAGE_PAYLOAD, "parameters": [], "warnings": []}
    )
    client = client_factory(fake)
    warnings = upload(client, synthetic_pdf_2pages).json()["data"]["warnings"]
    assert len(warnings) == len(set(warnings))


def test_one_failed_page_degrades_rather_than_failing_the_request(
    client_factory, synthetic_pdf_2pages
):
    fake = FakeGeminiClient(
        payloads=[
            WELL_FORMED_PAGE_PAYLOAD,
            ModelTimeoutError("timed out"),
        ]
    )
    client = client_factory(fake)
    response = upload(client, synthetic_pdf_2pages)
    assert response.status_code == 200

    data = response.json()["data"]
    assert len(data["extracted_parameters"]) == 2
    assert data["pages"][1]["raw_text"] is None
    assert any("Page 2 could not be processed" in w for w in data["warnings"])


def test_all_pages_failing_is_a_502_not_a_partial_success(
    client_factory, synthetic_pdf
):
    fake = FakeGeminiClient(payloads=[ModelTimeoutError("timed out")])
    client = client_factory(fake)
    response = upload(client, synthetic_pdf)
    assert response.status_code == 502
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == ErrorCode.MODEL_REQUEST_FAILED


def test_schema_violating_model_response_skips_the_page(
    client_factory, synthetic_pdf_2pages
):
    fake = FakeGeminiClient(
        payloads=[
            WELL_FORMED_PAGE_PAYLOAD,
            {"raw_text": "t", "parameters": [{"value_raw": "6.8"}]},
        ]
    )
    client = client_factory(fake)
    data = upload(client, synthetic_pdf_2pages).json()["data"]
    assert len(data["extracted_parameters"]) == 2
    assert any("did not match the expected schema" in w for w in data["warnings"])


def test_model_error_surfaces_as_a_clean_envelope(client_factory, synthetic_pdf):
    fake = FakeGeminiClient(
        payloads=[
            ModelError(
                "The extraction model is temporarily unavailable.",
                code=ErrorCode.MODEL_UNAVAILABLE,
                status_code=503,
            )
        ]
    )
    client = client_factory(fake)
    response = upload(client, synthetic_pdf)
    assert response.status_code == 502
    assert response.json()["success"] is False


def test_unexpected_exception_becomes_a_clean_500(client_factory, synthetic_pdf):
    fake = FakeGeminiClient(payloads=[RuntimeError("boom")])
    client = client_factory(fake)
    response = upload(client, synthetic_pdf)
    assert response.status_code == 500
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == ErrorCode.INTERNAL_ERROR
    assert "boom" not in response.text
    assert "Traceback" not in response.text


def test_missing_file_field_is_rejected(client):
    response = client.post(URL)
    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == ErrorCode.NO_FILE


def test_empty_file_is_rejected(client):
    response = upload(client, b"")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == ErrorCode.EMPTY_FILE


def test_unsupported_type_is_rejected(client):
    response = upload(client, b"GIF89a" + b"\x00" * 200, "img.gif", "image/gif")
    assert response.status_code == 415
    assert response.json()["error"]["code"] == ErrorCode.UNSUPPORTED_FILE_TYPE


def test_text_file_renamed_as_pdf_is_rejected(client):
    response = upload(client, b"just plain text, not a pdf" * 20)
    assert response.status_code == 415


def test_oversized_file_is_rejected(client_factory, synthetic_pdf):
    client = client_factory(max_file_size_bytes=500)
    response = upload(client, synthetic_pdf)
    assert response.status_code == 413
    assert response.json()["error"]["code"] == ErrorCode.FILE_TOO_LARGE


def test_oversized_upload_is_rejected_before_full_buffering(client_factory):
    client = client_factory(max_file_size_bytes=1024)
    huge = b"%PDF-1.4\n" + b"\x00" * (8 * 1024 * 1024)
    response = upload(client, huge)
    assert response.status_code == 413


def test_too_many_pages_is_rejected(client_factory):
    client = client_factory(max_page_count=2)
    response = upload(client, make_synthetic_pdf(4))
    assert response.status_code == 400
    assert response.json()["error"]["code"] == ErrorCode.TOO_MANY_PAGES


def test_corrupt_pdf_is_rejected_with_422(client):
    response = upload(client, b"%PDF-1.4\n" + b"\xde\xad\xbe\xef" * 500)
    assert response.status_code == 422
    assert response.json()["success"] is False


def test_corrupt_image_is_rejected_with_422(client):
    response = upload(
        client, b"\x89PNG\r\n\x1a\n" + b"\x00\xff" * 400, "scan.png", "image/png"
    )
    assert response.status_code == 422


def test_no_model_call_is_made_for_a_rejected_file(client_factory):
    fake = FakeGeminiClient()
    client = client_factory(fake)
    upload(client, b"GIF89a" + b"\x00" * 200, "x.gif", "image/gif")
    assert fake.calls == []


@pytest.mark.parametrize("method", ["get", "put", "delete"])
def test_wrong_method_uses_the_error_envelope(client, method):
    response = getattr(client, method)(URL)
    assert response.status_code == 405
    assert response.json()["success"] is False


def test_service_does_not_normalise_test_names(client_factory, synthetic_pdf):
    fake = FakeGeminiClient(
        payload={
            "raw_text": "t",
            "parameters": [
                {"test_name": "HbA1c (Glycated Haemoglobin)", "value_raw": "6.8"},
                {"test_name": "S. CREATININE", "value_raw": "1.0"},
            ],
        }
    )
    client = client_factory(fake)
    names = [
        p["test_name"]
        for p in upload(client, synthetic_pdf).json()["data"]["extracted_parameters"]
    ]
    assert names == ["HbA1c (Glycated Haemoglobin)", "S. CREATININE"]


def test_service_does_not_invent_a_flag_from_the_reference_range(
    client_factory, synthetic_pdf
):
    fake = FakeGeminiClient(
        payload={
            "raw_text": "t",
            "parameters": [
                {
                    "test_name": "Glucose",
                    "value_raw": "300",
                    "value_numeric": 300,
                    "reference_low": 70,
                    "reference_high": 99,
                    "flag": None,
                }
            ],
        }
    )
    client = client_factory(fake)
    param = upload(client, synthetic_pdf).json()["data"]["extracted_parameters"][0]
    assert param["flag"] is None


def test_response_contains_no_clinical_interpretation_keys(client, synthetic_pdf):
    body = upload(client, synthetic_pdf).json()
    text = str(body).lower()
    for forbidden in ("diagnosis", "risk_score", "recommendation", "explanation"):
        assert forbidden not in text
