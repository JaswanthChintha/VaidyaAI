"""Module 8 -- the Clinical Rule Engine, exercised through `evaluate_rules()`.

The framework-independent entry point, which is what Module 15 will call.

Covered here: every rule on both sides of, and EXACTLY ON, each of its
thresholds; rules not firing on missing inputs; an absent tri-state never being
read as a negative; rejected features never reaching a comparison; questionable
inputs surfacing in the decision; evidence completeness; risk ordering;
confidence=None; recommendation resolution; JSON round-tripping; warning
propagation with origins; and a realistic end-to-end feature set.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import pytest

from app.data import clinical_rules as cr
from app.data import conditions as C
from app.data import recommendation_catalog as rcat
from app.data.feature_catalog import FEATURES
from app.schemas.decisions import ClinicalDecision, DecisionSourceKind, DecisionStatus, RiskLevel
from app.schemas.rules import ValidatedFeaturesInput
from app.services import rule_engine as engine
from app.services.rule_engine import evaluate_rules

# --------------------------------------------------------------------------
# Builders
# --------------------------------------------------------------------------


def vf(
    name: str,
    value: Any,
    *,
    questionable: bool = False,
    extreme: bool = False,
    direction: Optional[str] = None,
    test_name: Optional[str] = None,
    source: Optional[str] = None,
    reference_low: Optional[float] = None,
    reference_high: Optional[float] = None,
) -> Dict[str, Any]:
    """One entry of Module 6's `valid` map."""
    definition = FEATURES[name]
    stage = source or definition.source
    provenance: Dict[str, Any] = {"source": stage}
    if test_name:
        provenance["original_test_name"] = test_name
    if reference_low is not None:
        provenance["reference_low"] = reference_low
    if reference_high is not None:
        provenance["reference_high"] = reference_high
    return {
        "name": name,
        "value": value,
        "unit": definition.canonical_unit,
        "canonical_unit": True,
        "source": stage,
        "provenance": provenance,
        "status": "questionable" if questionable else "valid",
        "questionable": questionable,
        "clinically_extreme": extreme,
        "extreme_direction": direction,
    }


def validated(features: Optional[Dict[str, Any]] = None, **overrides: Any) -> Dict[str, Any]:
    """Module 6's `data` object."""
    features = features or {}
    payload: Dict[str, Any] = {
        "valid": features,
        "questionable": {k: v for k, v in features.items() if v["questionable"]},
        "rejected": {},
        "clinically_extreme": [k for k, v in features.items() if v["clinically_extreme"]],
        "missing_features": [],
        "unmapped": [],
        "warnings": [],
        "upstream_warnings": [],
        "all_warnings": [],
        "upstream": {"provided": True},
        "summary": {},
    }
    payload.update(overrides)
    return payload


def for_rule(data: Any, rule_id: str) -> Optional[ClinicalDecision]:
    for decision in data.decisions:
        if decision.metadata.get("rule_id") == rule_id:
            return decision
    return None


def for_condition(data: Any, condition: str) -> List[ClinicalDecision]:
    return [d for d in data.decisions if d.condition == condition]


#: Printed test names needed to satisfy each rule's sample-timing gate.
RULE_TEST_NAME = {
    "RULE_DIABETES_GLUCOSE_FASTING": "Fasting Blood Sugar",
    "RULE_DIABETES_GLUCOSE_UNSPECIFIED": "Glucose",
    "RULE_HYPOGLYCEMIA_GLUCOSE": "Glucose",
}


def fire(rule: cr.ThresholdRule, value: float, sex: Optional[str] = None, age: float = 40):
    features = {
        rule.feature: vf(rule.feature, value, test_name=RULE_TEST_NAME.get(rule.id))
    }
    if sex is not None:
        features["gender"] = vf("gender", sex)
    if age is not None and rule.feature != "age":
        features["age"] = vf("age", age)
    return for_rule(evaluate_rules(validated(features)), rule.id)


# --------------------------------------------------------------------------
# THRESHOLD BOUNDARIES -- every rule, every band, exactly on and either side
# --------------------------------------------------------------------------


def _boundary_cases():
    cases = []
    for rule in cr.THRESHOLD_RULES:
        contextual = any(
            isinstance(band.threshold, cr.ContextualThreshold) for band in rule.bands
        )
        for index, band in enumerate(rule.bands[:-1]):
            if band.only_when_sex_unknown:
                sexes = [None]
            elif contextual:
                sexes = ["male", "female", None]
            else:
                sexes = [None]
            for sex in sexes:
                cases.append(
                    pytest.param(
                        rule,
                        band,
                        sex,
                        id=f"{rule.id}-band{index}-{sex or 'unknownsex'}",
                    )
                )
    return cases


@pytest.mark.parametrize("rule,band,sex", _boundary_cases())
def test_band_fires_exactly_as_its_comparator_says(rule, band, sex):
    threshold, _ = cr.resolve_threshold(band.threshold, sex, 40)
    assert threshold is not None
    epsilon = 0.01

    on_threshold = fire(rule, threshold, sex)
    assert on_threshold is not None, "the rule did not fire at all"
    inclusive = band.comparator in (">=", "<=")
    if inclusive:
        assert on_threshold.metadata["band_label"] == band.label
        assert on_threshold.metadata["threshold"] == threshold
        assert on_threshold.metadata["comparator"] == band.comparator
    else:
        assert on_threshold.metadata["band_label"] != band.label

    if band.comparator in (">=", ">"):
        inside, outside = threshold + epsilon, threshold - epsilon
    else:
        inside, outside = threshold - epsilon, threshold + epsilon

    assert fire(rule, inside, sex).metadata["band_label"] == band.label
    assert fire(rule, outside, sex).metadata["band_label"] != band.label


def test_the_ada_hba1c_thresholds_are_the_ones_the_brief_named():
    assert fire(cr.rule_by_id("RULE_DIABETES_HBA1C"), 6.5).status is (
        DecisionStatus.INDICATED
    )
    assert fire(cr.rule_by_id("RULE_DIABETES_HBA1C"), 5.7).status is (
        DecisionStatus.BORDERLINE
    )
    assert fire(cr.rule_by_id("RULE_DIABETES_HBA1C"), 5.69).status is (
        DecisionStatus.NOT_INDICATED
    )


# --------------------------------------------------------------------------
# MISSING DATA MUST NEVER READ AS NORMAL
# --------------------------------------------------------------------------


def test_a_rule_with_no_input_does_not_fire_at_all():
    data = evaluate_rules(validated({"hba1c": vf("hba1c", 5.0)}))
    # No vitamin D was measured, so the THRESHOLD RULE never fires...
    assert for_rule(data, "RULE_VITAMIN_D_DEFICIENCY") is None
    # ...but the topic is still accounted for, as an absence and never as a
    # finding. A rule that did not fire and a topic nobody looked at are two
    # different things, and only the second one reaches the reader.
    decisions = for_condition(data, C.VITAMIN_D_DEFICIENCY)
    assert len(decisions) == 1
    assert decisions[0].status is DecisionStatus.INSUFFICIENT_DATA
    assert decisions[0].risk is None


def test_absent_inputs_never_produce_a_not_indicated_decision():
    data = evaluate_rules(validated({}))
    for decision in data.decisions:
        assert decision.status is DecisionStatus.INSUFFICIENT_DATA
        assert decision.risk is None


def test_the_three_fusion_conditions_are_always_mentioned():
    data = evaluate_rules(validated({}))
    for condition in C.FUSION_CONDITIONS:
        assert for_condition(data, condition), condition


def test_insufficient_data_names_the_inputs_it_lacked():
    data = evaluate_rules(validated({}))
    kidney = for_condition(data, C.KIDNEY_DISEASE)[0]
    assert kidney.status is DecisionStatus.INSUFFICIENT_DATA
    assert kidney.evidence_features() == ["creatinine"]
    assert kidney.evidence[0].value is None
    assert rcat.INFORMATION_INCOMPLETE in [r.code for r in kidney.recommendations]


def test_empty_input_raises_a_rules_stage_warning():
    data = evaluate_rules(validated({}))
    assert any("no usable features" in w for w in data.warnings)


# --------------------------------------------------------------------------
# TRI-STATE BOOLEANS -- absent is never a stated negative
# --------------------------------------------------------------------------


def _cvd_features(**extra: Any) -> Dict[str, Any]:
    features = {
        "cholesterol": vf("cholesterol", 250.0),
        "bmi": vf("bmi", 31.0),
        "age": vf("age", 60),
        "gender": vf("gender", "male"),
    }
    features.update(extra)
    return features


def test_absent_hypertension_is_reported_as_missing_not_as_false():
    data = evaluate_rules(validated(_cvd_features()))
    heart = for_rule(data, cr.HEART_DISEASE_RULE.id)
    assert "hypertension" in heart.metadata["features_missing"]
    assert "hypertension" not in heart.metadata["factors_evaluable"]
    item = next(e for e in heart.evidence if e.feature == "hypertension")
    assert item.value is None
    assert item.note == engine.NOTE_NOT_AVAILABLE


# --------------------------------------------------------------------------
# A POST-LOAD THRESHOLD ON A SAMPLE NOBODY ESTABLISHED AS FASTING
# --------------------------------------------------------------------------
#
# The clinician page showed, for Test 3 on 2026-09-18:
#
#     RANDOM BLOOD GLUCOSE ( RBS ) was 168 mg/dl (>= 140, at or above the
#     2-hour post-load impaired-glucose-tolerance boundary of 140 mg/dL)
#
# A clinician reading that would reasonably take it for a post-load draw. It
# was a random sample, and the rule's own `basis` says the uncertainty "is
# stated to the reader via DISCUSS_SAMPLE_TIMING".
#
# THAT CLAIM IS TRUE ON THE PATIENT PAGE -- the recommendation renders there,
# checked live. The CLINICIAN page carries no recommendations at all, so the
# qualification went in the BAND LABEL instead, where it reaches every reader.
#
# WHAT MAKES THE LABEL HONEST is `only_timing`: this rule fires ONLY for
# unspecified, random and post-prandial samples, so "not established as
# fasting" is true of every band on it. The first test below pins that
# invariant, because the label becomes a lie the moment it stops holding.

_NOT_FASTING_PHRASE = "not established as fasting"


def test_the_unspecified_glucose_rule_never_sees_a_fasting_sample():
    """THE INVARIANT THE BAND LABELS REST ON.

    If `TIMING_FASTING` were ever added to this rule, every band would start
    claiming a sample was not established as fasting when it was.
    """
    rule = next(
        r for r in cr.THRESHOLD_RULES if r.id == "RULE_DIABETES_GLUCOSE_UNSPECIFIED"
    )
    assert rule.only_timing
    assert cr.TIMING_FASTING not in rule.only_timing


def test_every_band_of_that_rule_says_the_sample_was_not_established_as_fasting():
    rule = next(
        r for r in cr.THRESHOLD_RULES if r.id == "RULE_DIABETES_GLUCOSE_UNSPECIFIED"
    )
    for band in rule.bands:
        assert _NOT_FASTING_PHRASE in band.label, band.label


def test_the_FASTING_glucose_rule_does_not_carry_the_phrase():
    """No over-reach: on a fasting sample the qualification would be false."""
    rule = next(
        r for r in cr.THRESHOLD_RULES if r.id == "RULE_DIABETES_GLUCOSE_FASTING"
    )
    for band in rule.bands:
        assert _NOT_FASTING_PHRASE not in band.label, band.label


def test_a_random_glucose_reaches_the_reader_with_the_timing_qualification():
    """END TO END through the engine, not just the table.

    The classification is what the clinician page and the narrative both
    print, so this is the assertion that matches what a reader sees.
    """
    # THE TIMING IS DERIVED FROM THE PRINTED TEST NAME, not from a field --
    # `sample_timing(original_test_name, matched_synonym)`. Driven the way the
    # producer does it, with the name Test 3 actually prints.
    data = evaluate_rules(
        validated(
            {
                "blood_glucose": vf(
                    "blood_glucose",
                    168.0,
                    test_name="RANDOM BLOOD GLUCOSE ( RBS )",
                )
            }
        )
    )
    diabetes = [d for d in data.decisions if d.condition == C.DIABETES]
    assert diabetes, "the unspecified-timing glucose rule did not fire"
    notes = " ".join(
        e.note or "" for d in diabetes for e in d.evidence
    ) + " ".join(str(d.metadata.get("band_label", "")) for d in diabetes)
    assert _NOT_FASTING_PHRASE in notes


# --------------------------------------------------------------------------
# A CRITERION THAT WAS NOT MET MUST NOT READ AS ONE THAT WAS
# --------------------------------------------------------------------------
#
# FOUND IN STORED EVIDENCE ON A REAL REPORT, 2026-09-18. `factor.label` states
# the TEST, not the result, and it was emitted bare whether or not the factor
# held. Heart Disease on Test 3 carried three lines, all three false:
#
#     bmi 25.25       -> "body mass index at or above 30.0; present, but not
#                         counted as a cardiovascular risk factor"
#     age 20          -> "age at or above the sex-specific cardiovascular age
#                         threshold; present, but not counted..."
#     smoking never   -> "current or lifetime smoking recorded in the patient
#                         profile; present, but not counted..."
#
# The patient is 20, has a BMI of 25.25 and has never smoked. None of it
# reached a screen -- the dashboard was checked -- but it sits in the evidence
# Module 32 builds from.


def test_a_factor_that_was_not_met_says_so_instead_of_stating_its_threshold():
    data = evaluate_rules(
        validated(_cvd_features(bmi=vf("bmi", 25.25), age=vf("age", 20)))
    )
    heart = for_rule(data, cr.HEART_DISEASE_RULE.id)

    item = next(e for e in heart.evidence if e.feature == "bmi")
    assert item.value == 25.25
    # THE METADATA IS KEYED ON FACTOR ID, NOT FEATURE NAME -- BMI's factor is
    # `obesity`. Read off the real payload after asserting the wrong key here.
    assert "obesity" in heart.metadata["factors_evaluable"]
    assert "obesity" not in heart.metadata["factors_counted"]

    # THE DEFECT, DIRECTLY: the bare criterion must not stand as a statement.
    assert not item.note.startswith("body mass index at or above 30.0")
    assert item.note.startswith(engine.NOTE_FACTOR_NOT_MET)
    assert "body mass index at or above 30.0" in item.note
    assert engine.NOTE_FACTOR_NOT_COUNTED in item.note


def test_a_factor_that_WAS_met_still_states_the_criterion_plainly():
    """The ANSWERING branch. A criterion that holds IS a finding about the
    patient, and prefixing it would make a true line read as a refusal."""
    data = evaluate_rules(validated(_cvd_features()))  # bmi 31.0, age 60
    heart = for_rule(data, cr.HEART_DISEASE_RULE.id)

    item = next(e for e in heart.evidence if e.feature == "bmi")
    assert "obesity" in heart.metadata["factors_counted"]
    assert item.note.startswith("body mass index at or above 30.0")
    assert engine.NOTE_FACTOR_NOT_MET not in item.note
    assert engine.NOTE_FACTOR_COUNTED in item.note


def test_the_word_present_is_gone_from_the_not_counted_note():
    """`present` meant "the value was available" and read as "the risk factor
    is present" -- the same collapse one word smaller."""
    assert "present" not in engine.NOTE_FACTOR_NOT_COUNTED


@pytest.mark.parametrize("factor", cr.HEART_DISEASE_RULE.factors, ids=lambda f: f.id)
def test_no_factor_label_can_stand_alone_as_a_statement_when_unmet(factor):
    """EVERY label, not the three that happened to be wrong on one report.

    Gathered from the rule itself so a factor added later is covered without
    anyone remembering to extend this test.
    """
    unmet = f"{engine.NOTE_FACTOR_NOT_MET}{factor.label}"
    assert unmet.startswith(engine.NOTE_FACTOR_NOT_MET)
    assert not unmet.startswith(factor.label)


def test_an_absent_feature_still_uses_the_ABSENT_note_and_not_this_one():
    """The two are different claims and must stay different branches.

    "not supplied" and "supplied and did not meet the threshold" are the
    tri-state distinction this rule's own docstring promises to keep.
    """
    data = evaluate_rules(validated(_cvd_features()))
    heart = for_rule(data, cr.HEART_DISEASE_RULE.id)
    item = next(e for e in heart.evidence if e.feature == "hypertension")
    assert item.note == engine.NOTE_NOT_AVAILABLE
    assert engine.NOTE_FACTOR_NOT_MET not in item.note


def test_explicit_false_hypertension_is_evaluable_but_not_counted():
    data = evaluate_rules(
        validated(_cvd_features(hypertension=vf("hypertension", False)))
    )
    heart = for_rule(data, cr.HEART_DISEASE_RULE.id)
    assert "hypertension" not in heart.metadata["features_missing"]
    assert "hypertension" in heart.metadata["factors_evaluable"]
    assert "hypertension" not in heart.metadata["factors_counted"]
    item = next(e for e in heart.evidence if e.feature == "hypertension")
    assert item.value is False


def test_absent_and_false_tri_states_produce_the_same_factor_count():
    """Neither may be read as evidence for the other."""
    absent = for_rule(
        evaluate_rules(validated(_cvd_features())), cr.HEART_DISEASE_RULE.id
    )
    explicit = for_rule(
        evaluate_rules(validated(_cvd_features(hypertension=vf("hypertension", False)))),
        cr.HEART_DISEASE_RULE.id,
    )
    assert absent.metadata["factor_count"] == explicit.metadata["factor_count"]


def test_true_hypertension_adds_a_factor():
    without = for_rule(
        evaluate_rules(validated(_cvd_features())), cr.HEART_DISEASE_RULE.id
    )
    with_htn = for_rule(
        evaluate_rules(validated(_cvd_features(hypertension=vf("hypertension", True)))),
        cr.HEART_DISEASE_RULE.id,
    )
    assert with_htn.metadata["factor_count"] == without.metadata["factor_count"] + 1
    assert "hypertension" in with_htn.metadata["factors_counted"]


def test_known_heart_disease_is_surfaced_regardless_of_the_count():
    data = evaluate_rules(
        validated(
            {
                "heart_disease": vf("heart_disease", True),
                "age": vf("age", 30),
                "gender": vf("gender", "female"),
                "bmi": vf("bmi", 22.0),
            }
        )
    )
    heart = for_rule(data, cr.HEART_DISEASE_RULE.id)
    assert heart.status is DecisionStatus.INDICATED
    assert heart.risk is RiskLevel.HIGH


def test_smoking_no_info_and_not_current_are_not_counted():
    for token in ("no_info", "not_current", "never", "former"):
        data = evaluate_rules(
            validated(_cvd_features(smoking_history=vf("smoking_history", token)))
        )
        heart = for_rule(data, cr.HEART_DISEASE_RULE.id)
        assert "smoking" not in heart.metadata["factors_counted"], token
    for token in ("current", "ever"):
        data = evaluate_rules(
            validated(_cvd_features(smoking_history=vf("smoking_history", token)))
        )
        heart = for_rule(data, cr.HEART_DISEASE_RULE.id)
        assert "smoking" in heart.metadata["factors_counted"], token


def test_too_few_inputs_gives_insufficient_data_rather_than_a_low_count():
    data = evaluate_rules(
        validated({"bmi": vf("bmi", 22.0), "age": vf("age", 30)})
    )
    heart = for_rule(data, cr.HEART_DISEASE_RULE.id)
    assert heart.status is DecisionStatus.INSUFFICIENT_DATA
    assert heart.risk is None
    assert heart.metadata["skipped_reason"] == "insufficient_inputs"


# --------------------------------------------------------------------------
# REJECTED FEATURES ARE NEVER CONSUMED
# --------------------------------------------------------------------------


def test_the_input_schema_has_no_rejected_field():
    """The guarantee is structural: there is no attribute to read."""
    assert "rejected" not in ValidatedFeaturesInput.model_fields


def test_a_rejected_feature_never_reaches_a_rule():
    payload = validated(
        {},
        rejected={
            "hba1c": {
                "name": "hba1c",
                "value": 40.0,
                "reason_code": "IMPLAUSIBLE_VALUE_HIGH",
                "reason": "above the possible band",
            }
        },
    )
    data = evaluate_rules(payload)
    diabetes = for_condition(data, C.DIABETES)
    assert len(diabetes) == 1
    assert diabetes[0].status is DecisionStatus.INSUFFICIENT_DATA
    for decision in data.decisions:
        for item in decision.evidence:
            assert item.value != 40.0


def test_a_valid_feature_is_used_even_when_another_was_rejected():
    payload = validated(
        {"hba1c": vf("hba1c", 7.2)},
        rejected={"creatinine": {"name": "creatinine", "value": 900.0,
                                 "reason_code": "IMPLAUSIBLE_VALUE_HIGH",
                                 "reason": "above the possible band"}},
    )
    data = evaluate_rules(payload)
    assert for_rule(data, "RULE_DIABETES_HBA1C").status is DecisionStatus.INDICATED
    kidney = for_condition(data, C.KIDNEY_DISEASE)[0]
    assert kidney.status is DecisionStatus.INSUFFICIENT_DATA


# --------------------------------------------------------------------------
# QUESTIONABLE AND CLINICALLY EXTREME
# --------------------------------------------------------------------------


def test_a_questionable_input_is_surfaced_in_the_decision():
    data = evaluate_rules(validated({"hba1c": vf("hba1c", 7.2, questionable=True)}))
    decision = for_rule(data, "RULE_DIABETES_HBA1C")
    assert decision.metadata["questionable_inputs"] == ["hba1c"]
    assert rcat.INPUT_QUALITY_CAVEAT in [r.code for r in decision.recommendations]
    assert engine.NOTE_QUESTIONABLE in decision.evidence[0].note
    assert data.summary.questionable_features_used == ["hba1c"]


def test_a_solid_input_carries_no_quality_caveat():
    data = evaluate_rules(validated({"hba1c": vf("hba1c", 7.2)}))
    decision = for_rule(data, "RULE_DIABETES_HBA1C")
    assert decision.metadata["questionable_inputs"] == []
    assert rcat.INPUT_QUALITY_CAVEAT not in [r.code for r in decision.recommendations]


def test_clinically_extreme_is_a_priority_signal_and_never_a_doubt():
    features = {
        "blood_glucose": vf(
            "blood_glucose", 450.0, extreme=True, direction="high", test_name="Glucose"
        )
    }
    data = evaluate_rules(validated(features))
    decision = for_rule(data, "RULE_DIABETES_GLUCOSE_UNSPECIFIED")
    # The value is used at full strength: still INDICATED, still HIGH risk.
    assert decision.status is DecisionStatus.INDICATED
    assert decision.risk is RiskLevel.HIGH
    assert decision.metadata["clinically_extreme_inputs"] == ["blood_glucose"]
    assert engine.NOTE_EXTREME_HIGH in decision.evidence[0].note
    assert data.summary.clinically_extreme_features_used == ["blood_glucose"]
    # And it is NOT treated as a questionable input.
    assert rcat.INPUT_QUALITY_CAVEAT not in [r.code for r in decision.recommendations]


# --------------------------------------------------------------------------
# SAMPLE TIMING
# --------------------------------------------------------------------------


def test_fasting_cutoffs_are_applied_only_to_a_fasting_sample():
    fasting = evaluate_rules(
        validated(
            {"blood_glucose": vf("blood_glucose", 130.0, test_name="Fasting Blood Sugar")}
        )
    )
    assert for_rule(fasting, "RULE_DIABETES_GLUCOSE_FASTING").status is (
        DecisionStatus.INDICATED
    )
    assert for_rule(fasting, "RULE_DIABETES_GLUCOSE_UNSPECIFIED") is None

    unspecified = evaluate_rules(
        validated({"blood_glucose": vf("blood_glucose", 130.0, test_name="Glucose")})
    )
    assert for_rule(unspecified, "RULE_DIABETES_GLUCOSE_FASTING") is None
    decision = for_rule(unspecified, "RULE_DIABETES_GLUCOSE_UNSPECIFIED")
    assert decision.status is DecisionStatus.NOT_INDICATED
    assert rcat.DISCUSS_SAMPLE_TIMING in [r.code for r in decision.recommendations]


def test_hypoglycemia_applies_whatever_the_timing():
    for name in ("Fasting Blood Sugar", "Glucose", "Random Blood Sugar"):
        data = evaluate_rules(
            validated({"blood_glucose": vf("blood_glucose", 50.0, test_name=name)})
        )
        decision = for_rule(data, "RULE_HYPOGLYCEMIA_GLUCOSE")
        assert decision.status is DecisionStatus.INDICATED, name
        assert decision.risk is RiskLevel.HIGH


# --------------------------------------------------------------------------
# SEX- AND AGE-SPECIFIC THRESHOLDS
# --------------------------------------------------------------------------


def test_haemoglobin_uses_the_sex_specific_who_cutoff():
    female = evaluate_rules(
        validated({"hemoglobin": vf("hemoglobin", 12.5), "gender": vf("gender", "female")})
    )
    male = evaluate_rules(
        validated({"hemoglobin": vf("hemoglobin", 12.5), "gender": vf("gender", "male")})
    )
    assert for_rule(female, "RULE_ANEMIA_HEMOGLOBIN").status is (
        DecisionStatus.NOT_INDICATED
    )
    assert for_rule(male, "RULE_ANEMIA_HEMOGLOBIN").status is DecisionStatus.INDICATED


def test_unrecorded_sex_gives_a_borderline_zone_and_says_why():
    data = evaluate_rules(validated({"hemoglobin": vf("hemoglobin", 12.5)}))
    decision = for_rule(data, "RULE_ANEMIA_HEMOGLOBIN")
    assert decision.status is DecisionStatus.BORDERLINE
    assert decision.metadata["sex_established"] is False
    assert "sex was not recorded" in decision.evidence[0].note


@pytest.mark.parametrize("gender", ["other", "prefer_not_to_say"])
def test_a_non_binary_gender_is_respected_and_not_coerced(gender):
    data = evaluate_rules(
        validated({"hemoglobin": vf("hemoglobin", 12.5), "gender": vf("gender", gender)})
    )
    decision = for_rule(data, "RULE_ANEMIA_HEMOGLOBIN")
    assert decision.metadata["sex_established"] is False
    assert decision.status is DecisionStatus.BORDERLINE


def _anemia_for_age(value: float, age: int, sex: str = "male"):
    data = evaluate_rules(
        validated(
            {
                "hemoglobin": vf("hemoglobin", value),
                "age": vf("age", age),
                "gender": vf("gender", sex),
            }
        )
    )
    return for_rule(data, "RULE_ANEMIA_HEMOGLOBIN")


def test_paediatric_haemoglobin_cutoffs_are_applied():
    # 11.6 is above the WHO 5-11 year cut-off of 11.5, but below the adult
    # male cut-off of 13.0 -- so the age band, not the sex band, must decide.
    assert _anemia_for_age(11.6, 8).status is DecisionStatus.NOT_INDICATED
    flagged = _anemia_for_age(11.4, 8)
    assert flagged.status is DecisionStatus.INDICATED
    assert flagged.metadata["threshold"] == 11.5
    # The same value in a 15-year-old is judged against the adult male cut-off.
    assert _anemia_for_age(11.6, 15).metadata["threshold"] == 13.0


def test_adult_only_rules_refuse_to_judge_a_child():
    data = evaluate_rules(
        validated({"creatinine": vf("creatinine", 1.8), "age": vf("age", 10)})
    )
    decision = for_rule(data, "RULE_KIDNEY_CREATININE")
    assert decision.status is DecisionStatus.INSUFFICIENT_DATA
    assert decision.risk is None
    assert decision.metadata["skipped_reason"] == "below_minimum_age"


def test_adult_thresholds_are_used_when_age_is_absent():
    data = evaluate_rules(validated({"creatinine": vf("creatinine", 1.8)}))
    decision = for_rule(data, "RULE_KIDNEY_CREATININE")
    assert decision.status is DecisionStatus.INDICATED


# --------------------------------------------------------------------------
# EVIDENCE COMPLETENESS
# --------------------------------------------------------------------------


def test_evidence_names_feature_value_unit_threshold_and_comparator():
    data = evaluate_rules(
        validated({"hba1c": vf("hba1c", 7.4, reference_low=4.0, reference_high=5.6)})
    )
    item = for_rule(data, "RULE_DIABETES_HBA1C").evidence[0]
    assert item.feature == "hba1c"
    assert item.value == 7.4
    assert item.unit == "%"
    assert item.threshold == 6.5
    assert item.comparator == ">="
    assert item.reference_low == 4.0
    assert item.reference_high == 5.6
    assert item.note and "6.5" in item.note
    assert item.source_stage == "lab_report"


def test_every_assessed_decision_carries_at_least_one_evidence_item():
    data = evaluate_rules(validated(REALISTIC_FEATURES()))
    for decision in data.decisions:
        assert decision.evidence, decision.condition


def test_context_features_appear_in_the_evidence_when_they_chose_a_threshold():
    data = evaluate_rules(
        validated({"hemoglobin": vf("hemoglobin", 10.0), "gender": vf("gender", "female")})
    )
    decision = for_rule(data, "RULE_ANEMIA_HEMOGLOBIN")
    assert "gender" in decision.evidence_features()


def test_evidence_dedup_key_is_stable_for_module_16():
    data = evaluate_rules(validated({"hba1c": vf("hba1c", 7.4)}))
    item = for_rule(data, "RULE_DIABETES_HBA1C").evidence[0]
    assert item.dedup_key() == ("hba1c", "7.4", "%", "6.5")


# --------------------------------------------------------------------------
# THE DECISION CONTRACT
# --------------------------------------------------------------------------


def test_every_decision_is_a_clinical_rule_decision_with_no_confidence():
    data = evaluate_rules(validated(REALISTIC_FEATURES()))
    assert data.decisions
    for decision in data.decisions:
        assert decision.source == cr.RULE_ENGINE_SOURCE
        assert decision.source_kind is DecisionSourceKind.CLINICAL_RULE
        # None means "produces no probability". NOT 0.0.
        assert decision.confidence is None
        assert decision.confidence != 0.0


def test_every_decision_uses_a_canonical_condition():
    data = evaluate_rules(validated(REALISTIC_FEATURES()))
    for decision in data.decisions:
        assert C.is_canonical_condition(decision.condition), decision.condition


def test_every_recommendation_resolves_to_a_catalogue_entry():
    data = evaluate_rules(validated(REALISTIC_FEATURES()))
    seen = 0
    for decision in data.decisions:
        for rec in decision.recommendations:
            assert rcat.is_known_code(rec.code), rec.code
            assert rec.text == rcat.RECOMMENDATIONS[rec.code].text
            assert rcat.scan_text(rec.text) == []
            seen += 1
    assert seen > 0


def test_every_decision_carries_the_not_a_diagnosis_recommendation():
    data = evaluate_rules(validated(REALISTIC_FEATURES()))
    for decision in data.decisions:
        codes = [r.code for r in decision.recommendations]
        assert rcat.NOT_A_DIAGNOSIS in codes, decision.condition


def test_metadata_carries_the_rule_id_and_version_and_no_values():
    data = evaluate_rules(validated({"hba1c": vf("hba1c", 7.4)}))
    decision = for_rule(data, "RULE_DIABETES_HBA1C")
    assert decision.metadata["rule_id"] == "RULE_DIABETES_HBA1C"
    assert decision.metadata["rule_version"] == "1.0.0"
    assert decision.metadata["rule_table_version"] == cr.RULE_TABLE_VERSION
    assert decision.metadata["engine_version"] == engine.ENGINE_VERSION


def test_metadata_never_contains_a_measured_value_or_report_text():
    features = REALISTIC_FEATURES()
    measured = {
        v["value"]
        for v in features.values()
        if isinstance(v["value"], (int, float)) and not isinstance(v["value"], bool)
    }
    data = evaluate_rules(validated(features))
    for decision in data.decisions:
        blob = json.dumps(decision.metadata, default=str)
        payload = json.loads(blob)
        thresholds = {decision.metadata.get("threshold")}
        for value in measured:
            # A threshold may legitimately coincide with a value; a value must
            # never appear anywhere else in metadata.
            if value in thresholds:
                continue
            assert f": {value}" not in blob, (decision.condition, value)
        assert "original_test_name" not in payload


# --------------------------------------------------------------------------
# RISK ORDERING
# --------------------------------------------------------------------------


def test_highest_risk_uses_the_types_own_ordering():
    data = evaluate_rules(validated(REALISTIC_FEATURES()))
    risks = [d.risk for d in data.decisions if d.risk is not None]
    assert data.summary.highest_risk == RiskLevel.highest(risks)
    assert data.summary.highest_risk is RiskLevel.HIGH


def test_highest_risk_is_none_when_nothing_could_be_assessed():
    data = evaluate_rules(validated({}))
    # NOT RiskLevel.LOW: "nothing assessed" must never look reassuring.
    assert data.summary.highest_risk is None


def test_risk_levels_compare_as_ordered():
    assert RiskLevel.LOW < RiskLevel.MEDIUM < RiskLevel.HIGH


# --------------------------------------------------------------------------
# WARNING PROPAGATION
# --------------------------------------------------------------------------


UPSTREAM_WARNINGS = [
    {"stage": "extraction", "module": 4, "message": "page 1 was recovered by the PDF repairer"},
    {"stage": "feature_engineering", "module": 5, "message": "unit was assumed for hba1c"},
    {"stage": "validation", "module": 6, "message": "creatinine was rejected"},
]


def test_upstream_warnings_are_carried_through_with_their_origins():
    data = evaluate_rules(
        validated({"hba1c": vf("hba1c", 7.4)}, all_warnings=UPSTREAM_WARNINGS)
    )
    assert [w.stage for w in data.upstream_warnings] == [
        "extraction",
        "feature_engineering",
        "validation",
    ]
    assert [w.module for w in data.upstream_warnings] == [4, 5, 6]
    assert data.all_warnings[:3] == data.upstream_warnings


def test_module_8_warnings_are_appended_under_the_rules_stage():
    data = evaluate_rules(validated({}, all_warnings=UPSTREAM_WARNINGS))
    rules_stage = [w for w in data.all_warnings if w.stage == "rules"]
    assert rules_stage
    assert all(w.module == 8 for w in rules_stage)
    assert {w.message for w in rules_stage} == set(data.warnings)


def test_warnings_are_rebuilt_when_all_warnings_was_not_forwarded():
    data = evaluate_rules(
        validated(
            {"hba1c": vf("hba1c", 5.0)},
            upstream_warnings=UPSTREAM_WARNINGS[:2],
            warnings=["a module 6 message"],
        )
    )
    messages = {w.message for w in data.upstream_warnings}
    assert "page 1 was recovered by the PDF repairer" in messages
    assert "a module 6 message" in messages


def test_upstream_extraction_context_is_preserved():
    data = evaluate_rules(
        validated(
            {"hba1c": vf("hba1c", 5.0)},
            upstream={"provided": True, "extraction_confidence": 0.91, "pages_unreadable": []},
        )
    )
    assert data.upstream.extraction_confidence == 0.91


# --------------------------------------------------------------------------
# PARTIALLY UNREADABLE DOCUMENTS
# --------------------------------------------------------------------------


def test_an_unread_page_turns_absence_into_insufficient_data():
    data = evaluate_rules(
        validated(
            {"hba1c": vf("hba1c", 5.0)},
            upstream={"provided": True, "pages_unreadable": [2]},
        )
    )
    vitamin_d = for_condition(data, C.VITAMIN_D_DEFICIENCY)
    assert len(vitamin_d) == 1
    assert vitamin_d[0].status is DecisionStatus.INSUFFICIENT_DATA
    codes = [r.code for r in vitamin_d[0].recommendations]
    assert rcat.UNREADABLE_DOCUMENT_RECHECK in codes
    assert data.summary.partial_document is True
    assert any("only partially readable" in w for w in data.warnings)


def test_a_fully_read_report_still_reports_the_tests_it_did_not_contain():
    """The defect this replaced a test for.

    This used to assert SILENCE -- a fully-read report lacking vitamin D
    produced no vitamin D decision at all, on the reading that the laboratory
    simply had not ordered it. True about the cause, wrong about the reader: a
    real report produced eight of thirteen topics, `unassessed_condition_count`
    then said 0, and the dashboard offered the eight as though they were the
    whole of what this tool checks.

    An unordered test and an unremarkable one are not the same thing, and the
    difference is the entire subject of this platform.
    """
    data = evaluate_rules(validated({"hba1c": vf("hba1c", 5.0)}))
    assert data.summary.partial_document is False

    decisions = for_condition(data, C.VITAMIN_D_DEFICIENCY)
    assert len(decisions) == 1
    assert decisions[0].status is DecisionStatus.INSUFFICIENT_DATA
    # NEVER a risk level: a topic nobody looked at has no risk to report.
    assert decisions[0].risk is None

    # And still ONE line per missing test -- the secondary reading of the same
    # absent vitamin D stays suppressed even now that the primary is reported.
    assert for_condition(data, C.ELEVATED_VITAMIN_D) == []


def test_secondary_readings_are_not_duplicated_when_unread():
    data = evaluate_rules(
        validated({}, upstream={"provided": True, "pages_unreadable": [1]})
    )
    # One "could not assess" card per missing test, not two.
    assert for_condition(data, C.ELEVATED_VITAMIN_D) == []
    assert len(for_condition(data, C.VITAMIN_D_DEFICIENCY)) == 1


# --------------------------------------------------------------------------
# JSON ROUND TRIP
# --------------------------------------------------------------------------


def test_decisions_survive_a_json_round_trip():
    data = evaluate_rules(validated(REALISTIC_FEATURES()))
    for decision in data.decisions:
        blob = decision.model_dump_json()
        restored = ClinicalDecision.model_validate(json.loads(blob))
        assert restored == decision


def test_the_whole_result_serialises_to_json():
    data = evaluate_rules(validated(REALISTIC_FEATURES()))
    blob = data.model_dump_json()
    parsed = json.loads(blob)
    assert len(parsed["decisions"]) == len(data.decisions)
    assert parsed["decisions"][0]["confidence"] is None


# --------------------------------------------------------------------------
# INPUT FORMS
# --------------------------------------------------------------------------


def test_a_raw_module_5_feature_set_is_validated_in_process_first():
    engineered = {
        "features": {
            "hba1c": {
                "name": "hba1c",
                "value": 7.4,
                "unit": "%",
                "canonical_unit": True,
                "source": "lab_report",
                "provenance": {"source": "lab_report", "original_test_name": "HbA1c"},
            }
        }
    }
    data = evaluate_rules(engineered=engineered)
    assert data.summary.input_kind == "engineered"
    assert for_rule(data, "RULE_DIABETES_HBA1C").status is DecisionStatus.INDICATED


def test_an_implausible_raw_value_is_rejected_before_any_rule_sees_it():
    engineered = {
        "features": {
            "hba1c": {
                "name": "hba1c",
                "value": 400.0,  # outside Module 6's possible band
                "unit": "%",
                "canonical_unit": True,
                "source": "lab_report",
                "provenance": {"source": "lab_report"},
            }
        }
    }
    data = evaluate_rules(engineered=engineered)
    assert for_rule(data, "RULE_DIABETES_HBA1C") is None
    assert for_condition(data, C.DIABETES)[0].status is (
        DecisionStatus.INSUFFICIENT_DATA
    )


def test_validated_input_wins_over_engineered_input():
    data = evaluate_rules(
        validated({"hba1c": vf("hba1c", 5.0)}),
        engineered={"features": {}},
    )
    assert data.summary.input_kind == "validated"
    assert for_rule(data, "RULE_DIABETES_HBA1C").status is (
        DecisionStatus.NOT_INDICATED
    )


def test_no_input_at_all_is_handled():
    data = evaluate_rules()
    assert data.summary.input_kind == "none"
    assert data.summary.highest_risk is None


def test_a_module_6_model_can_be_passed_directly():
    from app.services.validator import validate_features

    result = validate_features(
        {
            "features": {
                "hba1c": {
                    "name": "hba1c",
                    "value": 6.0,
                    "unit": "%",
                    "source": "lab_report",
                    "provenance": {"source": "lab_report"},
                }
            }
        }
    )
    data = evaluate_rules(result)
    assert for_rule(data, "RULE_DIABETES_HBA1C").status is DecisionStatus.BORDERLINE


def test_a_non_canonical_feature_key_is_ignored_with_a_warning():
    payload = validated({"hba1c": vf("hba1c", 5.0)})
    payload["valid"]["unicorn_count"] = {"name": "unicorn_count", "value": 3}
    data = evaluate_rules(payload)
    assert any("unicorn_count" in w for w in data.warnings)


# --------------------------------------------------------------------------
# END TO END
# --------------------------------------------------------------------------


def REALISTIC_FEATURES() -> Dict[str, Any]:
    """A plausible middle-aged patient with several real findings."""
    return {
        "hba1c": vf("hba1c", 7.8, test_name="HbA1c", reference_low=4.0, reference_high=5.6),
        "blood_glucose": vf(
            "blood_glucose", 168.0, test_name="Fasting Blood Sugar",
            reference_low=70.0, reference_high=99.0,
        ),
        "hemoglobin": vf("hemoglobin", 11.4, test_name="Haemoglobin"),
        "vitamin_d": vf("vitamin_d", 14.0, test_name="Vitamin D (25-OH)"),
        "vitamin_b12": vf("vitamin_b12", 410.0, test_name="Vitamin B12"),
        "creatinine": vf("creatinine", 1.6, test_name="Serum Creatinine"),
        "cholesterol": vf("cholesterol", 232.0, test_name="Total Cholesterol"),
        "triglycerides": vf("triglycerides", 260.0, test_name="Triglycerides"),
        "bmi": vf("bmi", 31.4),
        "age": vf("age", 57),
        "gender": vf("gender", "male"),
        "hypertension": vf("hypertension", True),
        "smoking_history": vf("smoking_history", "former"),
    }


def test_a_realistic_feature_set_produces_a_coherent_set_of_decisions():
    data = evaluate_rules(validated(REALISTIC_FEATURES()))
    by_condition = {d.condition: d for d in data.decisions}

    assert by_condition[C.DIABETES].status is DecisionStatus.INDICATED
    assert by_condition[C.ANEMIA].status is DecisionStatus.INDICATED
    assert by_condition[C.VITAMIN_D_DEFICIENCY].risk is RiskLevel.MEDIUM
    assert by_condition[C.VITAMIN_B12_DEFICIENCY].status is (
        DecisionStatus.NOT_INDICATED
    )
    assert by_condition[C.KIDNEY_DISEASE].status is DecisionStatus.INDICATED
    assert by_condition[C.HIGH_CHOLESTEROL].status is DecisionStatus.BORDERLINE
    assert by_condition[C.HIGH_TRIGLYCERIDES].status is DecisionStatus.INDICATED
    assert by_condition[C.OBESITY].status is DecisionStatus.INDICATED
    assert by_condition[C.HEART_DISEASE].status is DecisionStatus.INDICATED
    assert by_condition[C.HYPOGLYCEMIA].status is DecisionStatus.NOT_INDICATED

    assert data.summary.highest_risk is RiskLevel.HIGH
    assert data.summary.insufficient_data_count == 0
    assert data.summary.input_kind == "validated"
    assert set(data.summary.conditions_flagged) >= {C.DIABETES, C.ANEMIA}


def test_decision_order_is_stable_and_puts_fusion_conditions_first():
    first = evaluate_rules(validated(REALISTIC_FEATURES()))
    second = evaluate_rules(validated(REALISTIC_FEATURES()))
    order = [d.condition for d in first.decisions]
    assert order == [d.condition for d in second.decisions]
    assert order[0] == C.DIABETES
    assert C.HEART_DISEASE in order[:4]


def test_the_engine_never_asserts_a_diagnosis_anywhere_in_its_output():
    data = evaluate_rules(validated(REALISTIC_FEATURES()))
    for decision in data.decisions:
        for rec in decision.recommendations:
            assert rcat.scan_text(rec.text) == []
        for item in decision.evidence:
            assert rcat.scan_text(item.note or "") == []
