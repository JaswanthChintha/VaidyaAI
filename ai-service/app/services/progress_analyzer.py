"""Module 30 -- Health Progress Analysis. The Health Progress Score.

Specification (Module 30): "calculate a Health Progress Score based on changes
across selected laboratory parameters ... based on predefined rules ...
reflects health trends rather than disease diagnosis ... improved parameters,
worsened parameters, stable parameters, relative changes ... an easy-to-
understand representation of longitudinal progress."

==========================================================================
WHAT THIS FILE DOES, AND WHAT IT REFUSES TO DO
==========================================================================

It calls `report_comparator.compare_reports()` -- Module 29 -- and turns the
finished per-parameter `category` labels into one number using the table in
`app/data/progress_scoring.py`.

That is the whole of it. This file contains:

* **no polarity lookup.** It never asks `polarity_for()`. Whether a rise in
  creatinine is better or worse was decided by Module 28, through Module 29,
  from `app/data/trend_polarity.py`.
* **no stability comparison.** It never calls `_is_significant`, never reads a
  `StabilityBand`, and never compares a percent change with a threshold. It
  reports Module 29's `significant` boolean and scores Module 29's label.
* **no arithmetic on patient values at all**, beyond a weighted mean of point
  values that came from a lookup table. `absolute_change` and `percent_change`
  are carried through from Module 28's `TrendChange` untouched.

A third table that could disagree with the other two about whether a rising
value is good is the defect class this project's audits keep finding, so
Module 30 deliberately has no clinical table of its own. `progress_scoring.py`
declares only the shape of the scale.

==========================================================================
THE HAZARD THIS MODULE IS BUILT AROUND
==========================================================================

    Absence must never become a value.

A parameter that Module 29 returned as `not_classifiable` or
`changed_direction_only` -- because it was missing from one report, arrived in
an inconsistent unit, is not trendable, or has no declared clinical direction
-- contributes NOTHING. Not a neutral 50. Not a reduced weight. Nothing.

It is listed in `coverage.excluded` with a reason code, and it lowers
`coverage.contributing_count`. `ExcludedParameter` has no `points` field at
all, so an exclusion is structurally incapable of being read as a neutral
contribution.

When no parameter could be placed on the scale, `score` is `None` and
`outcome` is `NOTHING_ASSESSED`. `HealthProgressData` enforces that pairing in
a model validator, so no future edit can publish a confident-looking 50 for a
patient about whom nothing could be told. This is the same rule that makes
`RiskLevel.highest([])` return None rather than LOW, that stops Module 18
reporting a healthy status when nothing was assessed, and that stops Module 28
reporting `stable` for a series with fewer than two readings.

The second half of the same idea is the COVERAGE FLOOR. A score built from one
lucky parameter prints with exactly the confidence of one built from nine, so
below `MINIMUM_CONTRIBUTING_PARAMETERS` the outcome is
`INSUFFICIENT_COVERAGE`, the contributions found are still returned in full,
and no headline number is. The floor's stated basis -- no single parameter may
hold a majority of the score -- lives in the data file with the number.

==========================================================================
DETERMINISTIC AND MODEL-FREE
==========================================================================

No LLM, no I/O, no clock except `generated_at`, no randomness, no dict
iteration order that depends on anything but the catalogue. Same request in,
byte-identical response out. Every emitted sentence comes from `_TEMPLATES`
below, which is scanned by the Module 24 safety scanner at import time; the
only things substituted in are feature names, integers, dates and code
constants.

==========================================================================
REGISTER
==========================================================================

The copy is deliberately flat and non-clinical, in the register
`app/population/policy.py` uses. Module 30 makes no clinical claim, so none of
its text may contain a risk word, a recommendation, a normal/abnormal
judgement of its own, or a severity word. The band labels describe MOVEMENT
ACROSS MEASURED PARAMETERS, not a state of health.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from app.core.errors import ErrorCode, ServiceError
from app.core.logging import get_logger, safe_meta
from app.data.feature_catalog import CANONICAL_FEATURES
from app.data.progress_scoring import (
    BANDS,
    CATEGORY_POINTS,
    EXCLUDED_DIRECTION_UNDECLARED,
    EXCLUDED_NOT_CLASSIFIABLE,
    EXCLUDED_NO_WEIGHT_DECLARED,
    EXCLUDED_UNKNOWN_CATEGORY,
    EXCLUDED_ZERO_WEIGHT,
    MINIMUM_CONTRIBUTING_PARAMETERS,
    NEUTRAL_ANCHOR,
    NON_CONTRIBUTING_CATEGORIES,
    PROGRESS_SCORING_VERSION,
    ROUNDING_NOTE,
    SCALE_DIRECTION,
    SCALE_DIRECTION_TEXT,
    SCALE_KIND,
    SCALE_KIND_NOTE,
    SCALE_MAX,
    SCALE_MIN,
    SCORE_DECIMAL_PLACES,
    WHAT_THIS_IS,
    WHAT_THIS_IS_NOT,
    band_for,
    points_for,
    scoring_document,
    weight_for,
)
from app.data.recommendation_catalog import assert_safe
from app.data.trend_polarity import TREND_POLICY_VERSION
from app.schemas.comparison import (
    CATEGORY_IMPROVED,
    CATEGORY_NEWLY_ABNORMAL,
    CATEGORY_NEWLY_NORMAL,
    CATEGORY_UNCHANGED,
    CATEGORY_VALUES,
    CATEGORY_WORSENED,
    ComparisonOptions,
    ParameterComparison,
    ReportComparisonRequest,
)
from app.schemas.progress import (
    PROGRESS_INSUFFICIENT_COVERAGE,
    PROGRESS_NO_PAIR,
    PROGRESS_NOTHING_ASSESSED,
    PROGRESS_SCORE_COMPUTED,
    ExcludedParameter,
    HealthProgressData,
    HealthProgressRequest,
    ParameterContribution,
    ProgressBand,
    ProgressCounts,
    ProgressCoverage,
    ProgressScale,
    ProgressSummary,
)
from app.services.report_comparator import COMPARATOR_VERSION, compare_reports
from app.services.trend_analyzer import (
    TREND_ANALYZER_VERSION,
    format_date,
    format_value,
)

logger = get_logger(__name__)

#: Bumped when this scorer's own behaviour changes, independently of the
#: scoring table's `PROGRESS_SCORING_VERSION` and of the clinical tables'
#: `TREND_POLICY_VERSION`.
PROGRESS_ANALYZER_VERSION = "1.0.0"


# --------------------------------------------------------------------------
# Every user-facing string this module can emit
# --------------------------------------------------------------------------
#
# Scanned by the Module 24 safety scanner at import time (see `_self_check`).
# Substituted values are feature names, integers, formatted numbers and code
# constants; none of them can introduce a banned phrase.

DISCLAIMER = (
    "The health progress score describes how a set of measured laboratory "
    "values moved between two reports. It is not a measure of health, not a "
    "measure of risk, and it is not a diagnosis. It cannot see any parameter "
    "that was not measured on both reports, and it does not know why any "
    "value moved. Discuss your results with a qualified healthcare "
    "professional."
)

_TEMPLATES: Dict[str, str] = {
    # ---- headlines, one per outcome. Exactly one of them mentions a number.
    "headline_scored": (
        "Health progress score {score} out of {maximum}, on a scale where "
        "higher means more of the measured movement was in the direction "
        "recorded as favourable. Built from {contributing} of the "
        "{examined} parameter(s) compared between the report of "
        "{baseline_date} and the report of {comparison_date}."
    ),
    "headline_no_pair": (
        "No health progress score. Fewer than two reports were supplied, so "
        "there is nothing to compare and no movement to describe."
    ),
    "headline_nothing_assessed": (
        "No health progress score. Two reports were compared, but not one of "
        "the {examined} parameter(s) examined could be placed on the scale. "
        "Being unable to tell whether a parameter moved is not the same as "
        "that parameter holding steady, so no number is reported."
    ),
    "headline_insufficient": (
        "No health progress score. Only {contributing} of the {examined} "
        "parameter(s) examined could be placed on the scale, and at least "
        "{minimum} are required. Below that, a single parameter would decide "
        "most of the number, so the parameters found are listed instead."
    ),
    # ---- coverage, stated in every response ----
    "coverage_note": (
        "This score was built from {contributing} parameter(s) out of the "
        "{examined} examined. The {excluded} parameter(s) that could not be "
        "placed on the scale are listed with the reason and count for nothing "
        "in the number."
    ),
    "coverage_note_none": (
        "None of the {examined} parameter(s) examined could be placed on the "
        "scale. They are listed with the reason, and no number was computed "
        "from them."
    ),
    "coverage_note_no_pair": (
        "No parameters were examined, because fewer than two reports were "
        "supplied."
    ),
    # ---- summary lines ----
    "line_newly_normal": (
        "{count} parameter(s) moved from outside to inside the reference "
        "interval printed on the report: {features}."
    ),
    "line_improved": (
        "{count} parameter(s) moved in the direction recorded as favourable: "
        "{features}."
    ),
    "line_unchanged": (
        "{count} parameter(s) were measured on both reports and did not move "
        "by more than their declared stability band: {features}."
    ),
    "line_worsened": (
        "{count} parameter(s) moved in the direction recorded as "
        "unfavourable: {features}."
    ),
    "line_newly_abnormal": (
        "{count} parameter(s) moved from inside to outside the reference "
        "interval printed on the report: {features}."
    ),
    "line_significant": (
        "{count} of the parameters in the score changed by more than their "
        "declared stability band: {features}."
    ),
    "line_excluded": (
        "{count} parameter(s) counted for nothing in the score: {items}."
    ),
    "line_band": "Band: {label}. {description}",
    "line_equal_weight": (
        "Every parameter in the score counts the same. No parameter is "
        "weighted above another, because there is no basis for ranking them."
    ),
    # ---- exclusion reasons ----
    "excluded_direction_undeclared": (
        "{feature} moved by more than its declared stability band, but no "
        "clinical direction is recorded for it, so there is no way to say "
        "whether that movement was favourable or unfavourable. It counts for "
        "nothing in the score rather than counting as no movement."
    ),
    "excluded_not_classifiable": (
        "{feature} could not be compared between the two reports "
        "({outcome}), so nothing is known about whether it moved. It counts "
        "for nothing in the score rather than counting as no movement."
    ),
    "excluded_zero_weight": (
        "{feature} carries no weight in the scoring table, because it is not "
        "a quantity that has a direction of change. It counts for nothing in "
        "the score."
    ),
    "excluded_no_weight": (
        "{feature} has no weight recorded in the scoring table, so it counts "
        "for nothing in the score. Nothing is assumed on its behalf."
    ),
    "excluded_unknown_category": (
        "{feature} came back with a category ({category}) that the scoring "
        "table has no entry for, so it counts for nothing in the score. "
        "Nothing is assumed on its behalf."
    ),
}

_WARNING_TEMPLATES: Dict[str, str] = {
    "below_minimum": (
        "Only {contributing} parameter(s) could be placed on the scale and at "
        "least {minimum} are required, so no score was computed. A number "
        "built from fewer parameters would be shown with the same confidence "
        "as one built from many."
    ),
    "nothing_assessed": (
        "No parameter could be placed on the scale, so no score was computed. "
        "This is not a statement that nothing changed."
    ),
    "no_pair": (
        "Fewer than two reports were supplied, so no comparison and no score "
        "were produced."
    ),
    "narrow_coverage": (
        "This score was built from {contributing} parameter(s). It describes "
        "those parameters and says nothing about any parameter that was not "
        "measured on both reports."
    ),
    "features_narrowed": (
        "The request restricted the score to {count} named parameter(s), so "
        "the coverage below is the coverage that was asked for rather than "
        "everything the two reports carried."
    ),
    "significance_not_scaled": (
        "The size of each change decides only whether it counts as a change "
        "at all, against the stability band declared for that parameter. A "
        "larger change does not move the score further than a smaller one in "
        "the same category."
    ),
}


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------


def _join(names: Sequence[str]) -> str:
    """Deterministic comma list. Order is the caller's, never a set's."""
    return ", ".join(names)


#: Module 29 category -> the summary-line template that names it. Only the
#: five SCORED categories appear; the two excluded ones are reported through
#: `line_excluded`, which carries their reason instead of a count alone.
_CATEGORY_LINES: Tuple[Tuple[str, str], ...] = (
    (CATEGORY_NEWLY_NORMAL, "line_newly_normal"),
    (CATEGORY_IMPROVED, "line_improved"),
    (CATEGORY_UNCHANGED, "line_unchanged"),
    (CATEGORY_WORSENED, "line_worsened"),
    (CATEGORY_NEWLY_ABNORMAL, "line_newly_abnormal"),
)


def _band_models() -> List[ProgressBand]:
    """The declared bands, echoed. Describes the instrument, not the patient."""
    return [
        ProgressBand(
            key=band.key,
            lower_inclusive=band.lower,
            upper_exclusive=band.upper,
            label=band.label,
            description=band.description,
        )
        for band in BANDS
    ]


def _scale() -> ProgressScale:
    """The scale block, identical on every response including the refusals.

    Every field is read from a named constant in
    `app/data/progress_scoring.py`, the same constants `scoring_document()`
    returns, so the wording a patient sees beside the number and the wording
    `GET /api/v1/progress/policy` publishes cannot drift apart.
    """
    return ProgressScale(
        min=SCALE_MIN,
        max=SCALE_MAX,
        direction=SCALE_DIRECTION,
        direction_text=SCALE_DIRECTION_TEXT,
        neutral_anchor=NEUTRAL_ANCHOR,
        kind=SCALE_KIND,
        kind_note=SCALE_KIND_NOTE,
        rounding=ROUNDING_NOTE,
        bands=_band_models(),
    )


def _exclusion(
    parameter: ParameterComparison,
    reason_code: str,
    template_key: str,
    **fields: object,
) -> ExcludedParameter:
    """Build one exclusion. There is no code path that builds a partial one."""
    return ExcludedParameter(
        feature=parameter.feature,
        description=parameter.description,
        category=parameter.category,
        outcome=parameter.outcome,
        transition_outcome=parameter.transition_outcome,
        reason_code=reason_code,
        reason=_TEMPLATES[template_key].format(feature=parameter.feature, **fields),
    )


# --------------------------------------------------------------------------
# The one decision this module makes per parameter
# --------------------------------------------------------------------------


def _score_parameter(
    parameter: ParameterComparison,
) -> Tuple[Optional[ParameterContribution], Optional[ExcludedParameter]]:
    """Score ONE already-compared parameter, or explain why it cannot be.

    Returns exactly one of the two: a contribution or an exclusion, never both
    and never neither. The caller relies on that to keep
    `contributing + excluded == examined`, which `ProgressCoverage` then
    re-checks structurally.

    THE ONLY INPUT TO THE POINT VALUE IS `parameter.category`. Nothing here
    inspects a patient value, a unit, a reference interval or a threshold.
    """
    # 1. Is this category on the scale at all? A category that is deliberately
    #    off the scale is an exclusion carrying the reason the DATA FILE gives,
    #    not a reason invented here.
    entry = points_for(parameter.category)
    if entry is None:
        declared = NON_CONTRIBUTING_CATEGORIES.get(parameter.category)
        if declared is None:
            # Unreachable while `progress_scoring._self_check()` holds -- it
            # fails at import if any Module 29 category lacks a decision. Kept
            # because the alternative to an explicit branch here is a KeyError
            # in the middle of a patient's score, or worse, a silent default
            # onto the neutral anchor.
            return None, _exclusion(
                parameter,
                EXCLUDED_UNKNOWN_CATEGORY,
                "excluded_unknown_category",
                category=parameter.category,
            )
        if declared.reason_code == EXCLUDED_DIRECTION_UNDECLARED:
            return None, _exclusion(
                parameter,
                EXCLUDED_DIRECTION_UNDECLARED,
                "excluded_direction_undeclared",
            )
        if declared.reason_code == EXCLUDED_NOT_CLASSIFIABLE:
            return None, _exclusion(
                parameter,
                EXCLUDED_NOT_CLASSIFIABLE,
                "excluded_not_classifiable",
                outcome=parameter.outcome,
            )
        # A new non-contributing category with a reason code this function has
        # no sentence for. Excluded with the code it declared, using the
        # generic wording -- never scored, and never silently dropped.
        return None, _exclusion(
            parameter,
            declared.reason_code,
            "excluded_unknown_category",
            category=parameter.category,
        )

    # 2. Does the scoring table give this feature a weight, and is it non-zero?
    weight = weight_for(parameter.feature)
    if weight is None:
        return None, _exclusion(
            parameter, EXCLUDED_NO_WEIGHT_DECLARED, "excluded_no_weight"
        )
    if weight.weight <= 0.0:
        return None, _exclusion(
            parameter, EXCLUDED_ZERO_WEIGHT, "excluded_zero_weight"
        )

    change = parameter.change
    unit = parameter.canonical_unit or parameter.baseline.unit or parameter.comparison.unit

    return (
        ParameterContribution(
            feature=parameter.feature,
            description=parameter.description,
            unit=unit,
            category=parameter.category,
            outcome=parameter.outcome,
            transition_outcome=parameter.transition_outcome,
            transition=parameter.transition,
            direction=parameter.direction,
            significant=parameter.significant,
            absolute_change=change.absolute_change if change else None,
            percent_change=change.percent_change if change else None,
            points=entry.points,
            weight=weight.weight,
            weighted_points=entry.points * weight.weight,
        ),
        None,
    )


# --------------------------------------------------------------------------
# The summary
# --------------------------------------------------------------------------


def _counts(
    contributions: Sequence[ParameterContribution],
    parameters: Dict[str, ParameterComparison],
) -> ProgressCounts:
    """Counts over the CONTRIBUTIONS, plus a full category tally beside them.

    `by_category` deliberately spans every examined parameter, contributing or
    not, so that a reader who adds the five scored counts and compares them
    with `features_examined` sees the shortfall rather than a tidy total that
    absorbed it.
    """
    by_category: Dict[str, int] = {}
    for parameter in parameters.values():
        by_category[parameter.category] = by_category.get(parameter.category, 0) + 1

    scored: Dict[str, int] = {name: 0 for name in CATEGORY_VALUES}
    significant = 0
    for contribution in contributions:
        scored[contribution.category] += 1
        if contribution.significant:
            significant += 1

    return ProgressCounts(
        newly_normal=scored[CATEGORY_NEWLY_NORMAL],
        improved=scored[CATEGORY_IMPROVED],
        unchanged=scored[CATEGORY_UNCHANGED],
        worsened=scored[CATEGORY_WORSENED],
        newly_abnormal=scored[CATEGORY_NEWLY_ABNORMAL],
        significant_changes=significant,
        by_category=dict(sorted(by_category.items())),
    )


def _summary(
    outcome: str,
    score: Optional[float],
    band: Optional[ProgressBand],
    contributions: Sequence[ParameterContribution],
    excluded: Sequence[ExcludedParameter],
    examined: int,
    baseline_date: Optional[str],
    comparison_date: Optional[str],
) -> ProgressSummary:
    """Templated prose. No generator, no model, no free-text entry point."""
    contributing = len(contributions)

    if outcome == PROGRESS_NO_PAIR:
        headline = _TEMPLATES["headline_no_pair"]
    elif outcome == PROGRESS_NOTHING_ASSESSED:
        headline = _TEMPLATES["headline_nothing_assessed"].format(examined=examined)
    elif outcome == PROGRESS_INSUFFICIENT_COVERAGE:
        headline = _TEMPLATES["headline_insufficient"].format(
            contributing=contributing,
            examined=examined,
            minimum=MINIMUM_CONTRIBUTING_PARAMETERS,
        )
    else:
        # SCORE_COMPUTED. `score`, `baseline_date` and `comparison_date` are
        # all non-None on this path -- the caller only reaches it with a pair
        # and a computed score -- but they are defaulted rather than asserted
        # so that a formatting bug can never raise mid-response.
        headline = _TEMPLATES["headline_scored"].format(
            score=format_value(score if score is not None else 0.0),
            maximum=format_value(SCALE_MAX),
            contributing=contributing,
            examined=examined,
            baseline_date=baseline_date or "",
            comparison_date=comparison_date or "",
        )

    lines: List[str] = []
    if band is not None:
        lines.append(
            _TEMPLATES["line_band"].format(
                label=band.label, description=band.description
            )
        )

    by_category: Dict[str, List[str]] = {name: [] for name in CATEGORY_VALUES}
    significant: List[str] = []
    for contribution in contributions:
        by_category[contribution.category].append(contribution.feature)
        if contribution.significant:
            significant.append(contribution.feature)

    for category, template_key in _CATEGORY_LINES:
        names = by_category[category]
        if names:
            lines.append(
                _TEMPLATES[template_key].format(
                    count=len(names), features=_join(names)
                )
            )

    if significant:
        lines.append(
            _TEMPLATES["line_significant"].format(
                count=len(significant), features=_join(significant)
            )
        )

    if excluded:
        lines.append(
            _TEMPLATES["line_excluded"].format(
                count=len(excluded),
                items=_join(
                    [f"{item.feature} ({item.reason_code})" for item in excluded]
                ),
            )
        )

    if contributions:
        lines.append(_TEMPLATES["line_equal_weight"])

    return ProgressSummary(headline=headline, lines=lines)


# --------------------------------------------------------------------------
# The whole request
# --------------------------------------------------------------------------


def analyse_progress(request: HealthProgressRequest) -> HealthProgressData:
    """The Module 30 entry point. Deterministic, offline, and model-free.

    Same input -> byte-identical output, apart from `generated_at`. Nothing
    here is random, nothing is cached, and nothing calls out of the process.

    The whole clinical decision -- which parameters improved, worsened, held
    steady, or could not be told -- is `compare_reports()`'s, which is
    `analyse_feature()`'s, which is `app/data/trend_polarity.py`'s. This
    function chooses no thresholds and looks up no polarity.
    """
    comparison = compare_reports(
        ReportComparisonRequest(
            patient_ref=request.patient_ref,
            reports=request.reports,
            baseline_ref=request.baseline_ref,
            comparison_ref=request.comparison_ref,
            options=ComparisonOptions(
                features=request.options.features,
                exclude_questionable=request.options.exclude_questionable,
                # The score is between two reports, so the intermediate series
                # is never needed here. `include_all_canonical` is left off:
                # padding the response with parameters neither report carried
                # would inflate `features_examined` with IN_NEITHER rows that
                # can only ever be exclusions, making the coverage figure read
                # worse than the data actually is.
                include_series=False,
                include_all_canonical=False,
            ),
        )
    )

    warnings: List[str] = list(comparison.warnings)

    # PER-PARAMETER WARNINGS MUST TRAVEL WITH THE SCORE THEY QUALIFY.
    #
    # `comparison.warnings` is the REQUEST-level list. Module 29 also attaches
    # warnings to individual parameters, and two of those exist precisely to
    # qualify a contribution this module then scores:
    # `crossed_without_significant_change` and
    # `transition_conflicts_with_change`. Neither has a request-level twin, so
    # taking only the outer list dropped them entirely.
    #
    # What that cost, measured: creatinine 1.19 -> 1.21 mg/dL against a printed
    # 0.6-1.20 interval is a move of 0.02, which this project's own declared
    # stability band calls measurement noise -- and it crosses the bound. The
    # crossing outranks the change axis by design (that call is Module 29's and
    # it is defensible), so the score fell 50.0 -> 37.5 and the headline band
    # moved from "Mixed, or little movement" to "More unfavourable movement
    # than favourable" -- with the one sentence explaining why nowhere in the
    # response. A number that moves a patient's headline must carry its own
    # caveat.
    #
    # De-duplicated because one warning text can arise on several parameters
    # and repeating it adds noise without adding information; order is the
    # parameters' own, so the output stays deterministic.
    for parameter in comparison.parameters.values():
        for warning in parameter.warnings:
            if warning not in warnings:
                warnings.append(warning)
    if request.options.features is not None:
        warnings.append(
            _WARNING_TEMPLATES["features_narrowed"].format(
                count=len(request.options.features)
            )
        )

    # ---- score every compared parameter, in CATALOGUE order so the response
    # ---- ordering depends on nothing but the data.
    parameters = comparison.parameters
    contributions: List[ParameterContribution] = []
    excluded: List[ExcludedParameter] = []
    for name in CANONICAL_FEATURES:
        parameter = parameters.get(name)
        if parameter is None:
            continue
        contribution, exclusion = _score_parameter(parameter)
        if contribution is not None:
            contributions.append(contribution)
        else:
            # `_score_parameter` returns exactly one of the two; the assertion
            # is structural, not defensive -- a None/None return would silently
            # drop a parameter out of both counts and out of the coverage
            # figure, which is the one number this module must not get wrong.
            if exclusion is None:  # pragma: no cover
                raise ServiceError(
                    "progress scoring produced neither a contribution nor an "
                    "exclusion for a compared parameter",
                    code=ErrorCode.INTERNAL_ERROR,
                    status_code=500,
                )
            excluded.append(exclusion)

    examined = len(parameters)
    contributing = len(contributions)

    # ---- outcome. This is the only place a score comes into existence, and
    # ---- every branch that does not produce one leaves it None.
    score: Optional[float] = None
    band_model: Optional[ProgressBand] = None

    if comparison.pair is None:
        outcome = PROGRESS_NO_PAIR
        warnings.append(_WARNING_TEMPLATES["no_pair"])
    elif contributing == 0:
        outcome = PROGRESS_NOTHING_ASSESSED
        warnings.append(_WARNING_TEMPLATES["nothing_assessed"])
    elif contributing < MINIMUM_CONTRIBUTING_PARAMETERS:
        outcome = PROGRESS_INSUFFICIENT_COVERAGE
        warnings.append(
            _WARNING_TEMPLATES["below_minimum"].format(
                contributing=contributing,
                minimum=MINIMUM_CONTRIBUTING_PARAMETERS,
            )
        )
    else:
        outcome = PROGRESS_SCORE_COMPUTED
        total_weight = sum(item.weight for item in contributions)
        # Unreachable while every contribution carries weight > 0, which
        # `ParameterContribution` enforces with `gt=0.0` and
        # `_score_parameter` enforces by excluding zero-weight features. The
        # branch exists so that a division by zero can never be the thing that
        # decides a patient's score.
        if total_weight <= 0.0:  # pragma: no cover
            raise ServiceError(
                "progress scoring reached a zero total weight",
                code=ErrorCode.INTERNAL_ERROR,
                status_code=500,
            )
        raw = sum(item.weighted_points for item in contributions) / total_weight
        score = round(raw, SCORE_DECIMAL_PLACES)
        # Guard the invariant the band lookup depends on. A weighted mean of
        # values inside 0-100 is inside 0-100, so this cannot fire; if it ever
        # does, refusing is right and inventing a band is not.
        if not SCALE_MIN <= score <= SCALE_MAX:  # pragma: no cover
            raise ServiceError(
                "progress score fell outside its declared scale",
                code=ErrorCode.INTERNAL_ERROR,
                status_code=500,
            )
        # The band is chosen from the ROUNDED score, so the number a reader
        # sees and the band beside it can never disagree.
        chosen = band_for(score)
        band_model = ProgressBand(
            key=chosen.key,
            lower_inclusive=chosen.lower,
            upper_exclusive=chosen.upper,
            label=chosen.label,
            description=chosen.description,
        )
        warnings.append(_WARNING_TEMPLATES["significance_not_scaled"])
        if contributing < 2 * MINIMUM_CONTRIBUTING_PARAMETERS:
            warnings.append(
                _WARNING_TEMPLATES["narrow_coverage"].format(
                    contributing=contributing
                )
            )

    # ---- coverage. Present on every response, refusals included.
    if comparison.pair is None:
        coverage_note = _TEMPLATES["coverage_note_no_pair"]
    elif contributing == 0:
        coverage_note = _TEMPLATES["coverage_note_none"].format(examined=examined)
    else:
        coverage_note = _TEMPLATES["coverage_note"].format(
            contributing=contributing,
            examined=examined,
            excluded=len(excluded),
        )

    coverage = ProgressCoverage(
        features_examined=examined,
        contributing_count=contributing,
        excluded_count=len(excluded),
        minimum_required=MINIMUM_CONTRIBUTING_PARAMETERS,
        sufficient=contributing >= MINIMUM_CONTRIBUTING_PARAMETERS,
        contributing=[item.feature for item in contributions],
        excluded=excluded,
        coverage_note=coverage_note,
    )

    summary = _summary(
        outcome=outcome,
        score=score,
        band=band_model,
        contributions=contributions,
        excluded=excluded,
        examined=examined,
        baseline_date=(
            format_date(comparison.pair.baseline_date) if comparison.pair else None
        ),
        comparison_date=(
            format_date(comparison.pair.comparison_date) if comparison.pair else None
        ),
    )

    logger.info(
        "health_progress %s",
        safe_meta(
            reports=len(comparison.reports),
            examined=examined,
            contributing=contributing,
            excluded=len(excluded),
            outcome=outcome,
            # The score is a derived, non-identifying summary statistic and is
            # NOT a medical value: it is a position on a fixed scale, carries
            # no unit, and cannot be inverted to any reading. No feature name,
            # no value and no unit is logged.
            score=score,
            scoring_version=PROGRESS_SCORING_VERSION,
            policy_version=TREND_POLICY_VERSION,
        ),
    )

    return HealthProgressData(
        patient_ref=request.patient_ref,
        policy_version=TREND_POLICY_VERSION,
        scoring_version=PROGRESS_SCORING_VERSION,
        analyzer_version=TREND_ANALYZER_VERSION,
        comparator_version=COMPARATOR_VERSION,
        progress_version=PROGRESS_ANALYZER_VERSION,
        reports=comparison.reports,
        pair=comparison.pair,
        outcome=outcome,
        score=score,
        band=band_model,
        scale=_scale(),
        coverage=coverage,
        contributions=contributions,
        counts=_counts(contributions, parameters),
        summary=summary,
        comparison=comparison if request.options.include_comparison else None,
        warnings=warnings,
        what_this_is=WHAT_THIS_IS,
        what_this_is_not=WHAT_THIS_IS_NOT,
        disclaimer=DISCLAIMER,
    )


def progress_document() -> Dict[str, object]:
    """Module 30's own policy plus the scoring table. No patient data."""
    return {
        "progress_version": PROGRESS_ANALYZER_VERSION,
        "scoring_version": PROGRESS_SCORING_VERSION,
        "comparator_version": COMPARATOR_VERSION,
        "analyzer_version": TREND_ANALYZER_VERSION,
        "policy_version": TREND_POLICY_VERSION,
        "method": (
            "Module 30 calls Module 29's compare_reports(), which delegates "
            "the improved / worsened / unchanged decision to Module 28's "
            "analyse_feature(), which reads the single polarity table and the "
            "single stability band table in app/data/trend_polarity.py. "
            "Module 30 maps each finished category label onto a point value "
            "from app/data/progress_scoring.py and takes the weighted mean. "
            "It performs no polarity lookup, no significance test and no "
            "arithmetic on any patient value."
        ),
        "outcomes": {
            "branch_on": "outcome",
            "score_present_for": PROGRESS_SCORE_COMPUTED,
            "note": (
                "score is non-null for exactly one outcome. Every other "
                "outcome carries score: null and band: null, enforced by a "
                "model validator on the response so that a refusal cannot "
                "acquire a number by a later edit."
            ),
        },
        "coverage_policy": (
            "Every examined parameter either contributes or is listed as "
            "excluded with a reason code; the response's own validator "
            "requires the two to add up to the number examined. A score built "
            "from few parameters is reported with the count that built it, and "
            "below the declared minimum no score is emitted at all."
        ),
        "scoring": scoring_document(),
        "disclaimer": DISCLAIMER,
    }


# --------------------------------------------------------------------------
# Import-time enforcement
# --------------------------------------------------------------------------


def _self_check() -> None:
    """Every emittable string is scanned by the Module 24 safety scanner.

    The templates carry `{placeholders}`; the scanner works on the literal
    text, and the substituted values are integers, formatted numbers, dates,
    feature names and code constants -- none of which can introduce a banned
    phrase. The band labels and descriptions, the coverage copy and the two
    `WHAT_THIS_IS*` paragraphs live in `app/data/progress_scoring.py` and are
    scanned here rather than there, so that every string this service can
    print for Module 30 passes through one scanner call site.
    """
    for key, template in _TEMPLATES.items():
        assert_safe(template, f"progress template {key}")
    for key, template in _WARNING_TEMPLATES.items():
        assert_safe(template, f"progress warning template {key}")
    assert_safe(DISCLAIMER, "progress disclaimer")
    assert_safe(WHAT_THIS_IS, "progress what_this_is")
    assert_safe(WHAT_THIS_IS_NOT, "progress what_this_is_not")
    assert_safe(SCALE_DIRECTION_TEXT, "progress scale direction text")
    for band in BANDS:
        assert_safe(band.label, f"progress band label {band.key}")
        assert_safe(band.description, f"progress band description {band.key}")
    for name, entry in NON_CONTRIBUTING_CATEGORIES.items():
        assert_safe(entry.basis, f"progress non-contributing basis {name}")

    # Guard the contract that makes this module safe: exactly the five ordered
    # categories may be scored, and `unchanged` must sit on the neutral anchor.
    # If Module 29 grows a category, `progress_scoring._self_check()` already
    # fails; this asserts the pairing this file relies on has not drifted.
    if set(CATEGORY_POINTS) != {
        CATEGORY_NEWLY_NORMAL,
        CATEGORY_IMPROVED,
        CATEGORY_UNCHANGED,
        CATEGORY_WORSENED,
        CATEGORY_NEWLY_ABNORMAL,
    }:
        raise ValueError(
            "the set of scored categories has changed. Module 30's summary "
            "lines and its 'absence is never a value' rule are written around "
            "these five; review both before changing the table."
        )
    if CATEGORY_POINTS[CATEGORY_UNCHANGED].points != NEUTRAL_ANCHOR:
        raise ValueError("'unchanged' must sit on the declared neutral anchor")

    # Every summary line template must exist for every scored category, or a
    # contributing parameter would be counted into the score and then vanish
    # from the prose that explains it.
    for category, template_key in _CATEGORY_LINES:
        if category not in CATEGORY_POINTS:
            raise ValueError(f"summary line for unscored category {category}")
        if template_key not in _TEMPLATES:
            raise ValueError(f"missing summary template {template_key}")
    if len(_CATEGORY_LINES) != len(CATEGORY_POINTS):
        raise ValueError("every scored category needs exactly one summary line")


_self_check()


__all__ = [
    "DISCLAIMER",
    "PROGRESS_ANALYZER_VERSION",
    "analyse_progress",
    "progress_document",
]
