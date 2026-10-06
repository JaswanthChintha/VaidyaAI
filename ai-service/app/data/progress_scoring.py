"""Module 30 Health Progress Score -- the REVIEWABLE data file.

`app/services/progress_analyzer.py` contains the logic; this file contains the
judgements. It follows `app/data/trend_polarity.py` and
`app/data/clinical_rules.py` exactly: plain tables, no control flow beyond a
lookup, every entry citing its basis, and a `_self_check()` that fails at
IMPORT time if this table and `app/data/feature_catalog.py` disagree.

==========================================================================
WHAT THIS FILE IS **NOT**
==========================================================================

It is **not a third clinical table**. It contains:

* no polarity declaration -- whether a rise in creatinine is better or worse
  is read from `app/data/trend_polarity.py`, and Module 30 never asks that
  question itself;
* no stability threshold -- whether a change is real is the reference change
  value in that same file, applied by Module 28 and re-used by Module 29;
* no notion of "improved" of its own -- Module 29 already produced the label,
  and this file maps that finished label onto a number.

Two tables that can disagree about whether a rising value is good is the
defect class this project's audits keep finding. So the ONLY thing declared
here is the arithmetic of turning a set of already-decided category labels
into one number, and the wording of the bands that number falls into.

==========================================================================
THE SCALE, AND WHICH WAY IT POINTS
==========================================================================

    0 to 100. **HIGHER IS BETTER**: a higher number means more of the
    parameters that could be assessed moved in the direction the polarity
    table declares favourable, between the two reports compared.

That sentence is repeated in `SCALE_DIRECTION`, in `scoring_document()` and in
the API response, because a one-dimensional score whose direction the reader
has to infer is worse than no score.

==========================================================================
HOW A CATEGORY BECOMES A NUMBER -- AND WHY THE SPACING IS EQUAL
==========================================================================

Module 29 emits one `category` per parameter, by a precedence it documents
itself. Five of those seven categories are ORDERED statements about the
direction a parameter moved, and this file assigns each of them a point value
on the 0-100 scale:

    newly_normal    100    moved from outside the interval its own report
                            printed, to inside it
    improved         75    moved favourably without crossing an interval
    unchanged        50    both readings present; the change did not clear
                            the declared stability band
    worsened         25    moved unfavourably without crossing an interval
    newly_abnormal    0    moved from inside the interval its own report
                            printed, to outside it

**THE SPACING IS EQUAL BECAUSE THERE IS NO DEFENSIBLE BASIS FOR ANY OTHER
SPACING.** Nobody on this project can say that "newly abnormal" is 3.2 times
as unfavourable as "worsened", and inventing such a ratio would dress a
guess as a measurement. What IS defensible is the ORDER, and the order is not
invented here either: it is Module 29's own stated category precedence, in
which a reference-interval crossing outranks the change axis because it is a
change of state relative to the interval the laboratory itself printed.

So this is an EQUALLY SPACED FIVE-POINT ORDINAL SCALE. It carries ordering
information and nothing more. It is not a measurement of how much better
anyone is, and `scoring_document()` says so in the response.

Two of Module 29's seven categories are deliberately NOT on the scale:

    changed_direction_only   the value moved measurably, but the polarity
                             table declines to say whether that is better or
                             worse. There is no honest place for it on a
                             better/worse axis, and putting it at 50 would
                             state "it did not move" -- which is false.
    not_classifiable         nothing could be established at all.

Both are EXCLUDED from the score and listed in the response with the reason.
See `NON_CONTRIBUTING_CATEGORIES`.

==========================================================================
WHY "UNCHANGED" SCORES AND "NOT CLASSIFIABLE" DOES NOT
==========================================================================

This is the single most important distinction in this file, and it is the
hazard this project keeps rediscovering (`RiskLevel.highest([])` returns None
rather than LOW; Module 18 will not report a healthy status when nothing was
assessed; Module 28 will not report `stable` when it had fewer than two
readings).

`unchanged` is a POSITIVE FINDING. Module 29 emits it only when both reports
carried a usable reading, the change was computed, and it failed to clear the
declared stability band. Someone looked, and the parameter did not move. That
is real information about the patient and it belongs in the score at the
neutral anchor.

`not_classifiable` and `changed_direction_only` are ABSENCES OF FINDING.
Nobody could tell. Scoring them at the neutral anchor would silently convert
"we could not tell" into "it did not move" -- two different facts -- and
averaging them together fabricates a result. They contribute NOTHING: not a
neutral value, not a reduced weight, nothing. They appear in the response's
`excluded` list, and they reduce the contributing count, which is exactly how
the score stays honest about its own coverage.

==========================================================================
WEIGHTS
==========================================================================

**Every scorable parameter carries weight 1.0.** This project has no
defensible basis for asserting that a change in one canonical parameter is
clinically more important than a change in another; constructing such a
hierarchy and presenting it inside a computed score would be inventing
clinical fact. An honest equal weighting is stated here in preference to an
invented one.

`WEIGHTS` is nevertheless a per-feature table, total over the catalogue and
checked at import, for two reasons: so that the equality is explicit and
checkable rather than implicit in a mean, and so that a reviewer who DOES have
a basis has exactly one place to record it -- with the basis alongside.

A weight of 0.0 is not "less important". It means the feature has no
direction of change at all (`gender` is not a trend), and the response
reports it as an exclusion, never as a small contribution.

==========================================================================
"RELATIVE CHANGES" -- WHERE THEY ARE, AND WHY THERE IS NO SECOND SCALING
==========================================================================

The specification asks the score to consider relative changes. It already
does, entirely upstream of this file:

* A change that does not clear the reference change value (RCV) band declared
  in `app/data/trend_polarity.py` is `unchanged` and scores at the neutral
  anchor. A change that does clear it is `improved` or `worsened`.
* The size of every contributing change is reported alongside the score, as
  `absolute_change` and `percent_change` taken from Module 28's arithmetic.

**No further magnitude multiplier is applied**, deliberately. A change of
twice the RCV is not "twice as improved"; there is no published basis for any
particular curve, and any curve invented here would be a third clinical table
that could disagree with the two that exist. The RCV band is the project's
one declared statement about when a relative change is real, and Module 30
uses it through Modules 28/29 rather than restating it.

==========================================================================
MINIMUM COVERAGE
==========================================================================

See `MINIMUM_CONTRIBUTING_PARAMETERS`. A score is refused below it.
"""

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

#: Bump when any point value, weight, band or coverage floor below changes.
#: Echoed in every response so a stored score can be traced back to the table
#: that produced it. Independent of `TREND_POLICY_VERSION`, which versions the
#: clinical tables Module 30 does not own.
PROGRESS_SCORING_VERSION = "1.0.0"


# --------------------------------------------------------------------------
# The scale
# --------------------------------------------------------------------------

SCALE_MIN = 0.0
SCALE_MAX = 100.0

#: The one token a consumer may branch on to know which way the scale points.
SCALE_DIRECTION = "higher_is_better"

#: WRITTEN FOR THE PATIENT, NOT FOR THIS SERVICE.
#: The previous wording shouted "HIGHER IS BETTER" in the middle of a sentence
#: whose caller ALSO prints "Higher is better." in front of it, and explained
#: the scale in terms of "the parameters that could be assessed" moving in "the
#: direction the polarity table records as favourable". A polarity table is a
#: file in this repository. Nothing about it is the reader's business, and
#: naming it on a results page is this platform's most repeated defect -- see
#: MEMORY 6u, 6w, 6af, and now this.
#: Every fact is kept: the range, which way it points, and what moves it.
SCALE_DIRECTION_TEXT = (
    "A higher number means more of your results moved in the better "
    "direction between the two reports. A lower number means more of them "
    "moved the other way."
)

#: What kind of scale it is, as a token and as a sentence. Named constants
#: rather than literals buried in `scoring_document()`, so that the API
#: response and the policy endpoint provably carry the SAME words.
SCALE_KIND = "equally_spaced_five_point_ordinal"

SCALE_KIND_NOTE = (
    "The five contributing categories are given equally spaced positions "
    "because the ORDER is defensible and no spacing is. Nobody on this "
    "project can say that one category is a stated multiple of another as "
    "bad, so no such ratio is asserted. The score carries ordering "
    "information and nothing more; it is not a measurement of how much "
    "anything changed."
)

#: The score returned when every contributing parameter is `unchanged`. Stated
#: as a named constant because it is the anchor the bands are built around,
#: and because it is the value a reader will most want to sanity-check.
NEUTRAL_ANCHOR = 50.0


# --------------------------------------------------------------------------
# Category -> points
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class CategoryPoints:
    """One of Module 29's category labels, and its place on the 0-100 scale."""

    category: str
    points: float
    #: Rank on the five-point ordinal scale, 1 = least favourable.
    rank: int
    basis: str


#: The five ORDERED categories, and nothing else. `changed_direction_only` and
#: `not_classifiable` are absent on purpose -- see `NON_CONTRIBUTING_CATEGORIES`
#: below and the module docstring. `_self_check()` asserts that these two dicts
#: together cover every value in Module 29's `CATEGORY_VALUES`, so a new
#: category cannot ship without a decision recorded here.
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


#: Why a category contributes NOTHING. A machine-readable code plus the
#: sentence the response carries. Absence is reported as absence; it is never
#: converted into a neutral score, a reduced weight, or a smaller contribution.
EXCLUDED_DIRECTION_UNDECLARED = "DIRECTION_UNDECLARED"
EXCLUDED_NOT_CLASSIFIABLE = "NOT_CLASSIFIABLE"
EXCLUDED_ZERO_WEIGHT = "ZERO_WEIGHT_IN_SCORING_TABLE"
EXCLUDED_NO_WEIGHT_DECLARED = "NO_WEIGHT_DECLARED"

#: Unreachable while `_self_check()` holds, because it fails at import if any
#: Module 29 category lacks a decision here. It exists so that the alternative
#: to a missing decision is a stated exclusion rather than a KeyError in the
#: middle of a patient's score -- or, far worse, a silent default onto the
#: neutral anchor.
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
    """A Module 29 category that is deliberately kept off the scale."""

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


# --------------------------------------------------------------------------
# Weights
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ParameterWeight:
    """How much one canonical feature counts toward the weighted mean."""

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

#: TOTAL over `CANONICAL_FEATURES`. `_self_check()` fails at import if a
#: catalogue feature has no row here, so adding a feature to
#: `feature_catalog.py` without deciding what Module 30 does about it cannot
#: silently produce a score that quietly ignores it.
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
    # The liver panel (2026-10-04): equal weight, like every measured value.
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
    # ================ the complete blood count ==============================
    #
    # WEIGHT 1.0, AND NONE OF THEM REACHES A SCORE TODAY. All twelve carry
    # POLARITY_UNDECLARED, so Module 29 returns them as
    # changed_direction_only or not_classifiable and they are excluded on the
    # CATEGORY axis -- which is where a "we do not say which way is better"
    # decision belongs, not here.
    #
    # THE WEIGHT IS 1.0 RATHER THAN 0.0 ON PURPOSE, following `hemoglobin`
    # and `blood_glucose` directly above. 0.0 in this file means "this is not
    # a trend at all" (gender, smoking history). These twelve ARE trends --
    # a platelet count can be followed -- so recording them as non-trends
    # would be false, and declaring a polarity later would then need a second
    # edit here that somebody would forget.
    #
    # ⚠ CONSEQUENCE, STATED BECAUSE IT WAS A DELIBERATE CHOICE: adding these
    # twelve did NOT change any existing progress score. Verified against all
    # four stored reports before and after.
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


# --------------------------------------------------------------------------
# Minimum coverage
# --------------------------------------------------------------------------

#: Below this many CONTRIBUTING parameters, no score is emitted at all:
#: `score` is null and the outcome says why. It is never replaced by 50, never
#: by a band, and never by a sentence that reads like steady progress.
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
    # DERIVED, NOT TYPED. This sentence is served verbatim by
    # `GET /api/v1/progress/policy`, and it said "eight" when the answer was
    # nine -- a number a reviewer would reasonably check the weights against.
    # The adjacent `feature_coverage_note` was computed and correct the whole
    # time, which is the argument for computing this one too: a hand-typed
    # count goes stale the first time the polarity table gains a row, and
    # nothing fails when it does.
    trendable=sum(1 for name in FEATURES if stability_for(name) is not None),
    with_polarity=sum(
        1
        for name in FEATURES
        if stability_for(name) is not None
        and polarity_for(name) is not None
        and polarity_for(name).kind != POLARITY_UNDECLARED
    ),
)


# --------------------------------------------------------------------------
# Bands
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ProgressBandDef:
    """One labelled interval of the 0-100 scale.

    `lower` is INCLUSIVE and `upper` is EXCLUSIVE, except for the topmost
    band, whose `upper` is inclusive so that a score of 100 has a band.
    """

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


#: The score is rounded to this many decimal places BEFORE the band is chosen,
#: so the number a reader sees and the band beside it can never disagree.
SCORE_DECIMAL_PLACES = 1

ROUNDING_NOTE = (
    f"The weighted mean is rounded to {SCORE_DECIMAL_PLACES} decimal place(s) "
    "BEFORE the band is chosen, so the number and the band beside it can "
    "never disagree."
)


# --------------------------------------------------------------------------
# Copy. Deliberately flat, non-clinical language, in the register
# `app/population/policy.py` uses. Scanned by the Module 24 safety scanner at
# import time from `app/services/progress_analyzer.py`.
# --------------------------------------------------------------------------

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

#: SHORTER, NEVER WEAKER. Ninety words of NOT-statements is a paragraph a
#: reader skips, and a caveat that is skipped is not a caveat. Every claim
#: from the long version survives here: it is not a risk score, not a measure
#: of health, not a diagnosis; it says nothing about what to do; it describes
#: only movement between two reports; it cannot see what was not measured on
#: both of them; and the question of whether any of it matters belongs to a
#: professional. MEMORY 6ag: shortening is not the same decision as dropping,
#: and this platform has found this class of sentence MISSING three times.
#: Checked by `assert_safe` at import -- see `progress_analyzer`.
WHAT_THIS_IS_NOT = (
    "This number is not a health score, not a risk score and not a "
    "diagnosis. It only describes which way your results moved between two "
    "reports: it cannot see anything that was not measured on both of them, "
    "it says nothing about how serious any value is, and it says nothing "
    "about what you should do. Whether any of it matters is a question for a "
    "qualified healthcare professional."
)


# --------------------------------------------------------------------------
# Lookup
# --------------------------------------------------------------------------


def points_for(category: str) -> Optional[CategoryPoints]:
    """The scale position for one of Module 29's categories, or None.

    None means the category is deliberately off the scale -- look it up in
    `NON_CONTRIBUTING_CATEGORIES` for the reason code. None does NOT mean
    "no threshold, so score it neutrally": the caller must exclude it.
    """
    return CATEGORY_POINTS.get(category)


def weight_for(feature: str) -> Optional[ParameterWeight]:
    """The weight row for a canonical feature, or None if it has none.

    `_self_check()` makes None unreachable for a catalogue feature; the
    Optional is kept so a caller that is handed an unknown name excludes it
    with `NO_WEIGHT_DECLARED` rather than defaulting it to 1.0.
    """
    return WEIGHTS.get(feature)


def band_for(score: float) -> ProgressBandDef:
    """The band a score falls in. Lower bound inclusive, upper exclusive.

    The topmost band's upper bound is inclusive, so 100 is banded. A value
    outside 0-100 cannot arise -- every point value is inside the range and a
    weighted mean of values in a range stays in that range -- and `_self_check`
    asserts the bands tile the whole range with no gap and no overlap, so this
    function always returns.
    """
    for band in BANDS:
        if band.lower <= score < band.upper:
            return band
    if score == BANDS[-1].upper:
        return BANDS[-1]
    raise ValueError(
        f"score {score!r} is outside the declared scale {SCALE_MIN}-{SCALE_MAX}. "
        "This is a bug in the scorer, not an input problem; no band is guessed."
    )


# --------------------------------------------------------------------------
# Import-time enforcement
# --------------------------------------------------------------------------


def _self_check() -> None:
    """Fail at IMPORT if this table is incomplete or internally inconsistent.

    The dangerous cases are all silent-default cases: a category with no
    decision recorded would have to be given one at runtime, and a feature
    with no weight row would have to be given a default weight. Both are
    clinical claims made by omission, so both fail loudly here instead.
    """
    # 1. Every Module 29 category has a decision: on the scale, or off it.
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

    # 2. The five scale positions are distinct, ranked consistently, and lie
    #    inside the declared scale.
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

    # 3. The claim made in the module docstring -- that the spacing is EQUAL --
    #    is enforced rather than merely asserted in a comment. If someone
    #    edits a point value into an uneven scale, this fails, because the
    #    docstring and `scoring_document()` would then both be lying.
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

    # 4. The weight table is TOTAL over the catalogue.
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

    # 5. A feature declared trendable with a declared polarity must be able to
    #    reach the score. A zero weight on such a feature would silently drop a
    #    parameter the clinical table says is meaningful.
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

    # 6. The bands tile the whole scale exactly once.
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

    # 7. Every anchor gets a band of its own, and no anchor sits on an
    #    INTERIOR boundary -- which is the stated basis for the boundaries. The
    #    two outer edges of the scale (0 and 100) are exempt because they are
    #    the ends of the scale itself, exactly as _BAND_BASIS says. If someone
    #    moves a boundary onto an anchor, that basis sentence stops being true,
    #    so it fails here rather than becoming a false comment.
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

    # 8. The coverage floor must actually enforce the rule it states.
    if MINIMUM_CONTRIBUTING_PARAMETERS < 3:
        raise ValueError(
            "MINIMUM_CONTRIBUTING_PARAMETERS below 3 lets a single parameter "
            "hold a majority of the score, which is the rule "
            "MINIMUM_COVERAGE_BASIS states it exists to prevent."
        )


def scoring_document() -> Dict[str, object]:
    """Machine-readable dump of the whole table, for review and for the API.

    Shape, points, weights, bands and their stated bases only -- no patient
    data of any kind.
    """
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
