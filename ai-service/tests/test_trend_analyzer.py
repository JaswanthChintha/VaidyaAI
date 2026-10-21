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


_LEAKS = (
    "Module ",
    "EXTENSION POINT",
    "REFUSED ON PURPOSE",
    "app/data",
    ".py",
    "sample_timing",
    "()",
    "_CUTOFF",
)
from app.services.trend_analyzer import analyse_trends
from tests.trend_payloads import rejection, report, series_reports, vf


def analyse(reports: List[Dict[str, Any]], **options: Any):
    return analyse_trends(
        TimelineTrendsRequest(reports=reports, options=options)
    )


def trend_of(
    feature: str, values: List[Any], unit: Optional[str], **options: Any
) -> FeatureTrend:
    return analyse(series_reports(feature, values, unit), **options).features[
        feature
    ]


def test_a_single_usable_reading_is_insufficient_data_and_never_stable():
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
    assert [gap.report_id for gap in trend.gaps] == ["r2"]


def test_a_feature_absent_from_every_report_is_never_a_clean_bill():
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
    assert data.summary.worsening == 1
    assert data.summary.not_determinable == len(CANONICAL_FEATURES) - 1


def test_a_gap_structurally_cannot_carry_a_value():
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


def test_the_specifications_own_hba1c_example_is_worsening():
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
    assert trend_of("hba1c", [6.8, 6.1], "%").trend == TREND_IMPROVING
    assert trend_of("creatinine", [0.9, 1.6], "mg/dl").trend == TREND_WORSENING
    assert trend_of("creatinine", [1.6, 0.9], "mg/dl").trend == TREND_IMPROVING


def test_rising_vitamin_d_from_a_deficient_level_is_improving():
    improving = trend_of("vitamin_d", [14.0, 28.0], "ng/ml")
    assert improving.trend == TREND_IMPROVING
    assert improving.direction == "rising"
    assert improving.polarity is not None
    assert improving.polarity.kind == POLARITY_TOWARD_REFERENCE

    worsening = trend_of("vitamin_d", [95.0, 140.0], "ng/ml")
    assert worsening.trend == TREND_WORSENING
    assert worsening.direction == "rising"


def test_a_change_wholly_inside_the_declared_interval_makes_no_claim():
    trend = trend_of("vitamin_d", [35.0, 95.0], "ng/ml")
    assert trend.outcome == OUTCOME_CHANGE_WITHIN_REFERENCE_INTERVAL
    assert trend.trend is None
    assert trend.direction == "rising"
    assert trend.stability is not None and trend.stability.exceeded is True


def test_crossing_the_whole_interval_is_refused_rather_than_labelled():
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
    trend = trend_of(feature, values, unit)
    assert trend.outcome == OUTCOME_CLINICAL_DIRECTION_UNKNOWN
    assert trend.trend is None
    assert trend.direction == "rising"
    assert trend.change is not None and trend.change.absolute_change > 0
    assert trend.polarity is not None
    assert trend.polarity.kind == POLARITY_UNDECLARED
    assert trend.polarity.direction_of_harm is None
    assert "the direction of change is" not in trend.reason
    assert "whether the change is favourable is not reported" in trend.reason
    for token in _LEAKS:
        assert token not in trend.reason, f"{feature}: reason contains {token!r}" 


@pytest.mark.parametrize(
    "feature",
    sorted(
        name
        for name, entry in POLARITY.items()
        if entry.kind == POLARITY_UNDECLARED and entry.trendable
    ),
)
def test_no_undeclared_feature_can_ever_be_classified(feature):
    unit = FEATURES[feature].canonical_unit
    rule = rule_for(feature)
    low = rule.possible_low if rule and rule.possible_low is not None else 1.0
    high = rule.possible_high if rule and rule.possible_high is not None else 1000.0
    small = low + (high - low) * 0.1
    large = low + (high - low) * 0.9

    rising = trend_of(feature, [small, large], unit)
    falling = trend_of(feature, [large, small], unit)
    assert rising.trend is None and falling.trend is None
    assert rising.outcome == OUTCOME_CLINICAL_DIRECTION_UNKNOWN
    assert falling.outcome == OUTCOME_CLINICAL_DIRECTION_UNKNOWN


def test_non_numeric_and_non_trendable_features_refuse_with_their_own_codes():
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


def test_stable_requires_clearing_both_thresholds_not_either():
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
    trend = trend_of("hba1c", [6.1, 6.2], "%")
    assert trend.trend == TREND_STABLE
    assert trend.stability is not None
    assert trend.stability.significant_change_pct == 8.0
    assert trend.stability.min_absolute_change == 0.2
    assert trend.stability.source == "app/data/trend_polarity.py"
    assert "8 % and 0.2" in trend.reason


@pytest.mark.parametrize("feature", sorted(STABILITY))
def test_every_band_claiming_to_be_an_rcv_recomputes_to_its_stated_value(feature):
    band = STABILITY[feature]
    if band.analytical_cv_pct is None or band.within_subject_cv_pct is None:
        pytest.skip(f"{feature}: stated as a reviewer judgement, not an RCV")
    computed = reference_change_value(
        band.analytical_cv_pct, band.within_subject_cv_pct
    )
    assert computed == pytest.approx(band.significant_change_pct, abs=0.6)


def test_a_reversal_inside_the_series_is_flagged_rather_than_absorbed():
    trend = trend_of("hba1c", [6.1, 7.5, 6.8], "%")
    assert trend.trend == TREND_WORSENING
    assert trend.change is not None
    assert trend.change.volatile is True
    assert trend.change.direction_consistency == 0.5
    assert trend.change.max_value == 7.5
    assert "opposite direction" in trend.reason


def test_a_zero_first_value_gives_a_null_percentage_not_infinity():
    trend = trend_of("vitamin_d", [0.0, 10.0], "ng/ml")
    assert trend.change is not None
    assert trend.change.percent_change is None
    assert trend.stability is not None and trend.stability.exceeded is True


def test_two_units_in_one_series_is_a_refusal_and_no_value_is_converted():
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


def _stable_dump(data: Any) -> str:
    payload = data.model_dump(mode="json")
    payload.pop("generated_at", None)
    return json.dumps(payload, sort_keys=True)


def test_the_array_order_of_the_reports_cannot_change_the_output():
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
    with pytest.raises(Exception):
        TimelineTrendsRequest(
            reports=[
                report("r1", "2024-01-01T00:00:00Z", {"hba1c": vf("hba1c", 6.1, "%")}),
                report("r1", "2024-06-01T00:00:00Z", {"hba1c": vf("hba1c", 6.8, "%")}),
            ]
        )


def test_supplying_both_feature_sources_for_one_report_is_refused():
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


def test_the_summary_counts_refusals_separately_from_findings():
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
    assert summary.worsening == 1
    assert summary.improving == 1
    assert summary.stable == 0
    assert summary.not_determinable == 2
    assert summary.features_examined == 4
    assert (
        summary.improving + summary.worsening + summary.stable
        + summary.not_determinable
        == summary.features_examined
    )
    assert sum(summary.outcomes.values()) == summary.features_examined


def test_every_emitted_outcome_is_in_the_declared_vocabulary():
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
    assert set(POLARITY) == set(CANONICAL_FEATURES)
    for name, entry in POLARITY.items():
        assert entry.basis.strip(), f"{name} declares no basis"
        if entry.trendable:
            assert name in STABILITY, f"{name} is trendable with no stability band"


def test_an_implausible_reading_takes_no_part_in_a_trend():
    trend = trend_of("hba1c", [-1.0, -2.0], "%")

    assert trend.trend is None
    assert trend.trend != TREND_IMPROVING
    assert trend.outcome == OUTCOME_INSUFFICIENT_DATA
    assert trend.usable_point_count == 0
    assert [gap.reason_code for gap in trend.gaps] == [
        "IMPLAUSIBLE_VALUE",
        "IMPLAUSIBLE_VALUE",
    ]
    assert "-1.0" not in json.dumps(trend.model_dump(mode="json"))


def test_one_implausible_reading_leaves_the_series_insufficient_not_wrong():
    trend = trend_of("hemoglobin", [14.2, 900.0], "g/dl")

    assert trend.outcome == OUTCOME_INSUFFICIENT_DATA
    assert trend.trend is None
    assert trend.usable_point_count == 1
    assert [gap.reason_code for gap in trend.gaps] == ["IMPLAUSIBLE_VALUE"]


def test_a_real_reading_at_the_edge_of_the_possible_band_still_trends():
    trend = trend_of("hemoglobin", [3.0, 4.5], "g/dl")
    assert trend.usable_point_count == 2
    assert trend.gaps == []
    assert trend.outcome != OUTCOME_INSUFFICIENT_DATA

    creatinine = trend_of("creatinine", [0.2, 0.4], "mg/dl")
    assert creatinine.usable_point_count == 2
    assert creatinine.gaps == []


@pytest.mark.parametrize("feature", sorted(POLARITY))
def test_no_reader_facing_reason_leaks_the_maintainer_note(feature):
    from app.data.trend_polarity import reader_reason

    text = reader_reason(POLARITY[feature])
    assert text.strip()
    for token in _LEAKS:
        assert token not in text, f"{feature}: reader text contains {token!r}"


def test_the_fallback_is_generic_rather_than_the_maintainer_note(monkeypatch):
    from app.data.trend_polarity import TrendPolarity, reader_reason

    bare = TrendPolarity(
        "made_up",
        POLARITY_UNDECLARED,
        basis="REFUSED ON PURPOSE. See app/data/clinical_rules.py, Module 8.",
    )
    text = reader_reason(bare)
    assert "app/data" not in text
    assert "Module " not in text
    assert "improvement" in text


_DECLARED = sorted(
    name for name, entry in POLARITY.items() if entry.kind != POLARITY_UNDECLARED
)


def test_the_declared_entries_are_the_ones_this_section_is_about():
    assert _DECLARED == [
        "alt", "ast", "bilirubin_total",
        "bmi", "cholesterol", "creatinine", "hba1c",
        "triglycerides", "vitamin_b12", "vitamin_d",
    ]


@pytest.mark.parametrize("feature", _DECLARED)
def test_a_declared_polarity_is_never_explained_as_undeclared(feature):
    from app.data.trend_polarity import reader_reason

    text = reader_reason(POLARITY[feature])
    assert "does not declare" not in text
    assert "not reported" not in text
    for token in _LEAKS:
        assert token not in text, f"{feature}: {token!r}"


@pytest.mark.parametrize(
    "feature",
    ["hba1c", "creatinine", "cholesterol", "triglycerides", "alt", "ast", "bilirubin_total"],
)
def test_a_monotone_explanation_names_the_direction_declared(feature):
    from app.data.trend_polarity import reader_reason

    text = reader_reason(POLARITY[feature])
    assert "counts a rise in this measurement as unfavourable" in text
    assert "a fall as favourable" in text


def test_a_monotone_decrease_would_be_said_the_other_way_round():
    from app.data.trend_polarity import HARM_DECREASE, TrendPolarity, reader_reason

    text = reader_reason(
        TrendPolarity("made_up", POLARITY_MONOTONE, basis="x", direction_of_harm=HARM_DECREASE)
    )
    assert "counts a fall in this measurement as unfavourable" in text


@pytest.mark.parametrize(
    "feature, interval, crossing",
    [
        ("vitamin_d", "the range 30 to 100 ng/ml", True),
        ("bmi", "the range 18.5 to 24.9 kg/m2", True),
        ("vitamin_b12", "200 pg/ml or above", False),
    ],
)
def test_a_toward_reference_explanation_states_its_own_interval(feature, interval, crossing):
    from app.data.trend_polarity import reader_reason

    text = reader_reason(POLARITY[feature])
    assert f"moves closer to {interval}" in text
    assert ("one side of it to the other" in text) is crossing


def test_the_hba1c_payload_basis_agrees_with_its_declaration():
    trend = trend_of("hba1c", [5.4, 7.0], "%")
    assert trend.polarity.kind == POLARITY_MONOTONE
    assert trend.polarity.direction_of_harm == "increase"
    assert "counts a rise in this measurement as unfavourable" in trend.polarity.basis


def test_a_refused_glucose_series_explains_itself_without_jargon():
    from app.data.trend_polarity import POLARITY, reader_reason

    text = reader_reason(POLARITY["blood_glucose"])
    assert "fasting" in text
    assert "too low" in text
    for token in _LEAKS:
        assert token not in text


@pytest.mark.parametrize(
    "feature",
    sorted(
        name
        for name, entry in POLARITY.items()
        if entry.kind == POLARITY_UNDECLARED and entry.trendable
    ),
)
def test_the_rendered_reason_is_clean_for_every_undeclared_feature(feature):
    trend = trend_of(feature, [10.0, 40.0], "mg/dl")
    assert trend.reason
    for token in _LEAKS:
        assert token not in trend.reason, f"{feature}: {token!r} in reason"


def test_the_feature_field_is_the_canonical_key_not_a_display_name():
    from app.data.feature_catalog import CANONICAL_FEATURES, FEATURES

    data = analyse(series_reports('hba1c', [8.4, 5.4, 5.2], '%'))
    assert data.features, "expected at least one analysed feature"

    for key, trend in data.features.items():
        assert trend.feature == key
        assert trend.feature in CANONICAL_FEATURES
        label = FEATURES[key].description
        if label != key:
            assert trend.feature != label


def test_the_reader_facing_reason_uses_the_label_not_the_key():
    from app.data.feature_catalog import FEATURES

    scenarios = [
        series_reports('blood_glucose', [186.0, 120.0, 88.0], 'mg/dl'),
        series_reports('hba1c', [6.1], '%'),
        series_reports('smoking_history', ['never', 'never'], None),
        [
            report('r1', '2024-01-01T00:00:00Z',
                   {'creatinine': vf('creatinine', 1.1, 'mg/dl')}),
            report('r2', '2024-02-01T00:00:00Z',
                   {'creatinine': vf('creatinine', 97.0, 'umol/l')}),
        ],
    ]

    snake_keys = [k for k in FEATURES if "_" in k]

    seen = 0
    for reports in scenarios:
        data = analyse(reports)
        for key, trend in data.features.items():
            if not trend.reason:
                continue
            text = trend.reason.lstrip()

            for leaked in snake_keys:
                assert leaked not in text, (
                    f"reason for {key!r} names the canonical key {leaked!r}: "
                    f"{trend.reason!r}"
                )

            for prefix in (f"{key} ", f"{key}:"):
                assert not text.startswith(prefix), (
                    f"reason for {key!r} OPENS with the canonical key: "
                    f"{trend.reason!r}"
                )
            seen += 1

    assert seen, "no reason sentence was exercised -- the test proved nothing"
