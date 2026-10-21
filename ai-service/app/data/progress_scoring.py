from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from app.data.feature_catalog import CANONICAL_FEATURES, FEATURES
from app.data.trend_polarity import (
    POLARITY,
    POLARITY_UNDECLARED,
    polarity_for,
    stability_for,
)
from app.schemas.comparison import (
    CATEGORY_CHANGED_DIRECTION_ONLY,
    CATEGORY_IMPROVED,
    CATEGORY_NEWLY_ABNORMAL,
    CATEGORY_NEWLY_NORMAL,
    CATEGORY_NOT_CLASSIFIABLE,
    CATEGORY_UNCHANGED,
    CATEGORY_VALUES,
    CATEGORY_WORSENED,
)

PROGRESS_SCORING_VERSION = "1.0.0"


SCALE_MIN = 0.0
SCALE_MAX = 100.0

SCALE_DIRECTION = "higher_is_better"

SCALE_DIRECTION_TEXT = (
    "A higher number means more of your results moved in the better "
    "direction between the two reports. A lower number means more of them "
    "moved the other way."
)

SCALE_KIND = "equally_spaced_five_point_ordinal"

SCALE_KIND_NOTE = (
    "The five contributing categories are given equally spaced positions "
    "because the ORDER is defensible and no spacing is. Nobody on this "
    "project can say that one category is a stated multiple of another as "
    "bad, so no such ratio is asserted. The score carries ordering "
    "information and nothing more; it is not a measurement of how much "
    "anything changed."
)

NEUTRAL_ANCHOR = 50.0


@dataclass(frozen=True)
class CategoryPoints:

    category: str
    points: float
    rank: int
    basis: str


CATEGORY_POINTS: Dict[str, CategoryPoints] = {
    CATEGORY_NEWLY_NORMAL: CategoryPoints(
        CATEGORY_NEWLY_NORMAL,
        points=100.0,
        rank=5,
        basis=(
            "Most favourable of the five ordered categories. Module 29 emits "
            "it only when the reading is established as OUTSIDE the reference "
            "interval printed on the baseline report and INSIDE the interval "
            "printed on the comparison report -- a change of state relative "
            "to the laboratory's own printed interval, which Module 29's "
            "documented category precedence already ranks above the "
            "better/worse change axis. The rank is inherited from that "
            "precedence; the number 100 is the top of an equally spaced "
            "five-point ordinal scale and carries no further meaning."
        ),
    ),
    CATEGORY_IMPROVED: CategoryPoints(
        CATEGORY_IMPROVED,
        points=75.0,
        rank=4,
        basis=(
            "Module 28 classified the net change as favourable against the "
            "polarity declared for this feature, and the change cleared the "
            "declared stability band. No reference-interval crossing was "
            "established, which is why it ranks below newly_normal. The "
            "number 75 is the fourth point of an equally spaced five-point "
            "ordinal scale."
        ),
    ),
    CATEGORY_UNCHANGED: CategoryPoints(
        CATEGORY_UNCHANGED,
        points=NEUTRAL_ANCHOR,
        rank=3,
        basis=(
            "The NEUTRAL ANCHOR, and an earned finding rather than a default: "
            "both reports carried a usable reading, the change was computed, "
            "and it did not clear the reference change value band declared in "
            "app/data/trend_polarity.py. Someone looked and the parameter did "
            "not move. A parameter nobody could assess never lands here -- it "
            "is excluded from the score entirely."
        ),
    ),
    CATEGORY_WORSENED: CategoryPoints(
        CATEGORY_WORSENED,
        points=25.0,
        rank=2,
        basis=(
            "The mirror of improved, held to the same bar: unfavourable "
            "against the declared polarity, clearing the declared stability "
            "band, with no reference-interval crossing established. The "
            "number 25 is the second point of an equally spaced five-point "
            "ordinal scale."
        ),
    ),
    CATEGORY_NEWLY_ABNORMAL: CategoryPoints(
        CATEGORY_NEWLY_ABNORMAL,
        points=0.0,
        rank=1,
        basis=(
            "The mirror of newly_normal: established as INSIDE the reference "
            "interval printed on the baseline report and OUTSIDE the interval "
            "printed on the comparison report. Ranked last for the same "
            "reason newly_normal ranks first -- Module 29's own category "
            "precedence puts a crossing above the change axis. The number 0 "
            "is the bottom of an equally spaced five-point ordinal scale and "
            "is not a claim that anything is absent, wrong or severe."
        ),
    ),
}


EXCLUDED_DIRECTION_UNDECLARED = "DIRECTION_UNDECLARED"
EXCLUDED_NOT_CLASSIFIABLE = "NOT_CLASSIFIABLE"
EXCLUDED_ZERO_WEIGHT = "ZERO_WEIGHT_IN_SCORING_TABLE"
EXCLUDED_NO_WEIGHT_DECLARED = "NO_WEIGHT_DECLARED"

EXCLUDED_UNKNOWN_CATEGORY = "UNKNOWN_CATEGORY"

EXCLUSION_REASON_CODES: Tuple[str, ...] = (
    EXCLUDED_DIRECTION_UNDECLARED,
    EXCLUDED_NOT_CLASSIFIABLE,
    EXCLUDED_ZERO_WEIGHT,
    EXCLUDED_NO_WEIGHT_DECLARED,
    EXCLUDED_UNKNOWN_CATEGORY,
)


@dataclass(frozen=True)
class NonContributingCategory:

    category: str
    reason_code: str
    basis: str


NON_CONTRIBUTING_CATEGORIES: Dict[str, NonContributingCategory] = {
    CATEGORY_CHANGED_DIRECTION_ONLY: NonContributingCategory(
        CATEGORY_CHANGED_DIRECTION_ONLY,
        reason_code=EXCLUDED_DIRECTION_UNDECLARED,
        basis=(
            "The value moved by more than its declared stability band, but "
            "app/data/trend_polarity.py declines to say whether that "
            "direction is favourable or unfavourable for this feature (or the "
            "movement sits wholly inside the declared interval, where a "
            "single better/worse label would mislead). There is no honest "
            "position for it on a better/worse scale. Placing it at the "
            "neutral anchor would state that it did not move, which is the "
            "opposite of what was observed."
        ),
    ),
    CATEGORY_NOT_CLASSIFIABLE: NonContributingCategory(
        CATEGORY_NOT_CLASSIFIABLE,
        reason_code=EXCLUDED_NOT_CLASSIFIABLE,
        basis=(
            "Neither the change axis nor the reference-interval axis could be "
            "established: the parameter was missing from one or both reports, "
            "arrived in inconsistent or non-canonical units, is not a "
            "trendable quantity, or was refused for one of the other reasons "
            "Module 29 carries in its `outcome`. Nothing was measured, so "
            "nothing is scored. The response reports the parameter, its "
            "Module 29 outcome, and this reason."
        ),
    ),
}


@dataclass(frozen=True)
class ParameterWeight:

    feature: str
    weight: float
    basis: str


_EQUAL_WEIGHT_BASIS = (
    "Weight 1.0, the same as every other scorable parameter. There is no "
    "defensible basis on this project for asserting that a change in one "
    "canonical parameter is more important than a change in another, and an "
    "invented importance hierarchy inside a computed score would be presented "
    "to a reader as clinical fact. An honest equal weighting is stated here "
    "in preference to an invented one. A reviewer who does have a basis "
    "should change this row and record that basis in place of this sentence."
)

_NOT_A_TREND_BASIS = (
    "Weight 0.0 -- an EXCLUSION, not a low importance. "
    "app/data/trend_polarity.py declares this feature not trendable, so it "
    "has no direction of change to score. Module 29 already returns it as "
    "not_classifiable; this row exists so that the weight table is total over "
    "the catalogue and a reviewer can see the decision rather than infer it "
    "from an omission."
)

WEIGHTS: Dict[str, ParameterWeight] = {
    "hba1c": ParameterWeight("hba1c", 1.0, _EQUAL_WEIGHT_BASIS),
    "blood_glucose": ParameterWeight(
        "blood_glucose",
        1.0,
        _EQUAL_WEIGHT_BASIS
        + " This feature currently has an UNDECLARED polarity, so in practice "
        "Module 29 returns it as changed_direction_only or not_classifiable "
        "and it is excluded on the category axis, which is where that "
        "decision belongs. The weight is 1.0 so that declaring a polarity for "
        "it later brings it into the score without a second edit here.",
    ),
    "hemoglobin": ParameterWeight(
        "hemoglobin",
        1.0,
        _EQUAL_WEIGHT_BASIS
        + " This feature currently has an UNDECLARED polarity; see the "
        "blood_glucose row for why the weight is still 1.0.",
    ),
    "vitamin_d": ParameterWeight("vitamin_d", 1.0, _EQUAL_WEIGHT_BASIS),
    "vitamin_b12": ParameterWeight("vitamin_b12", 1.0, _EQUAL_WEIGHT_BASIS),
    "creatinine": ParameterWeight("creatinine", 1.0, _EQUAL_WEIGHT_BASIS),
    "cholesterol": ParameterWeight("cholesterol", 1.0, _EQUAL_WEIGHT_BASIS),
    "triglycerides": ParameterWeight("triglycerides", 1.0, _EQUAL_WEIGHT_BASIS),
    "alt": ParameterWeight("alt", 1.0, _EQUAL_WEIGHT_BASIS),
    "ast": ParameterWeight("ast", 1.0, _EQUAL_WEIGHT_BASIS),
    "bilirubin_total": ParameterWeight("bilirubin_total", 1.0, _EQUAL_WEIGHT_BASIS),
    "bmi": ParameterWeight("bmi", 1.0, _EQUAL_WEIGHT_BASIS),
    "age": ParameterWeight(
        "age",
        0.0,
        _NOT_A_TREND_BASIS + " Age rises for everyone by construction.",
    ),
    "hypertension": ParameterWeight(
        "hypertension",
        0.0,
        _NOT_A_TREND_BASIS + " Recorded as yes / no / not answered.",
    ),
    "heart_disease": ParameterWeight(
        "heart_disease",
        0.0,
        _NOT_A_TREND_BASIS + " Recorded as yes / no / not answered.",
    ),
    "smoking_history": ParameterWeight(
        "smoking_history",
        0.0,
        _NOT_A_TREND_BASIS + " Recorded as a category, not a measured number.",
    ),
    "gender": ParameterWeight(
        "gender",
        0.0,
        _NOT_A_TREND_BASIS + " A categorical identity attribute.",
    ),
    **{
        _cbc: ParameterWeight(
            _cbc,
            1.0,
            _EQUAL_WEIGHT_BASIS
            + " This feature currently has an UNDECLARED polarity -- it is "
            "harmful at both extremes, and the five differentials are "
            "proportions of a total besides -- so in practice Module 29 "
            "returns it as changed_direction_only or not_classifiable and it "
            "is excluded on the category axis. The weight is 1.0 so that "
            "declaring a polarity for it later brings it into the score "
            "without a second edit here. See the `hemoglobin` row, which has "
            "carried exactly this shape since before these were added.",
        )
        for _cbc in (
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
        )
    },
}


MINIMUM_CONTRIBUTING_PARAMETERS = 3

MINIMUM_COVERAGE_BASIS = (
    "A STATED PROJECT JUDGEMENT, not a derived statistic, and recorded as "
    "such. The rule it implements is: NO SINGLE PARAMETER MAY BE A MAJORITY "
    "OF THE SCORE. With equal weights, one parameter carries the whole score "
    "at a count of 1 and half of it at a count of 2; 3 is the smallest count "
    "at which no single parameter holds a majority. A score built from one or "
    "two lucky parameters would print with exactly the same confidence as one "
    "built from nine, and this floor is what stops that. The floor is "
    "deliberately low because only {trendable} canonical features are "
    "numerically trendable at all and only {with_polarity} of those carry a "
    "declared polarity, so a higher floor would refuse almost every real "
    "request; that is a limit of the current polarity table, and it is "
    "reported in every response as the contributing count rather than hidden."
).format(
    trendable=sum(1 for name in FEATURES if stability_for(name) is not None),
    with_polarity=sum(
        1
        for name in FEATURES
        if stability_for(name) is not None
        and polarity_for(name) is not None
        and polarity_for(name).kind != POLARITY_UNDECLARED
    ),
)


@dataclass(frozen=True)
class ProgressBandDef:

    key: str
    lower: float
    upper: float
    label: str
    description: str


_BAND_BASIS = (
    "The band boundaries are NOT round numbers chosen for their own sake. The "
    "scale has five anchor points -- 0, 25, 50, 75 and 100 -- being the score "
    "obtained when EVERY contributing parameter falls in one of the five "
    "ordered categories. The boundaries 20, 40, 60 and 80 are the partition "
    "that gives each anchor a band of its own and puts no anchor on an "
    "interior boundary, so that 'every parameter worsened' and 'every "
    "parameter improved' can never share a band label with 'every parameter "
    "was unchanged'. (0 and 100 are the ends of the scale itself, and sit on "
    "the outer edges of the first and last bands.) The labels describe "
    "MOVEMENT ACROSS THE MEASURED PARAMETERS and deliberately contain no "
    "assessment of health, no severity word and no recommendation."
)

BANDS: Tuple[ProgressBandDef, ...] = (
    ProgressBandDef(
        "predominantly_unfavourable",
        0.0,
        20.0,
        "Most assessed parameters moved unfavourably",
        "Across the parameters that could be assessed, movement was "
        "predominantly in the direction recorded as unfavourable for those "
        "parameters.",
    ),
    ProgressBandDef(
        "more_unfavourable_than_favourable",
        20.0,
        40.0,
        "More unfavourable movement than favourable",
        "Across the parameters that could be assessed, more of the movement "
        "was in the direction recorded as unfavourable than in the direction "
        "recorded as favourable.",
    ),
    ProgressBandDef(
        "mixed_or_little_movement",
        40.0,
        60.0,
        "Mixed, or little movement",
        "Across the parameters that could be assessed, favourable and "
        "unfavourable movement roughly balance, or most parameters did not "
        "move by more than their declared stability band.",
    ),
    ProgressBandDef(
        "more_favourable_than_unfavourable",
        60.0,
        80.0,
        "More favourable movement than unfavourable",
        "Across the parameters that could be assessed, more of the movement "
        "was in the direction recorded as favourable than in the direction "
        "recorded as unfavourable.",
    ),
    ProgressBandDef(
        "predominantly_favourable",
        80.0,
        100.0,
        "Most assessed parameters moved favourably",
        "Across the parameters that could be assessed, movement was "
        "predominantly in the direction recorded as favourable for those "
        "parameters.",
    ),
)


SCORE_DECIMAL_PLACES = 1

ROUNDING_NOTE = (
    f"The weighted mean is rounded to {SCORE_DECIMAL_PLACES} decimal place(s) "
    "BEFORE the band is chosen, so the number and the band beside it can "
    "never disagree."
)


WHAT_THIS_IS = (
    "The health progress score is a single number describing how a set of "
    "measured laboratory parameters moved between two reports. It counts, for "
    "each parameter that could be assessed, whether the value moved in the "
    "direction recorded as favourable for that parameter, moved the other "
    "way, crossed the reference interval printed on the report, or did not "
    "move by more than its declared stability band. Those five outcomes are "
    "given equally spaced positions on a scale from 0 to 100, and the score "
    "is their average. Every parameter counts the same."
)

WHAT_THIS_IS_NOT = (
    "This number is not a health score, not a risk score and not a "
    "diagnosis. It only describes which way your results moved between two "
    "reports: it cannot see anything that was not measured on both of them, "
    "it says nothing about how serious any value is, and it says nothing "
    "about what you should do. Whether any of it matters is a question for a "
    "qualified healthcare professional."
)


def points_for(category: str) -> Optional[CategoryPoints]:
    return CATEGORY_POINTS.get(category)


def weight_for(feature: str) -> Optional[ParameterWeight]:
    return WEIGHTS.get(feature)


def band_for(score: float) -> ProgressBandDef:
    for band in BANDS:
        if band.lower <= score < band.upper:
            return band
    if score == BANDS[-1].upper:
        return BANDS[-1]
    raise ValueError(
        f"score {score!r} is outside the declared scale {SCALE_MIN}-{SCALE_MAX}. "
        "This is a bug in the scorer, not an input problem; no band is guessed."
    )


def _self_check() -> None:
    decided = set(CATEGORY_POINTS) | set(NON_CONTRIBUTING_CATEGORIES)
    missing = [name for name in CATEGORY_VALUES if name not in decided]
    if missing:
        raise ValueError(
            f"Module 29 categories with no Module 30 decision: {missing}. Add "
            "them to CATEGORY_POINTS or to NON_CONTRIBUTING_CATEGORIES; a "
            "category is never scored by default."
        )
    both = sorted(set(CATEGORY_POINTS) & set(NON_CONTRIBUTING_CATEGORIES))
    if both:
        raise ValueError(
            f"categories both on and off the scale: {both}. A category is one "
            "or the other."
        )
    unknown = sorted(decided - set(CATEGORY_VALUES))
    if unknown:
        raise ValueError(
            f"Module 30 scores categories Module 29 cannot emit: {unknown}."
        )

    ranks = sorted(entry.rank for entry in CATEGORY_POINTS.values())
    if ranks != list(range(1, len(CATEGORY_POINTS) + 1)):
        raise ValueError(f"CATEGORY_POINTS ranks are not 1..n: {ranks}")
    by_rank = sorted(CATEGORY_POINTS.values(), key=lambda e: e.rank)
    for lower, higher in zip(by_rank, by_rank[1:]):
        if not higher.points > lower.points:
            raise ValueError(
                f"{higher.category} ranks above {lower.category} but does not "
                "score above it."
            )
    for entry in CATEGORY_POINTS.values():
        if not SCALE_MIN <= entry.points <= SCALE_MAX:
            raise ValueError(
                f"{entry.category} scores {entry.points}, outside the scale."
            )

    steps = {
        round(higher.points - lower.points, 9)
        for lower, higher in zip(by_rank, by_rank[1:])
    }
    if len(steps) != 1:
        raise ValueError(
            f"CATEGORY_POINTS spacing is not equal: steps {sorted(steps)}. "
            "This file, scoring_document() and the API response all state that "
            "the five points are equally spaced because no basis exists for "
            "any other spacing. Change those statements first, with a basis, "
            "or restore the equal spacing."
        )
    if by_rank[0].points != SCALE_MIN or by_rank[-1].points != SCALE_MAX:
        raise ValueError("the ordinal scale must span the declared 0-100 range")
    neutral = CATEGORY_POINTS[CATEGORY_UNCHANGED].points
    if neutral != NEUTRAL_ANCHOR:
        raise ValueError("unchanged must sit on the declared NEUTRAL_ANCHOR")

    no_weight = [name for name in CANONICAL_FEATURES if name not in WEIGHTS]
    if no_weight:
        raise ValueError(
            f"canonical features with no Module 30 weight row: {no_weight}. "
            "Every feature needs a decision; none gets a default weight."
        )
    not_canonical = sorted(set(WEIGHTS) - set(CANONICAL_FEATURES))
    if not_canonical:
        raise ValueError(f"weights for non-canonical features: {not_canonical}")
    for name, entry in WEIGHTS.items():
        if entry.feature != name:
            raise ValueError(f"weight row {name!r} names feature {entry.feature!r}")
        if entry.weight < 0.0:
            raise ValueError(f"{name}: a negative weight is not meaningful")
        if not entry.basis.strip():
            raise ValueError(f"{name}: every weight must state its basis")

    for name, polarity in POLARITY.items():
        scorable = polarity.trendable and polarity.kind != POLARITY_UNDECLARED
        if scorable and WEIGHTS[name].weight <= 0.0:
            raise ValueError(
                f"{name} has a declared polarity and is trendable, but carries "
                "weight 0 in Module 30. That silently removes a parameter the "
                "polarity table says can be classified."
            )
        if not polarity.trendable and WEIGHTS[name].weight != 0.0:
            raise ValueError(
                f"{name} is declared not trendable but carries a non-zero "
                "Module 30 weight."
            )

    if BANDS[0].lower != SCALE_MIN or BANDS[-1].upper != SCALE_MAX:
        raise ValueError("the bands must span the whole declared scale")
    for lower, higher in zip(BANDS, BANDS[1:]):
        if lower.upper != higher.lower:
            raise ValueError(
                f"band gap or overlap between {lower.key} and {higher.key}"
            )
    for band in BANDS:
        if band.upper <= band.lower:
            raise ValueError(f"band {band.key} is empty or inverted")

    banded: Dict[str, str] = {}
    for entry in CATEGORY_POINTS.values():
        band = band_for(entry.points)
        on_interior_boundary = (
            entry.points == band.lower and band.lower != SCALE_MIN
        ) or (entry.points == band.upper and band is not BANDS[-1])
        if on_interior_boundary:
            raise ValueError(
                f"anchor {entry.points} for {entry.category} sits on an "
                "interior band boundary. _BAND_BASIS states no anchor does."
            )
        if band.key in banded:
            raise ValueError(
                f"anchors for {banded[band.key]} and {entry.category} share "
                f"band {band.key}. _BAND_BASIS states each anchor gets a band "
                "of its own."
            )
        banded[band.key] = entry.category

    if MINIMUM_CONTRIBUTING_PARAMETERS < 3:
        raise ValueError(
            "MINIMUM_CONTRIBUTING_PARAMETERS below 3 lets a single parameter "
            "hold a majority of the score, which is the rule "
            "MINIMUM_COVERAGE_BASIS states it exists to prevent."
        )


def scoring_document() -> Dict[str, object]:
    return {
        "module": 30,
        "scoring_version": PROGRESS_SCORING_VERSION,
        "scale": {
            "min": SCALE_MIN,
            "max": SCALE_MAX,
            "direction": SCALE_DIRECTION,
            "direction_text": SCALE_DIRECTION_TEXT,
            "neutral_anchor": NEUTRAL_ANCHOR,
            "kind": SCALE_KIND,
            "kind_note": SCALE_KIND_NOTE,
            "rounding": ROUNDING_NOTE,
        },
        "method": (
            "Module 30 computes NOTHING clinical of its own. It calls Module "
            "29's compare_reports(), which delegates the whole improved / "
            "worsened / unchanged decision to Module 28's analyse_feature() "
            "over the two chosen reports, which in turn reads the single "
            "polarity table and the single stability band table in "
            "app/data/trend_polarity.py. Module 30 maps the finished category "
            "label onto a point value from this file and takes the weighted "
            "mean. There is no second polarity table, no second stability "
            "threshold and no second definition of 'improved' anywhere in "
            "Module 30."
        ),
        "relative_changes": (
            "Relative change is honoured through the reference change value "
            "band already applied by Modules 28 and 29: a change that does "
            "not clear it is `unchanged` and scores at the neutral anchor. No "
            "further magnitude multiplier is applied, because a change of "
            "twice the reference change value is not twice as favourable and "
            "no published basis exists for any particular curve. The size of "
            "every contributing change is reported alongside the score "
            "instead, as absolute_change and percent_change."
        ),
        "category_points": {
            name: {
                "points": entry.points,
                "rank": entry.rank,
                "basis": entry.basis,
            }
            for name, entry in sorted(
                CATEGORY_POINTS.items(), key=lambda kv: -kv[1].rank
            )
        },
        "non_contributing_categories": {
            name: {"reason_code": entry.reason_code, "basis": entry.basis}
            for name, entry in sorted(NON_CONTRIBUTING_CATEGORIES.items())
        },
        "absence_policy": (
            "A parameter that could not be assessed contributes NOTHING: not "
            "a neutral value, not a reduced weight, nothing. It is listed in "
            "the response with its Module 29 outcome and an exclusion reason "
            "code, and it reduces the contributing count. 'We could not tell' "
            "and 'it did not move' are different facts and are never averaged "
            "together. When nothing at all could be assessed there is no "
            "score: the response carries score: null and an outcome saying so."
        ),
        "weights": {
            name: {"weight": WEIGHTS[name].weight, "basis": WEIGHTS[name].basis}
            for name in CANONICAL_FEATURES
        },
        "weighting_note": (
            "Every scorable parameter carries weight 1.0. This project has no "
            "defensible basis for ranking the parameters against one another, "
            "and an invented hierarchy inside a computed score would reach a "
            "reader as clinical fact. Weight 0.0 marks a feature that has no "
            "direction of change at all; it is an exclusion, not a low "
            "importance."
        ),
        "minimum_contributing_parameters": MINIMUM_CONTRIBUTING_PARAMETERS,
        "minimum_coverage_basis": MINIMUM_COVERAGE_BASIS,
        "exclusion_reason_codes": list(EXCLUSION_REASON_CODES),
        "bands": [
            {
                "key": band.key,
                "lower_inclusive": band.lower,
                "upper_exclusive": band.upper,
                "label": band.label,
                "description": band.description,
            }
            for band in BANDS
        ],
        "bands_basis": _BAND_BASIS,
        "band_boundary_convention": (
            "Lower bound inclusive, upper bound exclusive, except the topmost "
            "band whose upper bound is inclusive so that a score of 100 has a "
            "band."
        ),
        "what_this_is": WHAT_THIS_IS,
        "what_this_is_not": WHAT_THIS_IS_NOT,
        "makes_clinical_claims": False,
        "calls_an_llm": False,
        "feature_coverage_note": (
            "Only "
            + str(
                sum(
                    1
                    for name, polarity in POLARITY.items()
                    if polarity.trendable and polarity.kind != POLARITY_UNDECLARED
                )
            )
            + " of the "
            + str(len(CANONICAL_FEATURES))
            + " canonical features currently carry a declared polarity, so "
            "that is the largest number of parameters any score can be built "
            "from today. The contributing count is reported in every response "
            "so a reader can see how much of that was actually available."
        ),
        "unit_note": (
            "Units are Module 5's responsibility and Module 28 refuses a "
            "feature whose readings arrive in different or non-canonical "
            "units. Module 30 converts nothing."
        ),
        "feature_descriptions": {
            name: FEATURES[name].description for name in CANONICAL_FEATURES
        },
    }


_self_check()


__all__ = [
    "BANDS",
    "CATEGORY_POINTS",
    "EXCLUDED_DIRECTION_UNDECLARED",
    "EXCLUDED_NOT_CLASSIFIABLE",
    "EXCLUDED_NO_WEIGHT_DECLARED",
    "EXCLUDED_UNKNOWN_CATEGORY",
    "EXCLUDED_ZERO_WEIGHT",
    "EXCLUSION_REASON_CODES",
    "MINIMUM_CONTRIBUTING_PARAMETERS",
    "MINIMUM_COVERAGE_BASIS",
    "NEUTRAL_ANCHOR",
    "NON_CONTRIBUTING_CATEGORIES",
    "PROGRESS_SCORING_VERSION",
    "ROUNDING_NOTE",
    "SCALE_DIRECTION",
    "SCALE_DIRECTION_TEXT",
    "SCALE_KIND",
    "SCALE_KIND_NOTE",
    "SCALE_MAX",
    "SCALE_MIN",
    "SCORE_DECIMAL_PLACES",
    "WEIGHTS",
    "WHAT_THIS_IS",
    "WHAT_THIS_IS_NOT",
    "CategoryPoints",
    "NonContributingCategory",
    "ParameterWeight",
    "ProgressBandDef",
    "band_for",
    "points_for",
    "scoring_document",
    "weight_for",
]
