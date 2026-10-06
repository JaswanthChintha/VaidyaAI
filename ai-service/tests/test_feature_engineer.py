"""The Module 5 engineering function, called directly (no HTTP, no network).

`engineer_features` is the importable entry point Module 7 and the ML layer
use, so it is tested on its own rather than only through the endpoint.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.data.feature_catalog import (
    CANONICAL_FEATURES,
    SOURCE_LAB_REPORT,
    SOURCE_PATIENT_PROFILE,
    UnmappedReason,
)
from app.schemas.extraction import ExtractedParameter
from app.schemas.features import FeatureEngineeringData, PatientProfileContext
from app.services.feature_engineer import (
    engineer_features,
    engineer_from_extraction,
)


def row(**kw):
    """A Module 4 extracted_parameters[] row with sensible defaults."""
    base = {
        "test_name": "HbA1c",
        "value_raw": "6.8",
        "value_numeric": 6.8,
        "unit": "%",
        "reference_range_raw": None,
        "reference_low": None,
        "reference_high": None,
        "flag": None,
        "page_number": 1,
        "confidence": 0.9,
    }
    base.update(kw)
    return base


# --------------------------------------------------------------------------
# Empty / degenerate input
# --------------------------------------------------------------------------


def test_empty_input_returns_an_empty_but_valid_feature_set():
    data = engineer_features([])
    assert isinstance(data, FeatureEngineeringData)
    assert data.features == {}
    assert data.unmapped == []
    assert data.conversions_applied == []
    assert data.duplicates_resolved == []
    assert set(data.missing_features) == set(CANONICAL_FEATURES)
    assert data.summary.parameters_received == 0
    assert data.summary.profile_provided is False


def test_none_input_is_treated_as_empty():
    assert engineer_features(None).features == {}
    assert engineer_features(None, None).features == {}


def test_accepts_dicts_and_pydantic_models_alike():
    from_dicts = engineer_features([row()])
    from_models = engineer_features([ExtractedParameter(**row())])
    assert from_dicts.features["hba1c"].value == from_models.features["hba1c"].value


def test_invalid_row_raises_the_module_4_contract_error():
    with pytest.raises(ValidationError):
        engineer_features([{"value_raw": "6.8"}])  # no test_name


def test_engineer_from_extraction_accepts_module_4_data_object():
    data = engineer_from_extraction(
        {
            "source": {"filename": "r.pdf"},
            "raw_text": "...",
            "extracted_parameters": [row()],
            "extraction_confidence": 0.9,
        }
    )
    assert data.features["hba1c"].value == pytest.approx(6.8)


# --------------------------------------------------------------------------
# Straightforward mapping
# --------------------------------------------------------------------------


def test_canonical_feature_carries_value_unit_source_and_provenance():
    data = engineer_features(
        [
            row(
                test_name="Glycated Haemoglobin",
                value_raw="6.8",
                value_numeric=6.8,
                unit="%",
                reference_range_raw="4.0 - 5.6",
                reference_low=4.0,
                reference_high=5.6,
                flag="high",
                page_number=2,
                confidence=0.94,
            )
        ]
    )
    feature = data.features["hba1c"]
    assert feature.name == "hba1c"
    assert feature.value == pytest.approx(6.8)
    assert feature.unit == "%"
    assert feature.canonical_unit is True
    assert feature.source == SOURCE_LAB_REPORT

    prov = feature.provenance
    assert prov.source == SOURCE_LAB_REPORT
    assert prov.original_test_name == "Glycated Haemoglobin"
    assert prov.original_value_raw == "6.8"
    assert prov.original_value_numeric == pytest.approx(6.8)
    assert prov.original_unit == "%"
    assert prov.normalized_unit == "%"
    # The synonym-table entry that matched. British and American spellings
    # share one normalised key, so the table entry is the American one.
    assert prov.matched_synonym == "Glycated Hemoglobin"
    assert prov.parameter_index == 0
    assert prov.page_number == 2
    assert prov.confidence == pytest.approx(0.94)
    assert prov.reference_range_raw == "4.0 - 5.6"
    assert prov.reference_low == 4.0
    assert prov.reference_high == 5.6
    assert prov.flag == "high"
    assert prov.unit_converted is False
    assert prov.conversion is None
    assert prov.censored is None


def test_provenance_index_points_back_at_the_submitted_row():
    data = engineer_features(
        [
            row(test_name="Sodium", value_raw="140", value_numeric=140.0, unit="mmol/L"),
            row(test_name="Creatinine", value_raw="1.0", value_numeric=1.0, unit="mg/dL"),
        ]
    )
    assert data.features["creatinine"].provenance.parameter_index == 1
    assert data.unmapped[0].parameter_index == 0


# --------------------------------------------------------------------------
# Unit conversion through the engineering path
# --------------------------------------------------------------------------


def test_conversion_is_applied_and_recorded():
    data = engineer_features(
        [
            row(
                test_name="Creatinine",
                value_raw="88.4017",
                value_numeric=88.4017,
                unit="µmol/L",
            )
        ]
    )
    feature = data.features["creatinine"]
    assert feature.value == pytest.approx(1.0, abs=1e-5)
    assert feature.unit == "mg/dl"
    assert feature.canonical_unit is True
    assert feature.provenance.unit_converted is True
    assert feature.provenance.conversion.from_unit == "umol/l"
    assert feature.provenance.conversion.to_unit == "mg/dl"
    assert feature.provenance.conversion.factor == pytest.approx(0.011312)

    assert len(data.conversions_applied) == 1
    record = data.conversions_applied[0]
    assert record.feature == "creatinine"
    assert record.original_unit == "µmol/L"
    assert record.original_value == pytest.approx(88.4017)
    assert record.canonical_value == pytest.approx(1.0, abs=1e-5)
    assert record.canonical_unit == "mg/dl"


def test_identity_conversion_is_not_recorded_as_a_conversion():
    data = engineer_features([row(test_name="Creatinine", value_raw="1.0",
                                  value_numeric=1.0, unit="mg/dL")])
    assert data.conversions_applied == []
    assert data.features["creatinine"].provenance.unit_converted is False


def test_hba1c_ifcc_conversion_end_to_end():
    data = engineer_features(
        [row(test_name="HbA1c", value_raw="48", value_numeric=48.0, unit="mmol/mol")]
    )
    assert data.features["hba1c"].value == pytest.approx(6.54304)
    assert data.features["hba1c"].unit == "%"


# --------------------------------------------------------------------------
# Missing and unrecognised units
# --------------------------------------------------------------------------


def test_missing_unit_assumes_canonical_and_warns():
    data = engineer_features(
        [row(test_name="Creatinine", value_raw="1.0", value_numeric=1.0, unit=None)]
    )
    feature = data.features["creatinine"]
    assert feature.value == pytest.approx(1.0)
    assert feature.unit == "mg/dl"
    assert feature.canonical_unit is True
    assert feature.provenance.unit_assumed is True
    assert any("no printed unit" in w for w in data.warnings)


def test_unrecognised_unit_is_flagged_never_assumed_canonical():
    data = engineer_features(
        [row(test_name="Creatinine", value_raw="1.0", value_numeric=1.0, unit="IU/mL")]
    )
    feature = data.features["creatinine"]
    # Value is NOT converted and NOT relabelled as canonical.
    assert feature.value == pytest.approx(1.0)
    assert feature.unit == "IU/mL"
    assert feature.canonical_unit is False
    assert feature.provenance.unit_recognised is False
    assert feature.provenance.unit_assumed is False
    assert feature.provenance.conversion is None
    assert data.conversions_applied == []
    assert any("not a recognised unit" in w for w in data.warnings)


def test_unit_valid_elsewhere_but_wrong_for_this_feature_is_flagged():
    # pg/mL is a real unit, but not a creatinine unit.
    data = engineer_features(
        [row(test_name="Creatinine", value_raw="1.0", value_numeric=1.0, unit="pg/mL")]
    )
    assert data.features["creatinine"].canonical_unit is False
    assert data.features["creatinine"].unit == "pg/mL"


# --------------------------------------------------------------------------
# Non-numeric and censored values
# --------------------------------------------------------------------------


def test_qualitative_value_is_preserved_not_invented():
    data = engineer_features(
        [
            row(
                test_name="Urine Ketones",
                value_raw="Negative",
                value_numeric=None,
                unit=None,
            )
        ]
    )
    assert data.features == {}
    assert len(data.unmapped) == 1
    assert data.unmapped[0].test_name == "Urine Ketones"
    assert data.unmapped[0].value_raw == "Negative"


def test_qualitative_value_on_a_mapped_test_is_reported_as_non_numeric():
    data = engineer_features(
        [
            row(
                test_name="Vitamin B12",
                value_raw="Not Detected",
                value_numeric=None,
                unit="pg/mL",
            )
        ]
    )
    assert "vitamin_b12" not in data.features
    item = data.unmapped[0]
    assert item.reason == UnmappedReason.NON_NUMERIC_VALUE
    assert "vitamin_b12" in (item.detail or "")


@pytest.mark.parametrize(
    "raw,expected_value,expected_side",
    [
        ("<0.1", 0.1, "left"),
        (">500", 500.0, "right"),
        ("≤0.1", 0.1, "left"),
        ("≥500", 500.0, "right"),
    ],
)
def test_censored_values_are_kept_at_the_detection_limit(
    raw, expected_value, expected_side
):
    data = engineer_features(
        [
            row(
                test_name="Vitamin B12",
                value_raw=raw,
                value_numeric=None,
                unit="pg/mL",
            )
        ]
    )
    feature = data.features["vitamin_b12"]
    assert feature.value == pytest.approx(expected_value)
    assert feature.provenance.censored == expected_side
    assert any("censored" in w for w in data.warnings)


def test_thousands_separator_is_parsed():
    data = engineer_features(
        [
            row(
                test_name="Vitamin B12",
                value_raw="1,234",
                value_numeric=None,
                unit="pg/mL",
            )
        ]
    )
    assert data.features["vitamin_b12"].value == pytest.approx(1234.0)


def test_module_4_numeric_value_wins_over_reparsing():
    data = engineer_features(
        [row(test_name="Creatinine", value_raw="1.0 mg/dL", value_numeric=1.0,
             unit="mg/dL")]
    )
    assert data.features["creatinine"].value == pytest.approx(1.0)


# --------------------------------------------------------------------------
# Unmapped preservation
# --------------------------------------------------------------------------


def test_unmapped_tests_keep_their_original_names():
    data = engineer_features(
        [
            row(test_name="Serum Sodium", value_raw="140", value_numeric=140.0,
                unit="mmol/L"),
            row(test_name="TSH", value_raw="2.1", value_numeric=2.1, unit="µIU/mL"),
            row(test_name="HDL Cholesterol", value_raw="52", value_numeric=52.0,
                unit="mg/dL"),
        ]
    )
    assert data.features == {}
    names = [u.test_name for u in data.unmapped]
    assert names == ["Serum Sodium", "TSH", "HDL Cholesterol"]
    reasons = {u.test_name: u.reason for u in data.unmapped}
    assert reasons["HDL Cholesterol"] == UnmappedReason.DISTINCT_ANALYTE
    assert reasons["TSH"] == UnmappedReason.NO_SYNONYM


def test_urine_creatinine_does_not_become_serum_creatinine():
    data = engineer_features(
        [row(test_name="Urine Creatinine", value_raw="120", value_numeric=120.0,
             unit="mg/dL")]
    )
    assert "creatinine" not in data.features
    assert data.unmapped[0].reason == UnmappedReason.NON_BLOOD_SPECIMEN


# --------------------------------------------------------------------------
# Duplicate resolution
# --------------------------------------------------------------------------


def test_fasting_glucose_beats_postprandial_regardless_of_order():
    rows = [
        row(test_name="Post Prandial Blood Sugar", value_raw="180",
            value_numeric=180.0, unit="mg/dL", confidence=0.99),
        row(test_name="Fasting Blood Glucose", value_raw="112",
            value_numeric=112.0, unit="mg/dL", confidence=0.80),
    ]
    for ordering in (rows, list(reversed(rows))):
        data = engineer_features(ordering)
        assert data.features["blood_glucose"].value == pytest.approx(112.0)
        assert len(data.duplicates_resolved) == 1
        resolution = data.duplicates_resolved[0]
        assert resolution.feature == "blood_glucose"
        assert resolution.chosen.test_name == "Fasting Blood Glucose"
        assert [d.test_name for d in resolution.discarded] == [
            "Post Prandial Blood Sugar"
        ]


def test_discarded_duplicates_stay_visible_in_unmapped():
    data = engineer_features(
        [
            row(test_name="Fasting Blood Glucose", value_raw="112",
                value_numeric=112.0, unit="mg/dL"),
            row(test_name="Random Blood Sugar", value_raw="150",
                value_numeric=150.0, unit="mg/dL"),
        ]
    )
    discarded = [u for u in data.unmapped
                 if u.reason == UnmappedReason.DUPLICATE_DISCARDED]
    assert len(discarded) == 1
    assert discarded[0].test_name == "Random Blood Sugar"
    assert discarded[0].value_raw == "150"
    assert any("duplicates_resolved" in w for w in data.warnings)


def test_confidence_breaks_a_tie_between_equal_specificity_rows():
    data = engineer_features(
        [
            row(test_name="Creatinine", value_raw="1.0", value_numeric=1.0,
                unit="mg/dL", confidence=0.5),
            row(test_name="Serum Creatinine", value_raw="1.4", value_numeric=1.4,
                unit="mg/dL", confidence=0.95),
        ]
    )
    assert data.features["creatinine"].value == pytest.approx(1.4)


def test_recognised_unit_beats_unrecognised_unit():
    data = engineer_features(
        [
            row(test_name="Creatinine", value_raw="1.0", value_numeric=1.0,
                unit="IU/mL", confidence=0.99),
            row(test_name="Creatinine", value_raw="1.4", value_numeric=1.4,
                unit="mg/dL", confidence=0.10),
        ]
    )
    assert data.features["creatinine"].value == pytest.approx(1.4)
    assert data.features["creatinine"].canonical_unit is True


def test_uncensored_beats_censored():
    data = engineer_features(
        [
            row(test_name="Vitamin B12", value_raw="<200", value_numeric=None,
                unit="pg/mL", confidence=0.9),
            row(test_name="Vitamin B12", value_raw="210", value_numeric=210.0,
                unit="pg/mL", confidence=0.9),
        ]
    )
    assert data.features["vitamin_b12"].value == pytest.approx(210.0)


def test_missing_confidence_ranks_below_a_stated_one():
    data = engineer_features(
        [
            row(test_name="Creatinine", value_raw="1.0", value_numeric=1.0,
                unit="mg/dL", confidence=None),
            row(test_name="Creatinine", value_raw="1.4", value_numeric=1.4,
                unit="mg/dL", confidence=0.05),
        ]
    )
    assert data.features["creatinine"].value == pytest.approx(1.4)


def test_input_order_is_the_final_deterministic_tiebreak():
    identical = dict(test_name="Creatinine", unit="mg/dL", confidence=0.9,
                     page_number=1)
    data = engineer_features(
        [
            row(value_raw="1.0", value_numeric=1.0, **identical),
            row(value_raw="1.4", value_numeric=1.4, **identical),
        ]
    )
    assert data.features["creatinine"].value == pytest.approx(1.0)
    assert data.summary.duplicate_count == 1


def test_earlier_page_wins_before_input_order():
    data = engineer_features(
        [
            row(test_name="Creatinine", value_raw="1.0", value_numeric=1.0,
                unit="mg/dL", confidence=0.9, page_number=3),
            row(test_name="Creatinine", value_raw="1.4", value_numeric=1.4,
                unit="mg/dL", confidence=0.9, page_number=1),
        ]
    )
    assert data.features["creatinine"].value == pytest.approx(1.4)


def test_three_way_duplicate_keeps_all_losers():
    data = engineer_features(
        [
            row(test_name="Glucose", value_raw="100", value_numeric=100.0,
                unit="mg/dL"),
            row(test_name="Random Blood Sugar", value_raw="150",
                value_numeric=150.0, unit="mg/dL"),
            row(test_name="PPBS", value_raw="180", value_numeric=180.0,
                unit="mg/dL"),
        ]
    )
    resolution = data.duplicates_resolved[0]
    assert resolution.chosen.test_name == "Glucose"
    assert len(resolution.discarded) == 2
    assert resolution.policy.startswith("deterministic_rank")


# --------------------------------------------------------------------------
# Missing / null fields throughout
# --------------------------------------------------------------------------


def test_all_optional_module_4_fields_null():
    data = engineer_features([{"test_name": "HbA1c", "value_raw": "6.8"}])
    feature = data.features["hba1c"]
    assert feature.value == pytest.approx(6.8)
    assert feature.provenance.page_number is None
    assert feature.provenance.confidence is None
    assert feature.provenance.flag is None
    assert feature.provenance.reference_low is None
    assert feature.provenance.unit_assumed is True


def test_flag_normal_is_carried_through_untouched():
    data = engineer_features([row(flag="normal")])
    assert data.features["hba1c"].provenance.flag == "normal"


def test_missing_features_lists_everything_not_produced():
    data = engineer_features([row()])
    assert "hba1c" not in data.missing_features
    for name in ("blood_glucose", "bmi", "age", "hypertension", "heart_disease",
                 "smoking_history"):
        assert name in data.missing_features


# --------------------------------------------------------------------------
# Patient profile merge
# --------------------------------------------------------------------------


def test_profile_features_merge_into_the_same_feature_space():
    data = engineer_features(
        [row()],
        {
            "age": 45,
            "gender": "male",
            "bmi": 27.4,
            "hypertension": True,
            "heartDisease": False,
            "smokingHistory": "former",
        },
    )
    assert data.features["hba1c"].source == SOURCE_LAB_REPORT
    for name in ("age", "gender", "bmi", "hypertension", "heart_disease",
                 "smoking_history"):
        assert data.features[name].source == SOURCE_PATIENT_PROFILE
    assert data.features["age"].value == 45
    assert data.features["bmi"].value == pytest.approx(27.4)
    assert data.features["bmi"].unit == "kg/m2"
    assert data.features["gender"].value == "male"
    assert data.features["smoking_history"].value == "former"
    assert data.summary.profile_feature_count == 6
    assert data.summary.lab_feature_count == 1


def test_snake_case_profile_keys_are_accepted_too():
    data = engineer_features([], {"heart_disease": True, "smoking_history": "never"})
    assert data.features["heart_disease"].value is True
    assert data.features["smoking_history"].value == "never"


def test_profile_provenance_names_the_source_field():
    data = engineer_features([], {"heartDisease": True})
    prov = data.features["heart_disease"].provenance
    assert prov.source == SOURCE_PATIENT_PROFILE
    assert prov.original_test_name == "heartDisease"
    assert prov.original_value_raw == "True"


def test_age_stays_an_integer_and_bmi_stays_a_float():
    data = engineer_features([], {"age": 45, "bmi": 27.4})
    assert isinstance(data.features["age"].value, int)
    assert not isinstance(data.features["age"].value, bool)
    assert isinstance(data.features["bmi"].value, float)


def test_bmi_is_derived_from_height_and_weight_only_as_a_fallback():
    data = engineer_features([], {"heightCm": 170, "weightKg": 70})
    # 70 / 1.7^2 = 70 / 2.89 = 24.2214... -> 24.22
    assert data.features["bmi"].value == pytest.approx(24.22)
    assert data.features["bmi"].provenance.derived is not None
    assert any("derived from heightCm" in w for w in data.warnings)


def test_supplied_bmi_wins_over_height_and_weight():
    data = engineer_features([], {"bmi": 30.0, "heightCm": 170, "weightKg": 70})
    assert data.features["bmi"].value == pytest.approx(30.0)
    assert data.features["bmi"].provenance.derived is None


# --- TRI-STATE BOOLEAN PRESERVATION ---------------------------------------


def test_absent_boolean_is_unknown_and_never_false():
    data = engineer_features([], {"age": 45})
    assert "hypertension" not in data.features
    assert "heart_disease" not in data.features
    assert "hypertension" in data.missing_features
    assert "heart_disease" in data.missing_features


def test_explicit_null_boolean_is_unknown_and_never_false():
    data = engineer_features([], {"hypertension": None, "heartDisease": None})
    assert "hypertension" not in data.features
    assert "heart_disease" not in data.features


def test_explicit_false_boolean_is_present_and_false():
    data = engineer_features([], {"hypertension": False, "heartDisease": False})
    assert data.features["hypertension"].value is False
    assert data.features["heart_disease"].value is False
    assert "hypertension" not in data.missing_features
    assert "heart_disease" not in data.missing_features


def test_the_three_boolean_states_are_all_distinguishable():
    absent = engineer_features([], {})
    false = engineer_features([], {"hypertension": False})
    true = engineer_features([], {"hypertension": True})

    assert "hypertension" not in absent.features         # unknown
    assert false.features["hypertension"].value is False  # explicit negative
    assert true.features["hypertension"].value is True    # explicit positive


def test_unrecognised_boolean_is_unknown_and_reported():
    data = engineer_features([], {"hypertension": "sort of"})
    assert "hypertension" not in data.features
    assert any(u.test_name == "hypertension"
               and u.reason == UnmappedReason.UNRECOGNISED_CATEGORY
               for u in data.unmapped)
    assert any("UNKNOWN (not false)" in w for w in data.warnings)


def test_unrecognised_smoking_history_is_not_defaulted():
    data = engineer_features([], {"smokingHistory": "occasionally"})
    assert "smoking_history" not in data.features
    assert any(u.test_name == "smokingHistory" for u in data.unmapped)


def test_prefer_not_to_say_gender_is_preserved_verbatim():
    data = engineer_features([], {"gender": "prefer_not_to_say"})
    assert data.features["gender"].value == "prefer_not_to_say"


def test_profile_rejects_a_negative_age():
    with pytest.raises(ValidationError):
        engineer_features([], {"age": -1})


def test_profile_model_can_be_passed_directly():
    data = engineer_features([], PatientProfileContext(age=50))
    assert data.features["age"].value == 50


# --------------------------------------------------------------------------
# Determinism
# --------------------------------------------------------------------------


def test_repeated_runs_produce_identical_output():
    rows = [
        row(test_name="Fasting Blood Glucose", value_raw="112",
            value_numeric=112.0, unit="mg/dL"),
        row(test_name="Random Blood Sugar", value_raw="150",
            value_numeric=150.0, unit="mg/dL"),
        row(test_name="Creatinine", value_raw="88.4", value_numeric=88.4,
            unit="umol/L"),
    ]
    first = engineer_features(rows, {"age": 45}).model_dump()
    second = engineer_features(rows, {"age": 45}).model_dump()
    assert first == second


def test_feature_map_is_ordered_by_the_catalog_not_by_input_order():
    data = engineer_features(
        [
            row(test_name="Creatinine", value_raw="1.0", value_numeric=1.0,
                unit="mg/dL"),
            row(test_name="HbA1c", value_raw="6.8", value_numeric=6.8, unit="%"),
        ]
    )
    assert list(data.features) == ["hba1c", "creatinine"]


# --------------------------------------------------------------------------
# The real, observed Module 4 live output -- cross-module integration check
# --------------------------------------------------------------------------

OBSERVED_MODULE_4_PARAMETERS = [
    {
        "test_name": "HbA1c",
        "value_raw": "6.8",
        "value_numeric": 6.8,
        "unit": "%",
        "reference_range_raw": "4.0 - 5.6",
        "reference_low": 4.0,
        "reference_high": 5.6,
        "flag": "high",
        "page_number": 1,
        "confidence": 0.94,
    },
    {
        "test_name": "Fasting Blood Glucose",
        "value_raw": "112",
        "value_numeric": 112.0,
        "unit": "mg/dL",
        "reference_range_raw": "70 - 99",
        "reference_low": 70.0,
        "reference_high": 99.0,
        "flag": "high",
        "page_number": 1,
        "confidence": 0.95,
    },
    {
        "test_name": "Haemoglobin",
        "value_raw": "14.2",
        "value_numeric": 14.2,
        "unit": "g/dL",
        "reference_range_raw": "13.0 - 17.0",
        "reference_low": 13.0,
        "reference_high": 17.0,
        "flag": "normal",
        "page_number": 1,
        "confidence": 0.96,
    },
    {
        "test_name": "Creatinine",
        "value_raw": "1.0",
        "value_numeric": 1.0,
        "unit": "mg/dL",
        "reference_range_raw": "0.7 - 1.3",
        "reference_low": 0.7,
        "reference_high": 1.3,
        "flag": "normal",
        "page_number": 1,
        "confidence": 0.95,
    },
    {
        "test_name": "Total Cholesterol",
        "value_raw": "190",
        "value_numeric": 190.0,
        "unit": "mg/dL",
        "reference_range_raw": "< 200",
        "reference_low": None,
        "reference_high": 200.0,
        "flag": "normal",
        "page_number": 1,
        "confidence": 0.94,
    },
    {
        "test_name": "Vitamin D (25-OH)",
        "value_raw": "35",
        "value_numeric": 35.0,
        "unit": "ng/mL",
        "reference_range_raw": "30 - 100",
        "reference_low": 30.0,
        "reference_high": 100.0,
        "flag": "normal",
        "page_number": 1,
        "confidence": 0.93,
    },
    {
        "test_name": "Urine Ketones",
        "value_raw": "Negative",
        "value_numeric": None,
        "unit": None,
        "reference_range_raw": "Negative",
        "reference_low": None,
        "reference_high": None,
        "flag": None,
        "page_number": 1,
        "confidence": 0.9,
    },
]


def test_observed_module_4_output_produces_the_expected_feature_set():
    data = engineer_features(OBSERVED_MODULE_4_PARAMETERS)

    assert set(data.features) == {
        "hba1c",
        "blood_glucose",
        "hemoglobin",
        "creatinine",
        "cholesterol",
        "vitamin_d",
    }
    assert data.features["hba1c"].value == pytest.approx(6.8)
    assert data.features["hba1c"].unit == "%"
    assert data.features["blood_glucose"].value == pytest.approx(112.0)
    assert data.features["blood_glucose"].unit == "mg/dl"
    assert data.features["hemoglobin"].value == pytest.approx(14.2)
    assert data.features["hemoglobin"].unit == "g/dl"
    assert data.features["creatinine"].value == pytest.approx(1.0)
    assert data.features["creatinine"].unit == "mg/dl"
    assert data.features["cholesterol"].value == pytest.approx(190.0)
    assert data.features["cholesterol"].unit == "mg/dl"
    assert data.features["vitamin_d"].value == pytest.approx(35.0)
    assert data.features["vitamin_d"].unit == "ng/ml"

    # Every feature is in its canonical unit, and none needed converting.
    assert all(f.canonical_unit for f in data.features.values())
    assert data.conversions_applied == []
    assert data.duplicates_resolved == []

    # The one non-numeric row is preserved, not dropped and not guessed.
    assert [u.test_name for u in data.unmapped] == ["Urine Ketones"]
    assert data.unmapped[0].value_raw == "Negative"

    # Profile features are absent because no profile was supplied.
    #
    # ⚠ AND SO IS THE WHOLE BLOOD COUNT, WHICH IS NEW AND IS CORRECT. This
    # observed Module 4 payload is a metabolic panel: it prints no CBC at
    # all, so every one of the twelve complete-blood-count features is
    # genuinely absent from it. They appear here because the catalogue grew,
    # not because anything stopped being extracted -- `data.features` is
    # unchanged at the same six.
    #
    # CONSEQUENCE WORTH KNOWING: any report without a blood count now reports
    # twelve more features as not present, which flows into
    # `missing_count` in feature_repository.py and into `features_not_present`
    # on the clinician summary.
    assert set(data.missing_features) == {
        "vitamin_b12",
        "triglycerides",
        "bmi",
        "age",
        "hypertension",
        "heart_disease",
        "smoking_history",
        "gender",
        "hematocrit",
        "rbc_count",
        "mcv",
        "mch",
        "mchc",
        "wbc_count",
        "neutrophils",
        "lymphocytes",
        "monocytes",
        "eosinophils",
        "basophils",
        "platelet_count",
        # The liver panel (2026-10-04): not on this report, so missing.
        "alt",
        "ast",
        "bilirubin_total",
    }
    assert data.warnings == []
    assert data.summary.parameters_received == 7
    assert data.summary.lab_feature_count == 6


def test_observed_module_4_output_with_profile_context():
    data = engineer_features(
        OBSERVED_MODULE_4_PARAMETERS,
        {
            "age": 45,
            "gender": "male",
            "bmi": 27.4,
            "hypertension": True,
            "smokingHistory": "never",
            # heartDisease deliberately absent -> UNKNOWN, not false.
        },
    )
    assert data.summary.feature_count == 11
    assert data.features["hypertension"].value is True
    assert "heart_disease" not in data.features
    # CATALOGUE ORDER, and the twelve blood-count features sit between
    # `triglycerides` and the profile features because that is where they are
    # declared in feature_catalog.py. This payload prints no blood count, so
    # all twelve are genuinely missing from it.
    assert data.missing_features == [
        "vitamin_b12",
        "triglycerides",
        "hematocrit",
        "rbc_count",
        "mcv",
        "mch",
        "mchc",
        "wbc_count",
        "neutrophils",
        "lymphocytes",
        "monocytes",
        "eosinophils",
        "basophils",
        "platelet_count",
        # The liver panel follows the blood count in catalogue order.
        "alt",
        "ast",
        "bilirubin_total",
        "heart_disease",
    ]
