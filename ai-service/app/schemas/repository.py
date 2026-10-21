from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.data.feature_catalog import CANONICAL_FEATURES
from app.schemas.features import (
    STAGE_EXTRACTION,
    STAGE_FEATURE_ENGINEERING,
    FeatureProvenance,
    FeatureValue,
    StageWarning,
    UpstreamExtraction,
)
from app.schemas.validation import (
    STAGE_VALIDATION,
    STATUS_VALID,
    EngineeredFeaturesInput,
    FeatureValidationSummary,
    ValidationFinding,
)

STAGE_REPOSITORY = "repository"
REPOSITORY_MODULE = 7

STAGE_MODULE_REPOSITORY = {
    STAGE_EXTRACTION: 4,
    STAGE_FEATURE_ENGINEERING: 5,
    STAGE_VALIDATION: 6,
    STAGE_REPOSITORY: REPOSITORY_MODULE,
}

AVAILABILITY_REJECTED = "rejected"
AVAILABILITY_NOT_REPORTED = "not_reported"
AVAILABILITY_UNUSABLE = "unusable"

AVAILABILITY_KINDS = (
    AVAILABILITY_REJECTED,
    AVAILABILITY_NOT_REPORTED,
    AVAILABILITY_UNUSABLE,
)

REASON_NOT_REPORTED = "NOT_REPORTED"
REASON_NOT_REPORTED_PARTIAL_DOCUMENT = "NOT_REPORTED_PARTIAL_DOCUMENT"
REASON_NOT_CANONICAL = "NOT_A_CANONICAL_FEATURE"
REASON_UNUSABLE_VALUE = "UNUSABLE_VALUE"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_snapshot_id() -> str:
    return uuid.uuid4().hex


class IncomingStoredFeature(BaseModel):

    model_config = ConfigDict(extra="ignore")

    name: Optional[str] = None
    value: Any = None
    unit: Optional[str] = None
    canonical_unit: bool = True
    source: Optional[str] = None
    provenance: Optional[FeatureProvenance] = None
    status: str = STATUS_VALID
    questionable: bool = False
    clinically_extreme: bool = False
    extreme_direction: Optional[str] = None
    flags: List[ValidationFinding] = Field(default_factory=list)


class IncomingRejection(BaseModel):

    model_config = ConfigDict(extra="ignore")

    name: Optional[str] = None
    unit: Optional[str] = None
    canonical_unit: bool = True
    source: Optional[str] = None
    provenance: Optional[FeatureProvenance] = None
    reason_code: str = "REJECTED"
    reason: str = "Rejected by the validation engine."
    findings: List[ValidationFinding] = Field(default_factory=list)


class ValidatedFeatureSetInput(BaseModel):

    model_config = ConfigDict(extra="ignore")

    valid: Dict[str, IncomingStoredFeature] = Field(default_factory=dict)
    questionable: Dict[str, IncomingStoredFeature] = Field(default_factory=dict)
    rejected: Dict[str, IncomingRejection] = Field(default_factory=dict)
    clinically_extreme: List[str] = Field(default_factory=list)
    missing_features: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    upstream_warnings: List[StageWarning] = Field(default_factory=list)
    all_warnings: List[StageWarning] = Field(default_factory=list)
    upstream: UpstreamExtraction = Field(default_factory=UpstreamExtraction)
    summary: FeatureValidationSummary = Field(
        default_factory=FeatureValidationSummary
    )

    @field_validator("warnings", mode="before")
    @classmethod
    def _warnings_list(cls, v: object) -> object:
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return v


class StoredFeature(BaseModel):

    model_config = ConfigDict(extra="forbid")

    name: str
    value: FeatureValue
    unit: Optional[str] = None
    canonical_unit: bool = True
    source: str = Field(description="lab_report | patient_profile")
    provenance: FeatureProvenance

    status: str = STATUS_VALID
    questionable: bool = False
    clinically_extreme: bool = False
    extreme_direction: Optional[str] = None
    flags: List[ValidationFinding] = Field(default_factory=list)


class UnavailableFeature(BaseModel):

    model_config = ConfigDict(extra="forbid")

    name: str
    availability: str = Field(
        description=f"{AVAILABILITY_REJECTED} (Module 6 refused it) | "
        f"{AVAILABILITY_NOT_REPORTED} (never present) | "
        f"{AVAILABILITY_UNUSABLE} (present but not storable as a value)"
    )

    @field_validator("availability")
    @classmethod
    def _known_kind(cls, v: str) -> str:
        if v not in AVAILABILITY_KINDS:
            raise ValueError(f"availability must be one of {AVAILABILITY_KINDS}")
        return v
    reason_code: str = Field(description="Module 6's RejectionCode, or Module 7's.")
    reason: str = Field(description="Human-readable, safe to show a user.")
    source: Optional[str] = None
    provenance: Optional[FeatureProvenance] = Field(
        default=None,
        description="Kept for Module 20 so a refusal can be explained against "
        "the printed report line. Explanation metadata, never a value.",
    )
    findings: List[ValidationFinding] = Field(default_factory=list)


class SnapshotIdentity(BaseModel):

    model_config = ConfigDict(extra="forbid")

    snapshot_id: str = Field(default_factory=new_snapshot_id)
    patient_ref: Optional[str] = Field(
        default=None, description="Opaque patient identifier. Never a name."
    )
    report_ref: Optional[str] = Field(
        default=None, description="Opaque report identifier."
    )
    report_date: Optional[datetime] = Field(
        default=None,
        description="When the report was produced. The longitudinal ordering "
        "key (cf. the backend's Report.chronoDate).",
    )
    recorded_at: datetime = Field(
        default_factory=utcnow, description="When this snapshot was stored."
    )
    sequence: int = Field(
        default=0,
        ge=0,
        description="Monotonic per-backend insertion counter. Breaks ties "
        "between snapshots that share an ordering timestamp so the order is "
        "total and stable.",
    )

    @field_validator("report_date", "recorded_at")
    @classmethod
    def _tz_aware(cls, v: Optional[datetime]) -> Optional[datetime]:
        if v is None:
            return None
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc)

    @property
    def ordering_key(self) -> datetime:
        return self.report_date or self.recorded_at


class SnapshotSummary(BaseModel):

    model_config = ConfigDict(extra="forbid")

    feature_count: int = 0
    lab_feature_count: int = 0
    profile_feature_count: int = 0
    report_details_feature_count: int = 0
    questionable_count: int = 0
    clinically_extreme_count: int = 0
    rejected_count: int = 0
    not_reported_count: int = 0
    missing_count: int = 0
    warning_count: int = 0
    upstream_warning_count: int = 0
    pages_unreadable_count: int = 0
    extraction_confidence: Optional[float] = None
    partial_document: bool = Field(
        default=False,
        description="Module 4 could not read every page. An absent feature may "
        "then be UNREAD rather than absent from the report.",
    )


class FeatureSnapshot(BaseModel):

    model_config = ConfigDict(extra="forbid")

    identity: SnapshotIdentity = Field(default_factory=SnapshotIdentity)
    features: Dict[str, StoredFeature] = Field(
        default_factory=dict, description="THE USABLE FEATURE SET."
    )
    unavailable: Dict[str, UnavailableFeature] = Field(
        default_factory=dict,
        description="Why a feature has no usable value. No values here.",
    )
    missing_features: List[str] = Field(
        default_factory=list,
        description="Carried forward unchanged. For hypertension / "
        "heart_disease this means UNKNOWN, not false.",
    )
    warnings: List[str] = Field(
        default_factory=list, description="Warnings raised by MODULE 7 ITSELF."
    )
    upstream_warnings: List[StageWarning] = Field(
        default_factory=list,
        description="Every warning from Modules 4, 5 and 6, origins intact. "
        "Module 7 never edits, filters or drops these.",
    )
    all_warnings: List[StageWarning] = Field(
        default_factory=list,
        description="Every warning from every stage, upstream first. THIS is "
        "the list the final clinical report (spec Module 17) consumes.",
    )
    upstream: UpstreamExtraction = Field(
        default_factory=UpstreamExtraction,
        description="Module 4 context carried forward unchanged.",
    )
    upstream_summary: FeatureValidationSummary = Field(
        default_factory=FeatureValidationSummary,
        description="Module 6's own summary, preserved verbatim.",
    )
    summary: SnapshotSummary = Field(default_factory=SnapshotSummary)

    @model_validator(mode="after")
    def _maps_are_coherent(self) -> "FeatureSnapshot":
        for key, feature in self.features.items():
            if key not in CANONICAL_FEATURES:
                raise ValueError(f"{key!r} is not a canonical feature")
            if feature.name != key:
                raise ValueError(
                    f"feature key {key!r} != feature.name {feature.name!r}"
                )
        for key, entry in self.unavailable.items():
            if entry.name != key:
                raise ValueError(
                    f"unavailable key {key!r} != entry.name {entry.name!r}"
                )
        overlap = set(self.features) & set(self.unavailable)
        if overlap:
            raise ValueError(
                f"features in both features and unavailable: {sorted(overlap)}"
            )
        return self


AMBIGUOUS_REQUEST_MESSAGE = (
    "Ambiguous request: send Module 6's validated features under 'validated' "
    "(or Module 5's engineered features under 'engineered'), or relay exactly "
    "one response envelope -- but not several at once."
)

AMBIGUOUS_OBJECT_MESSAGE = (
    "Ambiguous request: the posted object carries both 'valid' (Module 6) and "
    "'features' (Module 5). Send one or the other, or name it explicitly with "
    "'validated' / 'engineered'."
)


class RepositoryLoadRequest(BaseModel):

    model_config = ConfigDict(extra="ignore")

    validated: Optional[ValidatedFeatureSetInput] = None
    engineered: Optional[EngineeredFeaturesInput] = None
    patient_ref: Optional[str] = Field(
        default=None, max_length=128, description="Opaque id. Never a name."
    )
    report_ref: Optional[str] = Field(default=None, max_length=128)
    report_date: Optional[datetime] = None
    snapshot_id: Optional[str] = Field(
        default=None,
        max_length=128,
        description="Supply to overwrite an existing snapshot; omitted means a "
        "new one is created.",
    )

    @model_validator(mode="before")
    @classmethod
    def _unwrap(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        if "validated" in value or "engineered" in value:
            return value

        envelope = value.get("data")
        has_envelope = isinstance(envelope, dict)
        bare_validated = "valid" in value
        bare_engineered = "features" in value

        if has_envelope and (bare_validated or bare_engineered):
            raise ValueError(AMBIGUOUS_REQUEST_MESSAGE)
        if bare_validated and bare_engineered:
            raise ValueError(AMBIGUOUS_OBJECT_MESSAGE)

        unwrapped = dict(value)
        if has_envelope:
            inner_validated = "valid" in envelope
            inner_engineered = "features" in envelope
            if inner_validated and inner_engineered:
                raise ValueError(AMBIGUOUS_OBJECT_MESSAGE)
            if inner_validated:
                unwrapped["validated"] = envelope
            elif inner_engineered:
                unwrapped["engineered"] = envelope
            return unwrapped
        if bare_validated:
            unwrapped["validated"] = value
            return unwrapped
        if bare_engineered:
            unwrapped["engineered"] = value
            return unwrapped
        return value


class SnapshotReference(BaseModel):

    model_config = ConfigDict(extra="forbid")

    identity: SnapshotIdentity
    summary: SnapshotSummary
    available: List[str] = Field(default_factory=list)
    unavailable: List[str] = Field(default_factory=list)


class RepositorySnapshotResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    success: bool = True
    data: FeatureSnapshot


class RepositorySnapshotListData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patient_ref: Optional[str] = None
    count: int = 0
    snapshots: List[SnapshotReference] = Field(
        default_factory=list,
        description="Chronological, oldest first, by the identity's "
        "ordering key.",
    )


class RepositorySnapshotListResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    success: bool = True
    data: RepositorySnapshotListData


class FeatureReadData(BaseModel):

    model_config = ConfigDict(extra="forbid")

    name: str
    available: bool
    feature: Optional[StoredFeature] = None
    unavailable: Optional[UnavailableFeature] = None


class FeatureReadResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    success: bool = True
    data: FeatureReadData


__all__ = [
    "AVAILABILITY_KINDS",
    "AVAILABILITY_NOT_REPORTED",
    "AVAILABILITY_REJECTED",
    "AVAILABILITY_UNUSABLE",
    "REASON_NOT_CANONICAL",
    "REASON_UNUSABLE_VALUE",
    "REASON_NOT_REPORTED",
    "REASON_NOT_REPORTED_PARTIAL_DOCUMENT",
    "REPOSITORY_MODULE",
    "STAGE_MODULE_REPOSITORY",
    "STAGE_REPOSITORY",
    "FeatureReadData",
    "FeatureReadResponse",
    "FeatureSnapshot",
    "IncomingRejection",
    "IncomingStoredFeature",
    "RepositoryLoadRequest",
    "RepositorySnapshotListData",
    "RepositorySnapshotListResponse",
    "RepositorySnapshotResponse",
    "SnapshotIdentity",
    "SnapshotReference",
    "SnapshotSummary",
    "StoredFeature",
    "UnavailableFeature",
    "ValidatedFeatureSetInput",
    "new_snapshot_id",
    "utcnow",
]
