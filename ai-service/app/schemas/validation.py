"""The Module 6 (Medical Feature Validation) contract, enforced by pydantic v2.

Module 6 consumes Module 5's `FeatureEngineeringData` and answers one question
per feature: **is this value believable?** It never answers "is this value
healthy?" -- that belongs to Module 8 and the ML layer.

--------------------------------------------------------------------------
THE OUTPUT PARTITION -- read this before consuming the response
--------------------------------------------------------------------------

    valid        Dict[str, ValidatedFeature]
                 THE USABLE FEATURE SET. Take this and go; nothing needs to be
                 re-derived. Every entry carries the same `name/value/unit/
                 canonical_unit/source/provenance` fields as Module 5's
                 `EngineeredFeature`, so an existing Module 5 consumer works
                 unchanged, plus validation metadata.

    questionable Dict[str, ValidatedFeature]
                 A SUBSET VIEW OF `valid`, not a separate partition. These are
                 the entries whose `questionable` flag is true (unit assumed,
                 censored, derived, low extraction confidence, partial
                 document). They ARE usable -- a consumer that ignores this
                 field still behaves correctly -- but a consumer that wants to
                 down-weight shaky inputs can read it directly.

    rejected     Dict[str, RejectedFeature]
                 DISJOINT from `valid`. Not usable. The ORIGINAL value is
                 preserved untouched together with full provenance and a
                 machine-readable `reason_code`, so Module 20 can explain the
                 exclusion. Never repaired, never guessed at.

So: `set(valid) & set(rejected) == set()` and `set(questionable) <= set(valid)`.

--------------------------------------------------------------------------
WHAT IS CARRIED FORWARD UNCHANGED
--------------------------------------------------------------------------

`missing_features`, `unmapped`, `upstream` (including `extraction_confidence`
and `pages_unreadable`) and every upstream warning. Warnings keep their origin:
Module 4's stay `stage="extraction"`, Module 5's stay
`stage="feature_engineering"`, and Module 6 adds `stage="validation"`. They are
never flattened into one undifferentiated list -- the final report (spec
Module 17) has to say which stage raised what.

For the tri-state booleans `hypertension` / `heart_disease`, absence from
`valid`, `questionable` AND `rejected` means UNKNOWN. It never means false.
"""

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

#: The stage identifier Module 6 stamps on its own warnings.
STAGE_VALIDATION = "validation"
VALIDATION_MODULE = 6

#: Extends `app.schemas.features.STAGE_MODULE` without mutating it.
STAGE_MODULE_VALIDATION = {
    STAGE_EXTRACTION: 4,
    STAGE_FEATURE_ENGINEERING: 5,
    STAGE_VALIDATION: VALIDATION_MODULE,
}

STATUS_VALID = "valid"
STATUS_QUESTIONABLE = "questionable"
STATUS_REJECTED = "rejected"


# --------------------------------------------------------------------------
# Request
# --------------------------------------------------------------------------


class IncomingFeature(BaseModel):
    """One feature as received from Module 5.

    DELIBERATELY PERMISSIVE about `value`. Module 5's own `EngineeredFeature`
    pins the value to a strict scalar union, but Module 6 exists precisely to
    catch values that are the wrong type or the wrong shape. Rejecting them at
    the parse boundary with a 422 would turn a per-feature, explainable
    rejection into an opaque whole-request failure, and would lose the other,
    perfectly good, features in the same payload.
    """

    model_config = ConfigDict(extra="ignore")

    name: Optional[str] = None
    value: Any = None
    unit: Optional[str] = None
    canonical_unit: bool = True
    source: Optional[str] = None
    provenance: Optional[FeatureProvenance] = None


class EngineeredFeaturesInput(BaseModel):
    """Module 5's `data` object. Post it verbatim; extra keys are ignored."""

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
    """Accepts Module 5's output under `engineered`, or its whole envelope.

    THE CANONICAL FORM is:

        {"engineered": <Module 5's `data` object>}

    Two other unambiguous forms are also accepted, mirroring exactly what
    `POST /api/v1/features/engineer` does for Module 4's output, so that a
    caller relaying a response verbatim is never silently handed an empty
    result:

      * `{"success": ..., "data": {...}}` -- Module 5's response envelope
        relayed unchanged. `data` is used as the engineered feature set.
      * `{"features": {...}, ...}` -- a bare Module 5 `data` object posted at
        the top level.

    An explicit `engineered` key always wins. A body carrying BOTH `data` and a
    top-level `features` key is REJECTED as ambiguous rather than guessed at.
    """

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
            return value  # Explicit wins.

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


# --------------------------------------------------------------------------
# Response
# --------------------------------------------------------------------------


class ValidationFinding(BaseModel):
    """One machine-readable reason, with a human-readable message.

    Attached to rejections and to flags alike so Module 20 (Explainability)
    can show a user exactly why a value was excluded or down-weighted.
    """

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
    """A usable feature.

    The first six fields are byte-identical in meaning to Module 5's
    `EngineeredFeature`, so a consumer written against Module 5 keeps working.
    `value` is passed through UNCHANGED -- validation never repairs.
    """

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
    """A feature excluded from the usable set.

    Nothing is deleted and nothing is corrected: the original value, unit and
    provenance are all preserved so the exclusion can be explained and, if the
    rule is wrong, challenged.
    """

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
    """The `data` object of a successful validation response."""

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
