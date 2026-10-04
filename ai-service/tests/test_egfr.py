"""eGFR -- the CKD-EPI 2021 equation and the rule that reads it (2026-10-04).

Three things are pinned here:

1. THE EQUATION. Anchored by its own algebra (at creatinine == kappa both
   power terms are 1, leaving 142 x 0.9938^age, x 1.012 for women) rather than
   only by numbers this file computed itself, plus fixed values across both
   branches so a changed constant cannot pass.
2. NO ESTIMATE ON AN ASSUMED VALUE. No age, under 18, sex not male/female,
   non-positive creatinine -> None, and the rule does not fire. The
   creatinine rule still reports, so the topic is never silent.
3. EVERY BAND, ON AND EITHER SIDE of its cut-off, on the rounded number the
   reader is shown -- by solving for the creatinine that produces each eGFR.
"""

from __future__ import annotations

from typing import Optional

import pytest

from app.data import clinical_rules as cr
from app.data.egfr import (
    EGFR_DISPLAY_NAME,
    EGFR_FEATURE,
    EGFR_UNIT,
    SOURCE_CALCULATED,
    ckd_epi_2021,
    reported_egfr,
)
from app.data.feature_catalog import FEATURES
from app.schemas.decisions import DecisionStatus, RiskLevel
from app.services.rule_engine import (
    NOTE_EGFR_METHOD,
    NOTE_QUESTIONABLE,
    evaluate_rules,
)
from tests.test_rule_engine import for_rule, validated, vf

RULE = "RULE_KIDNEY_EGFR"


def kidney(creatinine: float, age: Optional[float], sex: Optional[str], **kw):
    features = {"creatinine": vf("creatinine", creatinine, **kw)}
    if age is not None:
        features["age"] = vf("age", age)
    if sex is not None:
        features["gender"] = vf("gender", sex)
    return evaluate_rules(validated(features))


def creatinine_for(target: float, age: float, sex: str) -> float:
    """The creatinine whose UNROUNDED eGFR is `target` (eGFR falls as it rises)."""
    low, high = 0.05, 30.0
    for _ in range(200):
        mid = (low + high) / 2
        if ckd_epi_2021(mid, age, sex) > target:
            low = mid
        else:
            high = mid
    return (low + high) / 2


# --------------------------------------------------------------------------
# 1. The equation
# --------------------------------------------------------------------------


@pytest.mark.parametrize("age", [18, 40, 63, 90])
def test_at_kappa_the_equation_reduces_to_its_age_term(age):
    """Inker 2021: at Scr == kappa, min and max are both 1."""
    assert ckd_epi_2021(0.9, age, "male") == pytest.approx(142 * 0.9938**age)
    assert ckd_epi_2021(0.7, age, "female") == pytest.approx(
        142 * 0.9938**age * 1.012
    )


@pytest.mark.parametrize(
    "creatinine,age,sex,expected",
    [
        (1.0, 50, "male", 91.69),
        (1.2, 60, "female", 51.82),
        (2.0, 65, "male", 36.36),
        (4.0, 55, "female", 12.61),
        (0.5, 25, "female", 133.40),  # below kappa: the alpha branch
        (1.0, 75, "female", 58.75),
    ],
)
def test_fixed_values_on_both_branches(creatinine, age, sex, expected):
    assert ckd_epi_2021(creatinine, age, sex) == pytest.approx(expected, abs=0.01)


def test_below_kappa_uses_alpha_and_above_uses_minus_1_2():
    male_low = ckd_epi_2021(0.45, 40, "male")
    assert male_low == pytest.approx(142 * (0.45 / 0.9) ** -0.302 * 0.9938**40)
    male_high = ckd_epi_2021(1.8, 40, "male")
    assert male_high == pytest.approx(142 * (1.8 / 0.9) ** -1.2 * 0.9938**40)


def test_the_estimate_falls_as_creatinine_and_age_rise():
    assert ckd_epi_2021(1.0, 40, "male") > ckd_epi_2021(1.3, 40, "male")
    assert ckd_epi_2021(1.0, 40, "male") > ckd_epi_2021(1.0, 70, "male")


@pytest.mark.parametrize(
    "creatinine,age,sex",
    [
        (1.0, None, "male"),
        (1.0, 50, None),
        (1.0, 50, "other"),
        (1.0, 50, "prefer_not_to_say"),
        (1.0, 17, "male"),
        (0.0, 50, "male"),
        (-1.0, 50, "female"),
        (None, 50, "female"),
        (float("nan"), 50, "female"),
        ("not a number", 50, "female"),
    ],
)
def test_no_estimate_without_valid_inputs(creatinine, age, sex):
    assert ckd_epi_2021(creatinine, age, sex) is None


def test_rounding_is_half_up_on_the_number_shown():
    assert reported_egfr(59.49) == 59
    assert reported_egfr(59.5) == 60
    assert reported_egfr(60.4) == 60


# --------------------------------------------------------------------------
# 2. The rule fires only on a real estimate
# --------------------------------------------------------------------------


def test_the_rule_is_a_derived_kidney_rule_on_creatinine():
    rule = cr.rule_by_id(RULE)
    assert rule.condition == "Kidney Disease"
    assert rule.feature == "creatinine"
    assert rule.derived == EGFR_FEATURE
    assert EGFR_FEATURE not in FEATURES, "a calculated value must not be a catalogue feature"
    assert cr.CONDITION_INPUTS["Kidney Disease"] == ("creatinine",)


@pytest.mark.parametrize(
    "age,sex",
    [(None, "female"), (75, None), (75, "other"), (75, "prefer_not_to_say")],
)
def test_no_age_or_no_binary_sex_means_no_egfr_decision_but_creatinine_still_reports(age, sex):
    data = kidney(1.0, age, sex)
    assert for_rule(data, RULE) is None
    assert for_rule(data, "RULE_KIDNEY_CREATININE") is not None
    assert any(RULE in w and "not applied" in w for w in data.warnings)
    # Never a fall-through to "at or above 60".
    assert not any(e.feature == EGFR_FEATURE for d in data.decisions for e in d.evidence)


def test_under_18_only_the_creatinine_rules_insufficient_data_is_emitted():
    data = kidney(1.0, 16, "male")
    assert for_rule(data, RULE) is None
    creatinine = for_rule(data, "RULE_KIDNEY_CREATININE")
    assert creatinine.status is DecisionStatus.INSUFFICIENT_DATA


def test_no_creatinine_no_decision():
    features = {"age": vf("age", 60), "gender": vf("gender", "male")}
    data = evaluate_rules(validated(features))
    assert for_rule(data, RULE) is None


# --------------------------------------------------------------------------
# 3. Bands, on and either side, on the rounded value
# --------------------------------------------------------------------------

BANDS = [
    # (cut-off, status below it, risk below it)
    (15, DecisionStatus.INDICATED, RiskLevel.HIGH),
    (30, DecisionStatus.INDICATED, RiskLevel.HIGH),
    (45, DecisionStatus.INDICATED, RiskLevel.MEDIUM),
    (60, DecisionStatus.INDICATED, RiskLevel.MEDIUM),
]


@pytest.mark.parametrize("sex", ["male", "female"])
@pytest.mark.parametrize("cutoff,status,risk", BANDS)
def test_each_band_on_and_either_side(cutoff, status, risk, sex):
    age = 55

    # Exactly AT the cut-off: "<" does not fire, so it falls to the next band.
    at = for_rule(kidney(creatinine_for(cutoff, age, sex), age, sex), RULE)
    assert at.metadata["derived_value"] == cutoff
    assert at.metadata["threshold"] is None or at.metadata["threshold"] > cutoff

    # Shown as one below: fires this band.
    below = for_rule(kidney(creatinine_for(cutoff - 0.6, age, sex), age, sex), RULE)
    assert below.metadata["derived_value"] == cutoff - 1
    assert below.metadata["threshold"] == float(cutoff)
    assert below.status is status
    assert below.risk is risk


def test_59_point_6_is_shown_as_60_and_not_flagged():
    """The reader must never see "60" beside "below 60"."""
    decision = for_rule(kidney(creatinine_for(59.6, 55, "male"), 55, "male"), RULE)
    assert decision.metadata["derived_value"] == 60
    assert decision.status is DecisionStatus.NOT_INDICATED
    assert decision.risk is RiskLevel.LOW


def test_low_egfr_flags_kidney_even_with_creatinine_inside_its_interval():
    """Owner's decision 2026-10-04: a 75-year-old woman, creatinine 1.0
    (female upper limit 1.04) -> eGFR 59 -> flagged."""
    data = kidney(1.0, 75, "female")
    assert for_rule(data, "RULE_KIDNEY_CREATININE").status is DecisionStatus.NOT_INDICATED
    egfr = for_rule(data, RULE)
    assert egfr.status is DecisionStatus.INDICATED
    assert egfr.risk is RiskLevel.MEDIUM
    assert egfr.metadata["derived_value"] == 59


# --------------------------------------------------------------------------
# 4. What the decision says about itself
# --------------------------------------------------------------------------


def test_evidence_is_marked_calculated_with_its_method_and_inputs():
    egfr = for_rule(kidney(1.0, 75, "female"), RULE)
    primary = egfr.evidence[0]
    assert primary.feature == EGFR_FEATURE
    assert primary.value == 59
    assert primary.unit == EGFR_UNIT
    assert primary.comparator == "<"
    assert primary.threshold == 60.0
    assert primary.source_stage == SOURCE_CALCULATED
    assert NOTE_EGFR_METHOD in primary.note
    assert {e.feature for e in egfr.evidence[1:]} == {"creatinine", "age", "gender"}
    assert egfr.metadata["derived_method"].startswith("CKD-EPI 2021")
    assert egfr.confidence is None


def test_a_questionable_creatinine_makes_the_estimate_questionable():
    egfr = for_rule(kidney(1.0, 75, "female", questionable=True), RULE)
    assert NOTE_QUESTIONABLE in egfr.evidence[0].note
    assert egfr.metadata["questionable_inputs"] == ["creatinine"]


def test_the_report_builder_names_the_calculated_value():
    from app.services.report_builder import _evidence_line

    egfr = for_rule(kidney(1.0, 75, "female"), RULE)
    line = _evidence_line(
        egfr.evidence[0],
        rejected={},
        questionable=set(),
        clinically_extreme=set(),
        warnings_by_feature={},
    )
    assert line.display_name == EGFR_DISPLAY_NAME
    assert line.availability == "observed"


def test_the_published_rule_table_carries_the_derived_unit():
    rule = next(
        r for r in cr.rules_document()["threshold_rules"] if r["id"] == RULE
    )
    assert rule["derived"] == EGFR_FEATURE
    assert rule["unit"] == EGFR_UNIT


def test_kidney_fuses_to_the_more_severe_of_the_two_rules():
    """Module 15/16 take the most severe status and highest risk per topic."""
    from app.services.decision_engine import merge_decision_set

    data = kidney(1.0, 75, "female")
    kidney_decisions = [d for d in data.decisions if d.condition == "Kidney Disease"]
    assert len(kidney_decisions) == 2
    merged = merge_decision_set(kidney_decisions)
    assert merged.status is DecisionStatus.INDICATED
    assert merged.risk is RiskLevel.MEDIUM
    assert any(e.feature == EGFR_FEATURE for e in merged.evidence)
