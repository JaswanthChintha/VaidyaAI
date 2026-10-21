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

COMPARATOR_VERSION = "1.0.0"

_TREND_TO_CHANGE: Dict[str, str] = {
    TREND_IMPROVING: CHANGE_IMPROVED,
    TREND_WORSENING: CHANGE_WORSENED,
    TREND_STABLE: CHANGE_UNCHANGED,
}

_FLAG_ABNORMAL: Dict[str, bool] = {
    "normal": False,
    "low": True,
    "high": True,
    "critical": True,
}


DISCLAIMER = (
    "This comparison describes how measured laboratory values differ between "
    "two reports, and whether a value moved across the reference interval "
    "printed on those reports. It reports arithmetic and declared directions "
    "of change only. It does not interpret those changes, does not identify "
    "any condition, and is not a substitute for review by a qualified health "
    "professional."
)

_TEMPLATES: Dict[str, str] = {
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
    "intermediate_reports_one": (
        "This comparison uses two of your reports. One other report is not "
        "included, though it still appears on the chart above."
    ),
    "intermediate_reports_many": (
        "This comparison uses two of your reports. {count} other reports are "
        "not included, though they still appear on the chart above."
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


def _flag_text(flag: object) -> Optional[str]:
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


def _reference_interval(
    provenance: object,
) -> Tuple[Optional[float], Optional[float], Optional[str], Optional[str]]:
    low = getattr(provenance, "reference_low", None)
    high = getattr(provenance, "reference_high", None)
    if not is_real_number(low):
        low = None
    if not is_real_number(high):
        high = None
    if low is None and high is None:
        return None, None, None, None

    if getattr(provenance, "reference_converted", False):
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
    if censored == "left":
        if low is not None and value < low:
            return True
        if low is not None:
            return None
        if high is not None and value > high:
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


def _abnormality(
    report: OrderedReport, feature: str, options: ComparisonOptions
) -> AbnormalityState:
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
            **extra,
        )

    if stored is None:
        return unknown(
            ABN_NO_USABLE_VALUE,
            _TEMPLATES["abn_no_value"].format(feature=feature),
        )
    if options.exclude_questionable and stored.questionable:
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

    inconclusive_interval: Optional[str] = None

    if basis is not None:
        outside = _outside_interval(value, low, high, censored, feature)
        if outside is None:
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
                **common,
            )

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
            **common,
        )

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


def _select_pair(
    ordered: Sequence[OrderedReport],
    baseline_ref: Optional[str],
    comparison_ref: Optional[str],
) -> Tuple[int, int, str]:
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
        index_of[baseline_ref],
        index_of[comparison_ref],
        SELECTION_EXPLICIT,
    )


def _features_to_compare(
    baseline: OrderedReport,
    comparison: OrderedReport,
    options: ComparisonOptions,
) -> List[str]:
    if options.features:
        return list(options.features)
    if options.include_all_canonical:
        return list(CANONICAL_FEATURES)
    present = set(baseline.snapshot.features) | set(comparison.snapshot.features)
    return [name for name in CANONICAL_FEATURES if name in present]


def _category(
    outcome: str,
    change_class: Optional[str],
    transition: Optional[str],
) -> str:
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
    definition = FEATURES[feature]

    trend = analyse_feature(
        feature, [baseline, comparison], timeline_options, recorded_ages=ages
    )

    warnings: List[str] = list(trend.warnings)
    outcome = trend.outcome
    change_class: Optional[str] = None
    reason = trend.reason

    if outcome == OUTCOME_TREND_CLASSIFIED:
        outcome = COMPARISON_CHANGE_CLASSIFIED
        change_class = _TREND_TO_CHANGE[trend.trend]
    elif outcome == OUTCOME_INSUFFICIENT_DATA:
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


def _summary(
    parameters: Dict[str, ParameterComparison],
    pair: Optional[ComparisonPair],
    reports_supplied: int,
) -> ComparisonSummary:
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


def compare_reports(request: ReportComparisonRequest) -> ReportComparisonData:
    ordered, warnings = order_reports(request.reports)
    options = request.options

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
            _WARNING_TEMPLATES["intermediate_reports_one"]
            if intermediate == 1
            else _WARNING_TEMPLATES["intermediate_reports_many"].format(
                count=intermediate
            )
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


def _self_check() -> None:
    for key, template in _TEMPLATES.items():
        assert_safe(template, f"comparison template {key}")
    for key, template in _WARNING_TEMPLATES.items():
        assert_safe(template, f"comparison warning template {key}")
    for key, template in _PARAMETER_WARNINGS.items():
        assert_safe(template, f"comparison parameter warning {key}")
    assert_safe(DISCLAIMER, "comparison disclaimer")

    from app.schemas.timeline import TREND_VALUES

    missing = [label for label in TREND_VALUES if label not in _TREND_TO_CHANGE]
    if missing:
        raise ValueError(
            f"trend labels with no comparison equivalent: {missing}. Module 29 "
            "maps Module 28's labels; it never invents one."
        )

    if _TREND_TO_CHANGE[TREND_STABLE] != CHANGE_UNCHANGED:
        raise ValueError("'unchanged' must map from Module 28's earned 'stable'")


_self_check()


reference_interval = _reference_interval

outside_interval = _outside_interval

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
