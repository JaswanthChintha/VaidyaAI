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

TREND_ANALYZER_VERSION = "1.0.0"


DISCLAIMER = (
    "This timeline describes how measured laboratory values changed between "
    "reports. It reports arithmetic and a declared direction of change only. "
    "It does not interpret those changes, does not identify any condition, and "
    "is not a substitute for review by a qualified health professional."
)

def _label(feature: str) -> str:
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


def _is_real_number(value: object) -> bool:
    if isinstance(value, bool):
        return False
    if not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value))


def _normalise_unit(unit: Optional[str]) -> Optional[str]:
    if unit is None:
        return None
    folded = " ".join(unit.split()).lower()
    return folded or None


def _fmt(value: float) -> str:
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


class _OrderedReport:

    __slots__ = ("report_id", "date", "snapshot")

    def __init__(
        self, report_id: str, date: datetime, snapshot: FeatureSnapshot
    ) -> None:
        self.report_id = report_id
        self.date = date
        self.snapshot = snapshot


def _sort_key(report: TimelineReportInput) -> Tuple[datetime, int, int, str]:
    return (
        report.chrono_date,
        0 if report.sequence is not None else 1,
        report.sequence if report.sequence is not None else 0,
        report.report_id,
    )


def _to_snapshot(report: TimelineReportInput) -> FeatureSnapshot:
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


def _is_physiologically_possible(
    feature: str, value: float, unit: Optional[str]
) -> bool:
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
    absolute = abs(last - first)
    if absolute < band.min_absolute_change:
        return False
    if absolute == 0:
        return False
    if first == 0:
        return True
    percent = absolute / abs(first) * 100.0
    return percent >= band.significant_change_pct


def _classify(
    polarity: TrendPolarity,
    change: TrendChange,
    significant: bool,
) -> Tuple[str, Optional[str], str]:
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

    return OUTCOME_CLINICAL_DIRECTION_UNKNOWN, None, "direction_unknown"


def analyse_feature(
    feature: str,
    reports: Sequence[_OrderedReport],
    options: Optional[TimelineOptions] = None,
    *,
    recorded_ages: Sequence[float] = (),
) -> FeatureTrend:
    options = options or TimelineOptions()
    definition = FEATURES[feature]
    polarity = polarity_for(feature)
    if polarity is None:
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

    if len(points) < 2:
        return result(
            OUTCOME_INSUFFICIENT_DATA,
            _TEMPLATES["insufficient"].format(
                feature=_label(feature), count=len(points), reports=len(reports)
            ),
        )

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
    return result_trend.model_copy(update={"stability": applied_stability})


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
    return [name for name in CANONICAL_FEATURES if name in present]


def _recorded_ages(reports: Sequence[_OrderedReport]) -> List[float]:
    ages: List[float] = []
    for report in reports:
        stored = report.snapshot.features.get("age")
        if stored is not None and _is_real_number(stored.value):
            ages.append(float(stored.value))
    return ages


def analyse_trends(request: TimelineTrendsRequest) -> TimelineTrendsData:
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


def _self_check() -> None:
    for key, template in _TEMPLATES.items():
        assert_safe(template, f"trend reason template {key}")
    for key, template in _WARNING_TEMPLATES.items():
        assert_safe(template, f"trend warning template {key}")
    assert_safe(DISCLAIMER, "trend disclaimer")

    if OUTCOME_TREND_CLASSIFIED not in (
        OUTCOME_TREND_CLASSIFIED,
        OUTCOME_INSUFFICIENT_DATA,
    ):
        raise ValueError("outcome vocabulary drifted")


_self_check()


OrderedReport = _OrderedReport

order_reports = _order_reports

to_snapshot = _to_snapshot

collect_series = _collect_series

recorded_ages = _recorded_ages

is_real_number = _is_real_number

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
