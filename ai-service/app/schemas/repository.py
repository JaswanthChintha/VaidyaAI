"""The Module 7 (Feature Repository) contract, enforced by pydantic v2.

Module 7 is the STORAGE step of the spec's

    Extraction -> Validation -> Storage -> Analysis

separation. It takes Module 6's validated output and turns it into a
`FeatureSnapshot`: one patient's usable feature set as of one report, with the
provenance, warnings and quality context intact, addressable by a stable
identity so that several reports for the same patient can be held side by side
over time (spec Modules 28-30).

--------------------------------------------------------------------------
THE TWO MAPS -- read this before consuming a snapshot
--------------------------------------------------------------------------

    features      Dict[str, StoredFeature]
                  THE USABLE FEATURE SET. Every entry keeps the same
                  `name/value/unit/canonical_unit/source/provenance` fields as
                  Module 5's `EngineeredFeature` and Module 6's
                  `ValidatedFeature`, plus the quality flags. A consumer
                  written against Module 6 keeps working.

    unavailable   Dict[str, UnavailableFeature]
                  WHY a feature has no usable value -- either Module 6
                  REJECTED it, or it was never reported at all. Disjoint from
                  `features`.

                  `UnavailableFeature` HAS NO `value` FIELD. That is the whole
                  point: `app/schemas/rules.py` makes "rules never see a
                  rejected value" structural by not parsing Module 6's
                  `rejected` map, and this schema does the same one level
                  deeper -- the repository DOES record that a rejection
                  happened and why, but there is no attribute anywhere on the
                  record that a caller could read as a feature value. The
                  rejected value is DISCARDED at the parse boundary
                  (`IncomingRejection` below is `extra="ignore"` and declares
                  no `value`).

                  `provenance` IS kept, because Module 20 (Explainability) has
                  to be able to say which printed report line was refused and
                  why. `provenance.original_value_raw` is therefore still the
                  text as printed -- but it is explanation metadata reached
                  through `provenance`, and no value accessor on
                  `FeatureRepository` can ever return it.

So: `set(features) & set(unavailable) == set()`.

--------------------------------------------------------------------------
ABSENCE
--------------------------------------------------------------------------

A feature with no usable value is ABSENT from `features`. It is never present
with a default, never `false`, never `0`. For the tri-state booleans
`hypertension` / `heart_disease`, absence means UNKNOWN. The read side of that
guarantee lives in `app/services/feature_repository.py`, whose accessors
refuse to hand a caller anything that could be mistaken for a value.

--------------------------------------------------------------------------
WHAT IS CARRIED FORWARD UNCHANGED
--------------------------------------------------------------------------

`missing_features`, `upstream` (including `extraction_confidence` and
`pages_unreadable`), and every warning with its origin. Module 4's stay
`stage="extraction"`, Module 5's `stage="feature_engineering"`, Module 6's
`stage="validation"`, and Module 7 adds `stage="repository"`. Silently dropping
upstream warnings has been a real defect on this project twice; `all_warnings`
is the list the final report (spec Module 17) consumes.
"""

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

#: The stage identifier Module 7 stamps on its own warnings.
STAGE_REPOSITORY = "repository"
REPOSITORY_MODULE = 7

#: Extends `app.schemas.validation.STAGE_MODULE_VALIDATION` without mutating it.
STAGE_MODULE_REPOSITORY = {
    STAGE_EXTRACTION: 4,
    STAGE_FEATURE_ENGINEERING: 5,
    STAGE_VALIDATION: 6,
    STAGE_REPOSITORY: REPOSITORY_MODULE,
}

#: `unavailable[name].availability` -- why there is no usable value.
AVAILABILITY_REJECTED = "rejected"
AVAILABILITY_NOT_REPORTED = "not_reported"
AVAILABILITY_UNUSABLE = "unusable"

AVAILABILITY_KINDS = (
    AVAILABILITY_REJECTED,
    AVAILABILITY_NOT_REPORTED,
    AVAILABILITY_UNUSABLE,
)

#: Reason codes Module 7 assigns itself (rejections keep Module 6's code).
REASON_NOT_REPORTED = "NOT_REPORTED"
REASON_NOT_REPORTED_PARTIAL_DOCUMENT = "NOT_REPORTED_PARTIAL_DOCUMENT"
REASON_NOT_CANONICAL = "NOT_A_CANONICAL_FEATURE"
REASON_UNUSABLE_VALUE = "UNUSABLE_VALUE"


def utcnow() -> datetime:
    """Timezone-aware UTC now. Never naive -- snapshots are ordered by time."""
    return datetime.now(timezone.utc)


def new_snapshot_id() -> str:
    return uuid.uuid4().hex


# --------------------------------------------------------------------------
# Input -- Module 6's `data` object, as the repository is willing to parse it
# --------------------------------------------------------------------------


class IncomingStoredFeature(BaseModel):
    """One entry of Module 6's `valid` map.

    Permissive about `value` for the same reason Module 6 and Module 8 are:
    one odd entry must not turn into an opaque 422 that discards every other
    perfectly good feature in the payload.
    """

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
    """One entry of Module 6's `rejected` map, MINUS `value`.

    `extra="ignore"` plus the deliberate absence of a `value` field means the
    rejected value is dropped AT PARSE TIME. There is no later step that could
    forget to drop it, and no attribute a future edit could accidentally read.
    """

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
    """Module 6's `data` object as the repository reads it.

    Unlike `app.schemas.rules.ValidatedFeaturesInput` this DOES parse
    `rejected` -- the repository is the component that has to be able to answer
    "why can I not have creatinine?". It parses it into a shape with no value
    (see `IncomingRejection`), so recording the rejection cannot make the
    rejected number readable.
    """

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


# --------------------------------------------------------------------------
# Stored records
# --------------------------------------------------------------------------


class StoredFeature(BaseModel):
    """A USABLE feature. Every field is passed through unchanged.

    The repository never repairs, rescales, rounds or re-derives a value; it is
    a storage and access layer, not a second feature engineer.
    """

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
    """WHY a feature has no usable value. HAS NO `value` FIELD, deliberately.

    See the module docstring. This record exists so a caller can ask
    "why is creatinine not here?" and be told, without any path by which the
    refused number could be read back as though it were usable.
    """

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
    """A snapshot's stable identity and its position in time.

    `report_date` is the ORDERING KEY, aligned conceptually with the
    `Report.chronoDate` the Node backend already carries. When it is absent,
    `recorded_at` (when the snapshot entered the repository) orders instead, so
    a set of snapshots is always totally ordered.

    `patient_ref` and `report_ref` are OPAQUE identifiers supplied by the
    caller (the backend's Mongo ids). They are not names, not dates of birth,
    and nothing here should ever be treated as a display value.
    """

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
        """Naive datetimes are read as UTC.

        Snapshots are sorted against each other; a mix of naive and aware
        datetimes would raise at comparison time, which is a runtime failure in
        the middle of a trend query rather than at the point of the mistake.
        """
        if v is None:
            return None
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc)

    @property
    def ordering_key(self) -> datetime:
        """`report_date` when known, else `recorded_at`. Always tz-aware."""
        return self.report_date or self.recorded_at


class SnapshotSummary(BaseModel):
    """Shape only. No values, no identifiers -- safe to log or expose."""

    model_config = ConfigDict(extra="forbid")

    feature_count: int = 0
    lab_feature_count: int = 0
    profile_feature_count: int = 0
    #: Sex / age taken from the report's printed patient details.
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
    """One patient's validated feature set as of one report.

    This is what a storage backend persists and what `FeatureRepository` reads.
    It is fully JSON round-trippable, so a future persistent backend can store
    `model_dump(mode="json")` and rebuild with `model_validate` -- no consumer
    changes.
    """

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


# --------------------------------------------------------------------------
# HTTP request / response
# --------------------------------------------------------------------------


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
    """Load one validated feature set into the repository.

    THE CANONICAL FORM is Module 6's output plus the snapshot's identity:

        {"validated": <Module 6's `data`>, "patient_ref": "...",
         "report_ref": "...", "report_date": "2024-03-12"}

    For the same reason `routes_rules.py` is tolerant -- a caller relaying a
    response verbatim must never be silently handed an empty result -- these
    are also accepted, and classified exactly the same way:

      * `{"engineered": <Module 5's `data`>}` -- validated in-process first, so
        the repository still only ever stores validated values.
      * `{"success": ..., "data": {...}}` -- either module's response envelope.
      * a BARE `data` object posted at the top level.

    Anything ambiguous is a 422. Nothing is guessed. An explicit `validated`
    beats an explicit `engineered`, because validated input is strictly better
    information.
    """

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
            return value  # Explicit wins; `validated` beats `engineered` later.

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
    """A snapshot's identity plus its shape. No feature values.

    What a listing returns: enough for Modules 28-30 to decide which snapshots
    to fetch, without shipping every patient value in a list response.
    """

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
    """The answer to "what do you have for X?" -- for one feature.

    `available` is the question a caller must branch on. When it is false there
    is NO `value` key in the JSON at all (not `null`, not `0`, not `false`):
    `reason_code` and `reason` say why instead.
    """

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
