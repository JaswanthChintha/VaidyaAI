"""The Liver Disease topic -- ALT, AST, total bilirubin (2026-10-04).

Owner's decisions pinned here:
  * ALT and AST are compared with the upper limit PRINTED ON THE REPORT;
    the guideline limits (ALT 33 men / 25 women / 33 sex unknown, AST 40)
    only when the report prints none, or prints one that is not believable.
  * Above the limit -> flagged (Medium); five times the limit or more -> High.
  * Total bilirubin: above 1.2 mg/dL flagged, 3.0 or more High.
  * Adults only.
And the reading of the report itself: the spellings Indian reports print,
direct/indirect bilirubin never read as total, units converted.
"""

from __future__ import annotations

from typing import Optional

import pytest

from app.data import clinical_rules as cr
from app.data import conditions as C
from app.data.feature_catalog import UnmappedReason, lookup_test_name
from app.schemas.decisions import DecisionStatus, RiskLevel
from app.services.feature_engineer import engineer_features
from app.services.rule_engine import evaluate_rules
from tests.test_rule_engine import for_rule, validated, vf


def liver(
    feature: str,
    value: float,
    *,
    sex: Optional[str] = "male",
    age: Optional[float] = 40,
    reference_high: Optional[float] = None,
):
    features = {feature: vf(feature, value, reference_high=reference_high)}
    if sex is not None:
        features["gender"] = vf("gender", sex)
    if age is not None:
        features["age"] = vf("age", age)
    return evaluate_rules(validated(features))


RULE_FOR = {
    "alt": "RULE_LIVER_ALT",
    "ast": "RULE_LIVER_AST",
    "bilirubin_total": "RULE_LIVER_BILIRUBIN",
}


def decision(feature, value, **kw):
    return for_rule(liver(feature, value, **kw), RULE_FOR[feature])


# --------------------------------------------------------------------------
# The topic and its rules exist where they should
# --------------------------------------------------------------------------


def test_the_topic_is_canonical_and_fed_by_three_rules():
    assert C.is_canonical_condition(C.LIVER_DISEASE)
    assert not C.CONDITIONS[C.LIVER_DISEASE].always_assessed  # no model yet
    assert set(cr.CONDITION_INPUTS[C.LIVER_DISEASE]) == {"alt", "ast", "bilirubin_total"}


# --------------------------------------------------------------------------
# ALT / AST against the PRINTED limit -- on and either side of each band
# --------------------------------------------------------------------------


@pytest.mark.parametrize("feature", ["alt", "ast"])
@pytest.mark.parametrize(
    "value,status,risk",
    [
        (45.0, DecisionStatus.NOT_INDICATED, RiskLevel.LOW),  # AT the limit: inside
        (45.1, DecisionStatus.INDICATED, RiskLevel.MEDIUM),
        (224.9, DecisionStatus.INDICATED, RiskLevel.MEDIUM),
        (225.0, DecisionStatus.INDICATED, RiskLevel.HIGH),  # AT 5x: fires
        (900.0, DecisionStatus.INDICATED, RiskLevel.HIGH),
    ],
)
def test_bands_use_the_printed_upper_limit(feature, value, status, risk):
    d = decision(feature, value, reference_high=45.0)
    assert d.status is status
    assert d.risk is risk
    if status is DecisionStatus.INDICATED:
        assert "printed on the report (45 U/L)" in d.evidence[0].note


def test_a_value_the_guideline_would_flag_is_not_flagged_under_a_higher_printed_limit():
    """The owner's choice in one line: ALT 38 is above the ACG male limit of
    33 but inside a lab's printed 0-45, and the lab's limit is what applies."""
    assert decision("alt", 38.0, reference_high=45.0).status is DecisionStatus.NOT_INDICATED
    assert decision("alt", 38.0).status is DecisionStatus.INDICATED


# --------------------------------------------------------------------------
# No printed limit -> the guideline, said so
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sex,limit", [("male", 33.0), ("female", 25.0)]
)
def test_alt_falls_back_to_the_sex_specific_acg_limit(sex, limit):
    assert decision("alt", limit, sex=sex).status is DecisionStatus.NOT_INDICATED
    over = decision("alt", limit + 0.1, sex=sex)
    assert over.status is DecisionStatus.INDICATED
    assert over.evidence[0].threshold == limit
    assert "no usable upper limit" in over.evidence[0].note
    assert decision("alt", limit * 5, sex=sex).risk is RiskLevel.HIGH


def test_ast_falls_back_to_40():
    assert decision("ast", 40.0).status is DecisionStatus.NOT_INDICATED
    assert decision("ast", 40.1).status is DecisionStatus.INDICATED
    assert decision("ast", 200.0).risk is RiskLevel.HIGH


@pytest.mark.parametrize("printed", [5.0, 400.0, 0.0])
def test_an_unbelievable_printed_limit_is_not_trusted(printed):
    """A misread "0-400" must not hide a raised ALT."""
    d = decision("alt", 60.0, reference_high=printed)
    assert d.status is DecisionStatus.INDICATED
    assert d.evidence[0].threshold == 33.0
    assert "no usable upper limit" in d.evidence[0].note


def test_sex_unknown_without_a_printed_limit_is_borderline_between_25_and_33():
    assert decision("alt", 25.0, sex=None).status is DecisionStatus.NOT_INDICATED
    mid = decision("alt", 30.0, sex=None)
    assert mid.status is DecisionStatus.BORDERLINE
    assert mid.risk is RiskLevel.LOW
    assert "sex was not recorded" in mid.evidence[0].note
    assert decision("alt", 33.1, sex=None).status is DecisionStatus.INDICATED


def test_sex_unknown_with_a_printed_limit_never_reaches_the_borderline_band():
    assert decision("alt", 30.0, sex=None, reference_high=45.0).status is (
        DecisionStatus.NOT_INDICATED
    )


def test_sex_is_cited_only_when_it_chose_the_limit():
    printed = decision("alt", 60.0, reference_high=45.0)
    assert {e.feature for e in printed.evidence} == {"alt"}
    guideline = decision("alt", 60.0)
    assert "gender" in {e.feature for e in guideline.evidence}


# --------------------------------------------------------------------------
# Bilirubin
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value,status,risk",
    [
        (1.2, DecisionStatus.NOT_INDICATED, RiskLevel.LOW),
        (1.21, DecisionStatus.INDICATED, RiskLevel.MEDIUM),
        (2.99, DecisionStatus.INDICATED, RiskLevel.MEDIUM),
        (3.0, DecisionStatus.INDICATED, RiskLevel.HIGH),
    ],
)
def test_bilirubin_bands(value, status, risk):
    d = decision("bilirubin_total", value)
    assert (d.status, d.risk) == (status, risk)


# --------------------------------------------------------------------------
# Adults only, and absence is never "fine"
# --------------------------------------------------------------------------


@pytest.mark.parametrize("feature", ["alt", "ast", "bilirubin_total"])
def test_under_18_is_insufficient_data_not_a_verdict(feature):
    d = decision(feature, 500.0, age=12)
    assert d.status is DecisionStatus.INSUFFICIENT_DATA
    assert d.risk is None


def test_no_liver_test_on_the_report_is_said_as_not_assessed():
    data = evaluate_rules(validated({"hba1c": vf("hba1c", 5.2)}))
    liver_decisions = [d for d in data.decisions if d.condition == C.LIVER_DISEASE]
    assert len(liver_decisions) == 1
    assert liver_decisions[0].status is DecisionStatus.INSUFFICIENT_DATA
    assert liver_decisions[0].risk is None


def test_the_topic_takes_the_most_severe_of_its_three_rules():
    from app.services.decision_engine import merge_decision_set

    data = evaluate_rules(
        validated(
            {
                "alt": vf("alt", 300.0, reference_high=45.0),
                "ast": vf("ast", 30.0, reference_high=40.0),
                "bilirubin_total": vf("bilirubin_total", 0.8),
                "age": vf("age", 40),
                "gender": vf("gender", "female"),
            }
        )
    )
    merged = merge_decision_set([d for d in data.decisions if d.condition == C.LIVER_DISEASE])
    assert merged.status is DecisionStatus.INDICATED
    assert merged.risk is RiskLevel.HIGH


def test_the_published_rule_table_explains_the_printed_limit():
    alt = next(r for r in cr.rules_document()["threshold_rules"] if r["id"] == "RULE_LIVER_ALT")
    band = alt["bands"][1]["threshold"]
    assert band["multiple_of_printed_upper_limit"] == 1.0
    assert band["printed_limit_trusted_between"] == [15.0, 100.0]
    assert band["fallback_when_none_printed"]["male"] == 33.0


# --------------------------------------------------------------------------
# Reading the report
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "printed,feature",
    [
        ("SGPT", "alt"),
        ("S.G.P.T.", "alt"),
        ("SGPT (ALT)", "alt"),
        ("Alanine Aminotransferase (ALT/SGPT)", "alt"),
        ("SGOT", "ast"),
        ("AST/SGOT", "ast"),
        ("Bilirubin Total", "bilirubin_total"),
        ("Total Bilirubin", "bilirubin_total"),
        ("Serum Bilirubin", "bilirubin_total"),
    ],
)
def test_printed_names_map(printed, feature):
    match, reason = lookup_test_name(printed)
    assert reason is None
    assert match.feature == feature


@pytest.mark.parametrize(
    "printed",
    ["Bilirubin Direct", "Direct Bilirubin", "Bilirubin (Indirect)", "Conjugated Bilirubin"],
)
def test_a_bilirubin_fraction_is_never_read_as_total(printed):
    """`direct` is a strippable method word for other tests; for bilirubin it
    names a different fraction and must refuse, not fold into the total."""
    match, reason = lookup_test_name(printed)
    assert match is None
    assert reason == UnmappedReason.DISTINCT_ANALYTE


def test_urine_bilirubin_is_a_different_specimen():
    match, reason = lookup_test_name("Urine Bilirubin")
    assert match is None
    assert reason == UnmappedReason.NON_BLOOD_SPECIMEN


def _param(name, value, unit, low=None, high=None):
    return {
        "test_name": name,
        "value_raw": str(value),
        "value_numeric": value,
        "unit": unit,
        "reference_range_raw": None,
        "reference_low": low,
        "reference_high": high,
        "flag": None,
        "page_number": 1,
        "confidence": 0.95,
    }


def test_an_extracted_liver_panel_becomes_three_features_with_units_converted():
    data = engineer_features(
        [
            _param("SGPT", 64.0, "IU/L", 0.0, 45.0),
            _param("SGOT", 38.0, "U/L", 0.0, 40.0),
            _param("Bilirubin Total", 20.5, "µmol/L", 3.4, 20.5),
            _param("Bilirubin Direct", 4.1, "µmol/L"),
        ]
    )
    assert data.features["alt"].value == pytest.approx(64.0)
    assert data.features["alt"].unit == "u/l"
    assert data.features["ast"].value == pytest.approx(38.0)
    # 20.5 umol/L = 1.199 mg/dL, and the printed interval converts with it.
    assert data.features["bilirubin_total"].value == pytest.approx(1.1986, abs=1e-3)
    assert data.features["bilirubin_total"].unit == "mg/dl"
    # The direct fraction is listed as printed, never mistaken for the total.
    assert any(u.test_name == "Bilirubin Direct" for u in data.unmapped)
