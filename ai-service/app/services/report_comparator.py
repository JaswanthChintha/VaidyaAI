"""Module 29 -- Smart Report Comparison. The computation.

`app/data/trend_polarity.py` holds the clinical judgements; Module 28's
`app/services/trend_analyzer.py` holds the change arithmetic; this file holds
only what is genuinely new: WHICH two reports are compared, whether a value
crossed the reference interval THAT REPORT PRINTED, and the templated summary.

It is framework-independent -- no FastAPI, no I/O, no global state, no
network, NO LLM -- so Module 27 (dashboard), Module 30 (progress) and the Node
backend can call `compare_reports()` in-process exactly as they call
`analyse_trends()`.

--------------------------------------------------------------------------
1. THERE IS EXACTLY ONE POLARITY TABLE AND ONE STABILITY RULE
--------------------------------------------------------------------------

Grep this file for `POLARITY`, `STABILITY`, `direction_of_harm`,
`significant_change_pct` or `min_absolute_change`: none of them appears. The
entire improved / worsened / unchanged decision is made by calling Module 28's
`analyse_feature()` over a TWO-report series -- the baseline first, the
comparison second -- and renaming its three labels:

    improving -> improved      worsening -> worsened      stable -> unchanged

`significant` is likewise read straight off the `AppliedStability.exceeded`
that call returns. Nothing is recomputed and nothing is thresholded here.

Two tables that can disagree about whether rising creatinine is good is the
defect class this project's audits keep finding, so there is one table, one
lookup, and one arithmetic path.

--------------------------------------------------------------------------
2. NEWLY ABNORMAL IS A STATE TRANSITION, AND IT IS EARNED
--------------------------------------------------------------------------

Module 28 has no notion of abnormality: a trend is about numbers moving. A
transition is about a value crossing a boundary, so it needs an input the
trend does not -- the reference interval or flag printed on EACH report.

`newly_abnormal` is emitted if and only if BOTH of these are established:

    baseline:    known to be INSIDE its report's stated interval, or carrying
                 that report's printed `normal` flag
    comparison:  known to be OUTSIDE its report's stated interval, or carrying
                 a printed low / high / critical flag

If the baseline report stated no interval and printed no flag, the answer is
`NOT_DETERMINABLE_BASELINE`. It is NOT `newly_abnormal` and it is NOT
`unchanged`. Reading a missing reference range as "it must have been normal
then" would manufacture an alarming finding out of absent metadata, which is
this project's single most repeated hazard wearing a new costume.

`newly_normal` is the exact mirror, held to the exact same bar.

WHOSE interval? The one printed on the report. Not
`app/data/clinical_rules.py` (that answers "is this value clinically
concerning by this platform's rules", which is Module 8's question, and using
it here would let a parameter be "newly abnormal" in a report that never said
anything of the kind), and not `trend_polarity.optimal_low/high` (those are
targets for a direction-of-improvement calculation, not the issuing
laboratory's range).

--------------------------------------------------------------------------
3. ABSENCE IS NEVER A VALUE
--------------------------------------------------------------------------

A parameter in one report and not the other is `ONLY_IN_BASELINE` /
`ONLY_IN_COMPARISON` with the missing side's reason code, and its table cell
is `null`. A rejected value never reaches here at all: `to_snapshot` is
Module 7's `build_snapshot`, which discards the rejected map at the parse
boundary. Nothing is interpolated, carried forward or replaced with zero.

--------------------------------------------------------------------------
4. UNIT MISMATCH IS A REFUSAL
--------------------------------------------------------------------------

Inherited whole from Module 28: two readings of one feature in different
units, or any reading not in the canonical unit, refuses that parameter. No
value is coerced here.

The ONE place a conversion is applied in this file is to a REFERENCE INTERVAL,
and only ever using `provenance.conversion` -- the exact factor and offset that
`app/data/unit_conversions.py` already applied to the value itself, recorded on
the value at engineering time. As of 2026-09-04 Module 5 converts the interval
at the source and marks it `provenance.reference_converted`; when that flag is
set this file applies NOTHING and passes the bounds straight through. The
conversion branch survives only for carriers that predate the flag. See
`_reference_interval`.

--------------------------------------------------------------------------
5. NO MODEL, NO FREE TEXT
--------------------------------------------------------------------------

Every emittable string comes from `_TEMPLATES` / `_WARNING_TEMPLATES` below,
each scanned by the Module 24 safety scanner at import time, or from Module
28's own already-scanned reasons. There is no generator and no free-text entry
point.

--------------------------------------------------------------------------
LOGGING
--------------------------------------------------------------------------

Counts and codes only, through `safe_meta`. No value, no unit, no feature
name, no patient or report identifier is ever logged from this module.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

from app.core.errors import BadRequestError
from app.core.logging import get_logger, safe_meta
from app.data.feature_catalog import CANONICAL_FEATURES, FEATURES
from app.data.recommendation_catalog import assert_safe
from app.data.trend_polarity import (
    SIDE_ABOVE,
    SIDE_BELOW,
    TREND_POLICY_VERSION,
    harm_declared_beyond,
    polarity_for,
)
from app.schemas.comparison import (
    ABN_CENSORED_INCONCLUSIVE,
    ABN_ONE_SIDED_INTERVAL_INCONCLUSIVE,
    ABN_NO_REFERENCE_OR_FLAG,
    ABN_NO_USABLE_VALUE,
    ABN_RANGE_UNIT_NOT_COMPARABLE,
    ABN_UNKNOWN_FLAG,
    BASIS_NOT_DETERMINABLE,
    BASIS_PRINTED_FLAG,
    BASIS_REFERENCE_RANGE,
    BASIS_REFERENCE_RANGE_CONVERTED,
    CATEGORY_CHANGED_DIRECTION_ONLY,
    CATEGORY_IMPROVED,
    CATEGORY_NEWLY_ABNORMAL,
    CATEGORY_NEWLY_NORMAL,
    CATEGORY_NOT_CLASSIFIABLE,
    CATEGORY_UNCHANGED,
    CATEGORY_VALUES,
    CATEGORY_WORSENED,
    CHANGE_IMPROVED,
    CHANGE_UNCHANGED,
    CHANGE_WORSENED,
    COMPARISON_CHANGE_CLASSIFIED,
    COMPARISON_IN_NEITHER,
    COMPARISON_ONLY_IN_BASELINE,
    COMPARISON_ONLY_IN_COMPARISON,
    NOT_DETERMINABLE_BASELINE,
    NOT_DETERMINABLE_BOTH,
    NOT_DETERMINABLE_COMPARISON,
    SELECTION_EXPLICIT,
    SELECTION_FIRST_VS_LATEST,
    SYMBOL_DOWN,
    SYMBOL_LEVEL,
    SYMBOL_UP,
    TRANSITION_CLASSIFIED,
    TRANSITION_NEWLY_ABNORMAL,
    TRANSITION_NEWLY_NORMAL,
    TRANSITION_REMAINED_ABNORMAL,
    TRANSITION_REMAINED_NORMAL,
    AbnormalityState,
    ComparisonOptions,
    ComparisonPair,
    ComparisonRow,
    ComparisonSummary,
    FeatureSeries,
    ParameterComparison,
    ReportComparisonData,
    ReportComparisonRequest,
)
from app.schemas.timeline import (
    DIRECTION_FALLING,
    DIRECTION_RISING,
    DIRECTION_UNCHANGED,
    OUTCOME_CHANGE_WITHIN_REFERENCE_INTERVAL,
    OUTCOME_CLINICAL_DIRECTION_UNKNOWN,
    OUTCOME_INSUFFICIENT_DATA,
    OUTCOME_TREND_CLASSIFIED,
    TREND_IMPROVING,
    TREND_STABLE,
    TREND_WORSENING,
    TimelineOptions,
    TimelineReportRef,
)
from app.services.trend_analyzer import (
    OrderedReport,
    analyse_feature,
    collect_series,
    format_date,
    format_value,
    is_real_number,
    order_reports,
    recorded_ages,
)

logger = get_logger(__name__)

#: Bumped when this comparator's own behaviour changes, independently of the
#: clinical tables' `TREND_POLICY_VERSION`.
COMPARATOR_VERSION = "1.0.0"

#: Module 28's three trend labels -> Module 29's three change labels. A
#: mapping, not a re-derivation: the decision was already made.
_TREND_TO_CHANGE: Dict[str, str] = {
    TREND_IMPROVING: CHANGE_IMPROVED,
    TREND_WORSENING: CHANGE_WORSENED,
    TREND_STABLE: CHANGE_UNCHANGED,
}

#: Printed laboratory flags this service understands. Anything else is
#: `ABN_UNKNOWN_FLAG` -- never guessed at, and never read as normal.
_FLAG_ABNORMAL: Dict[str, bool] = {
    "normal": False,
    "low": True,
    "high": True,
    "critical": True,
}


# --------------------------------------------------------------------------
# Every user-facing string this module can emit
# --------------------------------------------------------------------------
#
# Scanned by the Module 24 recommendation safety scanner at import time (see
# `_self_check` at the bottom). Substituted values are feature names, numbers,
# dates, units and code constants; none of them can introduce a banned phrase.

DISCLAIMER = (
    "This comparison describes how measured laboratory values differ between "
    "two reports, and whether a value moved across the reference interval "
    "printed on those reports. It reports arithmetic and declared directions "
    "of change only. It does not interpret those changes, does not identify "
    "any condition, and is not a substitute for review by a qualified health "
    "professional."
)

_TEMPLATES: Dict[str, str] = {
    # ---- change-axis refusals Module 29 adds on top of Module 28's ----
    "only_in_baseline": (
        "{feature} had a usable reading in the baseline report but none in the "
        "comparison report ({reason}). A missing reading is not an unchanged "
        "reading, so no comparison is reported for it."
    ),
    "only_in_comparison": (
        "{feature} had a usable reading in the comparison report but none in "
        "the baseline report ({reason}). With nothing to compare against, no "
        "change is reported."
    ),
    "in_neither": (
        "{feature} had no usable reading in either of the two compared reports."
    ),
    # ---- how one report's abnormality was established ----
    "abn_range": (
        "Placed against the reference interval printed on this report "
        "({interval})."
    ),
    "abn_range_converted": (
        "Placed against the reference interval printed on this report "
        "({interval}), carried through the same unit conversion that was "
        "applied to the reading itself ({formula})."
    ),
    "abn_flag": (
        "This report printed no usable reference interval for {feature}, so "
        "the marker printed beside the result ({flag}) was used instead."
    ),
    "abn_no_value": (
        "This report carried no usable reading for {feature}, so whether it "
        "was inside or outside its reference interval is not known."
    ),
    "abn_no_reference": (
        "This report carried a reading for {feature} but printed neither a "
        "reference interval nor a marker beside it, so whether the reading was "
        "inside or outside range is not known. It is not assumed to be inside."
    ),
    "abn_range_unit": (
        "This report printed a reference interval for {feature}, but it could "
        "not be placed in the same unit as the stored reading, so it was not "
        "used and the position of the reading is not known."
    ),
    "abn_censored": (
        "The reading for {feature} on this report is reported only as being "
        "beyond a detection limit, and the printed interval does not settle "
        "which side of the interval the true reading falls on."
    ),
    "abn_one_sided": (
        "The reference interval printed beside {feature} on this report states "
        "only {interval}, and this reading lies past no bound it states. "
        "Whether that is within the expected range cannot be established from "
        "a one-sided interval alone, and no bound has been assumed for the "
        "side the report leaves open."
    ),
    "abn_unknown_flag": (
        "This report printed a marker beside {feature} that this service does "
        "not recognise, so it was not used."
    ),
    # ---- transition sentences ----
    "newly_abnormal": (
        " This reading was inside the reference interval its own report stated "
        "for it in the baseline report, and is outside the interval its own "
        "report states for it in the comparison report."
    ),
    "newly_normal": (
        " This reading was outside the reference interval its own report "
        "stated for it in the baseline report, and is inside the interval its "
        "own report states for it in the comparison report."
    ),
    "remained_abnormal": (
        " The reading sat outside the reference interval stated on both "
        "reports."
    ),
    "remained_normal": (
        " The reading sat inside the reference interval stated on both "
        "reports."
    ),
    "transition_unknown_baseline": (
        " Whether this reading was inside or outside its reference interval "
        "could not be established for the baseline report, so no newly "
        "abnormal or newly normal finding is reported."
    ),
    "transition_unknown_comparison": (
        " Whether this reading is inside or outside its reference interval "
        "could not be established for the comparison report, so no newly "
        "abnormal or newly normal finding is reported."
    ),
    "transition_unknown_both": (
        " Whether this reading was inside or outside its reference interval "
        "could not be established for either report, so no newly abnormal or "
        "newly normal finding is reported."
    ),
    # ---- summary ----
    "headline": (
        "Comparing the report of {baseline_date} with the report of "
        "{comparison_date}, {days} days apart: {examined} parameter(s) were "
        "examined."
    ),
    "headline_reversed": (
        "Comparing the report of {baseline_date} (named as the baseline) with "
        "the report of {comparison_date}: {examined} parameter(s) were "
        "examined."
    ),
    "no_pair": (
        "Fewer than two reports were supplied, so there is nothing to compare."
    ),
    "line_newly_abnormal": (
        "{count} parameter(s) moved from inside to outside the reference "
        "interval printed on the report: {features}."
    ),
    "line_newly_normal": (
        "{count} parameter(s) moved from outside to inside the reference "
        "interval printed on the report: {features}."
    ),
    "line_improved": (
        "{count} parameter(s) moved in the direction declared favourable for "
        "them: {features}."
    ),
    "line_worsened": (
        "{count} parameter(s) moved in the direction declared unfavourable for "
        "them: {features}."
    ),
    "line_unchanged": (
        "{count} parameter(s) did not move by more than their declared "
        "stability band: {features}."
    ),
    "line_direction_only": (
        "{count} parameter(s) moved measurably, but no clinical direction is "
        "declared for them, so no favourable or unfavourable label is "
        "reported: {features}."
    ),
    "line_not_classifiable": (
        "{count} parameter(s) could not be compared, each with a stated "
        "reason: {items}."
    ),
    "line_significant": (
        "{count} parameter(s) changed by more than their declared stability "
        "band: {features}."
    ),
    "line_none_examined": (
        "No parameter carried a usable reading in either of the two compared "
        "reports."
    ),
    # ---- table cell text ----
    "row_pair": "{previous} to {current}{unit}",
}

_WARNING_TEMPLATES: Dict[str, str] = {
    "no_reports": "No reports were supplied, so there is nothing to compare.",
    "single_report": (
        "Only one report was supplied. A comparison needs two, so no "
        "parameters were compared."
    ),
    "reversed_pair": (
        "The named baseline report carries a LATER date than the named "
        "comparison report. The pair is used exactly as named and is NOT "
        "silently swapped, because swapping it would invert every direction of "
        "change. Check baseline_ref and comparison_ref."
    ),
    "same_date_pair": (
        "The two compared reports carry the same date. Any change between them "
        "cannot be placed in time."
    ),
    "intermediate_reports": (
        "{count} report(s) lie between the two compared reports. They take no "
        "part in the classification and appear only in the returned series."
    ),
    "extreme_present": (
        "{count} reading(s) used in this comparison were flagged as clinically "
        "extreme during validation."
    ),
    "flag_range_disagreement": (
        "{count} report/parameter pair(s) printed a reference interval and a "
        "marker that imply different answers. The printed interval was used "
        "and the disagreement is recorded on the parameter."
    ),
}

_PARAMETER_WARNINGS: Dict[str, str] = {
    "crossed_without_significant_change": (
        "This parameter crossed its stated reference interval, but the size of "
        "the change did not clear its declared stability band. The crossing "
        "may reflect measurement variation rather than a real move."
    ),
    "transition_conflicts_with_change": (
        "The direction of change and the reference-interval crossing point "
        "different ways for this parameter. Both are reported; neither is "
        "suppressed."
    ),
    "flag_disagrees_with_range": (
        "A report printed both a reference interval and a marker for this "
        "parameter and they imply different answers. The printed interval was "
        "used."
    ),
    "abnormality_from_flag_only": (
        "The position of at least one reading was taken from the marker "
        "printed beside it, because no usable reference interval was printed."
    ),
    "reference_interval_converted": (
        "At least one reference interval was carried through the same unit "
        "conversion that was applied to the reading, so that the two are in "
        "the same unit."
    ),
}


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------


def _flag_text(flag: object) -> Optional[str]:
    """`provenance.flag` as a plain lowercase string, or None.

    The field is an `Optional[Flag]` enum, but a `FeatureSnapshot` posted
    straight in may carry it as a bare string, so both are handled. Anything
    that is neither is returned as None rather than coerced.
    """
    if flag is None:
        return None
    value = getattr(flag, "value", flag)
    if not isinstance(value, str):
        return None
    return value.strip().lower() or None


def _interval_text(low: Optional[float], high: Optional[float], unit: Optional[str]) -> str:
    suffix = f" {unit}" if unit else ""
    if low is not None and high is not None:
        return f"{format_value(low)} to {format_value(high)}{suffix}"
    if low is not None:
        return f"at or above {format_value(low)}{suffix}"
    if high is not None:
        return f"at or below {format_value(high)}{suffix}"
    return "not stated"


def _join(names: Sequence[str]) -> str:
    return ", ".join(names)


# --------------------------------------------------------------------------
# The reference interval, in the same unit as the value
# --------------------------------------------------------------------------


def _reference_interval(
    provenance: object,
) -> Tuple[Optional[float], Optional[float], Optional[str], Optional[str]]:
    """`(low, high, basis, formula)` for the interval printed on ONE report.

    Returns `(None, None, None, None)` when there is no usable interval.

    THE SOURCE NOW CONVERTS THE INTERVAL ITSELF (changed 2026-09-04).
    `feature_engineer._reference_bounds` carries the printed bounds through the
    same audited transform as the value and sets
    `provenance.reference_converted`. When that flag is true the bounds ALREADY
    match the value's unit and are returned untouched -- re-applying
    `conversion` here would square the factor and turn a correct interval into
    a wrong one, which is worse than the original defect.

    THIS FUNCTION IS DELIBERATELY KEPT. It still converts for any carrier that
    does NOT report `reference_converted`: provenance persisted by an older
    build of Module 5, and the duck-typed carriers Module 32 passes. That is
    belt and braces over a source that is now correct, not the fix itself.

    WHAT THE CONVERSION BRANCH DOES. `provenance.conversion` records the
    precise arithmetic applied to this very value -- the factor and offset from
    the audited `app/data/unit_conversions.py` -- so the interval is carried
    through the SAME transform. `to = from * factor + offset` is monotonically
    increasing for a positive factor, so the interval's ends stay its ends; a
    non-positive or non-finite factor would not preserve the ordering and is
    refused rather than reasoned about.

    When no conversion was applied, the interval and the value are already in
    the same printed unit and the numbers are used as they stand. That holds
    whether or not the unit was canonical, and whether or not it was assumed:
    the interval and the value came off the same report line either way. Only
    a CONVERTED value can put them into different units.
    """
    low = getattr(provenance, "reference_low", None)
    high = getattr(provenance, "reference_high", None)
    if not is_real_number(low):
        low = None
    if not is_real_number(high):
        high = None
    if low is None and high is None:
        return None, None, None, None

    if getattr(provenance, "reference_converted", False):
        # Already in the value's unit. Converting again would double-convert.
        conversion = getattr(provenance, "conversion", None)
        return (
            float(low) if low is not None else None,
            float(high) if high is not None else None,
            BASIS_REFERENCE_RANGE_CONVERTED,
            str(getattr(conversion, "formula", "") or "") or None,
        )

    if not getattr(provenance, "unit_converted", False):
        return (
            float(low) if low is not None else None,
            float(high) if high is not None else None,
            BASIS_REFERENCE_RANGE,
            None,
        )

    conversion = getattr(provenance, "conversion", None)
    if conversion is None:
        return None, None, None, None
    factor = getattr(conversion, "factor", None)
    offset = getattr(conversion, "offset", 0.0)
    if not is_real_number(factor) or float(factor) <= 0.0:
        return None, None, None, None
    if not is_real_number(offset):
        return None, None, None, None

    def apply(bound: Optional[float]) -> Optional[float]:
        if bound is None:
            return None
        converted = float(bound) * float(factor) + float(offset)
        return converted if math.isfinite(converted) else None

    new_low, new_high = apply(low), apply(high)
    if (low is not None and new_low is None) or (
        high is not None and new_high is None
    ):
        return None, None, None, None
    return (
        new_low,
        new_high,
        BASIS_REFERENCE_RANGE_CONVERTED,
        str(getattr(conversion, "formula", "") or ""),
    )


def _inside_one_sided(
    low: Optional[float], high: Optional[float], feature: Optional[str]
) -> bool:
    """May a reading past NO stated bound be called INSIDE this interval?

    Only reached once the reading is known not to lie beyond any bound that
    was actually stated. The remaining question is about the MISSING bounds:
    an interval with no lower bound says nothing whatsoever about how low a
    reading may safely go, so "not above the upper bound" is only the same
    thing as "inside" when nothing below is unfavourable.

    That judgement is `app/data/trend_polarity.py`'s and is read from it here
    through `harm_declared_beyond`, which is tri-state. Module 29 still holds
    NO polarity table of its own: it asks Module 28's declaration a yes/no
    question and does not look at a direction of harm, a threshold or a band.

        no harm declared on the missing side  -> the reading is inside
        harm declared, or the feature declares no direction at all
                                              -> NOT determinable

    `feature=None` (a caller that does not know which feature this is) is the
    unknown case on both sides, so a one-sided interval settles nothing. That
    is the safe direction: it refuses, it never invents a normal reading.

    WHY THIS MATTERS -- the defect it exists to stop. `reference_low` and
    `reference_high` are independently nullable all the way from Module 4's
    contract through `feature_engineer._reference_bounds`, so a printed
    `13.0 - 17.0` can reach here as `high=17.0` alone. Treating "no lower
    bound" as "no lower bound EXISTS" then reports a haemoglobin of 7.5 g/dL
    -- severe anaemia -- as sitting inside the interval printed on the report,
    and suppresses a real `newly_abnormal` crossing. A missing bound is an
    absence, and an absence must not become a definite negative.
    """
    if low is None and harm_declared_beyond(feature or "", SIDE_BELOW) is not False:
        return False
    if high is None and harm_declared_beyond(feature or "", SIDE_ABOVE) is not False:
        return False
    return True


def _outside_interval(
    value: float,
    low: Optional[float],
    high: Optional[float],
    censored: Optional[str],
    feature: Optional[str] = None,
) -> Optional[bool]:
    """Is `value` outside `[low, high]`? `None` when that cannot be settled.

    A value ON a bound counts as inside: laboratories print inclusive ranges.

    ONE-SIDED INTERVALS. `low` and `high` are independently optional, and a
    reading that is not past the bound(s) actually stated is NOT automatically
    inside the interval -- see `_inside_one_sided`, which decides that from
    Module 28's polarity declaration and refuses where the declaration does
    not cover the missing side. `feature` is what lets it ask; a caller that
    omits it gets the refusal on every one-sided interval, never a normal
    reading it did not earn.

    CENSORED READINGS. Module 5 keeps a `<0.1` result at its detection limit
    and records `censored: "left"` (the true value is at or below the limit) or
    `"right"` (at or above it). The stored number is therefore a BOUND on the
    true value, not the true value, and only the conclusions that hold across
    the whole censored interval may be drawn:

      left-censored   true <= limit. Certainly outside only when the limit is
                      already below the lower bound. Certainly inside only when
                      there is no lower bound and the limit does not exceed the
                      upper bound. Anything else is unsettled.
      right-censored  the mirror image.

    Returning None here is what stops a `<0.1` printed against a 0.05-1.0
    interval from being reported as newly abnormal.
    """
    if censored == "left":
        if low is not None and value < low:
            return True
        if low is not None:
            return None
        if high is not None and value > high:
            # true <= limit, and the limit is above the upper bound: the true
            # value may be on either side.
            return None
        return False if _inside_one_sided(low, high, feature) else None
    if censored == "right":
        if high is not None and value > high:
            return True
        if high is not None:
            return None
        if low is not None and value < low:
            return None
        return False if _inside_one_sided(low, high, feature) else None

    if low is not None and value < low:
        return True
    if high is not None and value > high:
        return True
    return False if _inside_one_sided(low, high, feature) else None


# --------------------------------------------------------------------------
# One report's abnormality state for one feature
# --------------------------------------------------------------------------


def _abnormality(
    report: OrderedReport, feature: str, options: ComparisonOptions
) -> AbnormalityState:
    """Was `feature` abnormal in THIS report? True / False / not determinable.

    Every path that cannot answer returns `abnormal=None` with a reason code.
    There is no branch that answers `False` because nothing else matched.
    """
    snapshot = report.snapshot
    stored = snapshot.features.get(feature)

    def unknown(reason_code: str, reason: str, **extra: object) -> AbnormalityState:
        return AbnormalityState(
            report_id=report.report_id,
            date=report.date,
            abnormal=None,
            basis=BASIS_NOT_DETERMINABLE,
            reason_code=reason_code,
            reason=reason,
            **extra,  # type: ignore[arg-type]
        )

    if stored is None:
        return unknown(
            ABN_NO_USABLE_VALUE,
            _TEMPLATES["abn_no_value"].format(feature=feature),
        )
    if options.exclude_questionable and stored.questionable:
        # The caller asked for questionable readings to be treated as absent.
        # Honouring that on the change axis but not here would let an excluded
        # reading still drive a newly-abnormal finding.
        return unknown(
            ABN_NO_USABLE_VALUE,
            _TEMPLATES["abn_no_value"].format(feature=feature),
        )
    if not is_real_number(stored.value):
        return unknown(
            ABN_NO_USABLE_VALUE,
            _TEMPLATES["abn_no_value"].format(feature=feature),
        )

    value = float(stored.value)
    provenance = stored.provenance
    censored = getattr(provenance, "censored", None) if provenance else None
    raw_range = getattr(provenance, "reference_range_raw", None) if provenance else None
    flag = _flag_text(getattr(provenance, "flag", None)) if provenance else None

    low, high, basis, formula = (
        _reference_interval(provenance) if provenance else (None, None, None, None)
    )

    common = {
        "value": value,
        "unit": stored.unit,
        "reference_range_raw": raw_range,
        "printed_flag": flag,
    }

    # Tracks an interval that WAS printed but could not settle this reading, so
    # the fall-through below can say which of the two reasons applies instead of
    # blaming whichever one happens to be first.
    inconclusive_interval: Optional[str] = None

    if basis is not None:
        outside = _outside_interval(value, low, high, censored, feature)
        if outside is None:
            # THE INTERVAL COULD NOT SETTLE IT -- BUT THAT IS NOT THE END OF THE
            # QUESTION. This used to return immediately, which discarded the
            # laboratory's own printed flag; on the unbounded side of a
            # one-sided interval that flag is the ONLY real signal, and letting
            # a bound that says nothing about the value outrank it is one
            # concrete signal losing to an absence. So fall through to the flag
            # branch below, which is also unit-independent.
            #
            # `MEMORY.md` 6m records "the range wins" as this module's most
            # debatable call, reasoned as "two concrete signals rather than an
            # absence". That reasoning holds only where the interval actually
            # brackets the value, and this is precisely the branch where it
            # does not.
            inconclusive_interval = (
                ABN_CENSORED_INCONCLUSIVE
                if censored
                else ABN_ONE_SIDED_INTERVAL_INCONCLUSIVE
            )
        else:
            disagrees = False
            if flag is not None and flag in _FLAG_ABNORMAL:
                disagrees = _FLAG_ABNORMAL[flag] != outside
            reason = (
                _TEMPLATES["abn_range"].format(
                    interval=_interval_text(low, high, stored.unit)
                )
                if basis == BASIS_REFERENCE_RANGE
                else _TEMPLATES["abn_range_converted"].format(
                    interval=_interval_text(low, high, stored.unit),
                    formula=formula or "recorded conversion",
                )
            )
            return AbnormalityState(
                report_id=report.report_id,
                date=report.date,
                abnormal=outside,
                basis=basis,
                reason=reason,
                reference_low=low,
                reference_high=high,
                flag_disagrees_with_range=disagrees,
                **common,  # type: ignore[arg-type]
            )

    # No usable interval. Fall back to the marker the laboratory printed --
    # which is unit-independent, so it survives a conversion the interval did
    # not.
    if flag is not None:
        if flag not in _FLAG_ABNORMAL:
            return unknown(
                ABN_UNKNOWN_FLAG,
                _TEMPLATES["abn_unknown_flag"].format(feature=feature),
                **common,
            )
        return AbnormalityState(
            report_id=report.report_id,
            date=report.date,
            abnormal=_FLAG_ABNORMAL[flag],
            basis=BASIS_PRINTED_FLAG,
            reason=_TEMPLATES["abn_flag"].format(feature=feature, flag=flag),
            **common,  # type: ignore[arg-type]
        )

    # An interval WAS printed and WAS placed in the value's unit, but could not
    # settle this particular reading, and no printed flag rescued it. Reported
    # under its own code rather than as "no reference range", which would be
    # false -- there was one, it just does not answer this question. Censoring
    # and a one-sided interval are distinguished because they are different
    # facts about the data and a reader may act differently on each.
    if inconclusive_interval is not None:
        return unknown(
            inconclusive_interval,
            _TEMPLATES["abn_censored"].format(feature=feature)
            if inconclusive_interval == ABN_CENSORED_INCONCLUSIVE
            else _TEMPLATES["abn_one_sided"].format(
                feature=feature,
                interval=_interval_text(low, high, stored.unit),
            ),
            reference_low=low,
            reference_high=high,
            **common,
        )

    # A reference interval was printed but could not be placed in the value's
    # unit -- distinct from none having been printed at all, so it gets its own
    # code.
    printed_bounds = provenance is not None and (
        getattr(provenance, "reference_low", None) is not None
        or getattr(provenance, "reference_high", None) is not None
    )
    if printed_bounds:
        return unknown(
            ABN_RANGE_UNIT_NOT_COMPARABLE,
            _TEMPLATES["abn_range_unit"].format(feature=feature),
            **common,
        )
    return unknown(
        ABN_NO_REFERENCE_OR_FLAG,
        _TEMPLATES["abn_no_reference"].format(feature=feature),
        **common,
    )


def _transition(
    baseline: AbnormalityState, comparison: AbnormalityState
) -> Tuple[str, Optional[str]]:
    """`(transition_outcome, transition)`. Strict on both sides.

    A `None` on EITHER side is not determinable. There is deliberately no
    branch that treats one known side as enough.
    """
    before, after = baseline.abnormal, comparison.abnormal
    if before is None and after is None:
        return NOT_DETERMINABLE_BOTH, None
    if before is None:
        return NOT_DETERMINABLE_BASELINE, None
    if after is None:
        return NOT_DETERMINABLE_COMPARISON, None
    if not before and after:
        return TRANSITION_CLASSIFIED, TRANSITION_NEWLY_ABNORMAL
    if before and not after:
        return TRANSITION_CLASSIFIED, TRANSITION_NEWLY_NORMAL
    if before and after:
        return TRANSITION_CLASSIFIED, TRANSITION_REMAINED_ABNORMAL
    return TRANSITION_CLASSIFIED, TRANSITION_REMAINED_NORMAL


# --------------------------------------------------------------------------
# Pair selection
# --------------------------------------------------------------------------


def _select_pair(
    ordered: Sequence[OrderedReport],
    baseline_ref: Optional[str],
    comparison_ref: Optional[str],
) -> Tuple[int, int, str]:
    """`(baseline_index, comparison_index, selection)` into `ordered`.

    With no explicit refs this is first-versus-latest over the total order
    Module 28 already defines (`chrono_date`, then an explicit `sequence`, then
    `report_id`) -- so ties break on the DATA and two calls with the reports in
    a different array order select the same pair.

    With explicit refs the caller's naming is honoured exactly, including when
    the named baseline is the later report. Swapping it would invert every
    direction of change without telling anyone.
    """
    if baseline_ref is None and comparison_ref is None:
        return 0, len(ordered) - 1, SELECTION_FIRST_VS_LATEST

    index_of = {report.report_id: i for i, report in enumerate(ordered)}
    missing = [
        ref for ref in (baseline_ref, comparison_ref) if ref not in index_of
    ]
    if missing:
        raise BadRequestError(
            f"report id(s) {sorted(missing)!r} were named as the comparison "
            "pair but are not among the reports supplied in this request.",
            code="COMPARISON_REPORT_NOT_FOUND",
        )
    return (
        index_of[baseline_ref],  # type: ignore[index]
        index_of[comparison_ref],  # type: ignore[index]
        SELECTION_EXPLICIT,
    )


def _features_to_compare(
    baseline: OrderedReport,
    comparison: OrderedReport,
    options: ComparisonOptions,
) -> List[str]:
    """Which features to compare, always in catalogue order.

    The default is "present in at least one of the TWO CHOSEN reports", not
    "present anywhere in the request": a feature that appears only in an
    intermediate report is not part of this comparison and would come back as
    `IN_NEITHER` noise. `include_all_canonical` still returns everything.
    """
    if options.features:
        return list(options.features)
    if options.include_all_canonical:
        return list(CANONICAL_FEATURES)
    present = set(baseline.snapshot.features) | set(comparison.snapshot.features)
    return [name for name in CANONICAL_FEATURES if name in present]


# --------------------------------------------------------------------------
# One parameter, end to end
# --------------------------------------------------------------------------


def _category(
    outcome: str,
    change_class: Optional[str],
    transition: Optional[str],
) -> str:
    """The single specification-facing label, by a FIXED precedence.

    1. `newly_abnormal` / `newly_normal` -- a reference-interval crossing
       outranks the change axis. It is the more consequential fact, and the
       change axis remains visible in its own field, so nothing is lost.
    2. the change axis -- improved / worsened / unchanged.
    3. `changed_direction_only` -- it moved measurably but the polarity table
       declines to call that better or worse.
    4. `not_classifiable` -- everything else, with `outcome` saying which.
    """
    if transition == TRANSITION_NEWLY_ABNORMAL:
        return CATEGORY_NEWLY_ABNORMAL
    if transition == TRANSITION_NEWLY_NORMAL:
        return CATEGORY_NEWLY_NORMAL
    if change_class == CHANGE_IMPROVED:
        return CATEGORY_IMPROVED
    if change_class == CHANGE_WORSENED:
        return CATEGORY_WORSENED
    if change_class == CHANGE_UNCHANGED:
        return CATEGORY_UNCHANGED
    if outcome in (
        OUTCOME_CLINICAL_DIRECTION_UNKNOWN,
        OUTCOME_CHANGE_WITHIN_REFERENCE_INTERVAL,
    ):
        return CATEGORY_CHANGED_DIRECTION_ONLY
    return CATEGORY_NOT_CLASSIFIABLE


def _compare_feature(
    feature: str,
    baseline: OrderedReport,
    comparison: OrderedReport,
    options: ComparisonOptions,
    timeline_options: TimelineOptions,
    ages: Sequence[float],
) -> ParameterComparison:
    """The whole Module 29 computation for ONE canonical feature."""
    definition = FEATURES[feature]

    # The ENTIRE change axis, delegated. Baseline first, comparison second, so
    # Module 28's "first usable reading to last" is exactly this pair in the
    # order the caller named -- never re-sorted here.
    trend = analyse_feature(
        feature, [baseline, comparison], timeline_options, recorded_ages=ages
    )

    warnings: List[str] = list(trend.warnings)
    outcome = trend.outcome
    change_class: Optional[str] = None
    reason = trend.reason

    if outcome == OUTCOME_TREND_CLASSIFIED:
        outcome = COMPARISON_CHANGE_CLASSIFIED
        # `trend` is non-null for exactly this outcome; the mapping is total
        # over TREND_VALUES, so a KeyError here would mean Module 28 grew a
        # fourth label -- which should fail loudly, not default.
        change_class = _TREND_TO_CHANGE[trend.trend]  # type: ignore[index]
    elif outcome == OUTCOME_INSUFFICIENT_DATA:
        # Refine "fewer than two usable points" into WHICH side is missing.
        # `analyse_feature` returns this outcome only when len(points) < 2, so
        # these three cases are exhaustive over a two-report series.
        with_points = {point.report_id for point in trend.points}
        gap_reason = {gap.report_id: gap.reason for gap in trend.gaps}
        if baseline.report_id in with_points:
            outcome = COMPARISON_ONLY_IN_BASELINE
            reason = _TEMPLATES["only_in_baseline"].format(
                feature=feature,
                reason=gap_reason.get(comparison.report_id, "no usable reading"),
            )
        elif comparison.report_id in with_points:
            outcome = COMPARISON_ONLY_IN_COMPARISON
            reason = _TEMPLATES["only_in_comparison"].format(
                feature=feature,
                reason=gap_reason.get(baseline.report_id, "no usable reading"),
            )
        else:
            outcome = COMPARISON_IN_NEITHER
            reason = _TEMPLATES["in_neither"].format(feature=feature)

    significant = trend.stability.exceeded if trend.stability else None

    # ---- the abnormality axis -------------------------------------------
    baseline_state = _abnormality(baseline, feature, options)
    comparison_state = _abnormality(comparison, feature, options)
    transition_outcome, transition = _transition(baseline_state, comparison_state)

    if transition is not None:
        reason += _TEMPLATES[transition]
    elif transition_outcome == NOT_DETERMINABLE_BASELINE:
        reason += _TEMPLATES["transition_unknown_baseline"]
    elif transition_outcome == NOT_DETERMINABLE_COMPARISON:
        reason += _TEMPLATES["transition_unknown_comparison"]
    else:
        reason += _TEMPLATES["transition_unknown_both"]

    category = _category(outcome, change_class, transition)

    # ---- parameter-level warnings ----------------------------------------
    if transition in (TRANSITION_NEWLY_ABNORMAL, TRANSITION_NEWLY_NORMAL):
        if significant is False:
            warnings.append(
                _PARAMETER_WARNINGS["crossed_without_significant_change"]
            )
        if (transition == TRANSITION_NEWLY_ABNORMAL and change_class == CHANGE_IMPROVED) or (
            transition == TRANSITION_NEWLY_NORMAL and change_class == CHANGE_WORSENED
        ):
            warnings.append(_PARAMETER_WARNINGS["transition_conflicts_with_change"])
    if baseline_state.flag_disagrees_with_range or comparison_state.flag_disagrees_with_range:
        warnings.append(_PARAMETER_WARNINGS["flag_disagrees_with_range"])
    if BASIS_PRINTED_FLAG in (baseline_state.basis, comparison_state.basis):
        warnings.append(_PARAMETER_WARNINGS["abnormality_from_flag_only"])
    if BASIS_REFERENCE_RANGE_CONVERTED in (
        baseline_state.basis,
        comparison_state.basis,
    ):
        warnings.append(_PARAMETER_WARNINGS["reference_interval_converted"])

    return ParameterComparison(
        feature=feature,
        description=definition.description,
        value_type=definition.value_type,
        canonical_unit=definition.canonical_unit,
        outcome=outcome,
        change_class=change_class,
        direction=trend.direction,
        change=trend.change,
        significant=significant,
        polarity=trend.polarity,
        stability=trend.stability,
        baseline=baseline_state,
        comparison=comparison_state,
        transition_outcome=transition_outcome,
        transition=transition,
        category=category,
        reason=reason,
        warnings=warnings,
    )


def _row(parameter: ParameterComparison) -> ComparisonRow:
    """One table row. A cell with no reading is `null`, never `0`.

    `previous` and `current` come from the abnormality states, which hold the
    reading each report actually carried. That is deliberately NOT the same as
    reading them off `change`: `change` exists only when BOTH sides had a
    usable reading, whereas the specification's table should still show the one
    value that does exist when the other report is silent about it.
    """
    previous = parameter.baseline.value
    current = parameter.comparison.value
    unit = parameter.baseline.unit or parameter.comparison.unit

    symbol: Optional[str] = None
    if parameter.direction == DIRECTION_RISING:
        symbol = SYMBOL_UP
    elif parameter.direction == DIRECTION_FALLING:
        symbol = SYMBOL_DOWN
    elif parameter.direction == DIRECTION_UNCHANGED:
        symbol = SYMBOL_LEVEL

    return ComparisonRow(
        feature=parameter.feature,
        description=parameter.description,
        unit=unit,
        previous=previous,
        current=current,
        absolute_change=parameter.change.absolute_change if parameter.change else None,
        percent_change=parameter.change.percent_change if parameter.change else None,
        direction=parameter.direction,
        symbol=symbol,
        category=parameter.category,
        significant=parameter.significant,
    )


# --------------------------------------------------------------------------
# The summary
# --------------------------------------------------------------------------


def _summary(
    parameters: Dict[str, ParameterComparison],
    pair: Optional[ComparisonPair],
    reports_supplied: int,
) -> ComparisonSummary:
    """Counts plus the templated comparison summary. No generator, no model."""
    by_category: Dict[str, List[str]] = {name: [] for name in CATEGORY_VALUES}
    categories: Dict[str, int] = {}
    outcomes: Dict[str, int] = {}
    transition_outcomes: Dict[str, int] = {}
    significant: List[str] = []
    not_classifiable_items: List[str] = []

    for name, parameter in parameters.items():
        by_category[parameter.category].append(name)
        categories[parameter.category] = categories.get(parameter.category, 0) + 1
        outcomes[parameter.outcome] = outcomes.get(parameter.outcome, 0) + 1
        transition_outcomes[parameter.transition_outcome] = (
            transition_outcomes.get(parameter.transition_outcome, 0) + 1
        )
        if parameter.significant:
            significant.append(name)
        if parameter.category == CATEGORY_NOT_CLASSIFIABLE:
            not_classifiable_items.append(f"{name} ({parameter.outcome})")

    lines: List[str] = []
    if pair is None:
        headline = _TEMPLATES["no_pair"]
    else:
        days = (
            pair.comparison_date - pair.baseline_date
        ).total_seconds() / 86400.0
        key = "headline" if pair.chronological else "headline_reversed"
        headline = _TEMPLATES[key].format(
            baseline_date=format_date(pair.baseline_date),
            comparison_date=format_date(pair.comparison_date),
            days=format_value(round(days, 1)),
            examined=len(parameters),
        )
        if not parameters:
            lines.append(_TEMPLATES["line_none_examined"])

    for category, template in (
        (CATEGORY_NEWLY_ABNORMAL, "line_newly_abnormal"),
        (CATEGORY_NEWLY_NORMAL, "line_newly_normal"),
        (CATEGORY_WORSENED, "line_worsened"),
        (CATEGORY_IMPROVED, "line_improved"),
        (CATEGORY_UNCHANGED, "line_unchanged"),
        (CATEGORY_CHANGED_DIRECTION_ONLY, "line_direction_only"),
    ):
        names = by_category[category]
        if names:
            lines.append(
                _TEMPLATES[template].format(
                    count=len(names), features=_join(names)
                )
            )
    if significant:
        lines.append(
            _TEMPLATES["line_significant"].format(
                count=len(significant), features=_join(significant)
            )
        )
    if not_classifiable_items:
        lines.append(
            _TEMPLATES["line_not_classifiable"].format(
                count=len(not_classifiable_items),
                items=_join(not_classifiable_items),
            )
        )

    return ComparisonSummary(
        reports_supplied=reports_supplied,
        features_examined=len(parameters),
        newly_abnormal=len(by_category[CATEGORY_NEWLY_ABNORMAL]),
        newly_normal=len(by_category[CATEGORY_NEWLY_NORMAL]),
        improved=len(by_category[CATEGORY_IMPROVED]),
        worsened=len(by_category[CATEGORY_WORSENED]),
        unchanged=len(by_category[CATEGORY_UNCHANGED]),
        changed_direction_only=len(by_category[CATEGORY_CHANGED_DIRECTION_ONLY]),
        not_classifiable=len(by_category[CATEGORY_NOT_CLASSIFIABLE]),
        significant_changes=len(significant),
        categories=dict(sorted(categories.items())),
        outcomes=dict(sorted(outcomes.items())),
        transition_outcomes=dict(sorted(transition_outcomes.items())),
        headline=headline,
        lines=lines,
    )


# --------------------------------------------------------------------------
# The whole request
# --------------------------------------------------------------------------


def compare_reports(request: ReportComparisonRequest) -> ReportComparisonData:
    """The Module 29 entry point. Deterministic, offline, and model-free.

    Same input -> byte-identical output, apart from `generated_at`. Nothing
    here is random, nothing is cached, and nothing calls out of the process.
    """
    ordered, warnings = order_reports(request.reports)
    options = request.options

    # The options Module 28 is driven with. Only the two that mean the same
    # thing in both modules are forwarded; `features` is NOT, because Module 29
    # picks the feature list itself (from the chosen pair) and then asks Module
    # 28 about one feature at a time.
    timeline_options = TimelineOptions(
        exclude_questionable=options.exclude_questionable
    )

    report_refs = [
        TimelineReportRef(
            report_id=report.report_id,
            date=report.date,
            order=index,
            feature_count=len(report.snapshot.features),
        )
        for index, report in enumerate(ordered)
    ]

    if len(ordered) < 2:
        warnings.append(
            _WARNING_TEMPLATES["no_reports" if not ordered else "single_report"]
        )
        summary = _summary({}, None, len(ordered))
        logger.info(
            "report_comparison %s",
            safe_meta(
                reports=len(ordered),
                compared=0,
                policy_version=TREND_POLICY_VERSION,
            ),
        )
        return ReportComparisonData(
            patient_ref=request.patient_ref,
            policy_version=TREND_POLICY_VERSION,
            comparator_version=COMPARATOR_VERSION,
            reports=report_refs,
            pair=None,
            parameters={},
            table=[],
            series={},
            summary=summary,
            warnings=warnings,
            disclaimer=DISCLAIMER,
        )

    baseline_index, comparison_index, selection = _select_pair(
        ordered, request.baseline_ref, request.comparison_ref
    )
    baseline = ordered[baseline_index]
    comparison = ordered[comparison_index]

    chronological = baseline.date <= comparison.date
    if not chronological:
        warnings.append(_WARNING_TEMPLATES["reversed_pair"])
    if baseline.date == comparison.date:
        warnings.append(_WARNING_TEMPLATES["same_date_pair"])

    low_index, high_index = sorted((baseline_index, comparison_index))
    intermediate = max(0, high_index - low_index - 1)
    if len(ordered) > 2:
        warnings.append(
            _WARNING_TEMPLATES["intermediate_reports"].format(count=intermediate)
        )

    pair = ComparisonPair(
        baseline_report_id=baseline.report_id,
        baseline_date=baseline.date,
        comparison_report_id=comparison.report_id,
        comparison_date=comparison.date,
        days_between=round(
            (comparison.date - baseline.date).total_seconds() / 86400.0, 4
        ),
        selection=selection,
        chronological=chronological,
        reports_supplied=len(ordered),
        intermediate_report_count=intermediate,
    )

    # Ages come from the CHOSEN PAIR, not the whole request: the age-context
    # refusal in the polarity table is about the readings being classified, and
    # these two reports are the only ones being classified.
    ages = recorded_ages([baseline, comparison])

    names = _features_to_compare(baseline, comparison, options)
    parameters: Dict[str, ParameterComparison] = {
        name: _compare_feature(
            name, baseline, comparison, options, timeline_options, ages
        )
        for name in names
    }

    table = [_row(parameters[name]) for name in names]

    series: Dict[str, FeatureSeries] = {}
    if options.include_series and len(ordered) > 2:
        for name in names:
            polarity = polarity_for(name)
            points, gaps = collect_series(
                name,
                ordered,
                timeline_options,
                timing_sensitive=bool(polarity and polarity.timing_sensitive),
            )
            series[name] = FeatureSeries(feature=name, points=points, gaps=gaps)

    # Counted off the two snapshots actually compared, not off `change` --
    # `TrendChange` carries values, not the validation flags that go with them.
    extreme = 0
    for report in (baseline, comparison):
        for name in names:
            stored = report.snapshot.features.get(name)
            if stored is not None and stored.clinically_extreme:
                extreme += 1
    if extreme:
        warnings.append(_WARNING_TEMPLATES["extreme_present"].format(count=extreme))

    disagreements = sum(
        1
        for parameter in parameters.values()
        for state in (parameter.baseline, parameter.comparison)
        if state.flag_disagrees_with_range
    )
    if disagreements:
        warnings.append(
            _WARNING_TEMPLATES["flag_range_disagreement"].format(count=disagreements)
        )

    summary = _summary(parameters, pair, len(ordered))

    # Counts and codes only. No identifier, no value, no feature name.
    logger.info(
        "report_comparison %s",
        safe_meta(
            reports=len(ordered),
            compared=len(parameters),
            newly_abnormal=summary.newly_abnormal,
            newly_normal=summary.newly_normal,
            improved=summary.improved,
            worsened=summary.worsened,
            unchanged=summary.unchanged,
            not_classifiable=summary.not_classifiable,
            significant=summary.significant_changes,
            selection=selection,
            policy_version=TREND_POLICY_VERSION,
        ),
    )

    return ReportComparisonData(
        patient_ref=request.patient_ref,
        policy_version=TREND_POLICY_VERSION,
        comparator_version=COMPARATOR_VERSION,
        reports=report_refs,
        pair=pair,
        parameters=parameters,
        table=table,
        series=series,
        summary=summary,
        warnings=warnings,
        disclaimer=DISCLAIMER,
    )


def comparator_document() -> Dict[str, object]:
    """Module 29's own policy, machine-readable. No patient data."""
    return {
        "comparator_version": COMPARATOR_VERSION,
        "policy_version": TREND_POLICY_VERSION,
        "method": (
            "The improved / worsened / unchanged decision is delegated in full "
            "to Module 28's analyse_feature() over a two-report series, so the "
            "polarity table and the stability bands in "
            "app/data/trend_polarity.py are the only ones in the service. "
            "Module 29 adds the pair selection, the reference-interval state "
            "transition, and the templated summary."
        ),
        "pair_selection": (
            "baseline_ref plus comparison_ref when both are supplied, honoured "
            "in the order named even if that is reverse chronological (a "
            "warning is raised, never a silent swap); otherwise the earliest "
            "and latest reports by chrono_date, with ties broken on an "
            "explicit sequence then report_id, so the pair depends only on the "
            "data."
        ),
        "newly_abnormal_rule": (
            "Emitted only when the reading is known to be INSIDE the reference "
            "interval printed on the baseline report (or carries that report's "
            "printed normal marker) AND known to be OUTSIDE the interval "
            "printed on the comparison report (or carries a low/high/critical "
            "marker there). If either side cannot be established, the result "
            "is NOT_DETERMINABLE -- never newly abnormal and never unchanged. "
            "The interval used is the one printed on the report itself; "
            "app/data/clinical_rules.py thresholds are deliberately not "
            "consulted."
        ),
        "newly_normal_rule": (
            "The exact mirror of newly_abnormal, held to the same bar."
        ),
        "unchanged_rule": (
            "Returned only when both reports carried a usable reading and the "
            "net change failed to clear the declared stability band. It is "
            "never a default: a parameter missing from one report is "
            "ONLY_IN_BASELINE or ONLY_IN_COMPARISON."
        ),
        "absence_policy": (
            "A parameter missing from one report is not comparable, with a "
            "reason code, and its table cell is null. Nothing is interpolated "
            "or replaced with zero. A rejected value is discarded at Module "
            "7's parse boundary and cannot reach here."
        ),
        "unit_policy": (
            "Different units across the two reports, or any non-canonical "
            "unit, refuses that parameter -- inherited from Module 28. The "
            "only conversion applied in Module 29 is to a printed reference "
            "interval, using the exact factor and offset already applied to "
            "that value and recorded in its provenance."
        ),
        "categories": list(CATEGORY_VALUES),
        "disclaimer": DISCLAIMER,
    }


# --------------------------------------------------------------------------
# Import-time enforcement
# --------------------------------------------------------------------------


def _self_check() -> None:
    """Every emittable string is scanned by the Module 24 safety scanner.

    The templates carry `{placeholders}`; the scanner works on the literal
    text, and the substituted values are numbers, dates, feature names, units
    and code constants, none of which can introduce a banned phrase. The one
    substitution that is not a bare token is `{reason}` in the two
    `only_in_*` templates, which carries Module 7's `unavailable` reason -- the
    same reviewed text Module 28 already returns in its gaps.
    """
    for key, template in _TEMPLATES.items():
        assert_safe(template, f"comparison template {key}")
    for key, template in _WARNING_TEMPLATES.items():
        assert_safe(template, f"comparison warning template {key}")
    for key, template in _PARAMETER_WARNINGS.items():
        assert_safe(template, f"comparison parameter warning {key}")
    assert_safe(DISCLAIMER, "comparison disclaimer")

    # The trend -> change mapping must stay TOTAL over Module 28's labels. If
    # Module 28 gains a fourth trend label, this fails at import rather than
    # producing a KeyError in the middle of a patient's comparison.
    from app.schemas.timeline import TREND_VALUES

    missing = [label for label in TREND_VALUES if label not in _TREND_TO_CHANGE]
    if missing:
        raise ValueError(
            f"trend labels with no comparison equivalent: {missing}. Module 29 "
            "maps Module 28's labels; it never invents one."
        )

    # `unchanged` must be reachable only through the stability band, which is
    # what makes it earned. Guarding the mapping direction here means a future
    # edit that points `unchanged` at something other than Module 28's
    # band-derived `stable` fails loudly.
    if _TREND_TO_CHANGE[TREND_STABLE] != CHANGE_UNCHANGED:
        raise ValueError("'unchanged' must map from Module 28's earned 'stable'")


_self_check()


# --------------------------------------------------------------------------
# PUBLIC SURFACE ADDED FOR MODULE 32 (Doctor-Friendly Clinical Summary)
# -- ADDITIVE, 2026-09-04
# --------------------------------------------------------------------------
#
# These are ALIASES ONLY, exactly as `app/services/trend_analyzer.py` added a
# block of them for THIS module. Every name below refers to the object Module
# 29 has always used.
#
# WHY MODULE 32 NEEDS THEM. A doctor-facing laboratory table must print a
# reading beside the reference interval that reading is actually comparable
# with. Module 5 used to convert the VALUE to the canonical unit while copying
# `reference_low`/`reference_high` through in the unit they were PRINTED in,
# so on a converted parameter the two numbers were in different units. Module
# 29 solved that once, in `_reference_interval`, by carrying the interval
# through the same `provenance.conversion` arithmetic; a second implementation
# is precisely the "two tables that can disagree" defect class this project's
# audits keep finding.
#
# UPDATED 2026-09-04: Module 5 now converts the interval at the source
# (`feature_engineer._reference_bounds`) and marks it with
# `provenance.reference_converted`. `_reference_interval` honours that flag and
# returns such bounds UNTOUCHED, so this module and Module 32 do not
# double-convert. The conversion branch remains for carriers that predate the
# flag; it is now belt and braces, not the fix.
#
# If any of these three is ever changed, Module 32 is a caller and must be
# checked.

#: `(low, high, basis, formula)` for the interval printed on one report,
#: expressed in the same unit as the stored value, or `(None, None, None,
#: None)` when that cannot be established. Duck-typed on the argument: it
#: reads `reference_low`, `reference_high`, `reference_converted`,
#: `unit_converted` and `conversion` by `getattr`, so a `FeatureProvenance` and
#: any object carrying those attributes both work; an object MISSING
#: `reference_converted` falls back to the conversion branch, and one missing
#: `conversion` too degrades to the refusal branch rather than to a wrong
#: number.
reference_interval = _reference_interval

#: `Optional[bool]`: is a value outside `[low, high]`? `None` when a censored
#: reading leaves that unsettled. The single censoring rule in this service.
outside_interval = _outside_interval

#: Printed laboratory flags this service understands, mapped to "is abnormal".
#: Anything outside this table is never read as normal.
FLAG_ABNORMAL = _FLAG_ABNORMAL


__all__ = [
    "COMPARATOR_VERSION",
    "DISCLAIMER",
    "FLAG_ABNORMAL",
    "comparator_document",
    "compare_reports",
    "outside_interval",
    "reference_interval",
]
