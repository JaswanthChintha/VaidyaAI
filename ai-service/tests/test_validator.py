from __future__ import annotations

from typing import Any, Dict, Optional

import pytest

from app.data.validation_rules import FlagCode, RejectionCode
from app.schemas.features import STAGE_EXTRACTION, STAGE_FEATURE_ENGINEERING
from app.schemas.validation import (
    STAGE_VALIDATION,
    STATUS_QUESTIONABLE,
    STATUS_VALID,
)
from app.services.feature_engineer import engineer_from_extraction
from app.services.validator import (
    VALIDATION_POLICY,
    usable_features,
    validate_features,
)


def feature(
    name: str,
    value: Any,
    unit: Optional[str] = None,
    *,
    canonical_unit: bool = True,
    source: str = "lab_report",
    **provenance: Any,
) -> Dict[str, Any]:
    prov: Dict[str, Any] = {"source": source}
    prov.update(provenance)
    return {
        "name": name,
        "value": value,
        "unit": unit,
        "canonical_unit": canonical_unit,
        "source": source,
        "provenance": prov,
    }


def module_5_data(**overrides: Any) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "features": {},
        "unmapped": [],
        "conversions_applied": [],
        "duplicates_resolved": [],
        "missing_features": [],
        "warnings": [],
        "upstream_warnings": [],
        "all_warnings": [],
        "upstream": {"stage": "extraction", "module": 4, "provided": False},
        "summary": {},
    }
    payload.update(overrides)
    return payload


def with_features(*features: Dict[str, Any], **overrides: Any) -> Dict[str, Any]:
    return module_5_data(
        features={f["name"]: f for f in features}, **overrides
    )


def test_glucose_400_is_valid_and_flagged_clinically_extreme():
    result = validate_features(
        with_features(feature("blood_glucose", 400.0, "mg/dl"))
    )
    assert "blood_glucose" in result.valid
    assert "blood_glucose" not in result.rejected
    entry = result.valid["blood_glucose"]
    assert entry.value == 400.0
    assert entry.clinically_extreme is True
    assert entry.extreme_direction == "high"
    assert entry.questionable is False
    assert result.clinically_extreme == ["blood_glucose"]
    assert any(f.code == FlagCode.CLINICALLY_EXTREME_HIGH for f in entry.flags)


def test_glucose_40000_is_rejected_as_an_extraction_error():
    result = validate_features(
        with_features(feature("blood_glucose", 40000.0, "mg/dl"))
    )
    assert "blood_glucose" not in result.valid
    rejection = result.rejected["blood_glucose"]
    assert rejection.reason_code == RejectionCode.IMPLAUSIBLE_VALUE_HIGH
    assert rejection.value == 40000.0
    assert rejection.findings[0].bound == "possible_high"
    assert rejection.findings[0].limit == 3000.0
    assert rejection.findings[0].basis


@pytest.mark.parametrize(
    "name,value,unit",
    [
        ("hba1c", 14.0, "%"),
        ("blood_glucose", 20.0, "mg/dl"),
        ("hemoglobin", 2.0, "g/dl"),
        ("creatinine", 15.0, "mg/dl"),
        ("cholesterol", 800.0, "mg/dl"),
        ("triglycerides", 15000.0, "mg/dl"),
        ("vitamin_d", 0.0, "ng/ml"),
        ("bmi", 10.0, "kg/m2"),
    ],
)
def test_severely_abnormal_but_real_values_are_never_rejected(name, value, unit):
    result = validate_features(with_features(feature(name, value, unit)))
    assert name in result.valid, result.rejected
    assert result.valid[name].value == value


@pytest.mark.parametrize(
    "name,value,unit,code",
    [
        ("hba1c", 48.0, "%", RejectionCode.IMPLAUSIBLE_VALUE_HIGH),
        ("hba1c", 0.0, "%", RejectionCode.IMPLAUSIBLE_VALUE_LOW),
        ("hemoglobin", 142.0, "g/dl", RejectionCode.IMPLAUSIBLE_VALUE_HIGH),
        ("creatinine", 884.0, "mg/dl", RejectionCode.IMPLAUSIBLE_VALUE_HIGH),
        ("creatinine", 0.0, "mg/dl", RejectionCode.IMPLAUSIBLE_VALUE_LOW),
        ("bmi", 5000.0, "kg/m2", RejectionCode.IMPLAUSIBLE_VALUE_HIGH),
        ("age", -1, "years", RejectionCode.IMPLAUSIBLE_VALUE_LOW),
        ("age", 900, "years", RejectionCode.IMPLAUSIBLE_VALUE_HIGH),
    ],
)
def test_physiologically_impossible_values_are_rejected(name, value, unit, code):
    result = validate_features(with_features(feature(name, value, unit)))
    assert result.rejected[name].reason_code == code
    assert name not in result.valid


@pytest.mark.parametrize(
    "name,unit,attr",
    [
        ("blood_glucose", "mg/dl", "possible_high"),
        ("blood_glucose", "mg/dl", "possible_low"),
        ("hba1c", "%", "possible_high"),
        ("hba1c", "%", "possible_low"),
        ("bmi", "kg/m2", "possible_high"),
        ("bmi", "kg/m2", "possible_low"),
    ],
)
def test_possible_band_boundaries_are_inclusive(name, unit, attr):
    from app.data.validation_rules import RULES

    bound = getattr(RULES[name], attr)
    step = 0.001 if attr == "possible_low" else -0.001
    assert name in validate_features(
        with_features(feature(name, bound, unit))
    ).valid
    assert name in validate_features(
        with_features(feature(name, bound + step, unit))
    ).valid
    outside = bound - 0.001 if attr == "possible_low" else bound + 0.001
    assert name in validate_features(
        with_features(feature(name, outside, unit))
    ).rejected


@pytest.mark.parametrize(
    "name,unit,attr,direction",
    [
        ("blood_glucose", "mg/dl", "extreme_high", "high"),
        ("blood_glucose", "mg/dl", "extreme_low", "low"),
        ("hemoglobin", "g/dl", "extreme_high", "high"),
        ("hemoglobin", "g/dl", "extreme_low", "low"),
        ("bmi", "kg/m2", "extreme_high", "high"),
        ("bmi", "kg/m2", "extreme_low", "low"),
    ],
)
def test_extreme_band_boundaries_are_inclusive_and_never_reject(
    name, unit, attr, direction
):
    from app.data.validation_rules import RULES

    bound = getattr(RULES[name], attr)
    on_bound = validate_features(with_features(feature(name, bound, unit)))
    assert name in on_bound.valid
    assert on_bound.valid[name].clinically_extreme is True
    assert on_bound.valid[name].extreme_direction == direction

    inside = bound + (0.1 if direction == "low" else -0.1)
    just_normal = validate_features(with_features(feature(name, inside, unit)))
    assert just_normal.valid[name].clinically_extreme is False


def test_age_has_no_extreme_band_so_a_centenarian_is_not_flagged():
    result = validate_features(with_features(feature("age", 101, "years",
                                                     source="patient_profile")))
    assert result.valid["age"].clinically_extreme is False


def test_a_non_canonical_unit_is_rejected_and_never_range_checked():
    result = validate_features(
        with_features(
            feature(
                "creatinine",
                1.0,
                "flurbs",
                canonical_unit=False,
                unit_recognised=False,
            )
        )
    )
    rejection = result.rejected["creatinine"]
    assert rejection.reason_code == RejectionCode.NON_CANONICAL_UNIT
    assert rejection.value == 1.0
    assert rejection.unit == "flurbs"
    assert "creatinine" not in result.valid


def test_a_non_canonical_unit_is_not_converted_or_guessed():
    result = validate_features(
        with_features(
            feature("cholesterol", 5.2, "mmol/L-ish", canonical_unit=False)
        )
    )
    assert result.rejected["cholesterol"].value == 5.2


def test_a_unit_that_disagrees_with_the_canonical_one_is_refused():
    result = validate_features(
        with_features(feature("blood_glucose", 5.5, "mmol/l"))
    )
    assert result.rejected["blood_glucose"].reason_code == RejectionCode.UNIT_MISMATCH


def test_unit_spelling_variants_are_accepted():
    for unit in ("mg/dL", "MG/DL", "mg / dl"):
        result = validate_features(
            with_features(feature("blood_glucose", 95.0, unit))
        )
        assert "blood_glucose" in result.valid, unit


def test_a_missing_unit_on_a_numeric_feature_is_not_a_rejection():
    result = validate_features(with_features(feature("blood_glucose", 95.0, None)))
    assert "blood_glucose" in result.valid


def test_unitless_features_ignore_the_canonical_unit_check():
    result = validate_features(
        with_features(feature("gender", "male", None, source="patient_profile"))
    )
    assert "gender" in result.valid


@pytest.mark.parametrize("value", ["6.8", None, [1], {"a": 1}])
def test_a_non_numeric_value_in_a_numeric_feature_is_rejected(value):
    result = validate_features(with_features(feature("hba1c", value, "%")))
    assert result.rejected["hba1c"].reason_code == RejectionCode.NOT_A_NUMBER


def test_a_boolean_in_a_numeric_feature_is_rejected_not_measured():
    result = validate_features(with_features(feature("hba1c", True, "%")))
    assert result.rejected["hba1c"].reason_code == RejectionCode.NOT_A_NUMBER


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_numbers_are_rejected(value):
    result = validate_features(with_features(feature("hba1c", value, "%")))
    assert result.rejected["hba1c"].reason_code == RejectionCode.NON_FINITE_VALUE


def test_a_fractional_age_is_rejected_not_rounded():
    result = validate_features(
        with_features(feature("age", 45.5, "years", source="patient_profile"))
    )
    assert result.rejected["age"].reason_code == RejectionCode.NOT_AN_INTEGER
    assert result.rejected["age"].value == 45.5


def test_an_integral_float_age_is_accepted_unchanged():
    result = validate_features(
        with_features(feature("age", 45.0, "years", source="patient_profile"))
    )
    assert result.valid["age"].value == 45.0


def test_an_unknown_feature_name_is_rejected_not_passed_through():
    data = module_5_data()
    data["features"]["cortisol"] = feature("cortisol", 12.0, "ug/dl")
    result = validate_features(data)
    assert result.rejected["cortisol"].reason_code == RejectionCode.UNKNOWN_FEATURE
    assert "cortisol" not in result.valid


@pytest.mark.parametrize(
    "value", ["never", "former", "current", "ever", "not_current", "no_info"]
)
def test_every_module_2_smoking_category_is_valid(value):
    result = validate_features(
        with_features(
            feature("smoking_history", value, None, source="patient_profile")
        )
    )
    assert result.valid["smoking_history"].value == value


@pytest.mark.parametrize("value", ["male", "female", "other", "prefer_not_to_say"])
def test_every_module_2_gender_category_is_valid(value):
    result = validate_features(
        with_features(feature("gender", value, None, source="patient_profile"))
    )
    assert result.valid["gender"].value == value


@pytest.mark.parametrize(
    "name,value",
    [
        ("smoking_history", "sometimes"),
        ("smoking_history", "Never"),
        ("smoking_history", 1),
        ("gender", "man"),
        ("gender", True),
    ],
)
def test_a_token_outside_the_vocabulary_is_rejected(name, value):
    result = validate_features(
        with_features(feature(name, value, None, source="patient_profile"))
    )
    assert result.rejected[name].reason_code == RejectionCode.UNKNOWN_CATEGORY
    assert name not in result.valid


def test_no_info_is_a_real_category_not_a_missing_value():
    result = validate_features(
        with_features(
            feature("smoking_history", "no_info", None, source="patient_profile")
        )
    )
    assert result.valid["smoking_history"].value == "no_info"


@pytest.mark.parametrize("name", ["hypertension", "heart_disease"])
def test_tristate_true_survives(name):
    result = validate_features(
        with_features(feature(name, True, None, source="patient_profile"))
    )
    assert result.valid[name].value is True


@pytest.mark.parametrize("name", ["hypertension", "heart_disease"])
def test_tristate_explicit_false_survives_as_false(name):
    result = validate_features(
        with_features(feature(name, False, None, source="patient_profile"))
    )
    assert result.valid[name].value is False
    assert name not in result.rejected


@pytest.mark.parametrize("name", ["hypertension", "heart_disease"])
def test_tristate_unknown_stays_unknown_and_never_becomes_false(name):
    data = module_5_data(missing_features=[name])
    result = validate_features(data)
    assert name not in result.valid
    assert name not in result.questionable
    assert name not in result.rejected
    assert name in result.missing_features
    assert name not in usable_features(result)


@pytest.mark.parametrize("name", ["hypertension", "heart_disease"])
@pytest.mark.parametrize("value", ["yes", "true", 1, 0, "unknown", None])
def test_a_non_boolean_tristate_value_is_rejected_never_coerced(name, value):
    result = validate_features(
        with_features(feature(name, value, None, source="patient_profile"))
    )
    assert result.rejected[name].reason_code == RejectionCode.NOT_A_BOOLEAN
    assert name not in result.valid
    assert usable_features(result).get(name) is None


def test_unit_assumed_makes_a_feature_questionable_but_usable():
    result = validate_features(
        with_features(
            feature("hemoglobin", 14.2, "g/dl", unit_assumed=True)
        )
    )
    entry = result.valid["hemoglobin"]
    assert entry.questionable is True
    assert entry.status == STATUS_QUESTIONABLE
    assert "hemoglobin" in result.questionable
    assert any(f.code == FlagCode.UNIT_ASSUMED for f in entry.flags)
    assert usable_features(result)["hemoglobin"] == 14.2


def test_a_censored_value_is_flagged_and_kept_at_the_detection_limit():
    result = validate_features(
        with_features(
            feature(
                "vitamin_d", 3.0, "ng/ml", censored="left", original_value_raw="<3"
            )
        )
    )
    entry = result.valid["vitamin_d"]
    assert entry.value == 3.0
    assert entry.questionable is True
    assert any(f.code == FlagCode.CENSORED_VALUE for f in entry.flags)


def test_a_derived_value_is_flagged():
    result = validate_features(
        with_features(
            feature(
                "bmi",
                24.0,
                "kg/m2",
                source="patient_profile",
                derived="computed from height and weight",
            )
        )
    )
    entry = result.valid["bmi"]
    assert entry.questionable is True
    assert any(f.code == FlagCode.DERIVED_VALUE for f in entry.flags)


@pytest.mark.parametrize("confidence,flagged", [(0.3, True), (0.6, True), (0.95, False)])
def test_low_extraction_confidence_is_flagged(confidence, flagged):
    result = validate_features(
        with_features(feature("hba1c", 6.8, "%", confidence=confidence))
    )
    entry = result.valid["hba1c"]
    assert entry.questionable is flagged
    assert (
        any(f.code == FlagCode.LOW_EXTRACTION_CONFIDENCE for f in entry.flags)
        is flagged
    )


def test_a_value_attributed_to_an_unreadable_page_is_flagged():
    data = with_features(
        feature("hba1c", 6.8, "%", page_number=2),
        upstream={
            "provided": True,
            "pages": [
                {"page_number": 1, "raw_text_available": True},
                {"page_number": 2, "raw_text_available": False},
            ],
            "pages_unreadable": [2],
        },
    )
    result = validate_features(data)
    entry = result.valid["hba1c"]
    assert any(f.code == FlagCode.PARTIAL_DOCUMENT for f in entry.flags)
    assert entry.questionable is True


def test_a_clean_page_in_a_partially_unreadable_document_is_not_flagged():
    data = with_features(
        feature("hba1c", 6.8, "%", page_number=1),
        upstream={
            "provided": True,
            "pages": [
                {"page_number": 1, "raw_text_available": True},
                {"page_number": 2, "raw_text_available": False},
            ],
            "pages_unreadable": [2],
        },
    )
    result = validate_features(data)
    assert result.valid["hba1c"].questionable is False
    assert result.valid["hba1c"].status == STATUS_VALID
    assert any("partially readable" in w for w in result.warnings)
    assert any("UNREAD rather than absent" in w for w in result.warnings)


def test_an_extreme_value_is_not_questionable():
    result = validate_features(
        with_features(feature("blood_glucose", 500.0, "mg/dl"))
    )
    entry = result.valid["blood_glucose"]
    assert entry.clinically_extreme is True
    assert entry.questionable is False
    assert entry.status == STATUS_VALID
    assert "blood_glucose" not in result.questionable


def test_questionable_is_a_subset_of_valid_and_disjoint_from_rejected():
    result = validate_features(
        with_features(
            feature("hba1c", 6.8, "%", unit_assumed=True),
            feature("blood_glucose", 95.0, "mg/dl"),
            feature("creatinine", 40000.0, "mg/dl"),
        )
    )
    assert set(result.questionable) <= set(result.valid)
    assert not (set(result.valid) & set(result.rejected))
    assert set(result.valid) == {"hba1c", "blood_glucose"}
    assert set(result.questionable) == {"hba1c"}
    assert set(result.rejected) == {"creatinine"}


def test_every_rejection_carries_a_code_a_message_and_provenance():
    result = validate_features(
        with_features(
            feature(
                "blood_glucose",
                40000.0,
                "mg/dl",
                original_test_name="Fasting Blood Glucose",
                original_value_raw="40000",
                page_number=1,
            )
        )
    )
    rejection = result.rejected["blood_glucose"]
    assert rejection.reason_code
    assert len(rejection.reason) > 20
    assert rejection.provenance.original_test_name == "Fasting Blood Glucose"
    assert rejection.provenance.original_value_raw == "40000"
    assert rejection.provenance.page_number == 1


def test_summary_counts_match_the_partition():
    result = validate_features(
        with_features(
            feature("hba1c", 6.8, "%", unit_assumed=True),
            feature("blood_glucose", 400.0, "mg/dl"),
            feature("creatinine", 40000.0, "mg/dl"),
            missing_features=["bmi"],
        )
    )
    s = result.summary
    assert s.features_received == 3
    assert s.valid_count == 2
    assert s.questionable_count == 1
    assert s.rejected_count == 1
    assert s.clinically_extreme_count == 1
    assert s.missing_count == 1


def test_upstream_warnings_survive_with_their_origins():
    data = with_features(
        feature("hba1c", 6.8, "%"),
        upstream_warnings=[
            {
                "stage": STAGE_EXTRACTION,
                "module": 4,
                "message": "page 1 was recovered by the PDF repairer",
            }
        ],
        warnings=["2 report rows mapped to feature 'hba1c'"],
        all_warnings=[
            {
                "stage": STAGE_EXTRACTION,
                "module": 4,
                "message": "page 1 was recovered by the PDF repairer",
            },
            {
                "stage": STAGE_FEATURE_ENGINEERING,
                "module": 5,
                "message": "2 report rows mapped to feature 'hba1c'",
            },
        ],
    )
    result = validate_features(data)
    stages = [w.stage for w in result.all_warnings]
    assert stages[0] == STAGE_EXTRACTION
    assert stages[1] == STAGE_FEATURE_ENGINEERING
    assert {w.module for w in result.upstream_warnings} == {4, 5}
    messages = [w.message for w in result.all_warnings]
    assert "page 1 was recovered by the PDF repairer" in messages


def test_module_6_warnings_are_stamped_with_the_validation_stage():
    result = validate_features(
        with_features(feature("blood_glucose", 40000.0, "mg/dl"))
    )
    own = [w for w in result.all_warnings if w.stage == STAGE_VALIDATION]
    assert own
    assert all(w.module == 6 for w in own)
    assert any("rejected" in w.message for w in own)
    assert result.warnings == [w.message for w in own]


def test_upstream_warnings_are_rebuilt_when_all_warnings_was_dropped():
    data = with_features(
        feature("hba1c", 6.8, "%"),
        upstream_warnings=[
            {"stage": STAGE_EXTRACTION, "module": 4, "message": "damaged scan"}
        ],
        warnings=["a Module 5 caveat"],
        all_warnings=[],
    )
    result = validate_features(data)
    pairs = {(w.stage, w.message) for w in result.upstream_warnings}
    assert (STAGE_EXTRACTION, "damaged scan") in pairs
    assert (STAGE_FEATURE_ENGINEERING, "a Module 5 caveat") in pairs


def test_no_upstream_warning_is_edited_or_dropped():
    upstream = [
        {"stage": STAGE_EXTRACTION, "module": 4, "message": f"warning {i}"}
        for i in range(5)
    ]
    result = validate_features(
        with_features(feature("hba1c", 6.8, "%"), all_warnings=upstream)
    )
    assert [w.message for w in result.upstream_warnings] == [
        f"warning {i}" for i in range(5)
    ]
    assert result.summary.upstream_warning_count == 5


def test_unmapped_missing_and_upstream_are_carried_forward():
    data = with_features(
        feature("hba1c", 6.8, "%"),
        unmapped=[
            {
                "test_name": "Urine Ketones",
                "value_raw": "Negative",
                "reason": "non_numeric_value",
            }
        ],
        missing_features=["bmi", "hypertension"],
        upstream={
            "provided": True,
            "extraction_confidence": 0.42,
            "pages": [
                {"page_number": 1, "raw_text_available": True},
                {"page_number": 2, "raw_text_available": False},
            ],
            "pages_unreadable": [2],
            "report_metadata": {"lab_name": "Northfield"},
        },
        summary={"feature_count": 1, "parameters_received": 3},
    )
    result = validate_features(data)
    assert [u.test_name for u in result.unmapped] == ["Urine Ketones"]
    assert result.missing_features == ["bmi", "hypertension"]
    assert result.upstream.extraction_confidence == 0.42
    assert result.upstream.pages_unreadable == [2]
    assert result.upstream.report_metadata.lab_name == "Northfield"
    assert result.upstream_summary.parameters_received == 3
    assert result.summary.extraction_confidence == 0.42
    assert result.summary.partial_document is True
    assert result.summary.pages_unreadable_count == 1


def test_a_rejected_feature_is_not_added_to_missing_features():
    result = validate_features(
        with_features(
            feature("blood_glucose", 40000.0, "mg/dl"), missing_features=["bmi"]
        )
    )
    assert result.missing_features == ["bmi"]
    assert "blood_glucose" in result.rejected


def test_low_overall_extraction_confidence_raises_a_document_warning():
    result = validate_features(
        with_features(
            feature("hba1c", 6.8, "%"),
            upstream={"provided": True, "extraction_confidence": 0.4},
        )
    )
    assert any("Overall extraction confidence" in w for w in result.warnings)


def test_empty_input_is_valid_and_produces_an_empty_partition():
    result = validate_features(module_5_data())
    assert result.valid == {}
    assert result.questionable == {}
    assert result.rejected == {}
    assert result.summary.features_received == 0
    assert any("No engineered features" in w for w in result.warnings)


def test_no_argument_at_all_is_accepted():
    result = validate_features()
    assert result.summary.features_received == 0


def test_an_all_invalid_input_yields_an_empty_valid_set_and_a_warning():
    result = validate_features(
        with_features(
            feature("blood_glucose", 40000.0, "mg/dl"),
            feature("hba1c", "abc", "%"),
            feature("creatinine", 1.0, "flurbs", canonical_unit=False),
        )
    )
    assert result.valid == {}
    assert len(result.rejected) == 3
    assert any("No feature survived validation" in w for w in result.warnings)


def test_features_missing_provenance_are_still_validated():
    result = validate_features({"features": {"hba1c": {"value": 6.8, "unit": "%"}}})
    assert result.valid["hba1c"].value == 6.8
    assert result.valid["hba1c"].provenance.source == "lab_report"


def test_output_is_deterministic_in_catalog_order():
    result = validate_features(
        with_features(
            feature("gender", "male", None, source="patient_profile"),
            feature("hba1c", 6.8, "%"),
            feature("blood_glucose", 95.0, "mg/dl"),
        )
    )
    assert list(result.valid) == ["hba1c", "blood_glucose", "gender"]


def test_it_consumes_engineer_features_output_directly():
    engineered = engineer_from_extraction(
        {
            "source": {"filename": "report.pdf", "mime_type": "application/pdf"},
            "pages": [
                {"page_number": 1, "raw_text": "..."},
                {"page_number": 2, "raw_text": None},
            ],
            "extracted_parameters": [
                {
                    "test_name": "HbA1c",
                    "value_raw": "6.8",
                    "value_numeric": 6.8,
                    "unit": "%",
                    "page_number": 1,
                    "confidence": 0.94,
                },
                {
                    "test_name": "Fasting Blood Glucose",
                    "value_raw": "400",
                    "value_numeric": 400.0,
                    "unit": "mg/dL",
                    "page_number": 1,
                    "confidence": 0.91,
                },
                {
                    "test_name": "Creatinine",
                    "value_raw": "1.0",
                    "value_numeric": 1.0,
                    "unit": "flurbs",
                    "page_number": 1,
                    "confidence": 0.9,
                },
                {
                    "test_name": "Urine Ketones",
                    "value_raw": "Negative",
                    "value_numeric": None,
                    "unit": None,
                    "page_number": 1,
                    "confidence": 0.9,
                },
            ],
            "extraction_confidence": 0.92,
            "warnings": ["page 1 was recovered by the PDF repairer"],
        },
        {"age": 45, "gender": "male", "smokingHistory": "never"},
    )
    result = validate_features(engineered)

    assert set(result.valid) == {
        "hba1c",
        "blood_glucose",
        "age",
        "smoking_history",
        "gender",
    }
    assert result.valid["blood_glucose"].clinically_extreme is True
    assert result.rejected["creatinine"].reason_code == RejectionCode.NON_CANONICAL_UNIT
    assert [u.test_name for u in result.unmapped] == ["Urine Ketones"]
    assert "hypertension" in result.missing_features
    assert "hypertension" not in result.valid
    assert "hypertension" not in result.rejected
    assert any(
        w.stage == STAGE_EXTRACTION and "PDF repairer" in w.message
        for w in result.all_warnings
    )
    assert any(w.stage == STAGE_VALIDATION for w in result.all_warnings)


def test_the_policy_string_states_the_line():
    assert "abnormal" in VALIDATION_POLICY
    assert "clinically_extreme" in VALIDATION_POLICY
