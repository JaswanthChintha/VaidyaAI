from __future__ import annotations

import io

from app.prompts.extraction_prompt import build_page_prompt
from app.schemas.extraction import PageExtraction, gemini_response_schema
from tests.conftest import WELL_FORMED_PAGE_PAYLOAD, FakeGeminiClient, make_synthetic_pdf

URL = "/api/v1/ocr/extract"


def upload(client, data: bytes):
    return client.post(URL, files={"file": ("r.pdf", io.BytesIO(data), "application/pdf")})


def page(**overrides):
    return {**WELL_FORMED_PAGE_PAYLOAD, **overrides}


def test_the_printed_sex_and_age_reach_the_contract_verbatim(client_factory):
    fake = FakeGeminiClient(payload=page(patient_sex="Male", patient_age="63 Years"))
    metadata = upload(client_factory(fake), make_synthetic_pdf(1)).json()["data"]["report_metadata"]
    assert metadata["patient_sex"] == "Male"
    assert metadata["patient_age"] == "63 Years"


def test_not_printed_is_null_and_the_key_is_still_there(client_factory):
    metadata = upload(client_factory(), make_synthetic_pdf(1)).json()["data"]["report_metadata"]
    assert "patient_sex" in metadata and metadata["patient_sex"] is None
    assert "patient_age" in metadata and metadata["patient_age"] is None


def test_the_first_page_wins_and_a_disagreeing_page_is_warned_about(client_factory):
    fake = FakeGeminiClient(
        payloads=[
            page(patient_sex="Male", patient_age="63 Years"),
            page(patient_sex="Female", patient_age="34 Years"),
        ]
    )
    data = upload(client_factory(fake), make_synthetic_pdf(2)).json()["data"]
    assert data["report_metadata"]["patient_sex"] == "Male"
    assert data["report_metadata"]["patient_age"] == "63 Years"
    assert any("Different patient sexes" in w for w in data["warnings"])
    assert any("Different patient ages" in w for w in data["warnings"])


def test_the_same_details_on_every_page_raise_no_warning(client_factory):
    fake = FakeGeminiClient(
        payloads=[page(patient_sex="Male", patient_age="63 Years"), page(patient_sex="MALE", patient_age="63 years")]
    )
    warnings = upload(client_factory(fake), make_synthetic_pdf(2)).json()["data"]["warnings"]
    assert not any("Different patient" in w for w in warnings)


def test_a_page_that_omits_them_does_not_erase_them(client_factory):
    fake = FakeGeminiClient(payloads=[page(patient_sex="F", patient_age="34"), page()])
    metadata = upload(client_factory(fake), make_synthetic_pdf(2)).json()["data"]["report_metadata"]
    assert metadata["patient_sex"] == "F"
    assert metadata["patient_age"] == "34"


def test_blank_placeholders_and_non_text_are_null_and_long_text_is_capped():
    assert PageExtraction.model_validate({"patient_sex": "N/A", "patient_age": " - "}).patient_sex is None
    assert PageExtraction.model_validate({"patient_age": 63}).patient_age == "63"
    assert PageExtraction.model_validate({"patient_sex": True}).patient_sex is None
    assert len(PageExtraction.model_validate({"patient_age": "9" * 100}).patient_age) == 32


def test_the_model_is_asked_for_both_and_never_for_a_name():
    props = gemini_response_schema()["properties"]
    assert props["patient_sex"] == {"type": "string", "nullable": True}
    assert props["patient_age"] == {"type": "string", "nullable": True}
    assert {key for key in props if "name" in key} == {"lab_name", "patient_name_present"}

    prompt = build_page_prompt(1, 1)
    assert "`patient_sex`" in prompt and "`patient_age`" in prompt
    assert "Do not infer it from the name" in prompt
    assert "sex-specific reference ranges" in prompt
    assert "Do not compute it from a date of birth" in prompt
    assert "DO NOT EXTRACT THE PATIENT'S NAME" in prompt
