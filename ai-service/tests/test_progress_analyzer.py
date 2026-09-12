"""Module 30 -- the Health Progress Score, and the table it is computed from.

Framework-independent: no HTTP, no API key, no network, no model. Every report
snapshot here is hand-written from invented values for a fictional laboratory.

WHY THIS FILE EXISTS. Module 30 shipped with NO tests (MEMORY.md §6m). It
prints ONE NUMBER, on a scale a reader will treat as a summary of their
health, and the whole safety of that number rests on properties nothing was
checking:

1. **Nothing assessed must produce NO score.** `score: null`, `band: null` --
   never 50, never a band label reading like steady progress. "We could not
   tell" and "it did not move" are different facts, and the neutral anchor is
   exactly where a lazy edit would collapse them. §11 records this as the
   single most repeated hazard on this project.
2. **An excluded parameter must contribute nothing.** Not a reduced weight,
   not a neutral score -- nothing. `ExcludedParameter` is supposed to make
   that structural by having no `points`/`weight` field at all; this file
   asserts that stays true rather than trusting the docstring.
3. **The scoring table's self-asserted invariants.** `progress_scoring.py`
   enforces equal anchor spacing, a total weight table, band tiling and the
   anchor/boundary separation in `_self_check()`, which runs at import. A
   `_self_check()` deleted in a refactor would take every one of those
   guarantees with it silently, because nothing would then be looking. The
   invariant tests below are written against the TABLES, not against
   `_self_check()`, so they still fail if the function is removed.
4. **No caller-supplied option may buy a friendlier score.** The coverage
   floor, the weights and the band boundaries are declared in a reviewable
   data file; a request must not be able to move any of them.
5. **Determinism.** Same reports in any order -> byte-identical output apart
   from `generated_at`.
"""

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


# --------------------------------------------------------------------------
# Payload helpers -- invented values, never real patient data
# --------------------------------------------------------------------------


def value(
    name: str,
    number: Any,
    unit: Optional[str] = None,
    *,
    canonical: bool = True,
    ref_low: Optional[float] = None,
    ref_high: Optional[float] = None,
) -> Dict[str, Any]:
    """One entry of Module 6's `valid` map, as the backend would relay it."""
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
    """One `TimelineReportInput` -- Module 28's shape, which 29/30/32 reuse."""
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
    """Seven declared-polarity parameters spanning four of the five categories.

    Chosen so the arithmetic is checkable by hand:
    improved 75 + newly_normal 100 + unchanged 50 + worsened 25 +
    newly_normal 100 + unchanged 50 + unchanged 50 = 450 over 7 = 64.285...
    which rounds to 64.3.
    """
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


#: Three declared-polarity parameters, well inside their intervals on both
#: sides. Used as the "everything held steady" case.
STEADY_BASELINE = {
    "hba1c": value("hba1c", 5.0, "%", ref_low=4.0, ref_high=5.6),
    "creatinine": value("creatinine", 0.8, "mg/dl", ref_low=0.7, ref_high=1.3),
    "cholesterol": value("cholesterol", 150.0, "mg/dl", ref_high=200.0),
}


# ==========================================================================
# 1. The scoring table's own invariants
# ==========================================================================
#
# `progress_scoring._self_check()` asserts all of these at IMPORT. Every test
# below re-derives the property from the TABLES rather than calling
# `_self_check()`, so deleting that function -- the obvious casualty of a
# refactor that finds an import-time raise inconvenient -- does not delete the
# coverage with it.


def test_the_five_anchors_are_equally_spaced():
    """Equal spacing is a claim the file, the policy endpoint and the API all
    make in prose. Nobody on this project can defend a ratio between
    `newly_abnormal` and `worsened`, so no ratio is asserted -- which is only
    true while the four steps are identical.
    """
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
    """`unchanged` is an EARNED finding: both reports carried a reading and the
    change did not clear the declared stability band. It owns 50. A parameter
    nobody could assess must never land on the same number, which is why the
    exclusion machinery exists at all.
    """
    assert CATEGORY_POINTS[CATEGORY_UNCHANGED].points == NEUTRAL_ANCHOR == 50.0
    on_neutral = [
        e.category for e in CATEGORY_POINTS.values() if e.points == NEUTRAL_ANCHOR
    ]
    assert on_neutral == [CATEGORY_UNCHANGED]


def test_every_module_29_category_has_a_decision_and_none_has_two():
    """A category with no decision would have to be given one at RUNTIME --
    and the cheapest runtime default is the neutral anchor, which is the exact
    failure this module is built to prevent.
    """
    on_scale = set(CATEGORY_POINTS)
    off_scale = set(NON_CONTRIBUTING_CATEGORIES)
    assert on_scale | off_scale == set(CATEGORY_VALUES)
    assert on_scale & off_scale == set()
    for entry in NON_CONTRIBUTING_CATEGORIES.values():
        assert entry.reason_code in EXCLUSION_REASON_CODES
        assert entry.basis.strip()


def test_the_weight_table_is_total_over_the_catalogue():
    """Adding a feature to `feature_catalog.py` without deciding what Module 30
    does with it must not silently produce a score that ignores it.
    """
    assert set(WEIGHTS) == set(CANONICAL_FEATURES)
    for name, entry in WEIGHTS.items():
        assert entry.feature == name
        assert entry.weight >= 0.0
        assert entry.basis.strip(), f"{name} states no basis for its weight"


def test_the_non_zero_weights_are_exactly_the_trendable_features():
    """Weight 0 is an EXCLUSION, not a low importance. The two sets must line
    up exactly: a trendable feature carrying weight 0 would be silently
    dropped from a score that still printed with full confidence, and a
    non-trendable one carrying weight would be scored on a direction of change
    the polarity table says it does not have.
    """
    non_zero = {name for name, e in WEIGHTS.items() if e.weight > 0.0}
    trendable = {name for name, p in POLARITY.items() if p.trendable}
    assert non_zero == trendable
    assert len(non_zero) == 9, sorted(non_zero)
    assert {name for name, e in WEIGHTS.items() if e.weight == 0.0} == (
        set(CANONICAL_FEATURES) - trendable
    )


def test_every_declared_polarity_feature_can_reach_the_score():
    """The silent-drop guard. A feature the clinical table says CAN be
    classified must not be zero-weighted out of the number here.
    """
    scorable = [
        name
        for name, p in POLARITY.items()
        if p.trendable and p.kind != POLARITY_UNDECLARED
    ]
    assert len(scorable) == 7, sorted(scorable)
    for name in scorable:
        assert WEIGHTS[name].weight > 0.0, f"{name} is silently dropped"


def test_all_weights_are_equal_so_no_parameter_outranks_another():
    """An invented importance hierarchy inside a computed score reaches a
    reader as clinical fact. The table states there is no basis for one; that
    statement is only true while every scoring weight is the same.
    """
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
    """The stated basis for the boundaries 20/40/60/80. If a boundary moves
    onto an anchor, "every parameter worsened" could share a label with "every
    parameter was unchanged" -- and the sentence in `_BAND_BASIS` explaining
    why that cannot happen becomes a false comment.
    """
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
    # The top of the scale must have a band; an open interval there would
    # raise on a perfect score.
    assert band_for(100.0).key == BANDS[-1].key


def test_band_lookup_refuses_a_score_outside_the_scale_rather_than_guessing():
    for bad in (-0.1, 100.1):
        with pytest.raises(ValueError):
            band_for(bad)


def test_the_coverage_floor_enforces_the_rule_it_states():
    """The stated rule is NO SINGLE PARAMETER MAY BE A MAJORITY OF THE SCORE.
    With equal weights that is false at n=1 (one parameter is the whole score)
    and at n=2 (it is half), so 3 is the smallest floor that implements it.
    """
    assert MINIMUM_CONTRIBUTING_PARAMETERS >= 3
    assert 1.0 / MINIMUM_CONTRIBUTING_PARAMETERS <= 0.5


def test_rounding_happens_before_banding_so_number_and_band_never_disagree():
    """Exhaustive over every reachable score.

    A contribution can only ever carry one of the five anchor values, and at
    most nine features can contribute, so every possible weighted mean is
    enumerable. For each one, the band chosen from the ROUNDED score must
    actually contain that rounded score -- i.e. a reader comparing the printed
    number with the printed band can never find them inconsistent.
    """
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
    """`None` from either helper means "excluded", never "score it neutrally".
    A dict `.get` with a default would be the one-character edit that turns an
    unknown category into 50 out of 100.
    """
    assert points_for("no_such_category") is None
    assert weight_for("no_such_feature") is None
    for name in CATEGORY_VALUES:
        assert (points_for(name) is None) == (name in NON_CONTRIBUTING_CATEGORIES)


def test_scoring_document_publishes_the_same_numbers_the_scorer_uses():
    """`GET /progress/policy` is how a reviewer checks the table without
    sending a patient's reports through it. A document that drifted from the
    table would make that review worthless.
    """
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


# ==========================================================================
# 2. Outcomes -- and the refusals that must never carry a number
# ==========================================================================


def test_every_declared_outcome_is_reachable_and_only_one_carries_a_score():
    """A vocabulary with an unreachable member is a vocabulary nobody has
    tested. All four are produced below from real requests.
    """
    assert set(PROGRESS_OUTCOME_VALUES) == {
        PROGRESS_SCORE_COMPUTED,
        PROGRESS_NO_PAIR,
        PROGRESS_NOTHING_ASSESSED,
        PROGRESS_INSUFFICIENT_COVERAGE,
    }


def test_score_computed_carries_the_hand_checkable_weighted_mean():
    data = analyse(mixed_pair())
    assert data.outcome == PROGRESS_SCORE_COMPUTED

    # SIX, NOT SEVEN, AND THE SEVENTH IS THE POINT. `mixed_pair()` records no
    # `age`, and BMI's polarity declaration is adult-only -- the WHO 18.5-24.9
    # interval "is NOT valid in children and adolescents". Module 28 used to
    # apply it anyway whenever no age was present, so BMI was scored here
    # against an interval that may not have applied to the patient at all.
    # An unknown age is now refused rather than assumed adult, so BMI drops
    # out of the score and is listed with its reason.
    #
    # This test previously asserted 7 contributors and 450/7 = 64.3, i.e. it
    # asserted the defect. The numbers below are the same arithmetic over the
    # six parameters that are genuinely classifiable.
    assert data.coverage.contributing_count == 6
    assert {e.feature for e in data.coverage.excluded} == {"bmi"}
    assert data.score == 66.7  # 400 / 6 = 66.666..., rounded to 1 dp
    assert data.band is not None
    assert data.band.key == "more_favourable_than_unfavourable"
    assert data.band.lower_inclusive <= data.score < data.band.upper_exclusive
    # Every point value came from the table, and nothing else fed the number.
    assert sum(c.weighted_points for c in data.contributions) == 400.0
    assert {c.points for c in data.contributions} <= {
        e.points for e in CATEGORY_POINTS.values()
    }


@pytest.mark.parametrize(
    "baseline,comparison,expected_score,expected_band,expected_category",
    [
        # Every parameter crosses from inside to outside its printed interval.
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
        # Every parameter moves unfavourably without crossing an interval.
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
        # Nothing clears its declared stability band.
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
        # Every parameter crosses from outside to inside.
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
    """The band separation, proved through the whole service rather than only
    against the table: "everything worsened" and "everything held steady" must
    reach a reader under different labels.
    """
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
    """THE CASE THIS MODULE EXISTS FOR.

    Both parameters moved a long way -- blood glucose 180 -> 140, haemoglobin
    10.0 -> 11.5 -- and both stayed outside their printed intervals, so no
    reference crossing was established either. Neither has a declared clinical
    direction, so nothing here can be called favourable or unfavourable. The
    honest answer is "we cannot tell", and the dangerous answer is 50 out of
    100 beside a band whose label reads "little movement".
    """
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
    # The prose must not read as a finding of stability.
    text = " ".join([data.summary.headline, *data.summary.lines]).lower()
    assert "not one of the 4 parameter(s) examined could be placed" in (
        data.summary.headline
    )
    assert "stable" not in text
    assert "no change" not in text
    assert any("not a statement that nothing changed" in w for w in data.warnings)


def test_below_the_coverage_floor_the_contributions_are_returned_but_no_number_is():
    """Two parameters, both classified, both improving. A number here would
    print with exactly the confidence of one built from nine, and one
    parameter would hold half of it.
    """
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
    # The working IS still shown -- the refusal is of the headline number only.
    assert len(data.contributions) == 2
    assert {c.feature for c in data.contributions} == {"hba1c", "creatinine"}
    assert all(c.points in {e.points for e in CATEGORY_POINTS.values()}
               for c in data.contributions)


@pytest.mark.parametrize(
    "outcome_case",
    ["no_pair", "nothing_assessed", "insufficient"],
)
def test_no_refusal_ever_carries_a_score_or_a_band(outcome_case):
    """One assertion, three ways in. `HealthProgressData`'s own validator
    enforces this too; this proves the SERVICE never asks it to.
    """
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
    # The instrument is still described, because that is not a claim about
    # the patient.
    assert data.scale.direction == SCALE_DIRECTION
    assert len(data.scale.bands) == len(BANDS)
    assert data.coverage is not None


def test_the_response_model_refuses_a_refusal_that_acquired_a_number():
    """The guarantee at the lowest layer (MEMORY.md §11). Even if a future
    edit computed a score on a refusing branch, the type will not validate it.
    """
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


# ==========================================================================
# 3. Exclusions contribute NOTHING -- structurally, not by convention
# ==========================================================================


def test_excluded_parameter_has_no_points_weight_or_weighted_points_field():
    """The structural half of "absence is never a value", and the reason this
    is a separate model from `ParameterContribution` at all. No later code
    path can 'fill in' a 50 on a field that does not exist.
    """
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
    """`extra="forbid"` is what keeps the missing field from being smuggled
    back in as an extra attribute.
    """
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
    """THE CASE MEMORY.md §6n D1 makes unmissable.

    Creatinine is 1.4 mg/dL on the baseline and 168 umol/L (about 1.9 mg/dL)
    on the comparison -- a substantial WORSENING. Module 29 cannot compare the
    two units, so Module 30 must exclude it. What it must NOT do is score it
    at the neutral anchor: that would quietly convert an unreadable
    deterioration into "this parameter did not move", and drag the headline
    number toward 50 on the strength of a fact nobody established.
    """
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
    # It is absent from the number entirely -- not present with points 50.
    assert "creatinine" not in {c.feature for c in data.contributions}
    assert "creatinine" not in data.coverage.contributing
    assert data.coverage.contributing_count == 3
    assert data.score == 91.7  # (75 + 100 + 100) / 3, creatinine contributing nothing


def test_a_parameter_present_in_only_one_report_is_excluded_with_a_reason():
    """ONLY_IN_BASELINE. The value IS in the earlier report; nothing is known
    about where it went. That is not "unchanged".
    """
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
    # Two contributing parameters, so the floor refuses the headline number.
    assert data.outcome == PROGRESS_INSUFFICIENT_COVERAGE


def test_an_undeclared_polarity_parameter_is_excluded_with_its_own_reason_code():
    """Blood glucose moved 180 -> 140 -- a big, significant move, still
    outside its interval on both sides. No clinical direction is declared for
    it, so whether that move was good cannot be said. `DIRECTION_UNDECLARED`
    is a DIFFERENT fact from `NOT_CLASSIFIABLE` and is reported as such.
    """
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
    """Age rises for everyone by construction. It carries weight 0 as an
    EXCLUSION, and must never appear as a scored contribution.
    """
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
    """The coverage figure is the ONE number that must not be wrong: it is
    what separates a score built from two lucky parameters from one built from
    nine on a rendered page.
    """
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
    """`by_category` deliberately covers the excluded parameters too, so a
    reader adding the five scored counts and comparing with `features_examined`
    sees the shortfall rather than a tidy total that absorbed it.
    """
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


# ==========================================================================
# 4. No option can buy a friendlier score
# ==========================================================================


def test_a_caller_cannot_lower_the_floor_change_a_weight_or_move_a_band():
    """`ProgressOptions` has `extra="ignore"`, so an invented option is
    dropped rather than honoured -- but "dropped" has to be PROVED, because
    silently accepting `minimum_contributing=1` would be indistinguishable
    from ignoring it right up until it worked.
    """
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
    # And identical to the request with no options at all.
    plain = analyse(reports)
    assert hostile.model_dump(exclude={"generated_at"}) == plain.model_dump(
        exclude={"generated_at"}
    )


def test_narrowing_the_feature_list_narrows_coverage_and_still_faces_the_floor():
    """Cherry-picking the two best parameters must not buy a headline number.
    The narrowing is allowed -- it is a legitimate request -- but the coverage
    floor is applied to what is left, and the response says the list was
    narrowed.
    """
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
    """A score at the floor and a score from nine parameters print the same
    way. The warning is the only thing that separates them in prose.
    """
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
    # THE INVARIANT, NOT THE SENTENCE. The response must state that the SIZE
    # of a change decides only whether it counts at all -- never how much it
    # counts for -- so a reader cannot take a big number as a big score.
    # The wording was rewritten out of this service's own vocabulary ("the
    # stability band declared for that parameter"); what is pinned here is
    # the claim, in whichever words carry it.
    warnings_text = " ".join(data.warnings).lower()
    assert "big enough to count" in warnings_text or "counts as a change" in warnings_text
    assert (
        "count the same" in warnings_text
        or "does not move the score further" in warnings_text
    )


# ==========================================================================
# 5. Determinism, and the module's stated model-free property
# ==========================================================================


def test_the_same_reports_in_any_order_give_identical_output():
    """Ordering comes from `chrono_date`, never from array order. If it did
    not, the same patient's score would change between two identical calls
    that happened to serialise the history differently.
    """
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
    """Module 30's stated property: no LLM, no free-text entry point. Proved
    over the whole `app.*` import closure of the analyser and its scoring
    table, so it holds even if a helper three levels down grows an import.
    """
    from tests.test_doctor_summary import app_import_closure

    closure = app_import_closure("app.services.progress_analyzer")
    for banned in (
        "app.services.gemini_client",
        "app.services.gemini_text",
        "app.services.explanation",
    ):
        assert banned not in closure, f"progress_analyzer can reach {banned}"


def test_progress_document_states_which_outcome_carries_a_score():
    """The policy document is what a client integrator reads before deciding
    what to render. It must name `outcome` as the branch field.
    """
    doc = progress_document()
    assert doc["outcomes"]["branch_on"] == "outcome"
    assert doc["outcomes"]["score_present_for"] == PROGRESS_SCORE_COMPUTED
    assert doc["scoring"]["scale"]["direction"] == SCALE_DIRECTION
    assert "not a measure of health" in doc["disclaimer"]


def test_the_disclaimer_and_scale_wording_ride_on_every_response():
    """Including the refusals: a number a reader has to infer the direction of
    is worse than no number, and the same is true of one with no disclaimer.
    """
    for data in (analyse(mixed_pair()), analyse([])):
        assert data.scale.direction == "higher_is_better"
        assert data.scale.direction_text.strip()
        assert data.scale.rounding.strip()
        # The copy capitalises the negations for emphasis ("NOT a risk score,
        # NOT a measure of health"), so this is matched case-insensitively --
        # the property under test is that the disclaimer SAYS it, not how it
        # is cased. Asserting the exact lowercase literal would fail on a
        # purely typographic edit while a real removal of the sentence would
        # still be caught.
        # THE THREE DENIALS ARE THE INVARIANT. Which words carry them is not:
        # "not a measure of health" became "not a health score" when this
        # paragraph was rewritten for a reader, and pinning the old phrase
        # would fail on that edit while a genuine REMOVAL of the denial --
        # the thing this platform has actually done three times -- would slip
        # through either way. Each denial is matched in the forms that state
        # it, and the test fails if any of the three stops being stated.
        said = data.what_this_is_not.lower()
        assert "not a health score" in said or "not a measure of health" in said
        assert "not a risk score" in said
        assert "not a diagnosis" in said
        assert "not a diagnosis" in data.disclaimer
        assert data.what_this_is.strip()
