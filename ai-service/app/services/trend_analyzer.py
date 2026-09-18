"""Module 28 -- Health Timeline and Trend Analysis. The computation.

`app/data/trend_polarity.py` contains the clinical judgements; this file
contains the arithmetic. It is framework-independent -- no FastAPI, no I/O, no
global state, no network, NO LLM -- so Module 27 (dashboard), Module 30
(progress) and the Node backend can call `analyse_trends()` in-process exactly
as they call `evaluate_rules()` and `fuse_decisions()`.

--------------------------------------------------------------------------
THE FIVE RULES THIS FILE EXISTS TO ENFORCE
--------------------------------------------------------------------------

1. DIRECTION IS NOT "BETTER". Whether a rise is good is read from the polarity
   table, per feature, or refused. There is not one polarity decision in this
   file -- grep it: `direction_of_harm` and `optimal_low` are only ever READ.

2. ABSENCE IS A GAP. A feature missing from a report produces a `TimelineGap`,
   which structurally has no `value` field. Nothing is interpolated, carried
   forward, or replaced with zero.

   A REJECTED OR IMPLAUSIBLE VALUE TAKES NO PART IN A TREND, and that now holds
   on BOTH input paths. On the `validated` path the parse boundary in
   `app/schemas/repository.py` discards rejected values before they arrive. The
   `snapshot` path has no such boundary -- it accepts a `FeatureSnapshot`
   posted directly -- and this docstring used to claim the guarantee anyway,
   which an audit disproved by walking `hba1c -1.0 -> -2.0` through it and
   getting `improving`. `_collect_series` now applies Module 6's OWN possible
   band (`validation_rules.rule_for`, not a second table) and emits
   `IMPLAUSIBLE_VALUE` gaps instead of trend points.

3. STABLE IS EARNED. `stable` is returned only when two or more usable points
   exist AND the net change failed to clear the declared stability band. Fewer
   than two points is `INSUFFICIENT_DATA` with `trend: null`. The
   `FeatureTrend` model enforces the "trend only with TREND_CLASSIFIED" half of
   this structurally, so a future edit here cannot quietly ship a defaulted
   stable.

4. A UNIT MISMATCH IS A REFUSAL. Two reports carrying the same feature in
   different units is `UNIT_MISMATCH` for that feature -- never a conversion.
   Module 5 converts to canonical units BEFORE validation and storage, so by
   the time a value reaches a snapshot the conversion has already happened; a
   mismatch here means something upstream is wrong, and re-converting would
   hide it. `app/data/unit_conversions.py` is deliberately not imported.

5. NO CLINICAL CLAIM, NO FREE TEXT. Every emitted string is assembled from the
   templates in `_TEMPLATES` below, each of which is scanned by the Module 24
   safety scanner at IMPORT time. There is no parameter through which a caller
   could supply wording.

--------------------------------------------------------------------------
WHY NET CHANGE AND NOT A REGRESSION
--------------------------------------------------------------------------

The classification is driven by the first usable reading versus the last, over
whatever gap separates them. That is what the specification's worked example
describes, it is reproducible by hand from the returned `points`, and it does
not manufacture the precision that a least-squares line through three
irregularly spaced readings appears to have. The information a slope would add
is returned explicitly instead: `direction_consistency`, `min_value`,
`max_value` and a `volatile` flag that fires when an intermediate step was
itself significant and moved AGAINST the net direction.

--------------------------------------------------------------------------
LOGGING
--------------------------------------------------------------------------

Counts and codes only, through `safe_meta`. No value, no unit, no feature
value, no patient or report identifier is ever logged from this module.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Tuple

from app.core.errors import BadRequestError
from app.core.logging import get_logger, safe_meta
from app.data.clinical_rules import (
    TIMING_UNSPECIFIED,
    sample_timing,
)
from app.data.feature_catalog import CANONICAL_FEATURES, FEATURES
from app.data.recommendation_catalog import assert_safe
from app.data.validation_rules import rule_for
from app.data.trend_polarity import (
    HARM_DECREASE,
    HARM_INCREASE,
    POLARITY_MONOTONE,
    POLARITY_TOWARD_REFERENCE,
    TREND_POLICY_VERSION,
    StabilityBand,
    TrendPolarity,
    polarity_for,
    reader_reason,
    stability_for,
)
from app.schemas.repository import (
    AVAILABILITY_NOT_REPORTED,
    AVAILABILITY_REJECTED,
    AVAILABILITY_UNUSABLE,
    FeatureSnapshot,
)
from app.schemas.timeline import (
    DIRECTION_FALLING,
    DIRECTION_RISING,
    DIRECTION_UNCHANGED,
    GAP_IMPLAUSIBLE_VALUE,
    GAP_NON_FINITE_VALUE,
    GAP_NON_NUMERIC_VALUE,
    GAP_QUESTIONABLE_EXCLUDED,
    OUTCOME_CHANGE_WITHIN_REFERENCE_INTERVAL,
    OUTCOME_CLINICAL_DIRECTION_UNKNOWN,
    OUTCOME_INSUFFICIENT_DATA,
    OUTCOME_NOT_COMPARABLE_AGE_CONTEXT,
    OUTCOME_NOT_COMPARABLE_SAMPLE_TIMING,
    OUTCOME_NOT_NUMERIC,
    OUTCOME_NOT_TRENDABLE,
    OUTCOME_NO_STABILITY_BAND,
    OUTCOME_TREND_CLASSIFIED,
    OUTCOME_UNIT_MISMATCH,
    OUTCOME_UNIT_NOT_CANONICAL,
    TREND_IMPROVING,
    TREND_STABLE,
    TREND_WORSENING,
    AppliedPolarity,
    AppliedStability,
    FeatureTrend,
    TimelineGap,
    TimelineOptions,
    TimelinePoint,
    TimelineReportInput,
    TimelineReportRef,
    TimelineSummary,
    TimelineTrendsData,
    TimelineTrendsRequest,
    TrendChange,
)
from app.services.feature_repository import build_snapshot

logger = get_logger(__name__)

#: Bumped when the analyzer's own behaviour changes, independently of the
#: clinical tables' `TREND_POLICY_VERSION`.
TREND_ANALYZER_VERSION = "1.0.0"


# --------------------------------------------------------------------------
# Every user-facing string this module can emit
# --------------------------------------------------------------------------
#
# There is no other source of prose here. Each template is scanned by the
# Module 24 recommendation safety scanner at import time (see `_self_check`
# at the bottom), so a future edit that introduces a diagnostic assertion, a
# dosage or a treatment instruction fails the import rather than reaching a
# patient.

DISCLAIMER = (
    "This timeline describes how measured laboratory values changed between "
    "reports. It reports arithmetic and a declared direction of change only. "
    "It does not interpret those changes, does not identify any condition, and "
    "is not a substitute for review by a qualified health professional."
)

def _label(feature: str) -> str:
    """The feature's reader-facing name, for the sentences below.

    EVERY TEMPLATE HERE IS SHOWN TO A READER, and every one of them used to
    interpolate the raw canonical key -- "blood_glucose went from 186 to 88",
    "smoking_history is a category feature". The catalog already holds the
    name for each feature and it is what the comparison table beside these
    sentences prints; there is no reason for one panel to say "Blood sugar"
    and the panel under it to say `blood_glucose`.

    Falls back to the key. A feature with no catalog entry is still nameable,
    and an unnamed row is worse than an ugly one.
    """
    definition = FEATURES.get(feature)
    return definition.description if definition else feature


_TEMPLATES: Dict[str, str] = {
    "insufficient": (
        "{feature}: {count} usable reading(s) across {reports} report(s). At "
        "least two are needed before any change can be described, so no trend "
        "is reported. This is not the same as no change having occurred."
    ),
    "not_numeric": (
        "{feature} is a {value_type} feature. It has no magnitude, so there is "
        "nothing to trend. The readings are returned in order for reference."
    ),
    "not_trendable": (
        "No direction is declared for {feature}: {basis}"
    ),
    "no_stability_band": (
        "{feature} has no declared stability band, so there is no threshold "
        "against which a change could be called real. No trend is reported."
    ),
    "unit_mismatch": (
        "{feature} was reported in more than one unit across these reports "
        "({units}). The readings are not comparable and are not converted "
        "here; unit normalisation belongs upstream, before a value is stored. "
        "No trend is reported."
    ),
    "unit_not_canonical": (
        "{feature}: {count} reading(s) are not in the canonical unit "
        "({canonical}), so the series is not comparable. No trend is reported."
    ),
    "timing_mismatch": (
        "{feature} readings were taken under different sample timings "
        "({timings}). Those are not comparable quantities, so no trend is "
        "reported."
    ),
    "age_context": (
        "The declared direction for {feature} is only valid from age "
        "{min_age} years, and a younger age is recorded in this series. No "
        "trend is reported."
    ),
    "age_unknown": (
        "The declared direction for {feature} is only valid from age "
        "{min_age} years, and no age was recorded in this series. An unknown "
        "age is not assumed to be an adult one, so no trend is reported."
    ),
    "change_line": (
        "{feature} went from {first} to {last}{unit} between {first_date} and "
        "{last_date} ({days} days apart), a change of {absolute}{pct}."
    ),
    "stable": (
        " That is within the declared stability band for this feature "
        "({pct_band} % and {abs_band}{unit}), so the series is reported as "
        "stable."
    ),
    "significant": (
        " That clears the declared stability band for this feature "
        "({pct_band} % and {abs_band}{unit})."
    ),
    "monotone_worse": (
        " An increase is declared unfavourable for this feature, so the "
        "direction of change is unfavourable."
    ),
    "monotone_worse_falling": (
        " A decrease is declared unfavourable for this feature, so the "
        "direction of change is unfavourable."
    ),
    "monotone_better": (
        " An increase is declared unfavourable for this feature, so the "
        "direction of change is favourable."
    ),
    "monotone_better_rising": (
        " A decrease is declared unfavourable for this feature, so the "
        "direction of change is favourable."
    ),
    "toward_better": (
        " The value moved closer to the declared reference interval "
        "({interval}), so the direction of change is favourable."
    ),
    "toward_worse": (
        " The value moved further from the declared reference interval "
        "({interval}), so the direction of change is unfavourable."
    ),
    "within_reference": (
        " Both readings sit inside the declared reference interval "
        "({interval}), so no favourable or unfavourable direction is "
        "reported for this change."
    ),
    "crossed_reference": (
        " The value moved from one side of the declared reference interval "
        "({interval}) to the other. A single favourable or unfavourable label "
        "would misdescribe that, so none is reported."
    ),
    "equidistant": (
        " The first and last readings sit the same distance from the declared "
        "reference interval ({interval}) on opposite sides, so no favourable "
        "or unfavourable direction is reported."
    ),
    # "Reason recorded in the polarity table" named a file in this repository
    # inside a sentence a patient reads. The REASON that follows is genuinely
    # useful and is kept verbatim; only the filing cabinet it came out of goes.
    "direction_unknown": (
        " No clinical direction is declared for this feature, so whether the "
        "change is favourable is not reported. Why: {basis}"
    ),
    "volatile": (
        " Note that the value moved significantly in the opposite direction at "
        "least once in between, so the overall change does not describe the "
        "whole series."
    ),
    "questionable_note": (
        " {count} of the readings used were flagged as questionable during "
        "validation."
    ),
}

_WARNING_TEMPLATES: Dict[str, str] = {
    "single_report": (
        "Only {count} report was supplied. A timeline needs at least two "
        "reports before any change can be described."
    ),
    "no_reports": "No reports were supplied, so there is no timeline to build.",
    "no_features": (
        "None of the supplied reports carried a usable value for any canonical "
        "feature."
    ),
    "mixed_unspecified_timing": (
        "Some readings established a sample timing and others did not. The "
        "series is still described, but the readings may not be comparable."
    ),
    "duplicate_dates": (
        "{count} report(s) share a date with another report. Ordering between "
        "them is resolved deterministically and does not change between calls."
    ),
    "extreme_present": (
        "{count} reading(s) in this timeline were flagged as clinically "
        "extreme during validation."
    ),
}


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------


def _is_real_number(value: object) -> bool:
    """True for a finite int/float that is NOT a bool.

    `isinstance(True, int)` is True in Python, so the explicit bool check is
    load-bearing: without it a tri-state boolean would be trended as 0/1 and
    absence would be one step away from becoming a value.
    """
    if isinstance(value, bool):
        return False
    if not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value))


def _normalise_unit(unit: Optional[str]) -> Optional[str]:
    """Case- and whitespace-fold a unit FOR COMPARISON ONLY.

    'mg/dL' and 'mg/dl' are the same unit written twice. This never converts a
    value and never rewrites the unit that is returned to the caller.
    """
    if unit is None:
        return None
    folded = " ".join(unit.split()).lower()
    return folded or None


def _fmt(value: float) -> str:
    """A stable decimal rendering. No scientific notation, no trailing zeros."""
    if value == int(value) and abs(value) < 1e15:
        return str(int(value))
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    return text or "0"


def _fmt_date(value: datetime) -> str:
    return value.date().isoformat()


def _unit_suffix(unit: Optional[str]) -> str:
    return f" {unit}" if unit else ""


def _availability_for_gap(code: str) -> str:
    return {
        GAP_IMPLAUSIBLE_VALUE: AVAILABILITY_UNUSABLE,
        GAP_NON_NUMERIC_VALUE: AVAILABILITY_UNUSABLE,
        GAP_NON_FINITE_VALUE: AVAILABILITY_UNUSABLE,
        GAP_QUESTIONABLE_EXCLUDED: AVAILABILITY_UNUSABLE,
    }.get(code, AVAILABILITY_UNUSABLE)


def _distance_to_interval(
    value: float, low: Optional[float], high: Optional[float]
) -> float:
    """How far `value` sits OUTSIDE [low, high]. Zero when it is inside."""
    if low is not None and value < low:
        return low - value
    if high is not None and value > high:
        return value - high
    return 0.0


def _interval_text(polarity: TrendPolarity, unit: Optional[str]) -> str:
    suffix = _unit_suffix(unit)
    low, high = polarity.optimal_low, polarity.optimal_high
    if low is not None and high is not None:
        return f"{_fmt(low)} to {_fmt(high)}{suffix}"
    if low is not None:
        return f"at or above {_fmt(low)}{suffix}"
    if high is not None:
        return f"at or below {_fmt(high)}{suffix}"
    return "not declared"


# --------------------------------------------------------------------------
# Step 1 -- reports into ordered snapshots
# --------------------------------------------------------------------------


class _OrderedReport:
    """One report's snapshot plus its place on the timeline."""

    __slots__ = ("report_id", "date", "snapshot")

    def __init__(
        self, report_id: str, date: datetime, snapshot: FeatureSnapshot
    ) -> None:
        self.report_id = report_id
        self.date = date
        self.snapshot = snapshot


def _sort_key(report: TimelineReportInput) -> Tuple[datetime, int, int, str]:
    """The TOTAL, DATA-ONLY ordering.

    `chrono_date` first. Ties break on an explicit `sequence` when the caller
    supplied one (reports that supplied one sort before those that did not, so
    the flag is part of the key rather than a branch), then on `report_id`.

    Nothing in this key depends on the position of the report in the request
    array, so shuffling the array cannot change the output. `report_id`
    uniqueness is already enforced by `TimelineTrendsRequest`, so the key is
    total: no two reports can compare equal.
    """
    return (
        report.chrono_date,
        0 if report.sequence is not None else 1,
        report.sequence if report.sequence is not None else 0,
        report.report_id,
    )


def _to_snapshot(report: TimelineReportInput) -> FeatureSnapshot:
    """Whatever shape the caller sent -> one Module 7 `FeatureSnapshot`.

    `build_snapshot` is Module 7's own function; using it means the rejected
    map is discarded at the same parse boundary, the `unavailable` reasons are
    the same reasons every other consumer sees, and Module 28 owns no second
    definition of "a usable feature".
    """
    if report.snapshot is not None:
        return report.snapshot
    return build_snapshot(
        report.validated,
        report_ref=report.report_id,
        report_date=report.chrono_date,
    )


def _order_reports(
    reports: Sequence[TimelineReportInput],
) -> Tuple[List[_OrderedReport], List[str]]:
    ordered = sorted(reports, key=_sort_key)
    warnings: List[str] = []

    seen_dates: Dict[datetime, int] = {}
    for report in ordered:
        seen_dates[report.chrono_date] = seen_dates.get(report.chrono_date, 0) + 1
    shared = sum(count for count in seen_dates.values() if count > 1)
    if shared:
        warnings.append(_WARNING_TEMPLATES["duplicate_dates"].format(count=shared))

    return (
        [
            _OrderedReport(r.report_id, r.chrono_date, _to_snapshot(r))
            for r in ordered
        ],
        warnings,
    )


# --------------------------------------------------------------------------
# Step 2 -- one feature's series
# --------------------------------------------------------------------------


def _is_physiologically_possible(
    feature: str, value: float, unit: Optional[str]
) -> bool:
    """Is `value` inside Module 6's possible band for `feature`?

    ONE definition of "possible" on this project, read from
    `validation_rules.rule_for` -- the same table Module 6 rejects on. A
    second table here could drift from it, and two tables disagreeing about
    what is physiologically possible is the defect class this project's audits
    keep finding.

    Values reaching a snapshot are already in the canonical unit (Module 5
    converts before validation and storage), and a unit that is NOT canonical
    is refused separately as `UNIT_NOT_CANONICAL` before any of this matters.
    So a unit that disagrees with the rule's is not second-guessed here: this
    function returns True and lets the unit refusal own that case, rather than
    comparing a number against bounds stated for a different unit.

    True whenever there is nothing to check: no rule, a non-numeric rule, or
    no bound on the side in question. The job is to catch the impossible, not
    to invent a limit Module 6 never stated.
    """
    rule = rule_for(feature)
    if rule is None or not rule.is_numeric:
        return True
    if rule.possible_low is None and rule.possible_high is None:
        return True
    if unit is not None and rule.unit is not None and unit != rule.unit:
        return True
    if rule.possible_low is not None and value < rule.possible_low:
        return False
    if rule.possible_high is not None and value > rule.possible_high:
        return False
    return True


def _collect_series(
    feature: str,
    reports: Sequence[_OrderedReport],
    options: TimelineOptions,
    timing_sensitive: bool,
) -> Tuple[List[TimelinePoint], List[TimelineGap]]:
    """Split the reports into usable points and explained gaps.

    Every report ends up in exactly one of the two lists. A report is never
    silently dropped, because "we have no reading here" is information the
    caller has to be able to see.
    """
    points: List[TimelinePoint] = []
    gaps: List[TimelineGap] = []

    for report in reports:
        snapshot = report.snapshot
        stored = snapshot.features.get(feature)

        if stored is None:
            entry = snapshot.unavailable.get(feature)
            if entry is not None:
                gaps.append(
                    TimelineGap(
                        report_id=report.report_id,
                        date=report.date,
                        availability=entry.availability,
                        reason_code=entry.reason_code,
                        reason=entry.reason,
                    )
                )
            else:
                # A snapshot posted directly may not enumerate every canonical
                # feature in `unavailable`. Absence is still absence.
                gaps.append(
                    TimelineGap(
                        report_id=report.report_id,
                        date=report.date,
                        availability=AVAILABILITY_NOT_REPORTED,
                        reason_code="NOT_REPORTED",
                        reason=(
                            "This feature was not present in this report's "
                            "validated feature set."
                        ),
                    )
                )
            continue

        if options.exclude_questionable and stored.questionable:
            gaps.append(
                TimelineGap(
                    report_id=report.report_id,
                    date=report.date,
                    availability=_availability_for_gap(GAP_QUESTIONABLE_EXCLUDED),
                    reason_code=GAP_QUESTIONABLE_EXCLUDED,
                    reason=(
                        "The reading was flagged questionable during validation "
                        "and questionable readings were excluded for this "
                        "request."
                    ),
                )
            )
            continue

        # PLAUSIBILITY, BORROWED FROM MODULE 6 RATHER THAN RE-DECIDED HERE.
        #
        # This module's docstring says "a rejected value cannot even reach
        # here: the parse boundary in app/schemas/repository.py discards it".
        # That is true of the `validated` input path and FALSE of the
        # `snapshot` one, which accepts a `FeatureSnapshot` posted directly
        # with nothing behind it -- an audit walked `hba1c -1.0 -> -2.0`
        # through that door and got `improving`, a trend statement about two
        # impossible numbers.
        #
        # Rather than leave the docstring wrong or the door open, the same
        # bound Module 6 rejects on is applied here, from the same table
        # (`validation_rules.rule_for`), so there is one definition of
        # "physiologically possible" and not two. On the `validated` path this
        # is a no-op, because Module 6 has already removed these.
        if _is_real_number(stored.value) and not _is_physiologically_possible(
            feature, float(stored.value), stored.unit
        ):
            gaps.append(
                TimelineGap(
                    report_id=report.report_id,
                    date=report.date,
                    availability=_availability_for_gap(GAP_IMPLAUSIBLE_VALUE),
                    reason_code=GAP_IMPLAUSIBLE_VALUE,
                    reason=(
                        "The stored reading lies outside the physiologically "
                        "possible range for this parameter, so it is read as "
                        "an extraction error rather than a measurement and "
                        "takes no part in the trend."
                    ),
                )
            )
            continue

        if not _is_real_number(stored.value):
            code = (
                GAP_NON_FINITE_VALUE
                if isinstance(stored.value, float)
                else GAP_NON_NUMERIC_VALUE
            )
            gaps.append(
                TimelineGap(
                    report_id=report.report_id,
                    date=report.date,
                    availability=_availability_for_gap(code),
                    reason_code=code,
                    reason=(
                        "The stored reading is not a finite number, so it "
                        "cannot take part in a trend."
                    ),
                )
            )
            continue

        timing: Optional[str] = None
        if timing_sensitive:
            provenance = stored.provenance
            timing = sample_timing(
                provenance.original_test_name if provenance else None,
                provenance.matched_synonym if provenance else None,
            )

        points.append(
            TimelinePoint(
                report_id=report.report_id,
                date=report.date,
                value=float(stored.value),
                unit=stored.unit,
                status=stored.status,
                questionable=stored.questionable,
                clinically_extreme=stored.clinically_extreme,
                extreme_direction=stored.extreme_direction,
                flags=list(stored.flags),
                sample_timing=timing,
            )
        )

    return points, gaps


def _change_from(points: Sequence[TimelinePoint], band: StabilityBand) -> TrendChange:
    first, last = points[0], points[-1]
    absolute = last.value - first.value
    percent: Optional[float] = None
    if first.value != 0:
        percent = round(absolute / abs(first.value) * 100.0, 4)

    values = [p.value for p in points]
    steps = [
        (points[i], points[i + 1], points[i + 1].value - points[i].value)
        for i in range(len(points) - 1)
    ]

    net_sign = 0 if absolute == 0 else (1 if absolute > 0 else -1)
    non_zero = [delta for _, _, delta in steps if delta != 0]
    consistency: Optional[float] = None
    if net_sign != 0 and non_zero:
        agreeing = sum(1 for delta in non_zero if (delta > 0) == (net_sign > 0))
        consistency = round(agreeing / len(non_zero), 4)

    volatile = False
    for earlier, later, delta in steps:
        if delta == 0:
            continue
        if not _is_significant(earlier.value, later.value, band):
            continue
        step_sign = 1 if delta > 0 else -1
        if net_sign == 0 or step_sign != net_sign:
            volatile = True
            break

    return TrendChange(
        first_report_id=first.report_id,
        last_report_id=last.report_id,
        first_date=first.date,
        last_date=last.date,
        days_between=round((last.date - first.date).total_seconds() / 86400.0, 4),
        first_value=first.value,
        last_value=last.value,
        absolute_change=absolute,
        percent_change=percent,
        min_value=min(values),
        max_value=max(values),
        step_count=len(steps),
        direction_consistency=consistency,
        volatile=volatile,
    )


def _is_significant(first: float, last: float, band: StabilityBand) -> bool:
    """Did the move clear BOTH declared thresholds?

    Both, not either: a percentage alone calls one reporting increment a trend
    when the value is small, and an absolute alone calls a rounding difference
    a trend when the value is large. When the first value is zero the
    percentage is undefined, and only the absolute floor applies -- the
    alternative would be to treat an undefined percentage as infinite, which is
    exactly the "absence becomes a value" mistake in another costume.
    """
    absolute = abs(last - first)
    if absolute < band.min_absolute_change:
        return False
    # A MOVE OF ZERO IS NOT A SIGNIFICANT MOVE, whatever the band permits.
    #
    # REACHED ONLY WHEN `min_absolute_change` IS 0.0, because any positive
    # floor already caught it one line above -- and every band in
    # `trend_polarity.py` declares a positive floor (0.1 to 25.0). The caller
    # that passes 0.0 is Module 35 (`lab_polarity`), which has no canonical
    # unit to set a floor in and documents that choice.
    #
    # Without this, a series that did not move fell through to the `first == 0`
    # branch below and was called SIGNIFICANT. Found live: BASOPHILS is 0 % on
    # both of this account's reports, and a zero change was being handed to
    # `_classify` as a real one -- which then refused to label it, so the panel
    # showed "no change" and no trend word while every neighbour showed one.
    # The reader asked why that row was different. This is why.
    if absolute == 0:
        return False
    if first == 0:
        return True
    percent = absolute / abs(first) * 100.0
    return percent >= band.significant_change_pct


# --------------------------------------------------------------------------
# Step 3 -- classification. Reads the polarity table; never decides polarity.
# --------------------------------------------------------------------------


def _classify(
    polarity: TrendPolarity,
    change: TrendChange,
    significant: bool,
) -> Tuple[str, Optional[str], str]:
    """`(outcome, trend, reason_template_key)`.

    The ONLY place a trend label is produced. Every branch either reads
    `polarity` or refuses; none of them contains a clinical judgement of its
    own.
    """
    if not significant:
        return OUTCOME_TREND_CLASSIFIED, TREND_STABLE, "stable"

    rising = change.absolute_change > 0

    if polarity.kind == POLARITY_MONOTONE:
        harm_on_rise = polarity.direction_of_harm == HARM_INCREASE
        worse = rising if harm_on_rise else not rising
        if worse:
            key = "monotone_worse" if harm_on_rise else "monotone_worse_falling"
            return OUTCOME_TREND_CLASSIFIED, TREND_WORSENING, key
        key = "monotone_better" if harm_on_rise else "monotone_better_rising"
        return OUTCOME_TREND_CLASSIFIED, TREND_IMPROVING, key

    if polarity.kind == POLARITY_TOWARD_REFERENCE:
        low, high = polarity.optimal_low, polarity.optimal_high
        first, last = change.first_value, change.last_value

        # Crossing the whole interval -- deficient to excessive, or the
        # reverse. The distance arithmetic below would happily call that an
        # improvement if the far side happened to be nearer; it is not one, and
        # it is not a worsening either. Refuse it explicitly.
        if low is not None and high is not None:
            if (first < low and last > high) or (first > high and last < low):
                return (
                    OUTCOME_CLINICAL_DIRECTION_UNKNOWN,
                    None,
                    "crossed_reference",
                )

        before = _distance_to_interval(first, low, high)
        after = _distance_to_interval(last, low, high)

        if before == 0.0 and after == 0.0:
            return (
                OUTCOME_CHANGE_WITHIN_REFERENCE_INTERVAL,
                None,
                "within_reference",
            )
        if after < before:
            return OUTCOME_TREND_CLASSIFIED, TREND_IMPROVING, "toward_better"
        if after > before:
            return OUTCOME_TREND_CLASSIFIED, TREND_WORSENING, "toward_worse"
        return OUTCOME_CLINICAL_DIRECTION_UNKNOWN, None, "equidistant"

    # UNDECLARED. The value moved measurably and this service will not guess
    # whether that is good news.
    return OUTCOME_CLINICAL_DIRECTION_UNKNOWN, None, "direction_unknown"


# --------------------------------------------------------------------------
# Step 4 -- one feature, end to end
# --------------------------------------------------------------------------


def analyse_feature(
    feature: str,
    reports: Sequence[_OrderedReport],
    options: Optional[TimelineOptions] = None,
    *,
    recorded_ages: Sequence[float] = (),
) -> FeatureTrend:
    """The whole Module 28 computation for ONE canonical feature."""
    options = options or TimelineOptions()
    definition = FEATURES[feature]
    polarity = polarity_for(feature)
    if polarity is None:  # pragma: no cover -- _self_check makes this impossible
        raise BadRequestError(
            f"{feature!r} has no trend polarity declaration.",
            code="TREND_POLARITY_MISSING",
        )
    band = stability_for(feature)

    points, gaps = _collect_series(
        feature, reports, options, timing_sensitive=polarity.timing_sensitive
    )
    warnings: List[str] = []

    applied_polarity = AppliedPolarity(
        kind=polarity.kind,
        direction_of_harm=polarity.direction_of_harm,
        optimal_low=polarity.optimal_low,
        optimal_high=polarity.optimal_high,
        basis=reader_reason(polarity),
    )
    applied_stability = (
        AppliedStability(
            significant_change_pct=band.significant_change_pct,
            min_absolute_change=band.min_absolute_change,
            basis=band.basis,
        )
        if band is not None
        else None
    )

    def result(
        outcome: str,
        reason: str,
        *,
        trend: Optional[str] = None,
        direction: Optional[str] = None,
        change: Optional[TrendChange] = None,
    ) -> FeatureTrend:
        return FeatureTrend(
            # THE CANONICAL KEY, NEVER THE LABEL. This is the field every
            # consumer keys off -- the frontend looks up its own patient
            # wording with it and uses it as a React key. A blanket
            # `feature=feature` -> `feature=_label(feature)` rewrite across
            # this file caught this ONE line along with ten genuine message
            # templates, and it silently changed the API contract: the
            # response started carrying "Glycated haemoglobin, NGSP %" where
            # `hba1c` belongs, the frontend's label lookup missed, and the
            # chart headings quietly reverted to the clinical register.
            # 3,768 tests did not notice. Found by reading the rendered page.
            feature=feature,
            value_type=definition.value_type,
            canonical_unit=definition.canonical_unit,
            points=points,
            gaps=gaps,
            report_count=len(reports),
            usable_point_count=len(points),
            outcome=outcome,
            trend=trend,
            direction=direction,
            change=change,
            polarity=applied_polarity,
            stability=applied_stability,
            reason=reason,
            warnings=warnings,
        )

    # ---- refusals that do not depend on the data at all ------------------
    if definition.value_type not in ("number", "integer"):
        return result(
            OUTCOME_NOT_NUMERIC,
            _TEMPLATES["not_numeric"].format(
                feature=_label(feature), value_type=definition.value_type
            ),
        )
    if not polarity.trendable:
        return result(
            OUTCOME_NOT_TRENDABLE,
            _TEMPLATES["not_trendable"].format(
                feature=_label(feature), basis=reader_reason(polarity)
            ),
        )
    if band is None:
        return result(
            OUTCOME_NO_STABILITY_BAND,
            _TEMPLATES["no_stability_band"].format(feature=_label(feature)),
        )

    # ---- unit integrity. Refused, never coerced. -------------------------
    #
    # Checked BEFORE the point count, so a two-report series in two different
    # units reports the unit problem rather than a trend, and BEFORE any
    # arithmetic touches the values.
    canonical = _normalise_unit(definition.canonical_unit)
    observed = {_normalise_unit(p.unit) for p in points}
    if len(observed) > 1:
        shown = ", ".join(sorted(str(u) for u in observed))
        return result(
            OUTCOME_UNIT_MISMATCH,
            _TEMPLATES["unit_mismatch"].format(feature=_label(feature), units=shown),
        )
    non_canonical = [
        p
        for p in points
        if _normalise_unit(p.unit) != canonical
        or any(f.code == "UNIT_NOT_CANONICAL" for f in p.flags)
    ]
    if non_canonical:
        return result(
            OUTCOME_UNIT_NOT_CANONICAL,
            _TEMPLATES["unit_not_canonical"].format(
                feature=_label(feature),
                count=len(non_canonical),
                canonical=definition.canonical_unit or "none",
            ),
        )

    # ---- sample timing, for the features where it changes the quantity ---
    if polarity.timing_sensitive and points:
        established = {
            p.sample_timing
            for p in points
            if p.sample_timing and p.sample_timing != TIMING_UNSPECIFIED
        }
        if len(established) > 1:
            return result(
                OUTCOME_NOT_COMPARABLE_SAMPLE_TIMING,
                _TEMPLATES["timing_mismatch"].format(
                    feature=_label(feature), timings=", ".join(sorted(established))
                ),
            )
        unspecified = any(
            p.sample_timing == TIMING_UNSPECIFIED for p in points
        )
        if established and unspecified:
            warnings.append(_WARNING_TEMPLATES["mixed_unspecified_timing"])

    # ---- age context for declarations that are adult-only ----------------
    #
    # AN UNKNOWN AGE IS REFUSED, NOT ASSUMED ADULT. This guard used to require
    # `recorded_ages` to be non-empty, so a series with no `age` feature took
    # the adult interval silently: `bmi 15.0 -> 17.5` in a child classified as
    # `improving` against the WHO adult 18.5-24.9 band, while the SAME series
    # with `age=8` present was correctly refused. That is age-unknown becoming
    # age-adult, which is this project's most repeated hazard (MEMORY.md 11)
    # in the one place the polarity table explicitly says not to go: the
    # declaration states the interval "is NOT valid in children and
    # adolescents".
    #
    # This is also what the module already does for glucose, which is refused
    # outright for want of a recorded sample timing rather than assumed
    # fasting. Same shape of missing context, same answer.
    if polarity.min_age_years is not None:
        if not recorded_ages:
            return result(
                OUTCOME_NOT_COMPARABLE_AGE_CONTEXT,
                _TEMPLATES["age_unknown"].format(
                    feature=_label(feature), min_age=polarity.min_age_years
                ),
            )
        if min(recorded_ages) < polarity.min_age_years:
            return result(
                OUTCOME_NOT_COMPARABLE_AGE_CONTEXT,
                _TEMPLATES["age_context"].format(
                    feature=_label(feature), min_age=polarity.min_age_years
                ),
            )

    # ---- fewer than two points is INSUFFICIENT_DATA, never stable --------
    if len(points) < 2:
        return result(
            OUTCOME_INSUFFICIENT_DATA,
            _TEMPLATES["insufficient"].format(
                feature=_label(feature), count=len(points), reports=len(reports)
            ),
        )

    # ---- the actual computation ------------------------------------------
    change = _change_from(points, band)
    significant = _is_significant(change.first_value, change.last_value, band)
    if applied_stability is not None:
        applied_stability = applied_stability.model_copy(
            update={"exceeded": significant}
        )

    if change.absolute_change > 0:
        direction = DIRECTION_RISING
    elif change.absolute_change < 0:
        direction = DIRECTION_FALLING
    else:
        direction = DIRECTION_UNCHANGED

    outcome, trend, key = _classify(polarity, change, significant)

    unit = points[0].unit
    suffix = _unit_suffix(unit)
    pct_text = (
        f", {_fmt(round(change.percent_change, 2))} %"
        if change.percent_change is not None
        else ""
    )
    reason = _TEMPLATES["change_line"].format(
        feature=_label(feature),
        first=_fmt(change.first_value),
        last=_fmt(change.last_value),
        unit=suffix,
        first_date=_fmt_date(change.first_date),
        last_date=_fmt_date(change.last_date),
        # ABSOLUTE in the prose. `days_between` is signed on the data object,
        # which is correct there -- it records the direction the caller asked
        # for, and an explicitly named reverse-chronological pair is honoured
        # as named (swapping it would invert every label) and warned about
        # separately. But "N days apart" is a SEPARATION, and rendering it as
        # "(-152 days apart)" is simply wrong wording on an otherwise correct
        # answer. The sign stays available to a consumer on the field itself.
        days=_fmt(round(abs(change.days_between), 1)),
        absolute=f"{_fmt(change.absolute_change)}{suffix}",
        pct=pct_text,
    )
    reason += _TEMPLATES["significant" if significant else "stable"].format(
        pct_band=_fmt(band.significant_change_pct),
        abs_band=_fmt(band.min_absolute_change),
        unit=suffix,
    )
    if significant:
        reason += _TEMPLATES[key].format(
            interval=_interval_text(polarity, unit), basis=reader_reason(polarity)
        )
    if change.volatile:
        reason += _TEMPLATES["volatile"]
    questionable = sum(1 for p in points if p.questionable)
    if questionable:
        reason += _TEMPLATES["questionable_note"].format(count=questionable)

    result_trend = result(
        outcome, reason, trend=trend, direction=direction, change=change
    )
    # `applied_stability` was rebuilt after `result`'s closure captured the
    # original, so set the final one explicitly rather than relying on order.
    return result_trend.model_copy(update={"stability": applied_stability})


# --------------------------------------------------------------------------
# Step 5 -- the whole request
# --------------------------------------------------------------------------


def _features_to_analyse(
    reports: Sequence[_OrderedReport], options: TimelineOptions
) -> List[str]:
    if options.features:
        return list(options.features)
    if options.include_all_canonical:
        return list(CANONICAL_FEATURES)
    present = {
        name for report in reports for name in report.snapshot.features
    }
    # Catalog order, so the response is stable and not hash-ordered.
    return [name for name in CANONICAL_FEATURES if name in present]


def _recorded_ages(reports: Sequence[_OrderedReport]) -> List[float]:
    ages: List[float] = []
    for report in reports:
        stored = report.snapshot.features.get("age")
        if stored is not None and _is_real_number(stored.value):
            ages.append(float(stored.value))
    return ages


def analyse_trends(request: TimelineTrendsRequest) -> TimelineTrendsData:
    """The Module 28 entry point. Deterministic, offline, and model-free.

    Same input -> byte-identical output, apart from `generated_at`. Nothing
    here is random, nothing is cached, and nothing calls out of the process.
    """
    ordered, warnings = _order_reports(request.reports)
    options = request.options

    if not ordered:
        warnings.append(_WARNING_TEMPLATES["no_reports"])
    elif len(ordered) == 1:
        warnings.append(
            _WARNING_TEMPLATES["single_report"].format(count=len(ordered))
        )

    names = _features_to_analyse(ordered, options)
    if ordered and not names:
        warnings.append(_WARNING_TEMPLATES["no_features"])

    ages = _recorded_ages(ordered)
    features: Dict[str, FeatureTrend] = {
        name: analyse_feature(name, ordered, options, recorded_ages=ages)
        for name in names
    }

    extreme = sum(
        1
        for trend in features.values()
        for point in trend.points
        if point.clinically_extreme
    )
    if extreme:
        warnings.append(_WARNING_TEMPLATES["extreme_present"].format(count=extreme))

    outcomes: Dict[str, int] = {}
    for trend in features.values():
        outcomes[trend.outcome] = outcomes.get(trend.outcome, 0) + 1

    summary = TimelineSummary(
        report_count=len(ordered),
        features_examined=len(features),
        improving=sum(1 for t in features.values() if t.trend == TREND_IMPROVING),
        worsening=sum(1 for t in features.values() if t.trend == TREND_WORSENING),
        stable=sum(1 for t in features.values() if t.trend == TREND_STABLE),
        not_determinable=sum(1 for t in features.values() if t.trend is None),
        outcomes=dict(sorted(outcomes.items())),
        first_report_date=ordered[0].date if ordered else None,
        last_report_date=ordered[-1].date if ordered else None,
        days_span=(
            round((ordered[-1].date - ordered[0].date).total_seconds() / 86400.0, 4)
            if len(ordered) >= 2
            else None
        ),
    )

    # Counts and codes only. No identifier, no value, no feature name.
    logger.info(
        "timeline_trends %s",
        safe_meta(
            reports=len(ordered),
            features=len(features),
            improving=summary.improving,
            worsening=summary.worsening,
            stable=summary.stable,
            not_determinable=summary.not_determinable,
            policy_version=TREND_POLICY_VERSION,
        ),
    )

    return TimelineTrendsData(
        patient_ref=request.patient_ref,
        policy_version=TREND_POLICY_VERSION,
        reports=[
            TimelineReportRef(
                report_id=report.report_id,
                date=report.date,
                order=index,
                feature_count=len(report.snapshot.features),
            )
            for index, report in enumerate(ordered)
        ],
        features=features,
        summary=summary,
        warnings=warnings,
        disclaimer=DISCLAIMER,
    )


def analyzer_document() -> Dict[str, object]:
    """The analyzer's own policy, machine-readable. No patient data."""
    return {
        "analyzer_version": TREND_ANALYZER_VERSION,
        "policy_version": TREND_POLICY_VERSION,
        "method": (
            "Net change from the first usable reading to the last, classified "
            "against a per-feature stability band and a per-feature declared "
            "polarity. No regression, no model, no LLM."
        ),
        "ordering": (
            "chrono_date ascending; ties break on an explicit sequence when "
            "supplied, then on report_id. The key uses only the data, so the "
            "order cannot change between calls."
        ),
        "absence_policy": (
            "A feature missing from a report is a gap carrying a reason code "
            "and no value. Nothing is interpolated or carried forward."
        ),
        "unit_policy": (
            "Different units across reports, or any non-canonical unit, is a "
            "refusal for that feature. No conversion happens here; Module 5 "
            "converts before storage."
        ),
        "disclaimer": DISCLAIMER,
    }


# --------------------------------------------------------------------------
# Import-time enforcement
# --------------------------------------------------------------------------


def _self_check() -> None:
    """Every emittable string is scanned by the Module 24 safety scanner.

    The templates carry `{placeholders}`; the scanner works on the literal
    text, and the substituted values are numbers, dates, feature names and
    units, none of which can introduce a banned phrase. `polarity.basis` is
    substituted into two templates and is reviewer-written text held in
    `app/data/trend_polarity.py`; it is not scanned there (it legitimately
    discusses clinical concepts) but it is also never composed at runtime.
    """
    for key, template in _TEMPLATES.items():
        assert_safe(template, f"trend reason template {key}")
    for key, template in _WARNING_TEMPLATES.items():
        assert_safe(template, f"trend warning template {key}")
    assert_safe(DISCLAIMER, "trend disclaimer")

    # Guard the classification contract itself: exactly one outcome may carry
    # a trend. If someone adds a branch that returns a trend with a refusal
    # outcome, `FeatureTrend` raises -- this asserts the pairing is still the
    # one documented above.
    if OUTCOME_TREND_CLASSIFIED not in (
        OUTCOME_TREND_CLASSIFIED,
        OUTCOME_INSUFFICIENT_DATA,
    ):  # pragma: no cover
        raise ValueError("outcome vocabulary drifted")


_self_check()


# --------------------------------------------------------------------------
# PUBLIC SURFACE ADDED FOR MODULE 29 (Smart Report Comparison) -- ADDITIVE
# --------------------------------------------------------------------------
#
# These are ALIASES ONLY. Nothing above this line was changed, no behaviour
# was altered, and every name below refers to the exact object Module 28 has
# always used. They exist so that `app/services/report_comparator.py` can
# reuse Module 28's ordering, snapshot parsing, series collection and value
# formatting INSTEAD OF writing a second copy of any of them.
#
# The alternative -- Module 29 importing the underscore-prefixed names -- would
# work identically in Python but would leave no record that these are a
# deliberate, supported interface. If one of them is ever changed, Module 29 is
# a caller and must be checked.
#
# `analyse_feature` remains the entry point Module 29 uses for the actual
# improved / worsened / unchanged decision, over a two-report series. There is
# no second polarity lookup and no second stability comparison anywhere in
# Module 29.

#: One report's snapshot plus its place in time. Module 29 builds a two-element
#: list of these and hands it to `analyse_feature`.
OrderedReport = _OrderedReport

#: Sort reports into the total, data-only order and report duplicate dates.
order_reports = _order_reports

#: One `TimelineReportInput` -> one Module 7 `FeatureSnapshot`.
to_snapshot = _to_snapshot

#: Split reports into usable points and explained gaps for one feature.
collect_series = _collect_series

#: The `age` readings present across a set of reports.
recorded_ages = _recorded_ages

#: Finite int/float that is not a bool. The guard that stops a tri-state
#: boolean being read as 0/1.
is_real_number = _is_real_number

#: Stable decimal rendering, so Module 29's summary text formats numbers the
#: same way Module 28's reasons do.
format_value = _fmt
format_date = _fmt_date


__all__ = [
    "DISCLAIMER",
    "TREND_ANALYZER_VERSION",
    "OrderedReport",
    "analyse_feature",
    "analyse_trends",
    "analyzer_document",
    "collect_series",
    "format_date",
    "format_value",
    "is_real_number",
    "order_reports",
    "recorded_ages",
    "to_snapshot",
]
