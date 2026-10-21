from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.data.feature_catalog import CANONICAL_FEATURES
from app.schemas.features import (
    STAGE_EXTRACTION,
    STAGE_FEATURE_ENGINEERING,
    ConversionRecord,
    DuplicateResolution,
    FeatureEngineeringSummary,
    FeatureProvenance,
    FeatureValue,
    StageWarning,
    UnmappedItem,
    UpstreamExtraction,
)

STAGE_VALIDATION = "validation"
VALIDATION_MODULE = 6

STAGE_MODULE_VALIDATION = {
    STAGE_EXTRACTION: 4,
    STAGE_FEATURE_ENGINEERING: 5,
    STAGE_VALIDATION: VALIDATION_MODULE,
}

STATUS_VALID = "valid"
STATUS_QUESTIONABLE = "questionable"
STATUS_REJECTED = "rejected"


class IncomingFeature(BaseModel):

    model_config = ConfigDict(extra="ignore")

    name: Optional[str] = None
    value: Any = None
    unit: Optional[str] = None
    canonical_unit: bool = True
    source: Optional[str] = None
    provenance: Optional[FeatureProvenance] = None


class EngineeredFeaturesInput(BaseModel):

    model_config = ConfigDict(extra="ignore")

    features: Dict[str, IncomingFeature] = Field(default_factory=dict)
    unmapped: List[UnmappedItem] = Field(default_factory=list)
    conversions_applied: List[ConversionRecord] = Field(default_factory=list)
    duplicates_resolved: List[DuplicateResolution] = Field(default_factory=list)
    missing_features: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    upstream_warnings: List[StageWarning] = Field(default_factory=list)
    all_warnings: List[StageWarning] = Field(default_factory=list)
    upstream: UpstreamExtraction = Field(default_factory=UpstreamExtraction)
    summary: FeatureEngineeringSummary = Field(
        default_factory=FeatureEngineeringSummary
    )

    @field_validator("warnings", mode="before")
    @classmethod
    def _warnings_list(cls, v: object) -> object:
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return v


class FeatureValidationRequest(BaseModel):

    model_config = ConfigDict(extra="ignore")

    engineered: EngineeredFeaturesInput = Field(
        default_factory=EngineeredFeaturesInput
    )

    @model_validator(mode="before")
    @classmethod
    def _unwrap_module_5_envelope(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        if "engineered" in value:
            return value

        envelope = value.get("data")
        has_envelope = isinstance(envelope, dict)
        has_bare = "features" in value

        if has_envelope and has_bare:
            raise ValueError(
                "Ambiguous request: send the engineered features under "
                "'engineered', or relay Module 5's response envelope, but not "
                "both."
            )
        if has_envelope:
            unwrapped = dict(value)
            unwrapped["engineered"] = envelope
            return unwrapped
        if has_bare:
            return {"engineered": value}
        return value


class ValidationFinding(BaseModel):

    model_config = ConfigDict(extra="forbid")

    code: str = Field(description="A RejectionCode or a FlagCode.")
    message: str = Field(description="Human-readable, safe to show a user.")
    severity: str = Field(
        default="warning", description="error (rejects) | warning | info"
    )
    bound: Optional[str] = Field(
        default=None,
        description="Which rule bound was involved: possible_low | "
        "possible_high | extreme_low | extreme_high.",
    )
    limit: Optional[float] = Field(default=None, description="The bound's value.")
    observed: Optional[Union[FeatureValue, None]] = Field(
        default=None, description="The value as received. Never modified."
    )
    basis: Optional[str] = Field(
        default=None, description="Clinical basis of the bound, from the rule table."
    )


class ValidatedFeature(BaseModel):

    model_config = ConfigDict(extra="forbid")

    name: str
    value: FeatureValue
    unit: Optional[str] = None
    canonical_unit: bool = True
    source: str
    provenance: FeatureProvenance

    status: str = Field(
        default=STATUS_VALID, description=f"{STATUS_VALID} | {STATUS_QUESTIONABLE}"
    )
    questionable: bool = Field(
        default=False,
        description="Usable, but its trustworthiness is degraded (assumed "
        "unit, censored, derived, low confidence, partial document).",
    )
    clinically_extreme: bool = Field(
        default=False,
        description="Inside the physiologically possible band but beyond the "
        "critical threshold. STILL FULLY VALID -- a prioritisation signal for "
        "Module 8 and the report, not a data-quality doubt.",
    )
    extreme_direction: Optional[str] = Field(
        default=None, description="'low' | 'high' when clinically_extreme."
    )
    flags: List[ValidationFinding] = Field(default_factory=list)


class RejectedFeature(BaseModel):

    model_config = ConfigDict(extra="forbid")

    name: str
    value: Optional[Any] = Field(
        default=None, description="The ORIGINAL value, exactly as received."
    )
    unit: Optional[str] = None
    canonical_unit: bool = True
    source: Optional[str] = None
    provenance: Optional[FeatureProvenance] = None

    status: str = STATUS_REJECTED
    reason_code: str = Field(description="A RejectionCode. Machine-readable.")
    reason: str = Field(description="Human-readable explanation.")
    findings: List[ValidationFinding] = Field(default_factory=list)


class FeatureValidationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    features_received: int = 0
    valid_count: int = 0
    questionable_count: int = 0
    rejected_count: int = 0
    clinically_extreme_count: int = 0
    missing_count: int = 0
    unmapped_count: int = 0
    validation_warning_count: int = 0
    upstream_warning_count: int = 0
    pages_unreadable_count: int = 0
    extraction_confidence: Optional[float] = None
    partial_document: bool = Field(
        default=False,
        description="True when Module 4 could not read every page. An absent "
        "feature may then be UNREAD rather than ABSENT from the report.",
    )


class FeatureValidationData(BaseModel):

    model_config = ConfigDict(extra="forbid")

    valid: Dict[str, ValidatedFeature] = Field(
        default_factory=dict,
        description="THE USABLE FEATURE SET. Disjoint from `rejected`.",
    )
    questionable: Dict[str, ValidatedFeature] = Field(
        default_factory=dict,
        description="A SUBSET VIEW of `valid` -- usable, but flagged.",
    )
    rejected: Dict[str, RejectedFeature] = Field(
        default_factory=dict,
        description="Not usable. Original values and provenance preserved.",
    )
    clinically_extreme: List[str] = Field(
        default_factory=list,
        description="Names of VALID features beyond a critical threshold.",
    )
    missing_features: List[str] = Field(
        default_factory=list,
        description="Carried forward from Module 5 unchanged. For hypertension "
        "/ heart_disease this means UNKNOWN, not false.",
    )
    unmapped: List[UnmappedItem] = Field(
        default_factory=list, description="Carried forward from Module 5 unchanged."
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="Warnings raised by MODULE 6 ITSELF. Upstream warnings are "
        "NOT merged in here -- see `upstream_warnings` / `all_warnings`.",
    )
    upstream_warnings: List[StageWarning] = Field(
        default_factory=list,
        description="Every warning from Modules 4 and 5, carried forward with "
        "its original stage. Module 6 never edits, filters or drops these.",
    )
    all_warnings: List[StageWarning] = Field(
        default_factory=list,
        description="Every warning from all three stages, upstream first, each "
        "tagged with the stage that raised it. THIS is the list the final "
        "clinical report (spec Module 17) should consume.",
    )
    upstream: UpstreamExtraction = Field(
        default_factory=UpstreamExtraction,
        description="Module 4 context carried forward unchanged: source, "
        "report metadata, extraction confidence, per-page readability.",
    )
    upstream_summary: FeatureEngineeringSummary = Field(
        default_factory=FeatureEngineeringSummary,
        description="Module 5's own summary, preserved verbatim.",
    )
    summary: FeatureValidationSummary = Field(
        default_factory=FeatureValidationSummary
    )

    @model_validator(mode="after")
    def _partition_is_coherent(self) -> "FeatureValidationData":
        for key, feat in self.valid.items():
            if key not in CANONICAL_FEATURES:
                raise ValueError(f"{key!r} is not a canonical feature")
            if feat.name != key:
                raise ValueError(f"feature key {key!r} != feature.name {feat.name!r}")
        overlap = set(self.valid) & set(self.rejected)
        if overlap:
            raise ValueError(f"features in both valid and rejected: {sorted(overlap)}")
        stray = set(self.questionable) - set(self.valid)
        if stray:
            raise ValueError(
                f"questionable must be a subset of valid; stray: {sorted(stray)}"
            )
        return self


class FeatureValidationResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    success: bool = True
    data: FeatureValidationData


__all__ = [
    "STAGE_VALIDATION",
    "STATUS_QUESTIONABLE",
    "STATUS_REJECTED",
    "STATUS_VALID",
    "VALIDATION_MODULE",
    "EngineeredFeaturesInput",
    "FeatureValidationData",
    "FeatureValidationRequest",
    "FeatureValidationResponse",
    "FeatureValidationSummary",
    "IncomingFeature",
    "RejectedFeature",
    "ValidatedFeature",
    "ValidationFinding",
]
