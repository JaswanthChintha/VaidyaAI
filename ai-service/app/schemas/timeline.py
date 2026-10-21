from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.data.feature_catalog import CANONICAL_FEATURES
from app.data.trend_polarity import TREND_POLICY_VERSION
from app.schemas.repository import FeatureSnapshot, ValidatedFeatureSetInput
from app.schemas.validation import ValidationFinding

STAGE_TIMELINE = "timeline"
TIMELINE_MODULE = 28


TREND_IMPROVING = "improving"
TREND_WORSENING = "worsening"
TREND_STABLE = "stable"

TREND_VALUES = (TREND_IMPROVING, TREND_WORSENING, TREND_STABLE)

DIRECTION_RISING = "rising"
DIRECTION_FALLING = "falling"
DIRECTION_UNCHANGED = "unchanged"

DIRECTION_VALUES = (DIRECTION_RISING, DIRECTION_FALLING, DIRECTION_UNCHANGED)

OUTCOME_TREND_CLASSIFIED = "TREND_CLASSIFIED"
OUTCOME_INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
OUTCOME_CLINICAL_DIRECTION_UNKNOWN = "CLINICAL_DIRECTION_UNKNOWN"
OUTCOME_CHANGE_WITHIN_REFERENCE_INTERVAL = "CHANGE_WITHIN_REFERENCE_INTERVAL"
OUTCOME_UNIT_MISMATCH = "UNIT_MISMATCH"
OUTCOME_UNIT_NOT_CANONICAL = "UNIT_NOT_CANONICAL"
OUTCOME_NOT_NUMERIC = "NOT_NUMERIC"
OUTCOME_NOT_TRENDABLE = "NOT_TRENDABLE"
OUTCOME_NOT_COMPARABLE_SAMPLE_TIMING = "NOT_COMPARABLE_SAMPLE_TIMING"
OUTCOME_NOT_COMPARABLE_AGE_CONTEXT = "NOT_COMPARABLE_AGE_CONTEXT"
OUTCOME_NO_STABILITY_BAND = "NO_STABILITY_BAND"

OUTCOME_VALUES = (
    OUTCOME_TREND_CLASSIFIED,
    OUTCOME_INSUFFICIENT_DATA,
    OUTCOME_CLINICAL_DIRECTION_UNKNOWN,
    OUTCOME_CHANGE_WITHIN_REFERENCE_INTERVAL,
    OUTCOME_UNIT_MISMATCH,
    OUTCOME_UNIT_NOT_CANONICAL,
    OUTCOME_NOT_NUMERIC,
    OUTCOME_NOT_TRENDABLE,
    OUTCOME_NOT_COMPARABLE_SAMPLE_TIMING,
    OUTCOME_NOT_COMPARABLE_AGE_CONTEXT,
    OUTCOME_NO_STABILITY_BAND,
)

GAP_REJECTED = "REJECTED"
GAP_NOT_REPORTED = "NOT_REPORTED"
GAP_UNUSABLE = "UNUSABLE"
GAP_NON_NUMERIC_VALUE = "NON_NUMERIC_VALUE"
GAP_NON_FINITE_VALUE = "NON_FINITE_VALUE"
GAP_QUESTIONABLE_EXCLUDED = "QUESTIONABLE_EXCLUDED"
GAP_IMPLAUSIBLE_VALUE = "IMPLAUSIBLE_VALUE"

OUTCOME_DESCRIPTIONS: Dict[str, str] = {
    OUTCOME_TREND_CLASSIFIED: (
        "`trend` is set to improving, worsening or stable."
    ),
    OUTCOME_INSUFFICIENT_DATA: (
        "Fewer than two usable points. NOT stable -- 'we could not look' and "
        "'we looked and nothing changed' are different statements."
    ),
    OUTCOME_CLINICAL_DIRECTION_UNKNOWN: (
        "The value changed measurably, but no clinical direction is declared "
        "for this feature in app/data/trend_polarity.py, or the change "
        "crossed the declared reference interval so that a single better/worse "
        "label would mislead. Direction and magnitude are reported; better or "
        "worse is not guessed."
    ),
    OUTCOME_CHANGE_WITHIN_REFERENCE_INTERVAL: (
        "The value changed measurably but both the first and last readings sit "
        "inside the declared reference interval, so no better/worse claim is "
        "made."
    ),
    OUTCOME_UNIT_MISMATCH: (
        "Two reports carry this feature in DIFFERENT units. Refused. The "
        "values are not coerced; a unit conversion belongs in Module 5, "
        "upstream of storage, not in a trend calculation."
    ),
    OUTCOME_UNIT_NOT_CANONICAL: (
        "At least one reading is not in the feature's canonical unit (Module 5 "
        "could not convert it). Refused rather than compared."
    ),
    OUTCOME_NOT_NUMERIC: (
        "The feature is a boolean or a category. There is no magnitude to "
        "trend."
    ),
    OUTCOME_NOT_TRENDABLE: (
        "The feature is declared not trendable in app/data/trend_polarity.py "
        "(for example `age`, which rises for everyone by construction)."
    ),
    OUTCOME_NOT_COMPARABLE_SAMPLE_TIMING: (
        "The readings were taken under DIFFERENT established sample timings "
        "(for example a fasting and a post-prandial glucose). Not comparable."
    ),
    OUTCOME_NOT_COMPARABLE_AGE_CONTEXT: (
        "The polarity declaration is only valid at or above a stated age, and "
        "a younger age is recorded in the series."
    ),
    OUTCOME_NO_STABILITY_BAND: (
        "No stability band is declared for this feature, so 'stable' would "
        "have no meaning. Refused rather than defaulted."
    ),
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class TimelineReportInput(BaseModel):

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    report_id: str = Field(
        validation_alias="report_id",
        min_length=1,
        max_length=128,
        description="Opaque report identifier (the backend's Mongo _id). "
        "Never a name. Must be unique within one request.",
    )
    chrono_date: datetime = Field(
        description="When the report was produced. The ordering key."
    )
    sequence: Optional[int] = Field(
        default=None,
        ge=0,
        description="Optional caller-supplied tie-break for reports that share "
        "a chrono_date. When absent, ties break on report_id. Either way the "
        "order depends only on the DATA, never on the order of this array, so "
        "it cannot change between calls.",
    )
    validated: Optional[ValidatedFeatureSetInput] = Field(
        default=None, description="Module 6's `data` object, posted verbatim."
    )
    snapshot: Optional[FeatureSnapshot] = Field(
        default=None, description="An already-built Module 7 FeatureSnapshot."
    )

    @field_validator("chrono_date")
    @classmethod
    def _tz_aware(cls, v: datetime) -> datetime:
        return _as_utc(v)

    @model_validator(mode="before")
    @classmethod
    def _accept_report_ref(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        out = dict(value)
        if "report_id" not in out and "report_ref" in out:
            out["report_id"] = out["report_ref"]
        if "chrono_date" not in out and "report_date" in out:
            out["chrono_date"] = out["report_date"]
        return out

    @model_validator(mode="after")
    def _exactly_one_feature_source(self) -> "TimelineReportInput":
        if self.validated is not None and self.snapshot is not None:
            raise ValueError(
                f"report {self.report_id!r}: send the features as 'validated' "
                "(Module 6) OR as 'snapshot' (Module 7), not both."
            )
        return self


class TimelineOptions(BaseModel):

    model_config = ConfigDict(extra="ignore")

    features: Optional[List[str]] = Field(
        default=None,
        max_length=len(CANONICAL_FEATURES),
        description="Restrict the analysis to these canonical features. When "
        "omitted, every feature that has a usable value in at least one report "
        "is analysed. An unknown name is a 400, never a silent skip.",
    )
    include_all_canonical: bool = Field(
        default=False,
        description="Return an entry for EVERY canonical feature, including "
        "ones that appear in no report (they come back as INSUFFICIENT_DATA "
        "with an all-gap series). Off by default so the response is not padded.",
    )
    exclude_questionable: bool = Field(
        default=False,
        description="Treat Module 6 'questionable' readings (unit assumed, low "
        "extraction confidence) as gaps instead of points. Off by default: "
        "Module 6 accepted them as valid, and the point carries the flag either "
        "way. Turning it on can turn a trend into INSUFFICIENT_DATA, which is "
        "the correct conservative outcome.",
    )

    @field_validator("features")
    @classmethod
    def _known_features(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return None
        unknown = [name for name in v if name not in CANONICAL_FEATURES]
        if unknown:
            raise ValueError(
                f"not canonical features: {sorted(set(unknown))}. See "
                "GET /api/v1/features/catalog."
            )
        chosen = set(v)
        return [name for name in CANONICAL_FEATURES if name in chosen]


class TimelineTrendsRequest(BaseModel):

    model_config = ConfigDict(extra="ignore")

    patient_ref: Optional[str] = Field(
        default=None,
        max_length=128,
        description="Opaque patient identifier. Never a name. Echoed back only.",
    )
    reports: List[TimelineReportInput] = Field(
        default_factory=list,
        max_length=500,
        description="One entry per report. Order is irrelevant.",
    )
    options: TimelineOptions = Field(default_factory=TimelineOptions)

    @model_validator(mode="before")
    @classmethod
    def _unwrap(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        if "reports" in value:
            return value
        inner = value.get("data")
        if isinstance(inner, dict) and "reports" in inner:
            merged = dict(inner)
            for key in ("patient_ref", "options"):
                if key in value and key not in merged:
                    merged[key] = value[key]
            return merged
        return value

    @model_validator(mode="after")
    def _report_ids_unique(self) -> "TimelineTrendsRequest":
        seen: Dict[str, int] = {}
        for report in self.reports:
            seen[report.report_id] = seen.get(report.report_id, 0) + 1
        duplicates = sorted(rid for rid, count in seen.items() if count > 1)
        if duplicates:
            raise ValueError(
                "duplicate report_id in one request: "
                f"{duplicates}. Report ids must be unique -- a duplicate makes "
                "the ordering ambiguous and would double-count a reading."
            )
        return self


class TimelinePoint(BaseModel):

    model_config = ConfigDict(extra="forbid")

    report_id: str
    date: datetime
    value: float
    unit: Optional[str] = None
    status: str = Field(description="Module 6's status: valid | questionable")
    questionable: bool = False
    clinically_extreme: bool = False
    extreme_direction: Optional[str] = None
    flags: List[ValidationFinding] = Field(
        default_factory=list, description="Module 6's findings, carried intact."
    )
    sample_timing: Optional[str] = Field(
        default=None,
        description="For timing-sensitive features only (glucose): fasting | "
        "post_prandial | random | unspecified, inferred from the printed test "
        "name by app.data.clinical_rules.sample_timing.",
    )


class TimelineGap(BaseModel):

    model_config = ConfigDict(extra="forbid")

    report_id: str
    date: datetime
    availability: str = Field(
        description="rejected | not_reported | unusable, from Module 7's "
        "unavailable map, or a Module 28 code for a value it could not use."
    )
    reason_code: str
    reason: str


class TrendChange(BaseModel):

    model_config = ConfigDict(extra="forbid")

    first_report_id: str
    last_report_id: str
    first_date: datetime
    last_date: datetime
    days_between: float = Field(
        description="Elapsed days between the first and last usable readings."
    )
    first_value: float
    last_value: float
    absolute_change: float = Field(description="last_value - first_value.")
    percent_change: Optional[float] = Field(
        default=None,
        description="absolute_change / |first_value| * 100. None when the "
        "first value is zero -- not 0, and not infinity.",
    )
    min_value: float
    max_value: float
    step_count: int = Field(description="Number of consecutive-pair steps.")
    direction_consistency: Optional[float] = Field(
        default=None,
        description="Fraction of non-zero steps that move in the same "
        "direction as the net change. 1.0 is monotone. None when the net "
        "change is zero or there are no non-zero steps.",
    )
    volatile: bool = Field(
        default=False,
        description="True when at least one intermediate step was itself "
        "significant AND moved against the net direction. The net "
        "classification is still reported; this flag says it is not the whole "
        "story.",
    )


class AppliedPolarity(BaseModel):

    model_config = ConfigDict(extra="forbid")

    kind: str
    direction_of_harm: Optional[str] = None
    optimal_low: Optional[float] = None
    optimal_high: Optional[float] = None
    basis: str
    source: str = Field(
        default="app/data/trend_polarity.py",
        description="Where the declaration lives, so a reviewer can find it.",
    )


class AppliedStability(BaseModel):

    model_config = ConfigDict(extra="forbid")

    significant_change_pct: float
    min_absolute_change: float
    basis: str
    exceeded: Optional[bool] = Field(
        default=None,
        description="True when the change cleared BOTH thresholds. None when "
        "no change was computed at all.",
    )
    source: str = "app/data/trend_polarity.py"


class FeatureTrend(BaseModel):

    model_config = ConfigDict(extra="forbid")

    feature: str
    value_type: str
    canonical_unit: Optional[str] = None

    points: List[TimelinePoint] = Field(
        default_factory=list,
        description="The ordered series, oldest first. Suitable for plotting "
        "as-is: every point is a real reading in the canonical unit.",
    )
    gaps: List[TimelineGap] = Field(
        default_factory=list,
        description="Reports that carried no usable value, and why. Never "
        "plotted as zero.",
    )
    report_count: int = 0
    usable_point_count: int = 0

    outcome: str = Field(description="Always present. See OUTCOME_VALUES.")
    trend: Optional[str] = Field(
        default=None, description="improving | worsening | stable | null."
    )
    direction: Optional[str] = Field(
        default=None,
        description="rising | falling | unchanged | null. Pure arithmetic; "
        "says nothing about better or worse.",
    )
    change: Optional[TrendChange] = None
    polarity: Optional[AppliedPolarity] = None
    stability: Optional[AppliedStability] = None
    reason: str = Field(
        description="Deterministic, template-assembled explanation. No model "
        "wrote this and no free text can enter it."
    )
    warnings: List[str] = Field(default_factory=list)

    @field_validator("trend")
    @classmethod
    def _known_trend(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in TREND_VALUES:
            raise ValueError(f"trend must be one of {TREND_VALUES} or null")
        return v

    @field_validator("direction")
    @classmethod
    def _known_direction(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in DIRECTION_VALUES:
            raise ValueError(f"direction must be one of {DIRECTION_VALUES} or null")
        return v

    @field_validator("outcome")
    @classmethod
    def _known_outcome(cls, v: str) -> str:
        if v not in OUTCOME_VALUES:
            raise ValueError(f"outcome must be one of {OUTCOME_VALUES}")
        return v

    @model_validator(mode="after")
    def _trend_only_when_classified(self) -> "FeatureTrend":
        if self.outcome == OUTCOME_TREND_CLASSIFIED and self.trend is None:
            raise ValueError("TREND_CLASSIFIED requires a trend")
        if self.outcome != OUTCOME_TREND_CLASSIFIED and self.trend is not None:
            raise ValueError(f"outcome {self.outcome} must carry trend=None")
        if self.outcome == OUTCOME_INSUFFICIENT_DATA and self.change is not None:
            raise ValueError("INSUFFICIENT_DATA cannot carry a change")
        return self


class TimelineReportRef(BaseModel):

    model_config = ConfigDict(extra="forbid")

    report_id: str
    date: datetime
    order: int = Field(ge=0, description="0-based position, oldest first.")
    feature_count: int = Field(
        default=0, ge=0, description="Usable features in this report. A count."
    )


class TimelineSummary(BaseModel):

    model_config = ConfigDict(extra="forbid")

    report_count: int = 0
    features_examined: int = 0
    improving: int = 0
    worsening: int = 0
    stable: int = 0
    not_determinable: int = Field(
        default=0,
        description="Features with trend=None for ANY reason. The sum of "
        "`outcomes` minus the classified ones.",
    )
    outcomes: Dict[str, int] = Field(
        default_factory=dict, description="Count per outcome code."
    )
    first_report_date: Optional[datetime] = None
    last_report_date: Optional[datetime] = None
    days_span: Optional[float] = None


class TimelineTrendsData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patient_ref: Optional[str] = None
    policy_version: str = TREND_POLICY_VERSION
    generated_at: datetime = Field(default_factory=utcnow)
    reports: List[TimelineReportRef] = Field(default_factory=list)
    features: Dict[str, FeatureTrend] = Field(default_factory=dict)
    summary: TimelineSummary = Field(default_factory=TimelineSummary)
    warnings: List[str] = Field(
        default_factory=list,
        description="Warnings raised by MODULE 28 ITSELF about the request as "
        "a whole (for example: only one report was supplied).",
    )
    disclaimer: str = Field(
        default="",
        description="Fixed, reviewed text. Module 28 describes how measured "
        "values changed; it does not diagnose, and it does not interpret.",
    )


class TimelineTrendsResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    success: bool = True
    data: TimelineTrendsData


__all__ = [
    "DIRECTION_FALLING",
    "DIRECTION_RISING",
    "DIRECTION_UNCHANGED",
    "DIRECTION_VALUES",
    "GAP_NON_FINITE_VALUE",
    "GAP_NON_NUMERIC_VALUE",
    "GAP_NOT_REPORTED",
    "GAP_IMPLAUSIBLE_VALUE",
    "GAP_QUESTIONABLE_EXCLUDED",
    "GAP_REJECTED",
    "GAP_UNUSABLE",
    "OUTCOME_CHANGE_WITHIN_REFERENCE_INTERVAL",
    "OUTCOME_CLINICAL_DIRECTION_UNKNOWN",
    "OUTCOME_DESCRIPTIONS",
    "OUTCOME_INSUFFICIENT_DATA",
    "OUTCOME_NOT_COMPARABLE_AGE_CONTEXT",
    "OUTCOME_NOT_COMPARABLE_SAMPLE_TIMING",
    "OUTCOME_NOT_NUMERIC",
    "OUTCOME_NOT_TRENDABLE",
    "OUTCOME_NO_STABILITY_BAND",
    "OUTCOME_TREND_CLASSIFIED",
    "OUTCOME_UNIT_MISMATCH",
    "OUTCOME_UNIT_NOT_CANONICAL",
    "OUTCOME_VALUES",
    "STAGE_TIMELINE",
    "TIMELINE_MODULE",
    "TREND_IMPROVING",
    "TREND_STABLE",
    "TREND_VALUES",
    "TREND_WORSENING",
    "AppliedPolarity",
    "AppliedStability",
    "FeatureTrend",
    "TimelineGap",
    "TimelineOptions",
    "TimelinePoint",
    "TimelineReportInput",
    "TimelineReportRef",
    "TimelineSummary",
    "TimelineTrendsData",
    "TimelineTrendsRequest",
    "TimelineTrendsResponse",
    "TrendChange",
    "utcnow",
]
