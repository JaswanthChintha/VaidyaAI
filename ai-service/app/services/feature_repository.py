from __future__ import annotations

import threading
from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional, Tuple, Union

from app.core.logging import get_logger, safe_meta
from app.data.feature_catalog import (
    CANONICAL_FEATURES,
    FEATURES,
    SOURCE_LAB_REPORT,
    SOURCE_PATIENT_PROFILE,
    SOURCE_REPORT_DETAILS,
)
from app.schemas.features import (
    FeatureProvenance,
    FeatureValue,
    StageWarning,
    UpstreamExtraction,
)
from app.schemas.repository import (
    AVAILABILITY_NOT_REPORTED,
    AVAILABILITY_REJECTED,
    AVAILABILITY_UNUSABLE,
    REASON_NOT_REPORTED,
    REASON_NOT_REPORTED_PARTIAL_DOCUMENT,
    REASON_UNUSABLE_VALUE,
    REPOSITORY_MODULE,
    STAGE_REPOSITORY,
    FeatureSnapshot,
    SnapshotIdentity,
    SnapshotReference,
    SnapshotSummary,
    StoredFeature,
    UnavailableFeature,
    ValidatedFeatureSetInput,
)
from app.schemas.validation import STAGE_VALIDATION, STATUS_QUESTIONABLE, STATUS_VALID
from app.services.repository_backend import (
    InMemoryRepositoryBackend,
    RepositoryBackend,
)
from app.services.validator import validate_features

logger = get_logger(__name__)

REPOSITORY_POLICY = (
    "The Feature Repository stores only what Module 6 accepted. It never "
    "repairs, converts, derives or defaults a value; a feature with no usable "
    "value is ABSENT, never false, zero or normal; a rejected feature is kept "
    "as a reason with no value field, so it cannot be read as one; provenance "
    "and every upstream warning are carried through intact."
)

REPOSITORY_VERSION = "1.0.0"


class RepositoryError(Exception):
    pass


class UnknownFeatureError(RepositoryError, KeyError):
    pass


class FeatureUnavailableError(RepositoryError, LookupError):

    def __init__(
        self, name: str, reason: Optional[UnavailableFeature] = None
    ) -> None:
        self.name = name
        self.detail = reason
        self.reason_code = reason.reason_code if reason else REASON_NOT_REPORTED
        super().__init__(
            f"feature {name!r} has no usable value in this snapshot "
            f"({self.reason_code})"
        )


class FeatureTypeError(RepositoryError, TypeError):
    pass


class AbsentValueError(RepositoryError, TypeError):
    pass


class _AbsentType:

    __slots__ = ()
    _instance: Optional["_AbsentType"] = None

    def __new__(cls) -> "_AbsentType":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "ABSENT"

    def __str__(self) -> str:
        return "ABSENT"

    def _refuse(self, what: str) -> "AbsentValueError":
        return AbsentValueError(
            f"ABSENT cannot be used as {what}. The repository has no usable "
            "value for this feature; absent is not false, not zero and not "
            "normal. Branch on repository.has(name), or call require(name)."
        )

    def __bool__(self) -> bool:
        raise self._refuse("a boolean")

    def __float__(self) -> float:
        raise self._refuse("a number")

    def __int__(self) -> int:
        raise self._refuse("a number")

    def __index__(self) -> int:
        raise self._refuse("an index")

    def __len__(self) -> int:
        raise self._refuse("a sequence")

    def __iter__(self) -> Iterator[Any]:
        raise self._refuse("an iterable")

    def __add__(self, other: Any) -> Any:
        raise self._refuse("an operand")

    __radd__ = __add__
    __sub__ = __add__
    __rsub__ = __add__
    __mul__ = __add__
    __rmul__ = __add__
    __truediv__ = __add__
    __rtruediv__ = __add__

    def __lt__(self, other: Any) -> bool:
        raise self._refuse("a comparand")

    __le__ = __lt__
    __gt__ = __lt__
    __ge__ = __lt__

    def __eq__(self, other: Any) -> bool:
        return other is self

    def __ne__(self, other: Any) -> bool:
        return other is not self

    def __hash__(self) -> int:
        return hash("__vaidyaai_absent__")

    def __reduce__(self) -> str:
        return "ABSENT"

    def __copy__(self) -> "_AbsentType":
        return self

    def __deepcopy__(self, _memo: Any) -> "_AbsentType":
        return self


ABSENT = _AbsentType()


def is_absent(value: Any) -> bool:
    return value is ABSENT


def _coerce_validated(source: Any) -> Optional[ValidatedFeatureSetInput]:
    if source is None:
        return None
    if isinstance(source, ValidatedFeatureSetInput):
        return source
    if hasattr(source, "model_dump"):
        return ValidatedFeatureSetInput.model_validate(source.model_dump())
    return ValidatedFeatureSetInput.model_validate(source)


def _carried_warnings(data: ValidatedFeatureSetInput) -> List[StageWarning]:
    if data.all_warnings:
        return list(data.all_warnings)
    rebuilt: List[StageWarning] = list(data.upstream_warnings)
    seen = {(w.stage, w.message) for w in rebuilt}
    for message in data.warnings:
        key = (STAGE_VALIDATION, message)
        if key not in seen:
            seen.add(key)
            rebuilt.append(
                StageWarning(stage=STAGE_VALIDATION, module=6, message=message)
            )
    return rebuilt


def _default_provenance(name: str, source: Optional[str]) -> FeatureProvenance:
    definition = FEATURES.get(name)
    fallback = definition.source if definition else SOURCE_LAB_REPORT
    return FeatureProvenance(source=source or fallback)


def build_snapshot(
    validated: Any = None,
    *,
    engineered: Any = None,
    patient_ref: Optional[str] = None,
    report_ref: Optional[str] = None,
    report_date: Optional[Union[datetime, str]] = None,
    snapshot_id: Optional[str] = None,
    recorded_at: Optional[datetime] = None,
) -> FeatureSnapshot:
    data = _coerce_validated(validated)
    if data is None and engineered is not None:
        data = _coerce_validated(validate_features(engineered))
    if data is None:
        data = ValidatedFeatureSetInput()

    partial_document = bool(data.upstream.pages_unreadable)

    features: Dict[str, StoredFeature] = {}
    unavailable: Dict[str, UnavailableFeature] = {}
    own_warnings: List[str] = []

    for name, incoming in data.valid.items():
        if name not in CANONICAL_FEATURES:
            own_warnings.append(
                f"'{name}' is not a canonical feature and was not stored in the "
                "feature repository"
            )
            continue
        try:
            features[name] = StoredFeature(
                name=name,
                value=incoming.value,
                unit=incoming.unit,
                canonical_unit=incoming.canonical_unit,
                source=incoming.source or _default_provenance(name, None).source,
                provenance=incoming.provenance
                or _default_provenance(name, incoming.source),
                status=(
                    STATUS_QUESTIONABLE if incoming.questionable else STATUS_VALID
                ),
                questionable=incoming.questionable,
                clinically_extreme=incoming.clinically_extreme,
                extreme_direction=incoming.extreme_direction,
                flags=list(incoming.flags),
            )
        except Exception:
            own_warnings.append(
                f"'{name}' arrived in the validated set with a value the "
                "repository cannot store; it is recorded as unavailable"
            )
            unavailable[name] = UnavailableFeature(
                name=name,
                availability=AVAILABILITY_UNUSABLE,
                reason_code=REASON_UNUSABLE_VALUE,
                reason=(
                    "The validated value was not a storable scalar, so no "
                    "usable value is held for this feature."
                ),
                source=incoming.source,
                provenance=incoming.provenance,
            )

    for name, rejection in data.rejected.items():
        if name in features:
            own_warnings.append(
                f"'{name}' appeared in both the valid and rejected sets; it is "
                "treated as unavailable"
            )
            features.pop(name, None)
        unavailable[name] = UnavailableFeature(
            name=name,
            availability=AVAILABILITY_REJECTED,
            reason_code=rejection.reason_code,
            reason=rejection.reason,
            source=rejection.source,
            provenance=rejection.provenance,
            findings=list(rejection.findings),
        )

    not_reported_reason = (
        REASON_NOT_REPORTED_PARTIAL_DOCUMENT if partial_document
        else REASON_NOT_REPORTED
    )
    not_reported_text = (
        "This feature was not present in the validated feature set, and the "
        "source document had unreadable pages -- it may have been UNREAD "
        "rather than absent."
        if partial_document
        else "This feature was not present in the validated feature set."
    )
    for name in CANONICAL_FEATURES:
        if name in features or name in unavailable:
            continue
        unavailable[name] = UnavailableFeature(
            name=name,
            availability=AVAILABILITY_NOT_REPORTED,
            reason_code=not_reported_reason,
            reason=not_reported_text,
            source=FEATURES[name].source,
        )

    upstream_warnings = _carried_warnings(data)
    all_warnings = list(upstream_warnings) + [
        StageWarning(
            stage=STAGE_REPOSITORY, module=REPOSITORY_MODULE, message=message
        )
        for message in own_warnings
    ]

    summary = SnapshotSummary(
        feature_count=len(features),
        lab_feature_count=sum(
            1 for f in features.values() if f.source == SOURCE_LAB_REPORT
        ),
        profile_feature_count=sum(
            1 for f in features.values() if f.source == SOURCE_PATIENT_PROFILE
        ),
        report_details_feature_count=sum(
            1 for f in features.values() if f.source == SOURCE_REPORT_DETAILS
        ),
        questionable_count=sum(1 for f in features.values() if f.questionable),
        clinically_extreme_count=sum(
            1 for f in features.values() if f.clinically_extreme
        ),
        rejected_count=sum(
            1
            for u in unavailable.values()
            if u.availability == AVAILABILITY_REJECTED
        ),
        not_reported_count=sum(
            1
            for u in unavailable.values()
            if u.availability == AVAILABILITY_NOT_REPORTED
        ),
        missing_count=len(CANONICAL_FEATURES) - len(features),
        warning_count=len(all_warnings),
        upstream_warning_count=len(upstream_warnings),
        pages_unreadable_count=len(data.upstream.pages_unreadable),
        extraction_confidence=data.upstream.extraction_confidence,
        partial_document=partial_document,
    )

    identity_fields: Dict[str, Any] = {
        "patient_ref": patient_ref,
        "report_ref": report_ref,
        "report_date": report_date,
    }
    if snapshot_id is not None:
        identity_fields["snapshot_id"] = snapshot_id
    if recorded_at is not None:
        identity_fields["recorded_at"] = recorded_at

    return FeatureSnapshot(
        identity=SnapshotIdentity(**identity_fields),
        features=features,
        unavailable=unavailable,
        missing_features=list(data.missing_features),
        warnings=own_warnings,
        upstream_warnings=upstream_warnings,
        all_warnings=all_warnings,
        upstream=data.upstream,
        upstream_summary=data.summary,
        summary=summary,
    )


class FeatureRepository:

    __slots__ = ("_snapshot",)

    def __init__(self, snapshot: FeatureSnapshot) -> None:
        self._snapshot = snapshot


    @classmethod
    def from_validated(cls, validated: Any = None, **kwargs: Any) -> "FeatureRepository":
        return cls(build_snapshot(validated, **kwargs))

    @classmethod
    def empty(cls) -> "FeatureRepository":
        return cls(build_snapshot())


    @property
    def snapshot(self) -> FeatureSnapshot:
        return self._snapshot

    @property
    def identity(self) -> SnapshotIdentity:
        return self._snapshot.identity

    @property
    def snapshot_id(self) -> str:
        return self._snapshot.identity.snapshot_id

    @property
    def patient_ref(self) -> Optional[str]:
        return self._snapshot.identity.patient_ref

    @property
    def report_ref(self) -> Optional[str]:
        return self._snapshot.identity.report_ref

    @property
    def report_date(self) -> Optional[datetime]:
        return self._snapshot.identity.report_date

    @property
    def ordering_key(self) -> datetime:
        return self._snapshot.identity.ordering_key


    @staticmethod
    def _check_name(name: str) -> str:
        if name not in CANONICAL_FEATURES:
            raise UnknownFeatureError(
                f"{name!r} is not a canonical feature. Known features: "
                f"{', '.join(CANONICAL_FEATURES)}"
            )
        return name


    def has(self, name: str) -> bool:
        return self._check_name(name) in self._snapshot.features

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name in self._snapshot.features

    def __len__(self) -> int:
        return len(self._snapshot.features)

    def __iter__(self) -> Iterator[str]:
        return iter(self.available())

    def __repr__(self) -> str:
        return (
            f"<FeatureRepository features={len(self._snapshot.features)} "
            f"unavailable={len(self._snapshot.unavailable)}>"
        )


    def get(self, name: str, default: Any = ABSENT) -> Any:
        self._check_name(name)
        found = self._snapshot.features.get(name)
        return default if found is None else found.value

    def require(self, name: str) -> FeatureValue:
        self._check_name(name)
        found = self._snapshot.features.get(name)
        if found is None:
            raise FeatureUnavailableError(name, self.why_unavailable(name))
        return found.value

    def get_or_none(self, name: str) -> Optional[FeatureValue]:
        return self.get(name, default=None)

    def tristate(self, name: str) -> Optional[bool]:
        self._check_name(name)
        if FEATURES[name].value_type != "boolean":
            raise FeatureTypeError(
                f"{name!r} is not a tri-state boolean feature "
                f"(it is {FEATURES[name].value_type!r})"
            )
        found = self._snapshot.features.get(name)
        if found is None:
            return None
        if not isinstance(found.value, bool):
            raise FeatureTypeError(
                f"{name!r} is stored with a non-boolean value; the repository "
                "will not coerce it"
            )
        return found.value

    def numeric(self, name: str, default: Any = ABSENT) -> Any:
        self._check_name(name)
        found = self._snapshot.features.get(name)
        if found is None:
            return default
        if isinstance(found.value, bool) or not isinstance(found.value, (int, float)):
            raise FeatureTypeError(
                f"{name!r} does not hold a number; the repository will not "
                "coerce it"
            )
        if not found.canonical_unit:
            raise FeatureTypeError(
                f"{name!r} is not in its canonical unit, so its magnitude "
                "cannot be used numerically"
            )
        return float(found.value)

    def values(self) -> Dict[str, FeatureValue]:
        return {name: f.value for name, f in self._snapshot.features.items()}


    def feature(self, name: str, default: Any = ABSENT) -> Any:
        self._check_name(name)
        found = self._snapshot.features.get(name)
        return default if found is None else found

    def require_feature(self, name: str) -> StoredFeature:
        found = self.feature(name, default=None)
        if found is None:
            raise FeatureUnavailableError(name, self.why_unavailable(name))
        return found

    def unit(self, name: str, default: Any = ABSENT) -> Any:
        self._check_name(name)
        found = self._snapshot.features.get(name)
        return default if found is None else found.unit

    def canonical_unit(self, name: str) -> bool:
        return self.require_feature(name).canonical_unit

    def source(self, name: str, default: Any = ABSENT) -> Any:
        self._check_name(name)
        found = self._snapshot.features.get(name)
        return default if found is None else found.source

    def provenance(self, name: str, default: Any = ABSENT) -> Any:
        self._check_name(name)
        found = self._snapshot.features.get(name)
        return default if found is None else found.provenance

    def require_provenance(self, name: str) -> FeatureProvenance:
        return self.require_feature(name).provenance

    def is_questionable(self, name: str) -> bool:
        found = self.feature(name, default=None)
        return bool(found is not None and found.questionable)

    def is_clinically_extreme(self, name: str) -> bool:
        found = self.feature(name, default=None)
        return bool(found is not None and found.clinically_extreme)


    def available(self) -> Tuple[str, ...]:
        held = self._snapshot.features
        return tuple(name for name in CANONICAL_FEATURES if name in held)

    def missing(self) -> Tuple[str, ...]:
        held = self._snapshot.features
        return tuple(name for name in CANONICAL_FEATURES if name not in held)

    def questionable(self) -> Tuple[str, ...]:
        return tuple(n for n in self.available() if self._snapshot.features[n].questionable)

    def clinically_extreme(self) -> Tuple[str, ...]:
        return tuple(
            n for n in self.available() if self._snapshot.features[n].clinically_extreme
        )

    def rejected(self) -> Tuple[str, ...]:
        return tuple(
            name
            for name in sorted(self._snapshot.unavailable)
            if self._snapshot.unavailable[name].availability == AVAILABILITY_REJECTED
        )

    def from_source(self, source: str) -> Tuple[str, ...]:
        return tuple(
            n for n in self.available() if self._snapshot.features[n].source == source
        )

    def units(self) -> Dict[str, Optional[str]]:
        return {name: f.unit for name, f in self._snapshot.features.items()}


    def why_unavailable(self, name: str) -> Optional[UnavailableFeature]:
        self._check_name(name)
        if name in self._snapshot.features:
            return None
        return self._snapshot.unavailable.get(name)

    def availability(self, name: str) -> str:
        reason = self.why_unavailable(name)
        return "available" if reason is None else reason.availability

    def is_rejected(self, name: str) -> bool:
        reason = self.why_unavailable(name)
        return bool(reason is not None and reason.availability == AVAILABILITY_REJECTED)


    def warnings(self) -> List[StageWarning]:
        return list(self._snapshot.all_warnings)

    def upstream(self) -> UpstreamExtraction:
        return self._snapshot.upstream

    @property
    def extraction_confidence(self) -> Optional[float]:
        return self._snapshot.upstream.extraction_confidence

    @property
    def pages_unreadable(self) -> List[int]:
        return list(self._snapshot.upstream.pages_unreadable)

    @property
    def partial_document(self) -> bool:
        return self._snapshot.summary.partial_document

    def summary(self) -> SnapshotSummary:
        return self._snapshot.summary

    def reference(self) -> SnapshotReference:
        return SnapshotReference(
            identity=self._snapshot.identity,
            summary=self._snapshot.summary,
            available=list(self.available()),
            unavailable=list(self.missing()),
        )


    def to_validated_input(self) -> Dict[str, Any]:
        valid = {
            name: feature.model_dump(mode="json")
            for name, feature in self._snapshot.features.items()
        }
        return {
            "valid": valid,
            "questionable": {n: valid[n] for n in self.questionable()},
            "clinically_extreme": list(self.clinically_extreme()),
            "missing_features": list(self._snapshot.missing_features),
            "warnings": list(self._snapshot.warnings),
            "upstream_warnings": [
                w.model_dump(mode="json") for w in self._snapshot.upstream_warnings
            ],
            "all_warnings": [
                w.model_dump(mode="json") for w in self._snapshot.all_warnings
            ],
            "upstream": self._snapshot.upstream.model_dump(mode="json"),
            "summary": self._snapshot.upstream_summary.model_dump(mode="json"),
        }


_default_backend: Optional[RepositoryBackend] = None
_backend_lock = threading.RLock()


def default_backend() -> RepositoryBackend:
    global _default_backend
    with _backend_lock:
        if _default_backend is None:
            _default_backend = InMemoryRepositoryBackend()
        return _default_backend


def set_default_backend(backend: Optional[RepositoryBackend]) -> None:
    global _default_backend
    with _backend_lock:
        _default_backend = backend


def reset_default_backend() -> None:
    set_default_backend(None)


def _resolve(backend: Optional[RepositoryBackend]) -> RepositoryBackend:
    return backend if backend is not None else default_backend()


def load_features(
    validated: Any = None,
    *,
    engineered: Any = None,
    patient_ref: Optional[str] = None,
    report_ref: Optional[str] = None,
    report_date: Optional[Union[datetime, str]] = None,
    snapshot_id: Optional[str] = None,
    store: bool = True,
    backend: Optional[RepositoryBackend] = None,
) -> FeatureRepository:
    snapshot = build_snapshot(
        validated,
        engineered=engineered,
        patient_ref=patient_ref,
        report_ref=report_ref,
        report_date=report_date,
        snapshot_id=snapshot_id,
    )
    if store:
        snapshot = _resolve(backend).put(snapshot)
        logger.info(
            "repository_snapshot_stored %s",
            safe_meta(
                feature_count=snapshot.summary.feature_count,
                missing_count=snapshot.summary.missing_count,
                rejected_count=snapshot.summary.rejected_count,
            ),
        )
    return FeatureRepository(snapshot)


def get_snapshot(
    snapshot_id: str, *, backend: Optional[RepositoryBackend] = None
) -> Optional[FeatureRepository]:
    snapshot = _resolve(backend).get(snapshot_id)
    return None if snapshot is None else FeatureRepository(snapshot)


def history(
    patient_ref: Optional[str], *, backend: Optional[RepositoryBackend] = None
) -> List[FeatureRepository]:
    return [FeatureRepository(s) for s in _resolve(backend).for_patient(patient_ref)]


def latest(
    patient_ref: Optional[str], *, backend: Optional[RepositoryBackend] = None
) -> Optional[FeatureRepository]:
    snapshot = _resolve(backend).latest_for_patient(patient_ref)
    return None if snapshot is None else FeatureRepository(snapshot)


def references(
    patient_ref: Optional[str], *, backend: Optional[RepositoryBackend] = None
) -> List[SnapshotReference]:
    return [repo.reference() for repo in history(patient_ref, backend=backend)]


def repository_document() -> Dict[str, Any]:
    return {
        "module": REPOSITORY_MODULE,
        "version": REPOSITORY_VERSION,
        "policy": REPOSITORY_POLICY,
        "canonical_features": list(CANONICAL_FEATURES),
        "backend": type(default_backend()).__name__,
        "accessors": [
            "has", "get", "require", "get_or_none", "tristate", "numeric",
            "unit", "canonical_unit", "source", "provenance", "feature",
            "values", "available", "missing", "questionable",
            "clinically_extreme", "rejected", "why_unavailable",
            "availability", "warnings", "upstream", "summary",
            "to_validated_input",
        ],
        "absent_sentinel": repr(ABSENT),
        "availability_kinds": [
            "available",
            AVAILABILITY_REJECTED,
            AVAILABILITY_NOT_REPORTED,
            AVAILABILITY_UNUSABLE,
        ],
    }


__all__ = [
    "ABSENT",
    "REPOSITORY_POLICY",
    "REPOSITORY_VERSION",
    "AbsentValueError",
    "FeatureRepository",
    "FeatureTypeError",
    "FeatureUnavailableError",
    "RepositoryError",
    "UnknownFeatureError",
    "build_snapshot",
    "default_backend",
    "get_snapshot",
    "history",
    "is_absent",
    "latest",
    "load_features",
    "references",
    "repository_document",
    "reset_default_backend",
    "set_default_backend",
]
