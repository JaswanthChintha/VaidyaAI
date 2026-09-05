"""Module 28 -- Health Timeline and Trend Analysis. The in-process computation.

Framework-independent: no HTTP, no API key, no network, no model. Every value
here is invented; the payloads go in through the SAME parse boundary the Node
backend posts through (`ValidatedFeatureSetInput` -> Module 7's
`build_snapshot`), so a rejected reading is discarded exactly where production
discards it.

WHY THIS FILE EXISTS. Module 28 shipped with no tests at all (MEMORY.md
section 6m), and the end-to-end audit in section 6n found that a fully green
suite said nothing whatever about this code. The failure mode that matters
here is not a crash: it is a WRONG CLINICAL STATEMENT produced confidently.
The five things this file holds in place, each of which is a documented
guarantee that only a test can keep true:

1. ABSENCE NEVER BECOMES A VALUE (MEMORY.md section 11, the most repeated
   hazard on this project). Fewer than two usable readings is
   `INSUFFICIENT_DATA` with `trend: null` and MUST NOT be `stable` -- "we could
   not look" and "we looked and nothing moved" are different statements. A
   feature missing from a report is a gap carrying a reason, never a zero and
   never an interpolated point.

2. DIRECTION IS NOT "BETTER". Rising HbA1c is worsening; rising vitamin D from
   a deficient level is improving; rising creatinine is worsening. No rule of
   arithmetic separates those, so each is read from the declared polarity
   table -- and a feature with UNDECLARED polarity reports direction only,
   with `CLINICAL_DIRECTION_UNKNOWN`, never a guess.

3. STABLE IS EARNED. `stable` is returned only when two or more readings exist
   AND the net change failed BOTH declared thresholds of the stability band.

4. A UNIT PROBLEM IS A REFUSAL, never a conversion.

5. DETERMINISM. The same reports in any array order produce byte-identical
   output apart from `generated_at`, because the sort key uses only the data.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import pytest

from app.data.validation_rules import rule_for
from app.data.feature_catalog import CANONICAL_FEATURES, FEATURES
from app.data.trend_polarity import (
    POLARITY,
    POLARITY_MONOTONE,
    POLARITY_TOWARD_REFERENCE,
    POLARITY_UNDECLARED,
    STABILITY,
    reference_change_value,
)
from app.schemas.timeline import (
    OUTCOME_CHANGE_WITHIN_REFERENCE_INTERVAL,
    OUTCOME_CLINICAL_DIRECTION_UNKNOWN,
    OUTCOME_INSUFFICIENT_DATA,
    OUTCOME_NOT_COMPARABLE_AGE_CONTEXT,
    OUTCOME_NOT_COMPARABLE_SAMPLE_TIMING,
    OUTCOME_NOT_NUMERIC,
    OUTCOME_NOT_TRENDABLE,
    OUTCOME_TREND_CLASSIFIED,
    OUTCOME_UNIT_MISMATCH,
    OUTCOME_UNIT_NOT_CANONICAL,
    OUTCOME_VALUES,
    TREND_IMPROVING,
    TREND_STABLE,
    TREND_WORSENING,
    FeatureTrend,
    TimelineGap,
    TimelineTrendsRequest,
)
from app.services.trend_analyzer import analyse_trends
from tests.trend_payloads import rejection, report, series_reports, vf


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def analyse(reports: List[Dict[str, Any]], **options: Any):
    return analyse_trends(
        TimelineTrendsRequest(reports=reports, options=options)
    )


def trend_of(
    feature: str, values: List[Any], unit: Optional[str], **options: Any
) -> FeatureTrend:
    """One feature measured once per report, oldest first."""
    return analyse(series_reports(feature, values, unit), **options).features[
        feature
    ]


# --------------------------------------------------------------------------
# 1. The absence hazard -- MEMORY.md section 11
# --------------------------------------------------------------------------


def test_a_single_usable_reading_is_insufficient_data_and_never_stable():
    """The headline absence rule, in the exact shape it would be got wrong.

    One report carries HbA1c and the other does not. The tempting wrong answer
    is `stable` ("it did not change"), which asserts something nobody
    measured. The contract is `INSUFFICIENT_DATA`, `trend: null`, and NO
    change arithmetic at all.
    """
    trend = analyse(
        [
            report("r1", "2024-01-01T00:00:00Z", {"hba1c": vf("hba1c", 6.1, "%")}),
            report(
                "r2",
                "2024-06-01T00:00:00Z",
                {"cholesterol": vf("cholesterol", 190.0, "mg/dl")},
            ),
        ]
    ).features["hba1c"]

    assert trend.outcome == OUTCOME_INSUFFICIENT_DATA
    assert trend.trend is None
    assert trend.trend != TREND_STABLE
    assert trend.change is None
    assert trend.direction is None
    assert trend.usable_point_count == 1
    # The report that carried nothing is visible as a gap, not dropped.
    assert [gap.report_id for gap in trend.gaps] == ["r2"]


def test_a_feature_absent_from_every_report_is_never_a_clean_bill():
    """`include_all_canonical` pads the response; it must not pad it with news.

    Two reports carrying only cholesterol. Every other canonical feature comes
    back with an explicit refusal outcome, and NOT ONE of them carries a trend
    -- in particular not `stable`, which a dashboard would render as "no
    change", and not `improving`.
    """
    data = analyse(
        [
            report(
                "r1",
                "2024-01-01T00:00:00Z",
                {"cholesterol": vf("cholesterol", 190.0, "mg/dl")},
            ),
            report(
                "r2",
                "2024-06-01T00:00:00Z",
                {"cholesterol": vf("cholesterol", 240.0, "mg/dl")},
            ),
        ],
        include_all_canonical=True,
    )

    assert set(data.features) == set(CANONICAL_FEATURES)
    for name, trend in data.features.items():
        if name == "cholesterol":
            continue
        assert trend.trend is None, f"{name} invented a trend from no readings"
        assert trend.outcome != OUTCOME_TREND_CLASSIFIED
        assert trend.usable_point_count == 0
        assert trend.change is None
    assert data.summary.stable == 0
    assert data.summary.improving == 0
    assert data.summary.worsening == 1  # cholesterol, the only measured one
    assert data.summary.not_determinable == len(CANONICAL_FEATURES) - 1


def test_a_gap_structurally_cannot_carry_a_value():
    """The guarantee is the SHAPE, not a convention the writer remembered.

    `TimelineGap` has no `value` field and forbids extras, so no future edit
    can attach one and no renderer can read a gap as a zero. Asserted against
    the model itself, which is the only way this cannot silently regress.
    """
    assert "value" not in TimelineGap.model_fields
    assert TimelineGap.model_config["extra"] == "forbid"
    with pytest.raises(Exception):
        TimelineGap(
            report_id="r1",
            date="2024-01-01T00:00:00Z",
            availability="not_reported",
            reason_code="NOT_REPORTED",
            reason="x",
            value=0.0,
        )


def test_a_rejected_reading_becomes_a_gap_and_its_number_never_appears():
    """A refused value must not reach a trend, nor the response, at all.

    Module 6 rejected the creatinine on the second report. The series is one
    point plus a gap whose availability is `rejected` and whose reason code is
    Module 6's own -- and the refused number appears nowhere in the serialised
    response, because `IncomingRejection` drops it at the parse boundary.
    """
    data = analyse(
        [
            report(
                "r1",
                "2024-01-01T00:00:00Z",
                {"creatinine": vf("creatinine", 1.0, "mg/dl")},
            ),
            report(
                "r2",
                "2024-06-01T00:00:00Z",
                {},
                rejected={"creatinine": rejection("creatinine")},
            ),
        ],
        features=["creatinine"],
    )
    trend = data.features["creatinine"]

    assert trend.outcome == OUTCOME_INSUFFICIENT_DATA
    assert trend.trend is None
    assert len(trend.points) == 1
    gap = trend.gaps[0]
    assert gap.availability == "rejected"
    assert gap.reason_code == "IMPLAUSIBLE_VALUE_HIGH"
    assert gap.reason
    serialised = json.dumps(data.model_dump(mode="json"))
    assert "9999" not in serialised


def test_nothing_is_interpolated_across_a_missing_middle_report():
    """Three reports, the middle one silent: the series has TWO points.

    An interpolated midpoint would be indistinguishable from a measured one in
    `points`, which is the array a chart plots directly.
    """
    trend = analyse(
        [
            report("r1", "2024-01-01T00:00:00Z", {"hba1c": vf("hba1c", 6.1, "%")}),
            report("r2", "2024-03-01T00:00:00Z", {}),
            report("r3", "2024-06-01T00:00:00Z", {"hba1c": vf("hba1c", 6.8, "%")}),
        ],
        features=["hba1c"],
    ).features["hba1c"]

    assert [point.value for point in trend.points] == [6.1, 6.8]
    assert [gap.report_id for gap in trend.gaps] == ["r2"]
    assert trend.report_count == 3
    assert trend.usable_point_count == 2
    assert trend.change is not None
    assert trend.change.step_count == 1


def test_no_reports_at_all_produces_no_features_and_says_so():
    data = analyse([])
    assert data.features == {}
    assert data.summary.report_count == 0
    assert data.summary.first_report_date is None
    assert any("No reports" in warning for warning in data.warnings)


def test_excluding_questionable_turns_a_trend_into_a_refusal_not_a_stable():
    """Turning the conservative option on may only ever REMOVE a claim.

    The second reading is dropped, so the series falls to one point. The
    correct result is `INSUFFICIENT_DATA` with a gap carrying
    `QUESTIONABLE_EXCLUDED` -- not `stable`, and not the trend the two points
    would have produced.
    """
    questionable = vf("hba1c", 6.8, "%", questionable=True)
    questionable["questionable"] = True
    reports = [
        report("r1", "2024-01-01T00:00:00Z", {"hba1c": vf("hba1c", 6.1, "%")}),
        report("r2", "2024-06-01T00:00:00Z", {"hba1c": questionable}),
    ]

    included = analyse(reports).features["hba1c"]
    assert included.outcome == OUTCOME_TREND_CLASSIFIED
    assert included.trend == TREND_WORSENING

    excluded = analyse(reports, exclude_questionable=True).features["hba1c"]
    assert excluded.outcome == OUTCOME_INSUFFICIENT_DATA
    assert excluded.trend is None
    assert excluded.gaps[0].reason_code == "QUESTIONABLE_EXCLUDED"


def test_the_model_refuses_to_ship_a_trend_alongside_a_refusal():
    """The structural half of "stable is earned", asserted on the contract.

    `FeatureTrend` raises when a refusal outcome carries a trend and when
    TREND_CLASSIFIED carries none, so a future edit to the analyzer cannot
    quietly ship a defaulted `stable` even if a branch tried to.
    """
    base = dict(feature="hba1c", value_type="number", reason="x")
    with pytest.raises(Exception):
        FeatureTrend(outcome=OUTCOME_INSUFFICIENT_DATA, trend=TREND_STABLE, **base)
    with pytest.raises(Exception):
        FeatureTrend(outcome=OUTCOME_TREND_CLASSIFIED, trend=None, **base)
    with pytest.raises(Exception):
        FeatureTrend(
            outcome=OUTCOME_INSUFFICIENT_DATA,
            change={
                "first_report_id": "a",
                "last_report_id": "b",
                "first_date": "2024-01-01T00:00:00Z",
                "last_date": "2024-02-01T00:00:00Z",
                "days_between": 31.0,
                "first_value": 1.0,
                "last_value": 2.0,
                "absolute_change": 1.0,
                "min_value": 1.0,
                "max_value": 2.0,
                "step_count": 1,
            },
            **base,
        )


# --------------------------------------------------------------------------
# 2. Polarity -- direction is not "better"
# --------------------------------------------------------------------------


def test_the_specifications_own_hba1c_example_is_worsening():
    """Project Description, Module 28: HbA1c 6.1 -> 6.4 -> 6.8."""
    trend = trend_of("hba1c", [6.1, 6.4, 6.8], "%")
    assert trend.outcome == OUTCOME_TREND_CLASSIFIED
    assert trend.trend == TREND_WORSENING
    assert trend.direction == "rising"
    assert trend.change is not None
    assert trend.change.first_value == 6.1
    assert trend.change.last_value == 6.8
    assert trend.polarity is not None
    assert trend.polarity.kind == POLARITY_MONOTONE
    assert trend.polarity.direction_of_harm == "increase"


def test_falling_hba1c_is_improving_and_rising_creatinine_is_worsening():
    """Two monotone features, opposite directions of travel, one table."""
    assert trend_of("hba1c", [6.8, 6.1], "%").trend == TREND_IMPROVING
    assert trend_of("creatinine", [0.9, 1.6], "mg/dl").trend == TREND_WORSENING
    assert trend_of("creatinine", [1.6, 0.9], "mg/dl").trend == TREND_IMPROVING


def test_rising_vitamin_d_from_a_deficient_level_is_improving():
    """The case that makes a bare `last - first` rule wrong.

    Vitamin D is TOWARD_REFERENCE, not monotone: a rise from a deficient 14 to
    28 is improvement because it moved toward the declared interval, while a
    rise from 95 to 140 is worsening because it moved past the top of it. Both
    are the same arithmetic sign.
    """
    improving = trend_of("vitamin_d", [14.0, 28.0], "ng/ml")
    assert improving.trend == TREND_IMPROVING
    assert improving.direction == "rising"
    assert improving.polarity is not None
    assert improving.polarity.kind == POLARITY_TOWARD_REFERENCE

    worsening = trend_of("vitamin_d", [95.0, 140.0], "ng/ml")
    assert worsening.trend == TREND_WORSENING
    assert worsening.direction == "rising"


def test_a_change_wholly_inside_the_declared_interval_makes_no_claim():
    """35 -> 95 ng/mL is a big move, and both ends are sufficient.

    Calling that "improving" would tell a reader their vitamin D got better
    when both readings were already in range, so the outcome is
    CHANGE_WITHIN_REFERENCE_INTERVAL with `trend: null`.
    """
    trend = trend_of("vitamin_d", [35.0, 95.0], "ng/ml")
    assert trend.outcome == OUTCOME_CHANGE_WITHIN_REFERENCE_INTERVAL
    assert trend.trend is None
    assert trend.direction == "rising"
    assert trend.stability is not None and trend.stability.exceeded is True


def test_crossing_the_whole_interval_is_refused_rather_than_labelled():
    """Deficient to excessive is not an improvement, nor a worsening.

    10 -> 150 ng/mL ends further from the interval than it started only by
    arithmetic accident; the honest answer is that a single better/worse label
    would misdescribe it.
    """
    trend = trend_of("vitamin_d", [10.0, 150.0], "ng/ml")
    assert trend.outcome == OUTCOME_CLINICAL_DIRECTION_UNKNOWN
    assert trend.trend is None
    assert "one side" in trend.reason


@pytest.mark.parametrize(
    "feature,values,unit",
    [
        ("blood_glucose", [90.0, 180.0], "mg/dl"),
        ("hemoglobin", [10.0, 14.0], "g/dl"),
    ],
)
def test_an_undeclared_polarity_reports_direction_only(feature, values, unit):
    """The refusal that keeps this module honest about what it does not know.

    Glucose is harmful at both extremes and carries no sample timing;
    haemoglobin's lower bound is sex- and age-specific and this service does
    not record pregnancy. Both are UNDECLARED on purpose. A measurable rise
    must come back as CLINICAL_DIRECTION_UNKNOWN with the arithmetic intact
    and no better/worse word attached.
    """
    trend = trend_of(feature, values, unit)
    assert trend.outcome == OUTCOME_CLINICAL_DIRECTION_UNKNOWN
    assert trend.trend is None
    assert trend.direction == "rising"
    assert trend.change is not None and trend.change.absolute_change > 0
    assert trend.polarity is not None
    assert trend.polarity.kind == POLARITY_UNDECLARED
    assert trend.polarity.direction_of_harm is None
    # The reason may quote the table's reviewer-facing basis (which discusses
    # why no direction is declared), but it must NEVER contain the sentence
    # the classified branches emit.
    assert "the direction of change is" not in trend.reason
    assert "whether the change is favourable is not reported" in trend.reason


@pytest.mark.parametrize(
    "feature",
    sorted(
        name
        for name, entry in POLARITY.items()
        if entry.kind == POLARITY_UNDECLARED and entry.trendable
    ),
)
def test_no_undeclared_feature_can_ever_be_classified(feature):
    """Exhaustive over the table, so a NEW undeclared feature is covered too.

    A future row added as UNDECLARED gets this guard for free; a future edit
    that quietly gives one of them a direction fails here.

    THE TWO READINGS ARE DRAWN FROM THE FEATURE'S OWN POSSIBLE BAND rather
    than hard-coded. This used to probe every feature with `[10.0, 1000.0]`,
    which is 1000 g/dL of haemoglobin -- outside Module 6's 1-30 band, so once
    the analyzer began dropping implausible readings the probe stopped
    reaching the polarity logic at all and the test measured nothing. Deriving
    the pair keeps the test exhaustive over the table AND keeps every probe a
    value that could actually arrive.
    """
    unit = FEATURES[feature].canonical_unit
    rule = rule_for(feature)
    low = rule.possible_low if rule and rule.possible_low is not None else 1.0
    high = rule.possible_high if rule and rule.possible_high is not None else 1000.0
    # Comfortably inside both edges, and far enough apart to clear any
    # stability band, so the only thing that can refuse is the polarity.
    small = low + (high - low) * 0.1
    large = low + (high - low) * 0.9

    rising = trend_of(feature, [small, large], unit)
    falling = trend_of(feature, [large, small], unit)
    assert rising.trend is None and falling.trend is None
    assert rising.outcome == OUTCOME_CLINICAL_DIRECTION_UNKNOWN
    assert falling.outcome == OUTCOME_CLINICAL_DIRECTION_UNKNOWN


def test_non_numeric_and_non_trendable_features_refuse_with_their_own_codes():
    """A tri-state boolean has no magnitude; age rises for everyone.

    `_is_real_number` excludes bools explicitly -- without that guard
    `isinstance(True, int)` would let an absent tri-state be trended as 0/1,
    which is the absence hazard one step from becoming a value.
    """
    data = analyse(
        [
            report(
                "r1",
                "2024-01-01T00:00:00Z",
                {
                    "hypertension": vf("hypertension", False),
                    "age": vf("age", 45, "years"),
                    "gender": vf("gender", "male"),
                },
            ),
            report(
                "r2",
                "2024-06-01T00:00:00Z",
                {
                    "hypertension": vf("hypertension", True),
                    "age": vf("age", 46, "years"),
                    "gender": vf("gender", "male"),
                },
            ),
        ]
    )
    assert data.features["hypertension"].outcome == OUTCOME_NOT_NUMERIC
    assert data.features["gender"].outcome == OUTCOME_NOT_NUMERIC
    assert data.features["age"].outcome == OUTCOME_NOT_TRENDABLE
    for name in ("hypertension", "gender", "age"):
        assert data.features[name].trend is None


def test_an_adult_only_declaration_is_refused_at_a_recorded_child_age():
    """The WHO adult BMI bands are not valid in a 15-year-old.

    The polarity row declares `min_age_years=20`, and the series carries a
    recorded age below it, so the classification is refused rather than made
    with the wrong rule.
    """
    reports = [
        report(
            "r1",
            "2024-01-01T00:00:00Z",
            {"bmi": vf("bmi", 22.0, "kg/m2"), "age": vf("age", 15, "years")},
        ),
        report(
            "r2",
            "2024-06-01T00:00:00Z",
            {"bmi": vf("bmi", 26.0, "kg/m2"), "age": vf("age", 15, "years")},
        ),
    ]
    trend = analyse(reports).features["bmi"]
    assert trend.outcome == OUTCOME_NOT_COMPARABLE_AGE_CONTEXT
    assert trend.trend is None


def test_a_mixed_timing_glucose_series_is_refused():
    """A fasting and a post-prandial glucose are not the same quantity.

    Module 8 already refuses to apply fasting cut-offs to a sample whose
    timing was not established; Module 28 must not be less careful.
    """
    trend = analyse(
        [
            report(
                "r1",
                "2024-01-01T00:00:00Z",
                {
                    "blood_glucose": vf(
                        "blood_glucose",
                        95.0,
                        "mg/dl",
                        original_test_name="Fasting Blood Glucose",
                    )
                },
            ),
            report(
                "r2",
                "2024-06-01T00:00:00Z",
                {
                    "blood_glucose": vf(
                        "blood_glucose",
                        160.0,
                        "mg/dl",
                        original_test_name="Post Prandial Blood Sugar",
                    )
                },
            ),
        ]
    ).features["blood_glucose"]

    assert trend.outcome == OUTCOME_NOT_COMPARABLE_SAMPLE_TIMING
    assert trend.trend is None
    assert {point.sample_timing for point in trend.points} == {
        "fasting",
        "post_prandial",
    }


# --------------------------------------------------------------------------
# 3. Stable is earned
# --------------------------------------------------------------------------


def test_stable_requires_clearing_both_thresholds_not_either():
    """Two near-misses in opposite directions, both correctly `stable`.

    Creatinine's band is 14 % and 0.1 mg/dL. 0.50 -> 0.58 clears the
    percentage (16 %) but not the absolute floor; 3.0 -> 3.2 clears the
    absolute floor but not the percentage (6.7 %). A rule using EITHER
    threshold would call one of them a real change.
    """
    percent_only = trend_of("creatinine", [0.5, 0.58], "mg/dl")
    absolute_only = trend_of("creatinine", [3.0, 3.2], "mg/dl")
    for trend in (percent_only, absolute_only):
        assert trend.outcome == OUTCOME_TREND_CLASSIFIED
        assert trend.trend == TREND_STABLE
        assert trend.stability is not None and trend.stability.exceeded is False
    assert percent_only.change is not None
    assert percent_only.change.percent_change == 16.0
    assert absolute_only.change is not None
    assert absolute_only.change.absolute_change == pytest.approx(0.2)


def test_stable_is_reported_with_the_band_it_was_measured_against():
    """A `stable` a reader cannot check is a claim, not a finding."""
    trend = trend_of("hba1c", [6.1, 6.2], "%")
    assert trend.trend == TREND_STABLE
    assert trend.stability is not None
    assert trend.stability.significant_change_pct == 8.0
    assert trend.stability.min_absolute_change == 0.2
    assert trend.stability.source == "app/data/trend_polarity.py"
    assert "8 % and 0.2" in trend.reason


@pytest.mark.parametrize("feature", sorted(STABILITY))
def test_every_band_claiming_to_be_an_rcv_recomputes_to_its_stated_value(feature):
    """The data file says a reviewer can recompute every row. Do it.

    A typo in a percentage is otherwise invisible -- the number would simply be
    the threshold, and nothing would look wrong.
    """
    band = STABILITY[feature]
    if band.analytical_cv_pct is None or band.within_subject_cv_pct is None:
        pytest.skip(f"{feature}: stated as a reviewer judgement, not an RCV")
    computed = reference_change_value(
        band.analytical_cv_pct, band.within_subject_cv_pct
    )
    assert computed == pytest.approx(band.significant_change_pct, abs=0.6)


def test_a_reversal_inside_the_series_is_flagged_rather_than_absorbed():
    """6.1 -> 7.5 -> 6.8 is net worsening, but that is not the whole story.

    `volatile` and `direction_consistency` exist so a reader can SEE the
    reversal instead of the net classification quietly swallowing it.
    """
    trend = trend_of("hba1c", [6.1, 7.5, 6.8], "%")
    assert trend.trend == TREND_WORSENING
    assert trend.change is not None
    assert trend.change.volatile is True
    assert trend.change.direction_consistency == 0.5
    assert trend.change.max_value == 7.5
    assert "opposite direction" in trend.reason


def test_a_zero_first_value_gives_a_null_percentage_not_infinity():
    """An undefined percentage is null -- not 0, not infinity.

    Treating it as infinite would make every change from zero automatically
    significant, which is the absence-becomes-a-value mistake in another
    costume. Only the absolute floor applies.

    VITAMIN D, NOT CHOLESTEROL, and the difference matters. This probe used a
    cholesterol of 0 mg/dL, which is not a measurement -- Module 6's possible
    band for cholesterol starts at 20, and the analyzer now drops values
    outside that band as `IMPLAUSIBLE_VALUE` rather than trending them. So the
    old probe stopped reaching the arithmetic it was written to test.
    Vitamin D's possible band genuinely starts at 0.0, so a zero first reading
    is a real input there and the division-by-zero path is exercised by a
    value that could actually arrive.
    """
    trend = trend_of("vitamin_d", [0.0, 10.0], "ng/ml")
    assert trend.change is not None
    assert trend.change.percent_change is None
    assert trend.stability is not None and trend.stability.exceeded is True


# --------------------------------------------------------------------------
# 4. Units are refused, never coerced
# --------------------------------------------------------------------------


def test_two_units_in_one_series_is_a_refusal_and_no_value_is_converted():
    """1.0 mg/dL and 88.4 umol/L are the same creatinine -- and this is still
    a refusal.

    Module 5 converts before storage, so a mismatch here means something
    upstream is wrong; converting here would hide it, and the two numbers
    compared raw would look like a 88-fold rise.
    """
    trend = analyse(
        [
            report(
                "r1",
                "2024-01-01T00:00:00Z",
                {"creatinine": vf("creatinine", 1.0, "mg/dl")},
            ),
            report(
                "r2",
                "2024-06-01T00:00:00Z",
                {"creatinine": vf("creatinine", 88.4, "umol/l")},
            ),
        ]
    ).features["creatinine"]

    assert trend.outcome == OUTCOME_UNIT_MISMATCH
    assert trend.trend is None
    assert trend.change is None
    assert [point.value for point in trend.points] == [1.0, 88.4]


def test_a_non_canonical_unit_refuses_rather_than_compares():
    trend = trend_of("creatinine", [88.4, 100.0], "umol/l")
    assert trend.outcome == OUTCOME_UNIT_NOT_CANONICAL
    assert trend.trend is None


def test_the_same_unit_written_two_ways_is_not_a_mismatch():
    """`mg/dL` and `mg/dl` are one unit typed twice; folding is comparison
    only and never rewrites what is returned to the caller."""
    trend = analyse(
        [
            report(
                "r1",
                "2024-01-01T00:00:00Z",
                {"creatinine": vf("creatinine", 0.9, "mg/dL")},
            ),
            report(
                "r2",
                "2024-06-01T00:00:00Z",
                {"creatinine": vf("creatinine", 1.6, "mg/dl")},
            ),
        ]
    ).features["creatinine"]

    assert trend.outcome == OUTCOME_TREND_CLASSIFIED
    assert trend.trend == TREND_WORSENING
    assert trend.points[0].unit == "mg/dL"


# --------------------------------------------------------------------------
# 5. Determinism
# --------------------------------------------------------------------------


def _stable_dump(data: Any) -> str:
    payload = data.model_dump(mode="json")
    payload.pop("generated_at", None)
    return json.dumps(payload, sort_keys=True)


def test_the_array_order_of_the_reports_cannot_change_the_output():
    """Byte-identical apart from `generated_at`, for a shuffled request.

    The sort key is (chrono_date, has-sequence, sequence, report_id) -- all
    properties of the data -- so two callers who assembled the same history in
    a different order cannot be told different things.
    """
    reports = [
        report("rc", "2024-06-01T00:00:00Z", {"hba1c": vf("hba1c", 6.8, "%")}),
        report("ra", "2024-01-01T00:00:00Z", {"hba1c": vf("hba1c", 6.1, "%")}),
        report("rb", "2024-03-01T00:00:00Z", {"hba1c": vf("hba1c", 6.4, "%")}),
    ]
    forward = analyse(reports)
    reversed_ = analyse(list(reversed(reports)))
    rotated = analyse(reports[1:] + reports[:1])

    assert _stable_dump(forward) == _stable_dump(reversed_) == _stable_dump(rotated)
    assert [ref.report_id for ref in forward.reports] == ["ra", "rb", "rc"]


def test_reports_sharing_a_date_are_ordered_by_the_data_and_warned_about():
    """Ties break on `report_id`, not on array position, and are declared."""
    first = analyse(
        [
            report("rB", "2024-01-01T00:00:00Z", {"hba1c": vf("hba1c", 7.0, "%")}),
            report("rA", "2024-01-01T00:00:00Z", {"hba1c": vf("hba1c", 6.0, "%")}),
        ]
    )
    second = analyse(
        [
            report("rA", "2024-01-01T00:00:00Z", {"hba1c": vf("hba1c", 6.0, "%")}),
            report("rB", "2024-01-01T00:00:00Z", {"hba1c": vf("hba1c", 7.0, "%")}),
        ]
    )
    assert [ref.report_id for ref in first.reports] == ["rA", "rB"]
    assert _stable_dump(first) == _stable_dump(second)
    assert first.features["hba1c"].change is not None
    assert first.features["hba1c"].change.first_value == 6.0
    assert any("share a date" in warning for warning in first.warnings)


def test_an_explicit_sequence_breaks_a_tie_ahead_of_the_report_id():
    """A caller who knows the real order can state it, and it is honoured."""
    data = analyse(
        [
            report(
                "rA",
                "2024-01-01T00:00:00Z",
                {"hba1c": vf("hba1c", 7.0, "%")},
                sequence=2,
            ),
            report(
                "rB",
                "2024-01-01T00:00:00Z",
                {"hba1c": vf("hba1c", 6.0, "%")},
                sequence=1,
            ),
        ]
    )
    assert [ref.report_id for ref in data.reports] == ["rB", "rA"]
    assert data.features["hba1c"].change is not None
    assert data.features["hba1c"].change.first_value == 6.0


def test_duplicate_report_ids_are_rejected_rather_than_double_counted():
    """A duplicate id makes the ordering ambiguous and double-counts a
    reading; both are refusals, not warnings."""
    with pytest.raises(Exception):
        TimelineTrendsRequest(
            reports=[
                report("r1", "2024-01-01T00:00:00Z", {"hba1c": vf("hba1c", 6.1, "%")}),
                report("r1", "2024-06-01T00:00:00Z", {"hba1c": vf("hba1c", 6.8, "%")}),
            ]
        )


def test_supplying_both_feature_sources_for_one_report_is_refused():
    """`validated` OR `snapshot` -- never both, because nothing is guessed."""
    with pytest.raises(Exception):
        TimelineTrendsRequest(
            reports=[
                {
                    "report_id": "r1",
                    "chrono_date": "2024-01-01T00:00:00Z",
                    "validated": {"valid": {}},
                    "snapshot": {"features": {}, "unavailable": {}},
                }
            ]
        )


# --------------------------------------------------------------------------
# 6. Summary and vocabulary
# --------------------------------------------------------------------------


def test_the_summary_counts_refusals_separately_from_findings():
    """`not_determinable` must carry the refusals; the three trend counts must
    not absorb them."""
    data = analyse(
        [
            report(
                "r1",
                "2024-01-01T00:00:00Z",
                {
                    "hba1c": vf("hba1c", 6.1, "%"),
                    "vitamin_d": vf("vitamin_d", 14.0, "ng/ml"),
                    "blood_glucose": vf("blood_glucose", 90.0, "mg/dl"),
                    "cholesterol": vf("cholesterol", 190.0, "mg/dl"),
                },
            ),
            report(
                "r2",
                "2024-06-01T00:00:00Z",
                {
                    "hba1c": vf("hba1c", 6.8, "%"),
                    "vitamin_d": vf("vitamin_d", 28.0, "ng/ml"),
                    "blood_glucose": vf("blood_glucose", 180.0, "mg/dl"),
                },
            ),
        ]
    )
    summary = data.summary
    assert summary.worsening == 1  # hba1c
    assert summary.improving == 1  # vitamin_d
    assert summary.stable == 0
    assert summary.not_determinable == 2  # glucose + the single-point cholesterol
    assert summary.features_examined == 4
    assert (
        summary.improving + summary.worsening + summary.stable
        + summary.not_determinable
        == summary.features_examined
    )
    assert sum(summary.outcomes.values()) == summary.features_examined


def test_every_emitted_outcome_is_in_the_declared_vocabulary():
    """A consumer branches on `outcome`; an undeclared code would fall through
    every branch it has."""
    data = analyse(
        [
            report(
                "r1",
                "2024-01-01T00:00:00Z",
                {"hba1c": vf("hba1c", 6.1, "%")},
            ),
            report(
                "r2",
                "2024-06-01T00:00:00Z",
                {"hba1c": vf("hba1c", 6.8, "%")},
            ),
        ],
        include_all_canonical=True,
    )
    for trend in data.features.values():
        assert trend.outcome in OUTCOME_VALUES
        assert trend.reason.strip()


def test_the_polarity_table_is_total_over_the_catalogue():
    """A canonical feature with no polarity row would force the analyzer to
    pick a default, and every default here is a silent clinical claim. The
    data file enforces this at import; asserted again so the reason is
    recorded where a reader of the tests will see it."""
    assert set(POLARITY) == set(CANONICAL_FEATURES)
    for name, entry in POLARITY.items():
        assert entry.basis.strip(), f"{name} declares no basis"
        if entry.trendable:
            assert name in STABILITY, f"{name} is trendable with no stability band"


def test_an_implausible_reading_takes_no_part_in_a_trend():
    """The `snapshot` door, which had no validation behind it.

    This module's docstring claimed a rejected value "cannot even reach here".
    That is true of the `validated` path, whose parse boundary discards
    rejected readings, and was FALSE of the `snapshot` path -- an audit walked
    `hba1c -1.0 -> -2.0` through it and got `improving`, a confident trend
    statement about two impossible numbers.

    The bound is Module 6's own (`validation_rules.rule_for`), not a second
    table written here, so the two cannot drift apart about what is
    physiologically possible.
    """
    trend = trend_of("hba1c", [-1.0, -2.0], "%")

    assert trend.trend is None
    assert trend.trend != TREND_IMPROVING
    assert trend.outcome == OUTCOME_INSUFFICIENT_DATA
    assert trend.usable_point_count == 0
    assert [gap.reason_code for gap in trend.gaps] == [
        "IMPLAUSIBLE_VALUE",
        "IMPLAUSIBLE_VALUE",
    ]
    # A gap has no value field at all, so the impossible numbers cannot be
    # read back out of the response either.
    assert "-1.0" not in json.dumps(trend.model_dump(mode="json"))


def test_one_implausible_reading_leaves_the_series_insufficient_not_wrong():
    """A single bad reading must not be silently dropped INTO a trend.

    With one real reading and one impossible one, the tempting wrong answers
    are to trend the pair anyway or to call the survivor `stable`. Both assert
    something nobody measured; the contract is INSUFFICIENT_DATA with the bad
    reading visible as a gap.
    """
    trend = trend_of("hemoglobin", [14.2, 900.0], "g/dl")

    assert trend.outcome == OUTCOME_INSUFFICIENT_DATA
    assert trend.trend is None
    assert trend.usable_point_count == 1
    assert [gap.reason_code for gap in trend.gaps] == ["IMPLAUSIBLE_VALUE"]


def test_a_real_reading_at_the_edge_of_the_possible_band_still_trends():
    """The guard must catch the impossible without refusing the extreme.

    A critically low haemoglobin of 3.0 g/dL is a real, survivable value and
    Module 6's band starts at 1.0. If this ever refuses, the guard has been
    tightened into a clinical judgement, which is not its job -- Module 8 owns
    "is this concerning", this owns "is this a measurement at all".

    The assertion is that both readings were USED, not that a trend came out:
    haemoglobin's polarity is deliberately UNDECLARED, so the honest outcome
    here is `CLINICAL_DIRECTION_UNKNOWN`. That refusal is about direction and
    is a different question from plausibility -- conflating the two is exactly
    what this test would fail to notice if it asserted the outcome instead.
    """
    trend = trend_of("hemoglobin", [3.0, 4.5], "g/dl")
    assert trend.usable_point_count == 2
    assert trend.gaps == []
    assert trend.outcome != OUTCOME_INSUFFICIENT_DATA

    # And one with a DECLARED polarity, at the low end of its possible band,
    # classifies normally.
    creatinine = trend_of("creatinine", [0.2, 0.4], "mg/dl")
    assert creatinine.usable_point_count == 2
    assert creatinine.gaps == []
