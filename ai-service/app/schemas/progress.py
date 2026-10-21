from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.data.feature_catalog import CANONICAL_FEATURES
from app.data.progress_scoring import (
    EXCLUSION_REASON_CODES,
    PROGRESS_SCORING_VERSION,
    SCALE_MAX,
    SCALE_MIN,
)
from app.data.trend_polarity import TREND_POLICY_VERSION
from app.schemas.comparison import (
    CATEGORY_VALUES,
    ComparisonPair,
    ReportComparisonData,
)
from app.schemas.timeline import (
    DIRECTION_VALUES,
    TimelineReportInput,
    TimelineReportRef,
    utcnow,
)

STAGE_PROGRESS = "progress"
PROGRESS_MODULE = 30


PROGRESS_SCORE_COMPUTED = "SCORE_COMPUTED"

PROGRESS_NO_PAIR = "NO_PAIR"

PROGRESS_NOTHING_ASSESSED = "NOTHING_ASSESSED"

PROGRESS_INSUFFICIENT_COVERAGE = "INSUFFICIENT_COVERAGE"

PROGRESS_OUTCOME_VALUES: Tuple[str, ...] = (
    PROGRESS_SCORE_COMPUTED,
    PROGRESS_NO_PAIR,
    PROGRESS_NOTHING_ASSESSED,
    PROGRESS_INSUFFICIENT_COVERAGE,
)

PROGRESS_OUTCOME_DESCRIPTIONS: Dict[str, str] = {
    PROGRESS_SCORE_COMPUTED: (
        "`score` and `band` are set. At least the declared minimum number of "
        "parameters could be placed on the scale."
    ),
    PROGRESS_NO_PAIR: (
        "Fewer than two reports were supplied. Nothing was compared, so there "
        "is no movement to score."
    ),
    PROGRESS_NOTHING_ASSESSED: (
        "Two reports were compared but no parameter could be placed on the "
        "scale. 'Nothing could be told' is not 'nothing changed', so no score "
        "is emitted."
    ),
    PROGRESS_INSUFFICIENT_COVERAGE: (
        "Fewer parameters contributed than the declared minimum, so a single "
        "parameter would hold a majority of the score. The contributions "
        "found are returned; no headline number is."
    ),
}


class ProgressOptions(BaseModel):

    model_config = ConfigDict(extra="ignore")

    features: Optional[List[str]] = Field(
        default=None,
        max_length=len(CANONICAL_FEATURES),
        description="Restrict the score to these canonical features. When "
        "omitted, every feature with a usable value in at least one of the two "
        "compared reports is examined. An unknown name is a 422, never a "
        "silent skip. NOTE: narrowing the feature list narrows the score's "
        "coverage, and the contributing count in the response reflects that.",
    )
    exclude_questionable: bool = Field(
        default=False,
        description="Treat Module 6 'questionable' readings as absent. Off by "
        "default; turning it on can only ever turn a contribution into an "
        "exclusion, which is the conservative direction.",
    )
    include_comparison: bool = Field(
        default=False,
        description="Embed the full Module 29 comparison the score was built "
        "from, under `comparison`. Off by default so the response is not "
        "doubled; turn it on when the caller wants to show the working.",
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


class HealthProgressRequest(BaseModel):

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
        description="report_id of the EARLIER side. Supply with "
        "comparison_ref or not at all.",
    )
    comparison_ref: Optional[str] = Field(
        default=None,
        max_length=128,
        description="report_id of the LATER side.",
    )
    options: ProgressOptions = Field(default_factory=ProgressOptions)

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
    def _report_ids_unique(self) -> "HealthProgressRequest":
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
    def _pair_is_both_or_neither(self) -> "HealthProgressRequest":
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
                "the earliest and latest reports by chrono_date are used). "
                "The missing half is never guessed."
            )
        if (
            self.baseline_ref is not None
            and self.baseline_ref == self.comparison_ref
        ):
            raise ValueError(
                "baseline_ref and comparison_ref name the same report. A "
                "report compared with itself has no progress to report."
            )
        return self


class ProgressBand(BaseModel):

    model_config = ConfigDict(extra="forbid")

    key: str
    lower_inclusive: float
    upper_exclusive: float
    label: str
    description: str


class ProgressScale(BaseModel):

    model_config = ConfigDict(extra="forbid")

    min: float = SCALE_MIN
    max: float = SCALE_MAX
    direction: str = Field(
        description="higher_is_better. The one token to branch on."
    )
    direction_text: str = Field(
        description="The same fact in a sentence, for display."
    )
    neutral_anchor: float = Field(
        description="The score obtained when every contributing parameter was "
        "unchanged."
    )
    kind: str = Field(
        description="equally_spaced_five_point_ordinal -- the five categories "
        "carry ordering information and nothing more."
    )
    kind_note: str
    rounding: str
    bands: List[ProgressBand] = Field(default_factory=list)


class ParameterContribution(BaseModel):

    model_config = ConfigDict(extra="forbid")

    feature: str
    description: str = Field(description="The catalogue's description. Not a value.")
    unit: Optional[str] = None

    category: str = Field(
        description="Module 29's category label. The ONLY input to `points`."
    )
    outcome: str = Field(description="Module 29's change-axis outcome code.")
    transition_outcome: str = Field(
        description="Module 29's abnormality-axis outcome code."
    )
    transition: Optional[str] = None
    direction: Optional[str] = Field(
        default=None,
        description="rising | falling | unchanged | null. Pure arithmetic; "
        "says nothing about better or worse.",
    )
    significant: Optional[bool] = Field(
        default=None,
        description="Whether the measured change cleared the stability band "
        "declared in app/data/trend_polarity.py. Reported, not re-derived.",
    )
    absolute_change: Optional[float] = Field(
        default=None,
        description="Module 28's arithmetic. Null when no change was computed "
        "-- never 0.",
    )
    percent_change: Optional[float] = Field(
        default=None,
        description="Module 28's arithmetic. Null when the baseline value was "
        "zero or no change was computed -- never 0 and never infinity.",
    )

    points: float = Field(
        description="The scale position for this parameter's category, from "
        "app/data/progress_scoring.py."
    )
    weight: float = Field(
        gt=0.0,
        description="Always 1.0 today: see the weighting note in "
        "GET /api/v1/progress/policy. A contribution can never carry weight 0 "
        "-- a zero-weight parameter is an exclusion, not a contribution.",
    )
    weighted_points: float = Field(description="points * weight.")

    @field_validator("category")
    @classmethod
    def _known_category(cls, v: str) -> str:
        if v not in CATEGORY_VALUES:
            raise ValueError(f"category must be one of {CATEGORY_VALUES}")
        return v

    @field_validator("direction")
    @classmethod
    def _known_direction(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in DIRECTION_VALUES:
            raise ValueError(f"direction must be one of {DIRECTION_VALUES} or null")
        return v

    @field_validator("points")
    @classmethod
    def _points_on_scale(cls, v: float) -> float:
        if not SCALE_MIN <= v <= SCALE_MAX:
            raise ValueError(f"points must lie within {SCALE_MIN}-{SCALE_MAX}")
        return v


class ExcludedParameter(BaseModel):

    model_config = ConfigDict(extra="forbid")

    feature: str
    description: str
    category: str = Field(description="Module 29's category label.")
    outcome: str = Field(description="Module 29's change-axis outcome code.")
    transition_outcome: str
    reason_code: str = Field(
        description="Module 30's exclusion code. See EXCLUSION_REASON_CODES."
    )
    reason: str = Field(
        description="Deterministic, template-assembled. No model wrote this."
    )

    @field_validator("category")
    @classmethod
    def _known_category(cls, v: str) -> str:
        if v not in CATEGORY_VALUES:
            raise ValueError(f"category must be one of {CATEGORY_VALUES}")
        return v

    @field_validator("reason_code")
    @classmethod
    def _known_reason(cls, v: str) -> str:
        if v not in EXCLUSION_REASON_CODES:
            raise ValueError(f"reason_code must be one of {EXCLUSION_REASON_CODES}")
        return v


class ProgressCoverage(BaseModel):

    model_config = ConfigDict(extra="forbid")

    features_examined: int = Field(
        ge=0, description="Parameters Module 29 returned a comparison for."
    )
    contributing_count: int = Field(
        ge=0, description="Parameters actually placed on the scale."
    )
    excluded_count: int = Field(ge=0)
    minimum_required: int = Field(
        ge=0,
        description="The declared floor below which no score is emitted. See "
        "GET /api/v1/progress/policy for its stated basis.",
    )
    sufficient: bool = Field(
        description="contributing_count >= minimum_required. When false, "
        "`score` is null."
    )
    contributing: List[str] = Field(
        default_factory=list,
        description="The feature names behind the score, in catalogue order.",
    )
    excluded: List[ExcludedParameter] = Field(
        default_factory=list,
        description="Every examined parameter that contributed nothing, with "
        "the reason. Never silently dropped.",
    )
    coverage_note: str = Field(
        default="",
        description="Templated sentence stating the contributing count in "
        "words, so a rendered score cannot appear without its coverage.",
    )

    @model_validator(mode="after")
    def _counts_agree(self) -> "ProgressCoverage":
        if self.contributing_count != len(self.contributing):
            raise ValueError("contributing_count must equal len(contributing)")
        if self.excluded_count != len(self.excluded):
            raise ValueError("excluded_count must equal len(excluded)")
        if self.contributing_count + self.excluded_count != self.features_examined:
            raise ValueError(
                "every examined parameter must either contribute or be "
                "listed as excluded; a parameter cannot fall between the two"
            )
        if self.sufficient != (self.contributing_count >= self.minimum_required):
            raise ValueError("sufficient must be derived from the two counts")
        return self


class ProgressCounts(BaseModel):

    model_config = ConfigDict(extra="forbid")

    newly_normal: int = 0
    improved: int = 0
    unchanged: int = 0
    worsened: int = 0
    newly_abnormal: int = 0
    significant_changes: int = Field(
        default=0,
        description="Contributing parameters whose measured change cleared "
        "their declared stability band. Counted separately because "
        "significance and better/worse are different questions.",
    )
    by_category: Dict[str, int] = Field(
        default_factory=dict,
        description="Count per category across ALL examined parameters, "
        "contributing and excluded alike.",
    )


class ProgressSummary(BaseModel):

    model_config = ConfigDict(extra="forbid")

    headline: str = ""
    lines: List[str] = Field(default_factory=list)


class HealthProgressData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patient_ref: Optional[str] = None
    policy_version: str = TREND_POLICY_VERSION
    scoring_version: str = PROGRESS_SCORING_VERSION
    analyzer_version: str = ""
    comparator_version: str = ""
    progress_version: str = ""
    generated_at: datetime = Field(default_factory=utcnow)

    reports: List[TimelineReportRef] = Field(
        default_factory=list, description="Every supplied report, oldest first."
    )
    pair: Optional[ComparisonPair] = Field(
        default=None,
        description="Which two reports the score describes. Null ONLY when "
        "fewer than two reports were supplied, in which case `outcome` is "
        "NO_PAIR.",
    )

    outcome: str = Field(
        description="ALWAYS present, and the field to branch on. `score` is "
        "non-null for exactly one value, SCORE_COMPUTED."
    )
    score: Optional[float] = Field(
        default=None,
        description="0-100, higher is better. NULL whenever the outcome is "
        "not SCORE_COMPUTED -- never 50, never 0, and never a band label "
        "standing in for a missing number.",
    )
    band: Optional[ProgressBand] = Field(
        default=None,
        description="The band `score` falls in. Null exactly when `score` is.",
    )
    scale: ProgressScale = Field(
        description="What the number means and which way it points. Returned "
        "even for a refusal, because it describes the instrument."
    )

    coverage: ProgressCoverage
    contributions: List[ParameterContribution] = Field(
        default_factory=list,
        description="Every parameter placed on the scale, in catalogue order.",
    )
    counts: ProgressCounts = Field(default_factory=ProgressCounts)
    summary: ProgressSummary = Field(default_factory=ProgressSummary)

    comparison: Optional[ReportComparisonData] = Field(
        default=None,
        description="The full Module 29 comparison the score was built from. "
        "Present only when options.include_comparison is on.",
    )

    warnings: List[str] = Field(
        default_factory=list,
        description="Warnings about the request as a whole -- Module 30's own "
        "plus the ones Module 29 raised about the same pair.",
    )
    what_this_is: str = ""
    what_this_is_not: str = ""
    disclaimer: str = ""

    @field_validator("outcome")
    @classmethod
    def _known_outcome(cls, v: str) -> str:
        if v not in PROGRESS_OUTCOME_VALUES:
            raise ValueError(f"outcome must be one of {PROGRESS_OUTCOME_VALUES}")
        return v

    @model_validator(mode="after")
    def _score_matches_outcome(self) -> "HealthProgressData":
        if self.outcome == PROGRESS_SCORE_COMPUTED:
            if self.score is None:
                raise ValueError("SCORE_COMPUTED requires a score")
            if self.band is None:
                raise ValueError("SCORE_COMPUTED requires a band")
            if not self.coverage.sufficient:
                raise ValueError(
                    "SCORE_COMPUTED requires coverage.sufficient; a score is "
                    "never emitted below the declared minimum"
                )
        else:
            if self.score is not None:
                raise ValueError(
                    f"outcome {self.outcome} must carry score=None. A refusal "
                    "never carries a number."
                )
            if self.band is not None:
                raise ValueError(
                    f"outcome {self.outcome} must carry band=None. A refusal "
                    "never carries a band label either."
                )
        if self.score is not None and not SCALE_MIN <= self.score <= SCALE_MAX:
            raise ValueError(f"score must lie within {SCALE_MIN}-{SCALE_MAX}")
        return self


class HealthProgressResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    success: bool = True
    data: HealthProgressData


__all__ = [
    "PROGRESS_INSUFFICIENT_COVERAGE",
    "PROGRESS_MODULE",
    "PROGRESS_NOTHING_ASSESSED",
    "PROGRESS_NO_PAIR",
    "PROGRESS_OUTCOME_DESCRIPTIONS",
    "PROGRESS_OUTCOME_VALUES",
    "PROGRESS_SCORE_COMPUTED",
    "STAGE_PROGRESS",
    "ExcludedParameter",
    "HealthProgressData",
    "HealthProgressRequest",
    "HealthProgressResponse",
    "ParameterContribution",
    "ProgressBand",
    "ProgressCounts",
    "ProgressCoverage",
    "ProgressOptions",
    "ProgressScale",
    "ProgressSummary",
]
