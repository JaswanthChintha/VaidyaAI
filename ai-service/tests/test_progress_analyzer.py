from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from app.data.feature_catalog import CANONICAL_FEATURES
from app.data.progress_scoring import (
    BANDS,
    CATEGORY_POINTS,
    EXCLUDED_DIRECTION_UNDECLARED,
    EXCLUDED_NOT_CLASSIFIABLE,
    EXCLUSION_REASON_CODES,
    MINIMUM_CONTRIBUTING_PARAMETERS,
    NEUTRAL_ANCHOR,
    NON_CONTRIBUTING_CATEGORIES,
    SCALE_DIRECTION,
    SCALE_MAX,
    SCALE_MIN,
    SCORE_DECIMAL_PLACES,
    WEIGHTS,
    band_for,
    points_for,
    scoring_document,
    weight_for,
)
from app.data.trend_polarity import POLARITY, POLARITY_UNDECLARED
from app.schemas.comparison import (
    CATEGORY_IMPROVED,
    CATEGORY_NEWLY_ABNORMAL,
    CATEGORY_NEWLY_NORMAL,
    CATEGORY_UNCHANGED,
    CATEGORY_VALUES,
    CATEGORY_WORSENED,
)
from app.schemas.progress import (
    PROGRESS_INSUFFICIENT_COVERAGE,
    PROGRESS_NOTHING_ASSESSED,
    PROGRESS_NO_PAIR,
    PROGRESS_OUTCOME_VALUES,
    PROGRESS_SCORE_COMPUTED,
    ExcludedParameter,
    HealthProgressRequest,
)
from app.services.progress_analyzer import analyse_progress, progress_document


def value(
    name: str,
    number: Any,
    unit: Optional[str] = None,
    *,
    canonical: bool = True,
    ref_low: Optional[float] = None,
    ref_high: Optional[float] = None,
) -> Dict[str, Any]:
    provenance: Dict[str, Any] = {"source": "lab_report"}
    if ref_low is not None:
        provenance["reference_low"] = ref_low
    if ref_high is not None:
        provenance["reference_high"] = ref_high
    return {
        "name": name,
        "value": number,
        "unit": unit,
        "canonical_unit": canonical,
        "source": "lab_report",
        "provenance": provenance,
    }


def snapshot(report_id: str, date: str, **values: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "report_id": report_id,
        "chrono_date": date,
        "validated": {"valid": dict(values)},
    }


EARLIER = "2025-01-01T00:00:00Z"
LATER = "2025-07-01T00:00:00Z"


def analyse(reports: List[Dict[str, Any]], **extra: Any):
    return analyse_progress(
        HealthProgressRequest.model_validate({"reports": reports, **extra})
    )


def mixed_pair() -> List[Dict[str, Any]]:
    return [
        snapshot(
            "r1",
            EARLIER,
            hba1c=value("hba1c", 7.8, "%", ref_low=4.0, ref_high=5.6),
            creatinine=value("creatinine", 1.4, "mg/dl", ref_low=0.7, ref_high=1.3),
            cholesterol=value("cholesterol", 240.0, "mg/dl", ref_high=200.0),
            triglycerides=value("triglycerides", 300.0, "mg/dl", ref_high=150.0),
            vitamin_d=value("vitamin_d", 15.0, "ng/ml", ref_low=30.0, ref_high=100.0),
            vitamin_b12=value(
                "vitamin_b12", 300.0, "pg/ml", ref_low=200.0, ref_high=900.0
            ),
            bmi=value("bmi", 31.0, "kg/m2"),
        ),
        snapshot(
            "r2",
            LATER,
            hba1c=value("hba1c", 6.0, "%", ref_low=4.0, ref_high=5.6),
            creatinine=value("creatinine", 1.9, "mg/dl", ref_low=0.7, ref_high=1.3),
            cholesterol=value("cholesterol", 190.0, "mg/dl", ref_high=200.0),
            triglycerides=value("triglycerides", 298.0, "mg/dl", ref_high=150.0),
            vitamin_d=value("vitamin_d", 45.0, "ng/ml", ref_low=30.0, ref_high=100.0),
            vitamin_b12=value(
                "vitamin_b12", 305.0, "pg/ml", ref_low=200.0, ref_high=900.0
            ),
            bmi=value("bmi", 30.9, "kg/m2"),
        ),
    ]


def uniform_pair(baseline: Dict[str, Any], comparison: Dict[str, Any]):
    return [
        snapshot("r1", EARLIER, **baseline),
        snapshot("r2", LATER, **comparison),
    ]


STEADY_BASELINE = {
    "hba1c": value("hba1c", 5.0, "%", ref_low=4.0, ref_high=5.6),
    "creatinine": value("creatinine", 0.8, "mg/dl", ref_low=0.7, ref_high=1.3),
    "cholesterol": value("cholesterol", 150.0, "mg/dl", ref_high=200.0),
}


def test_the_five_anchors_are_equally_spaced():
    by_rank = sorted(CATEGORY_POINTS.values(), key=lambda e: e.rank)
    steps = {
        round(higher.points - lower.points, 9)
        for lower, higher in zip(by_rank, by_rank[1:])
    }
    assert len(steps) == 1, f"anchor spacing is not equal: {sorted(steps)}"
    assert steps == {25.0}


def test_the_anchor_scale_spans_the_declared_range_and_is_strictly_ordered():
    by_rank = sorted(CATEGORY_POINTS.values(), key=lambda e: e.rank)
    assert [e.rank for e in by_rank] == list(range(1, len(CATEGORY_POINTS) + 1))
    assert [e.points for e in by_rank] == sorted(e.points for e in by_rank)
    assert len(set(e.points for e in by_rank)) == len(by_rank)
    assert by_rank[0].points == SCALE_MIN
    assert by_rank[-1].points == SCALE_MAX
    assert by_rank[0].category == CATEGORY_NEWLY_ABNORMAL
    assert by_rank[-1].category == CATEGORY_NEWLY_NORMAL


def test_unchanged_sits_on_the_neutral_anchor_and_nothing_else_does():
    assert CATEGORY_POINTS[CATEGORY_UNCHANGED].points == NEUTRAL_ANCHOR == 50.0
    on_neutral = [
        e.category for e in CATEGORY_POINTS.values() if e.points == NEUTRAL_ANCHOR
    ]
    assert on_neutral == [CATEGORY_UNCHANGED]


def test_every_module_29_category_has_a_decision_and_none_has_two():
    on_scale = set(CATEGORY_POINTS)
    off_scale = set(NON_CONTRIBUTING_CATEGORIES)
    assert on_scale | off_scale == set(CATEGORY_VALUES)
    assert on_scale & off_scale == set()
    for entry in NON_CONTRIBUTING_CATEGORIES.values():
        assert entry.reason_code in EXCLUSION_REASON_CODES
        assert entry.basis.strip()


def test_the_weight_table_is_total_over_the_catalogue():
    assert set(WEIGHTS) == set(CANONICAL_FEATURES)
    for name, entry in WEIGHTS.items():
        assert entry.feature == name
        assert entry.weight >= 0.0
        assert entry.basis.strip(), f"{name} states no basis for its weight"


def test_the_non_zero_weights_are_exactly_the_trendable_features():
    non_zero = {name for name, e in WEIGHTS.items() if e.weight > 0.0}
    trendable = {name for name, p in POLARITY.items() if p.trendable}
    assert non_zero == trendable
    assert len(non_zero) == 24, sorted(non_zero)
    assert {name for name, e in WEIGHTS.items() if e.weight == 0.0} == (
        set(CANONICAL_FEATURES) - trendable
    )


def test_every_declared_polarity_feature_can_reach_the_score():
    scorable = [
        name
        for name, p in POLARITY.items()
        if p.trendable and p.kind != POLARITY_UNDECLARED
    ]
    assert len(scorable) == 10, sorted(scorable)
    for name in scorable:
        assert WEIGHTS[name].weight > 0.0, f"{name} is silently dropped"


def test_all_weights_are_equal_so_no_parameter_outranks_another():
    weights = {e.weight for e in WEIGHTS.values() if e.weight > 0.0}
    assert weights == {1.0}


def test_the_bands_tile_the_whole_scale_exactly_once():
    assert BANDS[0].lower == SCALE_MIN
    assert BANDS[-1].upper == SCALE_MAX
    for lower, higher in zip(BANDS, BANDS[1:]):
        assert lower.upper == higher.lower, f"gap/overlap at {lower.key}"
    for band in BANDS:
        assert band.upper > band.lower
        assert band.label.strip() and band.description.strip()
    assert len({b.key for b in BANDS}) == len(BANDS)


def test_each_anchor_gets_its_own_band_and_none_sits_on_an_interior_boundary():
    seen: Dict[str, str] = {}
    for entry in CATEGORY_POINTS.values():
        band = band_for(entry.points)
        interior_lower = entry.points == band.lower and band.lower != SCALE_MIN
        interior_upper = entry.points == band.upper and band is not BANDS[-1]
        assert not interior_lower and not interior_upper, (
            f"anchor {entry.points} ({entry.category}) is on an interior boundary"
        )
        assert band.key not in seen, (
            f"{entry.category} shares band {band.key} with {seen.get(band.key)}"
        )
        seen[band.key] = entry.category
    assert len(seen) == len(BANDS) == 5


def test_band_lookup_is_lower_inclusive_upper_exclusive_and_bands_100():
    assert band_for(0.0).key == BANDS[0].key
    assert band_for(19.9).key == BANDS[0].key
    assert band_for(20.0).key == BANDS[1].key
    assert band_for(39.9).key == BANDS[1].key
    assert band_for(40.0).key == BANDS[2].key
    assert band_for(59.9).key == BANDS[2].key
    assert band_for(60.0).key == BANDS[3].key
    assert band_for(79.9).key == BANDS[3].key
    assert band_for(80.0).key == BANDS[4].key
    assert band_for(100.0).key == BANDS[-1].key


def test_band_lookup_refuses_a_score_outside_the_scale_rather_than_guessing():
    for bad in (-0.1, 100.1):
        with pytest.raises(ValueError):
            band_for(bad)


def test_the_coverage_floor_enforces_the_rule_it_states():
    assert MINIMUM_CONTRIBUTING_PARAMETERS >= 3
    assert 1.0 / MINIMUM_CONTRIBUTING_PARAMETERS <= 0.5


def test_rounding_happens_before_banding_so_number_and_band_never_disagree():
    from itertools import combinations_with_replacement

    anchors = [e.points for e in CATEGORY_POINTS.values()]
    checked = 0
    for n in range(MINIMUM_CONTRIBUTING_PARAMETERS, 10):
        for combo in combinations_with_replacement(anchors, n):
            score = round(sum(combo) / n, SCORE_DECIMAL_PLACES)
            band = band_for(score)
            assert band.lower <= score <= band.upper
            if score != SCALE_MAX:
                assert score < band.upper
            checked += 1
    assert checked > 1000


def test_lookup_helpers_return_none_rather_than_a_default():
    assert points_for("no_such_category") is None
    assert weight_for("no_such_feature") is None
    for name in CATEGORY_VALUES:
        assert (points_for(name) is None) == (name in NON_CONTRIBUTING_CATEGORIES)


def test_scoring_document_publishes_the_same_numbers_the_scorer_uses():
    doc = scoring_document()
    assert doc["scale"]["min"] == SCALE_MIN
    assert doc["scale"]["max"] == SCALE_MAX
    assert doc["scale"]["direction"] == SCALE_DIRECTION == "higher_is_better"
    assert doc["scale"]["neutral_anchor"] == NEUTRAL_ANCHOR
    assert len(doc["bands"]) == len(BANDS)
    assert set(doc["category_points"]) == set(CATEGORY_POINTS)
    for name, entry in CATEGORY_POINTS.items():
        assert doc["category_points"][name]["points"] == entry.points
    assert set(doc["weights"]) == set(WEIGHTS)
    for name, entry in WEIGHTS.items():
        assert doc["weights"][name]["weight"] == entry.weight
    assert doc["minimum_contributing_parameters"] == MINIMUM_CONTRIBUTING_PARAMETERS
    assert doc["calls_an_llm"] is False
    assert doc["makes_clinical_claims"] is False


def test_every_declared_outcome_is_reachable_and_only_one_carries_a_score():
    assert set(PROGRESS_OUTCOME_VALUES) == {
        PROGRESS_SCORE_COMPUTED,
        PROGRESS_NO_PAIR,
        PROGRESS_NOTHING_ASSESSED,
        PROGRESS_INSUFFICIENT_COVERAGE,
    }


def test_score_computed_carries_the_hand_checkable_weighted_mean():
    data = analyse(mixed_pair())
    assert data.outcome == PROGRESS_SCORE_COMPUTED

    assert data.coverage.contributing_count == 6
    assert {e.feature for e in data.coverage.excluded} == {"bmi"}
    assert data.score == 66.7
    assert data.band is not None
    assert data.band.key == "more_favourable_than_unfavourable"
    assert data.band.lower_inclusive <= data.score < data.band.upper_exclusive
    assert sum(c.weighted_points for c in data.contributions) == 400.0
    assert {c.points for c in data.contributions} <= {
        e.points for e in CATEGORY_POINTS.values()
    }


@pytest.mark.parametrize(
    "baseline,comparison,expected_score,expected_band,expected_category",
    [
        (
            STEADY_BASELINE,
            {
                "hba1c": value("hba1c", 9.0, "%", ref_low=4.0, ref_high=5.6),
                "creatinine": value(
                    "creatinine", 2.2, "mg/dl", ref_low=0.7, ref_high=1.3
                ),
                "cholesterol": value("cholesterol", 280.0, "mg/dl", ref_high=200.0),
            },
            0.0,
            "predominantly_unfavourable",
            CATEGORY_NEWLY_ABNORMAL,
        ),
        (
            STEADY_BASELINE,
            {
                "hba1c": value("hba1c", 5.4, "%", ref_low=4.0, ref_high=5.6),
                "creatinine": value(
                    "creatinine", 1.1, "mg/dl", ref_low=0.7, ref_high=1.3
                ),
                "cholesterol": value("cholesterol", 190.0, "mg/dl", ref_high=200.0),
            },
            25.0,
            "more_unfavourable_than_favourable",
            CATEGORY_WORSENED,
        ),
        (
            STEADY_BASELINE,
            {
                "hba1c": value("hba1c", 5.01, "%", ref_low=4.0, ref_high=5.6),
                "creatinine": value(
                    "creatinine", 0.801, "mg/dl", ref_low=0.7, ref_high=1.3
                ),
                "cholesterol": value("cholesterol", 150.1, "mg/dl", ref_high=200.0),
            },
            50.0,
            "mixed_or_little_movement",
            CATEGORY_UNCHANGED,
        ),
        (
            {
                "hba1c": value("hba1c", 9.0, "%", ref_low=4.0, ref_high=5.6),
                "creatinine": value(
                    "creatinine", 2.2, "mg/dl", ref_low=0.7, ref_high=1.3
                ),
                "cholesterol": value("cholesterol", 280.0, "mg/dl", ref_high=200.0),
            },
            {
                "hba1c": value("hba1c", 5.0, "%", ref_low=4.0, ref_high=5.6),
                "creatinine": value(
                    "creatinine", 0.9, "mg/dl", ref_low=0.7, ref_high=1.3
                ),
                "cholesterol": value("cholesterol", 150.0, "mg/dl", ref_high=200.0),
            },
            100.0,
            "predominantly_favourable",
            CATEGORY_NEWLY_NORMAL,
        ),
    ],
)
def test_each_anchor_lands_in_its_own_band_end_to_end(
    baseline, comparison, expected_score, expected_band, expected_category
):
    data = analyse(uniform_pair(baseline, comparison))
    assert data.outcome == PROGRESS_SCORE_COMPUTED
    assert {c.category for c in data.contributions} == {expected_category}
    assert data.score == expected_score
    assert data.band is not None and data.band.key == expected_band


def test_a_worsened_run_and_an_unchanged_run_never_share_a_band_label():
    worsened = analyse(
        uniform_pair(
            STEADY_BASELINE,
            {
                "hba1c": value("hba1c", 5.4, "%", ref_low=4.0, ref_high=5.6),
                "creatinine": value(
                    "creatinine", 1.1, "mg/dl", ref_low=0.7, ref_high=1.3
                ),
                "cholesterol": value("cholesterol", 190.0, "mg/dl", ref_high=200.0),
            },
        )
    )
    unchanged = analyse(
        uniform_pair(
            STEADY_BASELINE,
            {
                "hba1c": value("hba1c", 5.01, "%", ref_low=4.0, ref_high=5.6),
                "creatinine": value(
                    "creatinine", 0.801, "mg/dl", ref_low=0.7, ref_high=1.3
                ),
                "cholesterol": value("cholesterol", 150.1, "mg/dl", ref_high=200.0),
            },
        )
    )
    assert worsened.band is not None and unchanged.band is not None
    assert worsened.band.key != unchanged.band.key
    assert worsened.band.label != unchanged.band.label


@pytest.mark.parametrize("reports", [[], [snapshot("only", EARLIER, **STEADY_BASELINE)]])
def test_fewer_than_two_reports_is_no_pair_with_no_number(reports):
    data = analyse(reports)
    assert data.outcome == PROGRESS_NO_PAIR
    assert data.score is None
    assert data.band is None
    assert data.pair is None
    assert data.coverage.features_examined == 0
    assert data.coverage.contributing_count == 0
    assert not data.coverage.sufficient
    assert "Fewer than two reports" in data.summary.headline


def test_nothing_assessed_produces_no_score_and_says_so_in_words():
    data = analyse(
        uniform_pair(
            {
                "blood_glucose": value(
                    "blood_glucose", 180.0, "mg/dl", ref_low=70.0, ref_high=99.0
                ),
                "hemoglobin": value(
                    "hemoglobin", 10.0, "g/dl", ref_low=13.0, ref_high=17.0
                ),
                "age": value("age", 50, "years"),
                "gender": value("gender", "male"),
            },
            {
                "blood_glucose": value(
                    "blood_glucose", 140.0, "mg/dl", ref_low=70.0, ref_high=99.0
                ),
                "hemoglobin": value(
                    "hemoglobin", 11.5, "g/dl", ref_low=13.0, ref_high=17.0
                ),
                "age": value("age", 51, "years"),
                "gender": value("gender", "male"),
            },
        )
    )
    assert data.outcome == PROGRESS_NOTHING_ASSESSED
    assert data.score is None
    assert data.band is None
    assert data.pair is not None, "two reports WERE compared"
    assert data.coverage.features_examined == 4
    assert data.coverage.contributing_count == 0
    assert data.coverage.excluded_count == 4
    assert data.contributions == []
    text = " ".join([data.summary.headline, *data.summary.lines]).lower()
    assert "not one of the 4 parameter(s) examined could be placed" in (
        data.summary.headline
    )
    assert "stable" not in text
    assert "no change" not in text
    assert any("not a statement that nothing changed" in w for w in data.warnings)


def test_below_the_coverage_floor_the_contributions_are_returned_but_no_number_is():
    data = analyse(
        uniform_pair(
            {
                "hba1c": value("hba1c", 7.8, "%", ref_low=4.0, ref_high=5.6),
                "creatinine": value(
                    "creatinine", 1.4, "mg/dl", ref_low=0.7, ref_high=1.3
                ),
            },
            {
                "hba1c": value("hba1c", 6.0, "%", ref_low=4.0, ref_high=5.6),
                "creatinine": value(
                    "creatinine", 1.9, "mg/dl", ref_low=0.7, ref_high=1.3
                ),
            },
        )
    )
    assert data.outcome == PROGRESS_INSUFFICIENT_COVERAGE
    assert data.score is None
    assert data.band is None
    assert data.coverage.contributing_count == 2
    assert data.coverage.minimum_required == MINIMUM_CONTRIBUTING_PARAMETERS
    assert not data.coverage.sufficient
    assert len(data.contributions) == 2
    assert {c.feature for c in data.contributions} == {"hba1c", "creatinine"}
    assert all(c.points in {e.points for e in CATEGORY_POINTS.values()}
               for c in data.contributions)


@pytest.mark.parametrize(
    "outcome_case",
    ["no_pair", "nothing_assessed", "insufficient"],
)
def test_no_refusal_ever_carries_a_score_or_a_band(outcome_case):
    if outcome_case == "no_pair":
        data = analyse([snapshot("only", EARLIER, **STEADY_BASELINE)])
    elif outcome_case == "nothing_assessed":
        data = analyse(
            uniform_pair(
                {"age": value("age", 50, "years")},
                {"age": value("age", 51, "years")},
            )
        )
    else:
        data = analyse(
            uniform_pair(
                {"hba1c": value("hba1c", 7.8, "%", ref_low=4.0, ref_high=5.6)},
                {"hba1c": value("hba1c", 6.0, "%", ref_low=4.0, ref_high=5.6)},
            )
        )
    assert data.outcome != PROGRESS_SCORE_COMPUTED
    assert data.score is None
    assert data.band is None
    assert data.score != NEUTRAL_ANCHOR
    assert data.scale.direction == SCALE_DIRECTION
    assert len(data.scale.bands) == len(BANDS)
    assert data.coverage is not None


def test_the_response_model_refuses_a_refusal_that_acquired_a_number():
    data = analyse([snapshot("only", EARLIER, **STEADY_BASELINE)])
    payload = data.model_dump(mode="json")
    assert payload["outcome"] == PROGRESS_NO_PAIR
    payload["score"] = 50.0
    with pytest.raises(Exception) as excinfo:
        type(data).model_validate(payload)
    assert "must carry score=None" in str(excinfo.value)


def test_the_response_model_refuses_a_computed_outcome_with_no_number():
    data = analyse(mixed_pair())
    payload = data.model_dump(mode="json")
    payload["score"] = None
    payload["band"] = None
    with pytest.raises(Exception) as excinfo:
        type(data).model_validate(payload)
    assert "requires a score" in str(excinfo.value)


def test_excluded_parameter_has_no_points_weight_or_weighted_points_field():
    fields = set(ExcludedParameter.model_fields)
    assert "points" not in fields
    assert "weight" not in fields
    assert "weighted_points" not in fields
    assert fields == {
        "feature",
        "description",
        "category",
        "outcome",
        "transition_outcome",
        "reason_code",
        "reason",
    }


def test_an_exclusion_cannot_be_given_points_by_a_caller():
    with pytest.raises(Exception):
        ExcludedParameter(
            feature="creatinine",
            description="Serum creatinine",
            category="not_classifiable",
            outcome="UNIT_MISMATCH",
            transition_outcome="NOT_DETERMINABLE_BOTH",
            reason_code=EXCLUDED_NOT_CLASSIFIABLE,
            reason="excluded",
            points=50.0,
        )


def test_a_unit_mismatched_parameter_is_excluded_not_scored_as_neutral():
    data = analyse(
        [
            snapshot(
                "r1",
                EARLIER,
                hba1c=value("hba1c", 7.8, "%", ref_low=4.0, ref_high=5.6),
                creatinine=value("creatinine", 1.4, "mg/dl", ref_low=0.7, ref_high=1.3),
                cholesterol=value("cholesterol", 240.0, "mg/dl", ref_high=200.0),
                triglycerides=value("triglycerides", 300.0, "mg/dl", ref_high=150.0),
            ),
            snapshot(
                "r2",
                LATER,
                hba1c=value("hba1c", 6.0, "%", ref_low=4.0, ref_high=5.6),
                creatinine=value(
                    "creatinine",
                    168.0,
                    "umol/l",
                    canonical=False,
                    ref_low=62.0,
                    ref_high=106.0,
                ),
                cholesterol=value("cholesterol", 190.0, "mg/dl", ref_high=200.0),
                triglycerides=value("triglycerides", 120.0, "mg/dl", ref_high=150.0),
            ),
        ]
    )
    excluded = {item.feature: item for item in data.coverage.excluded}
    assert "creatinine" in excluded
    assert excluded["creatinine"].reason_code == EXCLUDED_NOT_CLASSIFIABLE
    assert excluded["creatinine"].outcome == "UNIT_MISMATCH"
    assert "counts for nothing in the score" in excluded["creatinine"].reason
    assert "creatinine" not in {c.feature for c in data.contributions}
    assert "creatinine" not in data.coverage.contributing
    assert data.coverage.contributing_count == 3
    assert data.score == 91.7


def test_a_parameter_present_in_only_one_report_is_excluded_with_a_reason():
    data = analyse(
        [
            snapshot(
                "r1",
                EARLIER,
                hba1c=value("hba1c", 7.8, "%", ref_low=4.0, ref_high=5.6),
                creatinine=value("creatinine", 1.4, "mg/dl", ref_low=0.7, ref_high=1.3),
                cholesterol=value("cholesterol", 240.0, "mg/dl", ref_high=200.0),
            ),
            snapshot(
                "r2",
                LATER,
                hba1c=value("hba1c", 6.0, "%", ref_low=4.0, ref_high=5.6),
                cholesterol=value("cholesterol", 190.0, "mg/dl", ref_high=200.0),
            ),
        ]
    )
    excluded = {item.feature: item for item in data.coverage.excluded}
    assert excluded["creatinine"].outcome == "ONLY_IN_BASELINE"
    assert excluded["creatinine"].reason_code == EXCLUDED_NOT_CLASSIFIABLE
    assert "creatinine" not in data.coverage.contributing
    assert data.outcome == PROGRESS_INSUFFICIENT_COVERAGE


def test_an_undeclared_polarity_parameter_is_excluded_with_its_own_reason_code():
    data = analyse(
        uniform_pair(
            {
                "hba1c": value("hba1c", 7.8, "%", ref_low=4.0, ref_high=5.6),
                "creatinine": value(
                    "creatinine", 1.4, "mg/dl", ref_low=0.7, ref_high=1.3
                ),
                "cholesterol": value("cholesterol", 240.0, "mg/dl", ref_high=200.0),
                "blood_glucose": value(
                    "blood_glucose", 180.0, "mg/dl", ref_low=70.0, ref_high=99.0
                ),
            },
            {
                "hba1c": value("hba1c", 6.0, "%", ref_low=4.0, ref_high=5.6),
                "creatinine": value(
                    "creatinine", 1.5, "mg/dl", ref_low=0.7, ref_high=1.3
                ),
                "cholesterol": value("cholesterol", 190.0, "mg/dl", ref_high=200.0),
                "blood_glucose": value(
                    "blood_glucose", 140.0, "mg/dl", ref_low=70.0, ref_high=99.0
                ),
            },
        )
    )
    excluded = {item.feature: item for item in data.coverage.excluded}
    assert excluded["blood_glucose"].reason_code == EXCLUDED_DIRECTION_UNDECLARED
    assert "no clinical direction is recorded" in excluded["blood_glucose"].reason
    assert "counts for nothing in the score rather than counting as no movement" in (
        excluded["blood_glucose"].reason
    )
    assert "blood_glucose" not in data.coverage.contributing


def test_a_non_trendable_feature_is_excluded_as_zero_weight_not_scored():
    data = analyse(
        uniform_pair(
            {
                "hba1c": value("hba1c", 7.8, "%", ref_low=4.0, ref_high=5.6),
                "age": value("age", 50, "years"),
                "gender": value("gender", "male"),
                "hypertension": value("hypertension", True),
            },
            {
                "hba1c": value("hba1c", 6.0, "%", ref_low=4.0, ref_high=5.6),
                "age": value("age", 51, "years"),
                "gender": value("gender", "male"),
                "hypertension": value("hypertension", True),
            },
        )
    )
    scored = {c.feature for c in data.contributions}
    for name in ("age", "gender", "hypertension"):
        assert name not in scored
        assert WEIGHTS[name].weight == 0.0
    assert all(c.weight > 0.0 for c in data.contributions)


def test_every_examined_parameter_either_contributes_or_is_listed_as_excluded():
    for reports in (
        mixed_pair(),
        uniform_pair(
            {"age": value("age", 50, "years")}, {"age": value("age", 51, "years")}
        ),
    ):
        data = analyse(reports)
        coverage = data.coverage
        assert coverage.contributing_count == len(data.contributions)
        assert coverage.contributing_count == len(coverage.contributing)
        assert coverage.excluded_count == len(coverage.excluded)
        assert (
            coverage.contributing_count + coverage.excluded_count
            == coverage.features_examined
        )
        assert coverage.sufficient == (
            coverage.contributing_count >= coverage.minimum_required
        )
        assert coverage.coverage_note.strip()
        overlap = set(coverage.contributing) & {e.feature for e in coverage.excluded}
        assert overlap == set(), f"counted twice: {overlap}"


def test_the_category_tally_spans_every_examined_parameter_not_only_the_scored_ones():
    data = analyse(
        uniform_pair(
            {
                "hba1c": value("hba1c", 7.8, "%", ref_low=4.0, ref_high=5.6),
                "creatinine": value(
                    "creatinine", 1.4, "mg/dl", ref_low=0.7, ref_high=1.3
                ),
                "cholesterol": value("cholesterol", 240.0, "mg/dl", ref_high=200.0),
                "age": value("age", 50, "years"),
            },
            {
                "hba1c": value("hba1c", 6.0, "%", ref_low=4.0, ref_high=5.6),
                "creatinine": value(
                    "creatinine", 1.5, "mg/dl", ref_low=0.7, ref_high=1.3
                ),
                "cholesterol": value("cholesterol", 190.0, "mg/dl", ref_high=200.0),
                "age": value("age", 51, "years"),
            },
        )
    )
    counts = data.counts
    scored_total = (
        counts.newly_normal
        + counts.improved
        + counts.unchanged
        + counts.worsened
        + counts.newly_abnormal
    )
    assert scored_total == data.coverage.contributing_count
    assert sum(counts.by_category.values()) == data.coverage.features_examined
    assert scored_total < sum(counts.by_category.values()), (
        "the excluded parameter must be visible in the tally"
    )


def test_a_caller_cannot_lower_the_floor_change_a_weight_or_move_a_band():
    reports = uniform_pair(
        {"hba1c": value("hba1c", 7.8, "%", ref_low=4.0, ref_high=5.6)},
        {"hba1c": value("hba1c", 6.0, "%", ref_low=4.0, ref_high=5.6)},
    )
    hostile = analyse(
        reports,
        options={
            "minimum_contributing_parameters": 1,
            "minimum_required": 1,
            "coverage_floor": 0,
            "weights": {"hba1c": 99.0},
            "bands": [],
            "neutral_anchor": 90.0,
            "score": 100.0,
        },
    )
    assert hostile.outcome == PROGRESS_INSUFFICIENT_COVERAGE
    assert hostile.score is None
    assert hostile.band is None
    assert hostile.coverage.minimum_required == MINIMUM_CONTRIBUTING_PARAMETERS
    assert hostile.scale.neutral_anchor == NEUTRAL_ANCHOR
    assert len(hostile.scale.bands) == len(BANDS)
    plain = analyse(reports)
    assert hostile.model_dump(exclude={"generated_at"}) == plain.model_dump(
        exclude={"generated_at"}
    )


def test_narrowing_the_feature_list_narrows_coverage_and_still_faces_the_floor():
    data = analyse(mixed_pair(), options={"features": ["hba1c", "vitamin_d"]})
    assert data.coverage.contributing_count == 2
    assert data.outcome == PROGRESS_INSUFFICIENT_COVERAGE
    assert data.score is None
    assert any("restricted the score to 2 named parameter" in w for w in data.warnings)


def test_an_unknown_feature_name_is_refused_rather_than_silently_skipped():
    with pytest.raises(Exception) as excinfo:
        HealthProgressRequest.model_validate(
            {"reports": mixed_pair(), "options": {"features": ["not_a_feature"]}}
        )
    assert "not canonical features" in str(excinfo.value)


def test_naming_one_half_of_the_pair_is_refused_rather_than_guessed():
    with pytest.raises(Exception) as excinfo:
        HealthProgressRequest.model_validate(
            {"reports": mixed_pair(), "baseline_ref": "r1"}
        )
    assert "without the other side" in str(excinfo.value)


def test_a_report_compared_with_itself_is_refused():
    with pytest.raises(Exception) as excinfo:
        HealthProgressRequest.model_validate(
            {"reports": mixed_pair(), "baseline_ref": "r1", "comparison_ref": "r1"}
        )
    assert "same report" in str(excinfo.value)


def test_a_duplicate_report_id_is_refused_rather_than_double_counted():
    reports = mixed_pair()
    reports[1]["report_id"] = reports[0]["report_id"]
    with pytest.raises(Exception) as excinfo:
        HealthProgressRequest.model_validate({"reports": reports})
    assert "duplicate report_id" in str(excinfo.value)


def test_a_narrow_score_is_reported_as_narrow():
    data = analyse(
        uniform_pair(
            STEADY_BASELINE,
            {
                "hba1c": value("hba1c", 5.4, "%", ref_low=4.0, ref_high=5.6),
                "creatinine": value(
                    "creatinine", 1.1, "mg/dl", ref_low=0.7, ref_high=1.3
                ),
                "cholesterol": value("cholesterol", 190.0, "mg/dl", ref_high=200.0),
            },
        )
    )
    assert data.outcome == PROGRESS_SCORE_COMPUTED
    assert data.coverage.contributing_count == 3
    assert any("It describes those parameters" in w for w in data.warnings)
    warnings_text = " ".join(data.warnings).lower()
    assert "big enough to count" in warnings_text or "counts as a change" in warnings_text
    assert (
        "count the same" in warnings_text
        or "does not move the score further" in warnings_text
    )


def test_the_same_reports_in_any_order_give_identical_output():
    forward = analyse(mixed_pair())
    backward = analyse(list(reversed(mixed_pair())))
    assert forward.model_dump(exclude={"generated_at"}) == backward.model_dump(
        exclude={"generated_at"}
    )
    assert forward.generated_at is not None


def test_repeated_calls_are_byte_identical_apart_from_the_timestamp():
    first = analyse(mixed_pair())
    second = analyse(mixed_pair())
    assert first.model_dump_json(exclude={"generated_at"}) == (
        second.model_dump_json(exclude={"generated_at"})
    )


def test_module_30_reaches_no_model_client():
    from tests.test_doctor_summary import app_import_closure

    closure = app_import_closure("app.services.progress_analyzer")
    for banned in (
        "app.services.gemini_client",
        "app.services.gemini_text",
        "app.services.explanation",
    ):
        assert banned not in closure, f"progress_analyzer can reach {banned}"


def test_progress_document_states_which_outcome_carries_a_score():
    doc = progress_document()
    assert doc["outcomes"]["branch_on"] == "outcome"
    assert doc["outcomes"]["score_present_for"] == PROGRESS_SCORE_COMPUTED
    assert doc["scoring"]["scale"]["direction"] == SCALE_DIRECTION
    assert "not a measure of health" in doc["disclaimer"]


def test_the_disclaimer_and_scale_wording_ride_on_every_response():
    for data in (analyse(mixed_pair()), analyse([])):
        assert data.scale.direction == "higher_is_better"
        assert data.scale.direction_text.strip()
        assert data.scale.rounding.strip()
        said = data.what_this_is_not.lower()
        assert "not a health score" in said or "not a measure of health" in said
        assert "not a risk score" in said
        assert "not a diagnosis" in said
        assert "not a diagnosis" in data.disclaimer
        assert data.what_this_is.strip()
