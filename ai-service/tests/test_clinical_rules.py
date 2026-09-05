"""The clinical rule table (app/data/clinical_rules.py) as a DATA artefact.

These tests check the table's integrity -- that it agrees with the feature
catalog, that every threshold cites a basis, that its import-time self-check is
real. Threshold BEHAVIOUR (each rule on both sides of, and exactly on, its
threshold) is exercised in tests/test_rule_engine.py against the engine.
"""

from __future__ import annotations

import dataclasses

import pytest

from app.data import clinical_rules as cr
from app.data import conditions as C
from app.data.feature_catalog import FEATURES
from app.data.recommendation_catalog import is_known_code
from app.schemas.decisions import DecisionStatus, RiskLevel


def all_rules():
    return list(cr.THRESHOLD_RULES) + list(cr.COMPOSITE_RULES)


# --------------------------------------------------------------------------
# Agreement with the rest of the system
# --------------------------------------------------------------------------


def test_every_rule_targets_a_canonical_numeric_feature():
    for rule in cr.THRESHOLD_RULES:
        assert rule.feature in FEATURES, rule.id
        assert FEATURES[rule.feature].value_type in ("number", "integer"), rule.id


def test_every_composite_factor_targets_a_catalog_feature():
    for rule in cr.COMPOSITE_RULES:
        for factor in rule.factors:
            assert factor.feature in FEATURES, factor.id


def test_smoking_categories_come_from_the_catalog_vocabulary():
    allowed = set(FEATURES["smoking_history"].categories)
    for rule in cr.COMPOSITE_RULES:
        for factor in rule.factors:
            if factor.kind == cr.FACTOR_CATEGORY:
                assert set(factor.categories) <= allowed, factor.id


def test_tri_state_features_are_only_ever_read_as_boolean_true():
    """Absent must never be readable as a stated negative."""
    for rule in cr.COMPOSITE_RULES:
        for factor in rule.factors:
            if FEATURES[factor.feature].value_type == "boolean":
                assert factor.kind == cr.FACTOR_BOOLEAN_TRUE, factor.id


def test_rule_ids_are_unique():
    ids = [rule.id for rule in all_rules()]
    assert len(set(ids)) == len(ids)


def test_the_spec_named_features_are_all_covered_by_some_rule():
    covered = {rule.feature for rule in cr.THRESHOLD_RULES}
    for rule in cr.COMPOSITE_RULES:
        covered.update(factor.feature for factor in rule.factors)
    for name in (
        "hba1c",
        "blood_glucose",
        "hemoglobin",
        "vitamin_d",
        "vitamin_b12",
        "creatinine",
        "cholesterol",
        "triglycerides",
        "age",
        "gender",
        "bmi",
        "hypertension",
        "heart_disease",
        "smoking_history",
    ):
        if name == "gender":
            # Read as CONTEXT for sex-specific thresholds, not as a rule target.
            assert any(
                "gender" in rule.context_features for rule in cr.THRESHOLD_RULES
            )
            continue
        assert name in covered, name


# --------------------------------------------------------------------------
# Every threshold cites a basis
# --------------------------------------------------------------------------


def test_every_rule_and_every_band_cites_a_clinical_basis():
    for rule in all_rules():
        assert rule.basis.strip(), rule.id
        for band in rule.bands:
            assert band.basis.strip(), rule.id
            assert band.label.strip(), rule.id


def test_every_band_recommendation_resolves_to_the_catalogue():
    for rule in all_rules():
        for band in rule.bands:
            for code in band.recommendations:
                assert is_known_code(code), (rule.id, code)
        for code in rule.always_recommend:
            assert is_known_code(code), (rule.id, code)


def test_no_band_is_insufficient_data():
    """A band ran a comparison, so it assessed something. Only the ENGINE may
    emit INSUFFICIENT_DATA, and only when it had nothing to compare."""
    for rule in all_rules():
        for band in rule.bands:
            assert band.status is not DecisionStatus.INSUFFICIENT_DATA
            assert band.risk is not None


def test_each_threshold_rule_ends_with_an_always_matching_band():
    for rule in cr.THRESHOLD_RULES:
        assert rule.bands[-1].comparator is None, rule.id
        assert rule.bands[-1].threshold is None, rule.id
        for band in rule.bands[:-1]:
            assert band.comparator in cr.COMPARATORS, rule.id


def test_bands_are_ordered_most_severe_first():
    severity = {RiskLevel.HIGH: 0, RiskLevel.MEDIUM: 1, RiskLevel.LOW: 2}
    for rule in cr.THRESHOLD_RULES:
        ranks = [severity[band.risk] for band in rule.bands]
        assert ranks == sorted(ranks), rule.id


# --------------------------------------------------------------------------
# Contextual thresholds
# --------------------------------------------------------------------------


def test_unknown_sex_threshold_is_always_one_of_the_two_known_ones():
    for rule in cr.THRESHOLD_RULES:
        for band in rule.bands:
            threshold = band.threshold
            if isinstance(threshold, cr.ContextualThreshold):
                assert threshold.unknown in (threshold.male, threshold.female)


def test_resolve_threshold_picks_the_recorded_sex():
    threshold = cr.ANEMIA_CUTOFF
    assert cr.resolve_threshold(threshold, "male", 30)[0] == 13.0
    assert cr.resolve_threshold(threshold, "female", 30)[0] == 12.0


def test_resolve_threshold_explains_itself_when_sex_is_unknown():
    value, note = cr.resolve_threshold(cr.ANEMIA_CUTOFF, None, 30)
    assert value == 12.0
    assert note and "sex was not recorded" in note


def test_resolve_threshold_applies_paediatric_bands_before_sex():
    assert cr.resolve_threshold(cr.ANEMIA_CUTOFF, "male", 3)[0] == 11.0
    assert cr.resolve_threshold(cr.ANEMIA_CUTOFF, "male", 8)[0] == 11.5
    assert cr.resolve_threshold(cr.ANEMIA_CUTOFF, "male", 13)[0] == 12.0
    assert cr.resolve_threshold(cr.ANEMIA_CUTOFF, "male", 15)[0] == 13.0


def test_resolve_threshold_passes_a_plain_number_through():
    assert cr.resolve_threshold(6.5, None, None) == (6.5, None)
    assert cr.resolve_threshold(None, None, None) == (None, None)


# --------------------------------------------------------------------------
# Sample timing
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name,expected",
    [
        ("Fasting Blood Sugar", cr.TIMING_FASTING),
        ("FBS", cr.TIMING_FASTING),
        ("Fasting Plasma Glucose", cr.TIMING_FASTING),
        ("Random Blood Sugar", cr.TIMING_RANDOM),
        ("RBS", cr.TIMING_RANDOM),
        ("Post Prandial Glucose", cr.TIMING_POST_PRANDIAL),
        ("PPBS", cr.TIMING_POST_PRANDIAL),
        ("Glucose PP", cr.TIMING_POST_PRANDIAL),
        ("Glucose", cr.TIMING_UNSPECIFIED),
        ("Blood Sugar", cr.TIMING_UNSPECIFIED),
        ("", cr.TIMING_UNSPECIFIED),
        (None, cr.TIMING_UNSPECIFIED),
    ],
)
def test_sample_timing_is_never_guessed_as_fasting(name, expected):
    assert cr.sample_timing(name) == expected


# --------------------------------------------------------------------------
# The import-time self-check is real
# --------------------------------------------------------------------------


def test_self_check_rejects_a_rule_on_an_unknown_feature(monkeypatch):
    broken = dataclasses.replace(cr.THRESHOLD_RULES[0], feature="unicorn_count")
    monkeypatch.setattr(cr, "THRESHOLD_RULES", (broken,))
    with pytest.raises(ValueError, match="canonical feature"):
        cr._self_check()


def test_self_check_rejects_a_non_canonical_condition(monkeypatch):
    broken = dataclasses.replace(cr.THRESHOLD_RULES[0], condition="Diabetes Mellitus")
    monkeypatch.setattr(cr, "THRESHOLD_RULES", (broken,))
    with pytest.raises(ValueError, match="conditions.py"):
        cr._self_check()


def test_self_check_rejects_a_rule_with_no_fallback_band(monkeypatch):
    rule = cr.THRESHOLD_RULES[0]
    broken = dataclasses.replace(rule, bands=rule.bands[:-1])
    monkeypatch.setattr(cr, "THRESHOLD_RULES", (broken,))
    with pytest.raises(ValueError, match="always-matching"):
        cr._self_check()


def test_self_check_rejects_an_unknown_recommendation_code(monkeypatch):
    rule = cr.THRESHOLD_RULES[0]
    band = dataclasses.replace(rule.bands[0], recommendations=("MADE_UP_CODE",))
    broken = dataclasses.replace(rule, bands=(band,) + rule.bands[1:])
    monkeypatch.setattr(cr, "THRESHOLD_RULES", (broken,))
    with pytest.raises(ValueError, match="recommendation code"):
        cr._self_check()


def test_self_check_rejects_an_unsafe_band_label(monkeypatch):
    from app.data.recommendation_catalog import UnsafeRecommendationError

    rule = cr.THRESHOLD_RULES[0]
    band = dataclasses.replace(rule.bands[0], label="start metformin 500 mg daily")
    broken = dataclasses.replace(rule, bands=(band,) + rule.bands[1:])
    monkeypatch.setattr(cr, "THRESHOLD_RULES", (broken,))
    with pytest.raises(UnsafeRecommendationError):
        cr._self_check()


def test_condition_inputs_is_derived_and_covers_every_always_assessed_condition():
    for condition in C.ALWAYS_ASSESSED_CONDITIONS:
        assert cr.CONDITION_INPUTS[condition], condition
    assert cr.CONDITION_INPUTS[C.DIABETES] == ("hba1c", "blood_glucose")


def test_rules_document_round_trips_to_json():
    import json

    document = cr.rules_document()
    assert json.loads(json.dumps(document))["rule_table_version"] == (
        cr.RULE_TABLE_VERSION
    )
    ids = {entry["id"] for entry in document["threshold_rules"]}
    assert ids == {rule.id for rule in cr.THRESHOLD_RULES}


def test_rule_by_id_finds_both_kinds_and_returns_none_otherwise():
    assert cr.rule_by_id("RULE_DIABETES_HBA1C") is not None
    assert cr.rule_by_id(cr.HEART_DISEASE_RULE.id) is cr.HEART_DISEASE_RULE
    assert cr.rule_by_id("NOPE") is None
