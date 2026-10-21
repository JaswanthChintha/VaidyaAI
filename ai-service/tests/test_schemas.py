from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.extraction import (
    ExtractedParameter,
    ExtractionData,
    ExtractionResponse,
    PageExtraction,
    ReportMetadata,
    SourceInfo,
    coerce_numeric,
    gemini_response_schema,
    printed_range_is_only_a_range,
)


def test_minimal_parameter_needs_only_name_and_raw_value():
    p = ExtractedParameter(test_name="HbA1c", value_raw="6.8")
    assert p.test_name == "HbA1c"
    assert p.value_raw == "6.8"
    assert p.unit is None
    assert p.reference_range_raw is None
    assert p.reference_low is None
    assert p.reference_high is None
    assert p.flag is None
    assert p.page_number is None
    assert p.confidence is None
    assert p.value_numeric is None


@pytest.mark.parametrize(
    "payload",
    [
        {"value_raw": "6.8"},
        {"test_name": "HbA1c"},
        {"test_name": "", "value_raw": "6"},
        {"test_name": "HbA1c", "value_raw": ""},
        {"test_name": None, "value_raw": "6"},
        {"test_name": "HbA1c", "value_raw": None},
    ],
)
def test_missing_required_fields_are_rejected(payload):
    with pytest.raises(ValidationError):
        ExtractedParameter(**payload)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("6.8", 6.8),
        ("112", 112.0),
        ("0", 0.0),
        ("-1.5", -1.5),
        ("<0.01", 0.01),
        (">120", 120.0),
        ("1,234.5", 1234.5),
        (6.8, 6.8),
        (7, 7.0),
    ],
)
def test_numeric_values_are_coerced(raw, expected):
    assert coerce_numeric(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "Negative",
        "Trace",
        "Not Detected",
        "Reactive",
        "Positive +",
        "",
        "   ",
        None,
        "N/A",
        "see comment",
        "1.2.3",
        "abc",
        True,
        float("nan"),
        float("inf"),
    ],
)
def test_non_numeric_values_coerce_to_none(raw):
    assert coerce_numeric(raw) is None


def test_qualitative_result_keeps_raw_and_nulls_numeric():
    p = ExtractedParameter(
        test_name="Urine Ketones", value_raw="Negative", value_numeric=None
    )
    assert p.value_raw == "Negative"
    assert p.value_numeric is None


def test_model_supplied_number_for_a_qualitative_value_is_discarded():
    p = ExtractedParameter(
        test_name="Urine Ketones",
        value_raw="Negative",
        value_numeric="Negative",
    )
    assert p.value_numeric is None


def test_placeholder_strings_become_null_not_literal_text():
    p = ExtractedParameter(
        test_name="Sodium",
        value_raw="140",
        unit="N/A",
        reference_range_raw="null",
    )
    assert p.unit is None
    assert p.reference_range_raw is None


def test_numeric_value_raw_is_stringified_rather_than_rejected():
    p = ExtractedParameter(test_name="Glucose", value_raw=112)
    assert p.value_raw == "112"


@pytest.mark.parametrize(
    "printed",
    [
        "HbA1c",
        "HbA1c (Glycated Haemoglobin)",
        "VITAMIN D (25-OH)",
        "S. Creatinine",
        "Total Cholesterol",
        "Haemoglobin",
    ],
)
def test_test_names_are_preserved_verbatim(printed):
    p = ExtractedParameter(test_name=printed, value_raw="1")
    assert p.test_name == printed


def test_surrounding_whitespace_is_trimmed_but_content_is_not_altered():
    p = ExtractedParameter(test_name="  HbA1c (A1c)  ", value_raw=" 6.8 ")
    assert p.test_name == "HbA1c (A1c)"
    assert p.value_raw == "6.8"


@pytest.mark.parametrize("flag", ["low", "normal", "high", "critical"])
def test_valid_flags_are_accepted(flag):
    assert ExtractedParameter(test_name="X", value_raw="1", flag=flag).flag == flag


@pytest.mark.parametrize(
    "given,expected",
    [
        ("H", "high"),
        ("L", "low"),
        ("HIGH", "high"),
        ("WNL", "normal"),
        ("Panic", "critical"),
        ("abnormal", None),
        ("elevated-ish", None),
        ("", None),
        ("n/a", None),
        (None, None),
    ],
)
def test_flag_aliases_normalise_or_fall_back_to_null(given, expected):
    assert ExtractedParameter(test_name="X", value_raw="1", flag=given).flag == expected


@pytest.mark.parametrize("value,expected", [(1.5, 1.0), (-0.4, 0.0), (0.5, 0.5)])
def test_confidence_is_clamped_to_zero_one(value, expected):
    p = ExtractedParameter(test_name="X", value_raw="1", confidence=value)
    assert p.confidence == expected


@pytest.mark.parametrize("page", [0, -3, "abc", None])
def test_invalid_page_numbers_become_null(page):
    p = ExtractedParameter(test_name="X", value_raw="1", page_number=page)
    assert p.page_number is None


def test_extraction_confidence_must_be_in_range():
    with pytest.raises(ValidationError):
        ExtractionData(source=SourceInfo(), extraction_confidence=1.4)


def test_well_formed_page_response_validates(conftest_payload=None):
    from tests.conftest import WELL_FORMED_PAGE_PAYLOAD

    page = PageExtraction.model_validate(WELL_FORMED_PAGE_PAYLOAD)
    assert len(page.parameters) == 2
    assert page.parameters[0].test_name == "HbA1c"
    assert page.parameters[0].value_numeric == 6.8
    assert page.parameters[1].value_numeric is None
    assert page.page_confidence == 0.92


def test_page_response_tolerates_missing_optional_blocks():
    page = PageExtraction.model_validate({"raw_text": "text", "parameters": []})
    assert page.parameters == []
    assert page.lab_name is None
    assert page.warnings == []


def test_page_response_tolerates_null_raw_text():
    page = PageExtraction.model_validate({"raw_text": None, "parameters": []})
    assert page.raw_text == ""


def test_page_response_ignores_unexpected_extra_keys():
    page = PageExtraction.model_validate(
        {"raw_text": "t", "parameters": [], "diagnosis": "diabetes", "advice": "x"}
    )
    assert not hasattr(page, "diagnosis")


@pytest.mark.parametrize(
    "bad",
    [
        {"raw_text": "t", "parameters": [{"value_raw": "6.8"}]},
        {"raw_text": "t", "parameters": [{"test_name": "HbA1c"}]},
        {"raw_text": "t", "parameters": "not-a-list"},
        {"raw_text": "t", "parameters": [["not", "an", "object"]]},
        "a bare string",
        ["a", "list"],
    ],
)
def test_malformed_page_responses_are_rejected(bad):
    with pytest.raises(ValidationError):
        PageExtraction.model_validate(bad)


def test_string_warning_is_wrapped_into_a_list():
    page = PageExtraction.model_validate(
        {"raw_text": "t", "parameters": [], "warnings": "blurry region"}
    )
    assert page.warnings == ["blurry region"]


def test_response_serialises_with_every_contract_key_present():
    response = ExtractionResponse(
        success=True,
        data=ExtractionData(
            source=SourceInfo(
                filename="r.pdf",
                mime_type="application/pdf",
                page_count=1,
                size_bytes=10,
            ),
            raw_text="text",
            extracted_parameters=[
                ExtractedParameter(test_name="HbA1c", value_raw="6.8")
            ],
            report_metadata=ReportMetadata(patient_name_present=True),
            extraction_confidence=0.9,
        ),
    )
    body = response.model_dump(mode="json")

    assert set(body) == {"success", "data"}
    assert set(body["data"]) == {
        "source",
        "raw_text",
        "pages",
        "extracted_parameters",
        "report_metadata",
        "extraction_confidence",
        "warnings",
    }
    assert set(body["data"]["source"]) == {
        "filename",
        "mime_type",
        "page_count",
        "size_bytes",
    }
    assert set(body["data"]["report_metadata"]) == {
        "lab_name",
        "report_date",
        "patient_name_present",
        "patient_sex",
        "patient_age",
    }
    assert set(body["data"]["extracted_parameters"][0]) == {
        "test_name",
        "value_raw",
        "value_numeric",
        "unit",
        "reference_range_raw",
        "reference_low",
        "reference_high",
        "flag",
        "page_number",
        "confidence",
    }


def test_nulls_are_emitted_rather_than_omitted():
    body = ExtractionResponse(
        data=ExtractionData(
            source=SourceInfo(),
            extracted_parameters=[
                ExtractedParameter(test_name="X", value_raw="Negative")
            ],
        )
    ).model_dump(mode="json")
    param = body["data"]["extracted_parameters"][0]
    assert param["value_numeric"] is None
    assert param["unit"] is None
    assert param["flag"] is None


def test_gemini_schema_is_a_restricted_openapi_object():
    schema = gemini_response_schema()
    assert schema["type"] == "object"
    assert set(schema["required"]) == {"raw_text", "parameters"}

    item = schema["properties"]["parameters"]["items"]
    assert set(item["required"]) == {"test_name", "value_raw"}
    assert item["properties"]["flag"]["enum"] == [
        "low",
        "normal",
        "high",
        "critical",
    ]


def test_gemini_schema_avoids_unsupported_json_schema_constructs():
    import json

    text = json.dumps(gemini_response_schema())
    for unsupported in ("$ref", "$defs", "anyOf", "oneOf", "allOf"):
        assert unsupported not in text


def test_gemini_schema_fields_match_the_page_model():
    schema_keys = set(gemini_response_schema()["properties"])
    assert schema_keys <= set(PageExtraction.model_fields)


def test_a_category_label_after_a_range_refuses_the_bounds():
    p = ExtractedParameter(
        test_name="AVERAGE BLOOD GLUCOSE",
        value_raw="154",
        reference_range_raw="151 - 180 - Average Control",
        reference_low=151,
        reference_high=180,
    )

    assert p.reference_low is None
    assert p.reference_high is None
    assert p.reference_range_raw == "151 - 180 - Average Control"


def test_the_same_defect_with_the_dash_omitted_is_also_refused():
    p = ExtractedParameter(
        test_name="X",
        value_raw="154",
        reference_range_raw="151 - 180 Normal",
        reference_low=151,
        reference_high=180,
    )
    assert (p.reference_low, p.reference_high) == (None, None)


@pytest.mark.parametrize(
    "raw,low,high",
    [
        ("0 - 20", 0, 20),
        ("0-2", 0, 2),
        ("0.27-5.0", 0.27, 5.0),
        ("0.4 -1.4", 0.4, 1.4),
        ("00 - 01", 0, 1),
        ("1.5 - 4.5", 1.5, 4.5),
        ("11.0 - 13.0 g/dL", 11.0, 13.0),
        ("27 - 32 pg", 27, 32),
        ("32 - 36 g/dL", 32, 36),
        ("4.2 - 5.4 mill/cu.mm", 4.2, 5.4),
        ("40 - 75 %", 40, 75),
        ("4000 - 11000 cells/cumm", 4000, 11000),
        ("70 - 140 mg/dl", 70, 140),
        ("78-100 fL", 78, 100),
        ("< 100", None, 100),
        ("< 6 mg/l", None, 6),
        ("> 40", 40, None),
        ("UP TO 40", None, 40),
    ],
)
def test_a_plain_printed_range_keeps_its_bounds(raw, low, high):
    p = ExtractedParameter(
        test_name="X",
        value_raw="1",
        reference_range_raw=raw,
        reference_low=low,
        reference_high=high,
    )
    assert p.reference_low == (None if low is None else float(low))
    assert p.reference_high == (None if high is None else float(high))


@pytest.mark.parametrize(
    "raw",
    [
        "151 - 180 - Average Control",
        "151 - 180 Average",
        "5 - 40 Desirable",
        "0 - 20 Borderline",
        "F: 36 - 46 M: 40 - 50",
        "F:11 - 15 M:12 - 16",
        "Normal : < 5.7 Diabetes Mellitus : > 6.5",
        "Non Diabetic : 4.5 -5.6\nPre Diabetic : 5.7 -6.4",
    ],
)
def test_text_that_says_more_than_an_interval_is_refused(raw):
    assert printed_range_is_only_a_range(raw) is False


def test_the_gate_has_no_opinion_when_nothing_was_printed():
    assert printed_range_is_only_a_range(None) is True
    assert printed_range_is_only_a_range("") is True

    p = ExtractedParameter(
        test_name="X", value_raw="1", reference_low=3, reference_high=9
    )
    assert (p.reference_low, p.reference_high) == (3.0, 9.0)


def test_an_inferred_normal_flag_goes_with_the_refused_bounds():
    p = ExtractedParameter(
        test_name="AVERAGE BLOOD GLUCOSE",
        value_raw="154",
        unit="mg/dL",
        reference_range_raw="151 - 180 - Average Control",
        reference_low=151,
        reference_high=180,
        flag="normal",
    )
    assert (p.reference_low, p.reference_high) == (None, None)
    assert p.flag is None
    assert p.reference_range_raw == "151 - 180 - Average Control"
    assert p.value_raw == "154"
    assert p.unit == "mg/dL"


@pytest.mark.parametrize("flag", ["high", "low", "critical"])
def test_a_warning_flag_survives_a_refused_range(flag):
    p = ExtractedParameter(
        test_name="AVERAGE BLOOD GLUCOSE",
        value_raw="240",
        reference_range_raw="181 - 210 - Action Suggested",
        reference_low=181,
        reference_high=210,
        flag=flag,
    )
    assert (p.reference_low, p.reference_high) == (None, None)
    assert p.flag == flag


def test_a_normal_flag_is_dropped_even_when_the_model_supplied_no_bounds():
    p = ExtractedParameter(
        test_name="AVERAGE BLOOD GLUCOSE",
        value_raw="154",
        reference_range_raw="151 - 180 - Average Control",
        flag="normal",
    )
    assert p.flag is None


@pytest.mark.parametrize("raw", ["70 - 140 mg/dl", "< 100", "UP TO 40", "0.27-5.0"])
def test_a_normal_flag_survives_a_range_the_gate_accepts(raw):
    p = ExtractedParameter(
        test_name="X", value_raw="1", reference_range_raw=raw, flag="normal"
    )
    assert p.flag == "normal"


def test_a_normal_flag_survives_when_nothing_was_printed():
    p = ExtractedParameter(test_name="X", value_raw="1", flag="normal")
    assert p.flag == "normal"
