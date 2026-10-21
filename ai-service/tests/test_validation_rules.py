from __future__ import annotations

import pytest

from app.data.feature_catalog import FEATURES
from app.data.validation_rules import (
    LOW_CONFIDENCE_THRESHOLD,
    QUESTIONABLE_FLAGS,
    RULES,
    FlagCode,
    RejectionCode,
    rule_for,
    rules_document,
)

NUMERIC = [name for name, rule in RULES.items() if rule.is_numeric]


def test_every_catalog_feature_has_a_rule():
    assert set(RULES) == set(FEATURES)


def test_no_rule_exists_for_an_unknown_feature():
    assert rule_for("not_a_feature") is None


@pytest.mark.parametrize("name", sorted(RULES))
def test_rule_agrees_with_the_catalog(name):
    rule = RULES[name]
    definition = FEATURES[name]
    assert rule.value_type == definition.value_type
    assert rule.unit == definition.canonical_unit


@pytest.mark.parametrize("name", sorted(NUMERIC))
def test_numeric_features_have_a_possible_band(name):
    rule = RULES[name]
    assert rule.possible_low is not None
    assert rule.possible_high is not None
    assert rule.possible_low < rule.possible_high


@pytest.mark.parametrize("name", sorted(NUMERIC))
def test_the_extreme_band_sits_inside_the_possible_band(name):
    rule = RULES[name]
    for bound in (rule.extreme_low, rule.extreme_high):
        if bound is not None:
            assert rule.possible_low <= bound <= rule.possible_high


@pytest.mark.parametrize("name", sorted(RULES))
def test_every_rule_states_its_basis(name):
    assert RULES[name].basis.strip()


def test_non_numeric_features_carry_no_range_band():
    for name in ("hypertension", "heart_disease", "smoking_history", "gender"):
        rule = RULES[name]
        assert rule.possible_low is None and rule.possible_high is None
        assert rule.extreme_low is None and rule.extreme_high is None


BAND_CASES = [
    ("blood_glucose", 400.0, True),
    ("blood_glucose", 40000.0, False),
    ("blood_glucose", 2600.0, True),
    ("blood_glucose", 20.0, True),
    ("blood_glucose", 0.0, False),
    ("hba1c", 14.0, True),
    ("hba1c", 48.0, False),
    ("hba1c", 0.0, False),
    ("hemoglobin", 2.0, True),
    ("hemoglobin", 24.0, True),
    ("hemoglobin", 142.0, False),
    ("creatinine", 15.0, True),
    ("creatinine", 884.0, False),
    ("creatinine", 0.0, False),
    ("cholesterol", 800.0, True),
    ("cholesterol", 25.0, True),
    ("cholesterol", 19000.0, False),
    ("triglycerides", 15000.0, True),
    ("triglycerides", 100000.0, False),
    ("vitamin_d", 0.0, True),
    ("vitamin_d", 150.0, True),
    ("vitamin_d", 5000.0, False),
    ("vitamin_b12", 20000.0, True),
    ("vitamin_b12", 900000.0, False),
    ("bmi", 10.0, True),
    ("bmi", 185.0, True),
    ("bmi", 5000.0, False),
    ("age", 0.0, True),
    ("age", 122.0, True),
    ("age", 900.0, False),
    ("age", -1.0, False),
]


@pytest.mark.parametrize("feature,value,possible", BAND_CASES)
def test_possible_band_separates_real_extremes_from_extraction_errors(
    feature, value, possible
):
    rule = RULES[feature]
    inside = rule.possible_low <= value <= rule.possible_high
    assert inside is possible


def test_glucose_400_is_extreme_but_not_impossible():
    rule = RULES["blood_glucose"]
    assert rule.possible_low <= 400.0 <= rule.possible_high
    assert 400.0 >= rule.extreme_high
    assert 40000.0 > rule.possible_high


def test_extreme_thresholds_do_not_reject_merely_abnormal_values():
    for feature, value in [
        ("hba1c", 9.0),
        ("blood_glucose", 250.0),
        ("hemoglobin", 9.5),
        ("creatinine", 2.2),
        ("cholesterol", 260.0),
        ("triglycerides", 350.0),
        ("vitamin_d", 12.0),
        ("bmi", 34.0),
    ]:
        rule = RULES[feature]
        assert rule.possible_low <= value <= rule.possible_high


def test_clinically_extreme_is_not_a_questionable_flag():
    assert FlagCode.CLINICALLY_EXTREME_LOW not in QUESTIONABLE_FLAGS
    assert FlagCode.CLINICALLY_EXTREME_HIGH not in QUESTIONABLE_FLAGS


def test_questionable_flags_are_the_confidence_signals():
    assert set(QUESTIONABLE_FLAGS) == {
        FlagCode.UNIT_ASSUMED,
        FlagCode.CENSORED_VALUE,
        FlagCode.DERIVED_VALUE,
        FlagCode.LOW_EXTRACTION_CONFIDENCE,
        FlagCode.PARTIAL_DOCUMENT,
    }


def test_rejection_codes_are_unique_strings():
    codes = [v for k, v in vars(RejectionCode).items() if not k.startswith("_")]
    assert len(codes) == len(set(codes))
    assert all(isinstance(c, str) and c.isupper() for c in codes)


def test_rules_document_is_serialisable_and_complete():
    document = rules_document()
    assert set(document["features"]) == set(FEATURES)
    assert document["low_confidence_threshold"] == LOW_CONFIDENCE_THRESHOLD
    glucose = document["features"]["blood_glucose"]
    assert glucose["possible_high"] == RULES["blood_glucose"].possible_high
    assert glucose["extreme_high"] == RULES["blood_glucose"].extreme_high
    assert glucose["basis"]
    assert "possible" in document["band_semantics"]
    assert "extreme" in document["band_semantics"]


def test_categorical_rules_expose_the_module_2_vocabularies():
    document = rules_document()
    assert set(document["features"]["gender"]["categories"]) == {
        "male",
        "female",
        "other",
        "prefer_not_to_say",
    }
    assert set(document["features"]["smoking_history"]["categories"]) == {
        "never",
        "former",
        "current",
        "ever",
        "not_current",
        "no_info",
    }
