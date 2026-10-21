from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.data.feature_catalog import CANONICAL_FEATURES
from app.data.trend_polarity import TREND_POLICY_VERSION
from app.schemas.timeline import (
    DIRECTION_VALUES,
    OUTCOME_INSUFFICIENT_DATA,
    OUTCOME_TREND_CLASSIFIED,
    OUTCOME_VALUES,
    AppliedPolarity,
    AppliedStability,
    TimelineGap,
    TimelinePoint,
    TimelineReportInput,
    TimelineReportRef,
    TrendChange,
    utcnow,
)

STAGE_COMPARISON = "comparison"
COMPARISON_MODULE = 29


COMPARISON_CHANGE_CLASSIFIED = "CHANGE_CLASSIFIED"

COMPARISON_ONLY_IN_BASELINE = "ONLY_IN_BASELINE"

COMPARISON_ONLY_IN_COMPARISON = "ONLY_IN_COMPARISON"

COMPARISON_IN_NEITHER = "IN_NEITHER"

COMPARISON_OWN_OUTCOMES: Tuple[str, ...] = (
    COMPARISON_CHANGE_CLASSIFIED,
    COMPARISON_ONLY_IN_BASELINE,
    COMPARISON_ONLY_IN_COMPARISON,
    COMPARISON_IN_NEITHER,
)

INHERITED_REFUSAL_OUTCOMES: Tuple[str, ...] = tuple(
    code
    for code in OUTCOME_VALUES
    if code not in (OUTCOME_TREND_CLASSIFIED, OUTCOME_INSUFFICIENT_DATA)
)

COMPARISON_OUTCOME_VALUES: Tuple[str, ...] = (
    COMPARISON_OWN_OUTCOMES + INHERITED_REFUSAL_OUTCOMES
)


CHANGE_IMPROVED = "improved"
CHANGE_WORSENED = "worsened"
CHANGE_UNCHANGED = "unchanged"

CHANGE_VALUES: Tuple[str, ...] = (
    CHANGE_IMPROVED,
    CHANGE_WORSENED,
    CHANGE_UNCHANGED,
)


TRANSITION_NEWLY_ABNORMAL = "newly_abnormal"
TRANSITION_NEWLY_NORMAL = "newly_normal"
TRANSITION_REMAINED_ABNORMAL = "remained_abnormal"
TRANSITION_REMAINED_NORMAL = "remained_normal"

TRANSITION_VALUES: Tuple[str, ...] = (
    TRANSITION_NEWLY_ABNORMAL,
    TRANSITION_NEWLY_NORMAL,
    TRANSITION_REMAINED_ABNORMAL,
    TRANSITION_REMAINED_NORMAL,
)

TRANSITION_CLASSIFIED = "TRANSITION_CLASSIFIED"
NOT_DETERMINABLE_BASELINE = "NOT_DETERMINABLE_BASELINE"
NOT_DETERMINABLE_COMPARISON = "NOT_DETERMINABLE_COMPARISON"
NOT_DETERMINABLE_BOTH = "NOT_DETERMINABLE_BOTH"

TRANSITION_OUTCOME_VALUES: Tuple[str, ...] = (
    TRANSITION_CLASSIFIED,
    NOT_DETERMINABLE_BASELINE,
    NOT_DETERMINABLE_COMPARISON,
    NOT_DETERMINABLE_BOTH,
)


BASIS_REFERENCE_RANGE = "reference_range"

BASIS_REFERENCE_RANGE_CONVERTED = "reference_range_converted"

BASIS_PRINTED_FLAG = "printed_flag"

BASIS_NOT_DETERMINABLE = "not_determinable"

ABNORMALITY_BASIS_VALUES: Tuple[str, ...] = (
    BASIS_REFERENCE_RANGE,
    BASIS_REFERENCE_RANGE_CONVERTED,
    BASIS_PRINTED_FLAG,
    BASIS_NOT_DETERMINABLE,
)

ABN_NO_USABLE_VALUE = "NO_USABLE_VALUE"
ABN_NO_REFERENCE_OR_FLAG = "NO_REFERENCE_RANGE_OR_FLAG"
ABN_RANGE_UNIT_NOT_COMPARABLE = "REFERENCE_RANGE_UNIT_NOT_COMPARABLE"
ABN_CENSORED_INCONCLUSIVE = "CENSORED_VALUE_INCONCLUSIVE"
ABN_ONE_SIDED_INTERVAL_INCONCLUSIVE = "ONE_SIDED_INTERVAL_INCONCLUSIVE"
ABN_UNKNOWN_FLAG = "UNRECOGNISED_PRINTED_FLAG"

ABNORMALITY_REASON_CODES: Tuple[str, ...] = (
    ABN_NO_USABLE_VALUE,
    ABN_NO_REFERENCE_OR_FLAG,
    ABN_RANGE_UNIT_NOT_COMPARABLE,
    ABN_CENSORED_INCONCLUSIVE,
    ABN_ONE_SIDED_INTERVAL_INCONCLUSIVE,
    ABN_UNKNOWN_FLAG,
)


CATEGORY_NEWLY_ABNORMAL = "newly_abnormal"
CATEGORY_NEWLY_NORMAL = "newly_normal"
CATEGORY_IMPROVED = "improved"
CATEGORY_WORSENED = "worsened"
CATEGORY_UNCHANGED = "unchanged"
CATEGORY_CHANGED_DIRECTION_ONLY = "changed_direction_only"
CATEGORY_NOT_CLASSIFIABLE = "not_classifiable"

CATEGORY_VALUES: Tuple[str, ...] = (
    CATEGORY_NEWLY_ABNORMAL,
    CATEGORY_NEWLY_NORMAL,
    CATEGORY_IMPROVED,
    CATEGORY_WORSENED,
    CATEGORY_UNCHANGED,
    CATEGORY_CHANGED_DIRECTION_ONLY,
    CATEGORY_NOT_CLASSIFIABLE,
)

SELECTION_EXPLICIT = "explicit"
SELECTION_FIRST_VS_LATEST = "first_vs_latest"


class ComparisonOptions(BaseModel):

    model_config = ConfigDict(extra="ignore")

    features: Optional[List[str]] = Field(
        default=None,
        max_length=len(CANONICAL_FEATURES),
        description="Restrict the comparison to these canonical features. When "
        "omitted, every feature with a usable value in at least one of the TWO "
        "chosen reports is compared. An unknown name is a 422, never a silent "
        "skip.",
    )
    include_all_canonical: bool = Field(
        default=False,
        description="Return an entry for EVERY canonical feature, including "
        "ones neither chosen report carried (they come back as IN_NEITHER). "
        "Off by default so the response is not padded.",
    )
    exclude_questionable: bool = Field(
        default=False,
        description="Treat Module 6 'questionable' readings as absent, on both "
        "the change axis and the abnormality axis. Off by default; turning it "
        "on can only ever turn a classification into a refusal, which is the "
        "conservative direction.",
    )
    include_series: bool = Field(
        default=True,
        description="When more than two reports are supplied, also return the "
        "full ordered series (points and gaps) per feature, so a renderer can "
        "draw the intermediate readings. The CLASSIFICATION is still strictly "
        "between the two reports named in `pair`.",
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


class ReportComparisonRequest(BaseModel):

    model_config = ConfigDict(extra="ignore")

    patient_ref: Optional[str] = Field(
        default=None,
        max_length=128,
        description="Opaque patient identifier. Never a name. Echoed back only.",
    )
    reports: List[TimelineReportInput] = Field(
        default_factory=list,
        max_length=500,
        description="One entry per report. Array order is irrelevant; ordering "
        "comes from chrono_date, then sequence, then report_id.",
    )
    baseline_ref: Optional[str] = Field(
        default=None,
        max_length=128,
        description="report_id of the EARLIER side of the comparison. Supply "
        "with comparison_ref or not at all.",
    )
    comparison_ref: Optional[str] = Field(
        default=None,
        max_length=128,
        description="report_id of the LATER side of the comparison.",
    )
    options: ComparisonOptions = Field(default_factory=ComparisonOptions)

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
            for key in ("patient_ref", "options", "baseline_ref", "comparison_ref"):
                if key in value and key not in merged:
                    merged[key] = value[key]
            return merged
        return value

    @model_validator(mode="after")
    def _report_ids_unique(self) -> "ReportComparisonRequest":
        seen: Dict[str, int] = {}
        for report in self.reports:
            seen[report.report_id] = seen.get(report.report_id, 0) + 1
        duplicates = sorted(rid for rid, count in seen.items() if count > 1)
        if duplicates:
            raise ValueError(
                "duplicate report_id in one request: "
                f"{duplicates}. Report ids must be unique -- a duplicate makes "
                "the pair selection ambiguous and would double-count a reading."
            )
        return self

    @model_validator(mode="after")
    def _pair_is_both_or_neither(self) -> "ReportComparisonRequest":
        named = [
            name
            for name, value in (
                ("baseline_ref", self.baseline_ref),
                ("comparison_ref", self.comparison_ref),
            )
            if value is not None
        ]
        if len(named) == 1:
            raise ValueError(
                f"{named[0]} was supplied without the other side. Name BOTH "
                "baseline_ref and comparison_ref, or neither (in which case "
                "the first and latest reports by chrono_date are compared). "
                "The missing half is never guessed."
            )
        if (
            self.baseline_ref is not None
            and self.baseline_ref == self.comparison_ref
        ):
            raise ValueError(
                "baseline_ref and comparison_ref name the same report. A "
                "report compared with itself has nothing to report."
            )
        return self


class AbnormalityState(BaseModel):

    model_config = ConfigDict(extra="forbid")

    report_id: str
    date: datetime
    abnormal: Optional[bool] = Field(
        default=None,
        description="True | False | null (not determinable). Never defaulted.",
    )
    basis: str = Field(description="See ABNORMALITY_BASIS_VALUES.")
    reason_code: Optional[str] = Field(
        default=None,
        description="Present only when `abnormal` is null. See "
        "ABNORMALITY_REASON_CODES.",
    )
    reason: str = Field(
        description="Deterministic, template-assembled. No model wrote this."
    )

    value: Optional[float] = Field(
        default=None,
        description="The usable reading, when there was one. Null means there "
        "was none -- it never means zero.",
    )
    unit: Optional[str] = None
    reference_low: Optional[float] = Field(
        default=None,
        description="Lower bound actually used, expressed in the same unit as "
        "`value`. Null when no bound was used.",
    )
    reference_high: Optional[float] = None
    reference_range_raw: Optional[str] = Field(
        default=None, description="The interval exactly as printed."
    )
    printed_flag: Optional[str] = Field(
        default=None, description="low | normal | high | critical, as printed."
    )
    flag_disagrees_with_range: bool = Field(
        default=False,
        description="True when the report printed BOTH an interval and a flag "
        "and they imply different answers. The interval is used and this flag "
        "is raised; neither is silently dropped.",
    )

    @field_validator("basis")
    @classmethod
    def _known_basis(cls, v: str) -> str:
        if v not in ABNORMALITY_BASIS_VALUES:
            raise ValueError(f"basis must be one of {ABNORMALITY_BASIS_VALUES}")
        return v

    @model_validator(mode="after")
    def _basis_matches_answer(self) -> "AbnormalityState":
        if self.basis == BASIS_NOT_DETERMINABLE and self.abnormal is not None:
            raise ValueError("basis not_determinable requires abnormal=None")
        if self.basis != BASIS_NOT_DETERMINABLE and self.abnormal is None:
            raise ValueError(f"basis {self.basis} requires a non-null abnormal")
        if self.abnormal is None and self.reason_code is None:
            raise ValueError("abnormal=None requires a reason_code")
        return self


SYMBOL_UP = "↑"
SYMBOL_DOWN = "↓"
SYMBOL_LEVEL = "→"


class ComparisonRow(BaseModel):

    model_config = ConfigDict(extra="forbid")

    feature: str
    description: str = Field(description="The catalogue's description. Not a value.")
    unit: Optional[str] = None
    previous: Optional[float] = None
    current: Optional[float] = None
    absolute_change: Optional[float] = None
    percent_change: Optional[float] = None
    direction: Optional[str] = Field(
        default=None,
        description="rising | falling | unchanged | null. Pure arithmetic.",
    )
    symbol: Optional[str] = Field(
        default=None,
        description="The Trend column glyph: up, down, level arrow, or null "
        "when there is no comparable pair of readings.",
    )
    category: str
    significant: Optional[bool] = Field(
        default=None,
        description="True/False only when a change was measured against a "
        "declared stability band. Null when no change was computed at all.",
    )

    @field_validator("direction")
    @classmethod
    def _known_direction(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in DIRECTION_VALUES:
            raise ValueError(f"direction must be one of {DIRECTION_VALUES} or null")
        return v

    @field_validator("category")
    @classmethod
    def _known_category(cls, v: str) -> str:
        if v not in CATEGORY_VALUES:
            raise ValueError(f"category must be one of {CATEGORY_VALUES}")
        return v


class ParameterComparison(BaseModel):

    model_config = ConfigDict(extra="forbid")

    feature: str
    description: str
    value_type: str
    canonical_unit: Optional[str] = None

    outcome: str = Field(description="Always present. See COMPARISON_OUTCOME_VALUES.")
    change_class: Optional[str] = Field(
        default=None, description="improved | worsened | unchanged | null."
    )
    direction: Optional[str] = Field(
        default=None,
        description="rising | falling | unchanged | null. Says nothing about "
        "better or worse.",
    )
    change: Optional[TrendChange] = Field(
        default=None,
        description="The arithmetic, first (baseline) reading to last "
        "(comparison) reading, from Module 28.",
    )
    significant: Optional[bool] = None
    polarity: Optional[AppliedPolarity] = Field(
        default=None,
        description="The polarity declaration read from "
        "app/data/trend_polarity.py, echoed so the answer is checkable.",
    )
    stability: Optional[AppliedStability] = None

    baseline: AbnormalityState
    comparison: AbnormalityState
    transition_outcome: str = Field(description="See TRANSITION_OUTCOME_VALUES.")
    transition: Optional[str] = Field(
        default=None,
        description="newly_abnormal | newly_normal | remained_abnormal | "
        "remained_normal | null.",
    )

    category: str
    reason: str = Field(
        description="Deterministic, template-assembled explanation. No model "
        "wrote this and no free text can enter it."
    )
    warnings: List[str] = Field(default_factory=list)

    @field_validator("outcome")
    @classmethod
    def _known_outcome(cls, v: str) -> str:
        if v not in COMPARISON_OUTCOME_VALUES:
            raise ValueError(f"outcome must be one of {COMPARISON_OUTCOME_VALUES}")
        return v

    @field_validator("change_class")
    @classmethod
    def _known_change(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in CHANGE_VALUES:
            raise ValueError(f"change_class must be one of {CHANGE_VALUES} or null")
        return v

    @field_validator("direction")
    @classmethod
    def _known_direction(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in DIRECTION_VALUES:
            raise ValueError(f"direction must be one of {DIRECTION_VALUES} or null")
        return v

    @field_validator("transition_outcome")
    @classmethod
    def _known_transition_outcome(cls, v: str) -> str:
        if v not in TRANSITION_OUTCOME_VALUES:
            raise ValueError(
                f"transition_outcome must be one of {TRANSITION_OUTCOME_VALUES}"
            )
        return v

    @field_validator("transition")
    @classmethod
    def _known_transition(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in TRANSITION_VALUES:
            raise ValueError(f"transition must be one of {TRANSITION_VALUES} or null")
        return v

    @field_validator("category")
    @classmethod
    def _known_category(cls, v: str) -> str:
        if v not in CATEGORY_VALUES:
            raise ValueError(f"category must be one of {CATEGORY_VALUES}")
        return v

    @model_validator(mode="after")
    def _axes_are_consistent(self) -> "ParameterComparison":
        classified = self.outcome == COMPARISON_CHANGE_CLASSIFIED
        if classified and self.change_class is None:
            raise ValueError("CHANGE_CLASSIFIED requires a change_class")
        if not classified and self.change_class is not None:
            raise ValueError(f"outcome {self.outcome} must carry change_class=None")
        if classified and self.change is None:
            raise ValueError("CHANGE_CLASSIFIED requires the change arithmetic")
        if self.change_class == CHANGE_UNCHANGED and self.significant is not False:
            raise ValueError(
                "'unchanged' is only reachable by failing the declared "
                "stability band; significant must be False"
            )

        transition_ok = self.transition_outcome == TRANSITION_CLASSIFIED
        if transition_ok and self.transition is None:
            raise ValueError("TRANSITION_CLASSIFIED requires a transition")
        if not transition_ok and self.transition is not None:
            raise ValueError(
                f"transition_outcome {self.transition_outcome} must carry "
                "transition=None"
            )

        if self.category == CATEGORY_NEWLY_ABNORMAL:
            if self.transition != TRANSITION_NEWLY_ABNORMAL:
                raise ValueError(
                    "category newly_abnormal requires transition "
                    "newly_abnormal -- it is a state transition, not a guess"
                )
        elif self.category == CATEGORY_NEWLY_NORMAL:
            if self.transition != TRANSITION_NEWLY_NORMAL:
                raise ValueError(
                    "category newly_normal requires transition newly_normal"
                )
        elif self.category in (
            CATEGORY_IMPROVED,
            CATEGORY_WORSENED,
            CATEGORY_UNCHANGED,
        ):
            if self.change_class != self.category:
                raise ValueError(
                    f"category {self.category} requires change_class "
                    f"{self.category}, got {self.change_class!r}"
                )
        elif self.category == CATEGORY_CHANGED_DIRECTION_ONLY:
            if self.change is None:
                raise ValueError(
                    "category changed_direction_only requires a measured change"
                )
            if self.change_class is not None:
                raise ValueError(
                    "category changed_direction_only requires change_class=None"
                )
        else:
            if self.change_class is not None:
                raise ValueError(
                    "category not_classifiable cannot carry a change_class"
                )

        if self.category not in (CATEGORY_NEWLY_ABNORMAL, CATEGORY_NEWLY_NORMAL):
            if self.transition in (
                TRANSITION_NEWLY_ABNORMAL,
                TRANSITION_NEWLY_NORMAL,
            ):
                raise ValueError(
                    f"transition {self.transition} must surface as the "
                    "category; it outranks the change axis"
                )
        return self


class ComparisonPair(BaseModel):

    model_config = ConfigDict(extra="forbid")

    baseline_report_id: str
    baseline_date: datetime
    comparison_report_id: str
    comparison_date: datetime
    days_between: float = Field(
        description="comparison_date - baseline_date, in days. Negative when "
        "the caller named the pair in reverse chronological order."
    )
    selection: str = Field(
        description=f"{SELECTION_EXPLICIT} (the caller named both) | "
        f"{SELECTION_FIRST_VS_LATEST} (default: earliest and latest by "
        "chrono_date)."
    )
    chronological: bool = Field(
        description="True when baseline_date is at or before comparison_date. "
        "False means the caller named an explicit pair in reverse order; it is "
        "honoured as named, never silently swapped, and a warning is raised."
    )
    reports_supplied: int = Field(
        ge=0, description="How many reports the request carried in total."
    )
    intermediate_report_count: int = Field(
        ge=0,
        description="Reports lying strictly between the two chosen dates. They "
        "do NOT take part in the classification; they appear in `series`.",
    )

    @field_validator("selection")
    @classmethod
    def _known_selection(cls, v: str) -> str:
        if v not in (SELECTION_EXPLICIT, SELECTION_FIRST_VS_LATEST):
            raise ValueError("selection must be explicit or first_vs_latest")
        return v


class FeatureSeries(BaseModel):

    model_config = ConfigDict(extra="forbid")

    feature: str
    points: List[TimelinePoint] = Field(default_factory=list)
    gaps: List[TimelineGap] = Field(default_factory=list)


class ComparisonSummary(BaseModel):

    model_config = ConfigDict(extra="forbid")

    reports_supplied: int = 0
    features_examined: int = 0

    newly_abnormal: int = 0
    newly_normal: int = 0
    improved: int = 0
    worsened: int = 0
    unchanged: int = 0
    changed_direction_only: int = 0
    not_classifiable: int = 0
    significant_changes: int = Field(
        default=0,
        description="Parameters whose measured change cleared the declared "
        "stability band, whatever the category. Counted separately because "
        "significance and better/worse are different questions.",
    )

    categories: Dict[str, int] = Field(
        default_factory=dict, description="Count per category label."
    )
    outcomes: Dict[str, int] = Field(
        default_factory=dict, description="Count per change-axis outcome code."
    )
    transition_outcomes: Dict[str, int] = Field(
        default_factory=dict, description="Count per abnormality-axis outcome."
    )

    headline: str = ""
    lines: List[str] = Field(
        default_factory=list,
        description="The comparison summary, one templated sentence per "
        "non-empty group.",
    )


class ReportComparisonData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patient_ref: Optional[str] = None
    policy_version: str = TREND_POLICY_VERSION
    comparator_version: str = ""
    generated_at: datetime = Field(default_factory=utcnow)

    reports: List[TimelineReportRef] = Field(
        default_factory=list, description="Every supplied report, oldest first."
    )
    pair: Optional[ComparisonPair] = Field(
        default=None,
        description="Null ONLY when fewer than two reports were supplied, in "
        "which case nothing was compared and `warnings` says so.",
    )
    parameters: Dict[str, ParameterComparison] = Field(default_factory=dict)
    table: List[ComparisonRow] = Field(
        default_factory=list,
        description="The specification's comparison table, in catalogue order.",
    )
    series: Dict[str, FeatureSeries] = Field(
        default_factory=dict,
        description="Present only when more than two reports were supplied and "
        "`options.include_series` is on. Rendering aid; not the basis of any "
        "classification.",
    )
    summary: ComparisonSummary = Field(default_factory=ComparisonSummary)
    warnings: List[str] = Field(
        default_factory=list,
        description="Warnings raised by MODULE 29 ITSELF about the request as "
        "a whole.",
    )
    disclaimer: str = ""


class ReportComparisonResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    success: bool = True
    data: ReportComparisonData


__all__ = [
    "ABNORMALITY_BASIS_VALUES",
    "ABNORMALITY_REASON_CODES",
    "ABN_CENSORED_INCONCLUSIVE",
    "ABN_ONE_SIDED_INTERVAL_INCONCLUSIVE",
    "ABN_NO_REFERENCE_OR_FLAG",
    "ABN_NO_USABLE_VALUE",
    "ABN_RANGE_UNIT_NOT_COMPARABLE",
    "ABN_UNKNOWN_FLAG",
    "BASIS_NOT_DETERMINABLE",
    "BASIS_PRINTED_FLAG",
    "BASIS_REFERENCE_RANGE",
    "BASIS_REFERENCE_RANGE_CONVERTED",
    "CATEGORY_CHANGED_DIRECTION_ONLY",
    "CATEGORY_IMPROVED",
    "CATEGORY_NEWLY_ABNORMAL",
    "CATEGORY_NEWLY_NORMAL",
    "CATEGORY_NOT_CLASSIFIABLE",
    "CATEGORY_UNCHANGED",
    "CATEGORY_VALUES",
    "CATEGORY_WORSENED",
    "CHANGE_IMPROVED",
    "CHANGE_UNCHANGED",
    "CHANGE_VALUES",
    "CHANGE_WORSENED",
    "COMPARISON_CHANGE_CLASSIFIED",
    "COMPARISON_IN_NEITHER",
    "COMPARISON_MODULE",
    "COMPARISON_ONLY_IN_BASELINE",
    "COMPARISON_ONLY_IN_COMPARISON",
    "COMPARISON_OUTCOME_VALUES",
    "COMPARISON_OWN_OUTCOMES",
    "INHERITED_REFUSAL_OUTCOMES",
    "NOT_DETERMINABLE_BASELINE",
    "NOT_DETERMINABLE_BOTH",
    "NOT_DETERMINABLE_COMPARISON",
    "SELECTION_EXPLICIT",
    "SELECTION_FIRST_VS_LATEST",
    "STAGE_COMPARISON",
    "SYMBOL_DOWN",
    "SYMBOL_LEVEL",
    "SYMBOL_UP",
    "TRANSITION_CLASSIFIED",
    "TRANSITION_NEWLY_ABNORMAL",
    "TRANSITION_NEWLY_NORMAL",
    "TRANSITION_OUTCOME_VALUES",
    "TRANSITION_REMAINED_ABNORMAL",
    "TRANSITION_REMAINED_NORMAL",
    "TRANSITION_VALUES",
    "AbnormalityState",
    "ComparisonOptions",
    "ComparisonPair",
    "ComparisonRow",
    "ComparisonSummary",
    "FeatureSeries",
    "ParameterComparison",
    "ReportComparisonData",
    "ReportComparisonRequest",
    "ReportComparisonResponse",
]
