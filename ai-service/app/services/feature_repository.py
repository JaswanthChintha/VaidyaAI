"""Module 7 -- the Feature Repository.

The spec's storage step:

    Extraction -> Validation -> STORAGE -> Analysis

"After validation, accepted features are stored in a centralized Feature
Repository. The repository provides a common interface through which different
analytical components can access the same patient information... This
architecture prevents every module from independently extracting the same
laboratory values."

So this module is a SINGLE ACCESS POINT, not a second feature engineer. It
computes nothing clinical, converts no units, derives no values and applies no
rules. It stores what Module 6 accepted and hands it out through a typed
interface.

--------------------------------------------------------------------------
THE INTERFACE CONSUMERS USE
--------------------------------------------------------------------------

    repo = load_features(validated_result, patient_ref="p1", report_date=...)

    repo.has("hba1c")                 -> bool
    repo.get("hba1c")                 -> value, or the ABSENT sentinel
    repo.get("hba1c", default=None)   -> value, or your own default
    repo.require("hba1c")             -> value, or raises FeatureUnavailableError
    repo.get_or_none("hba1c")         -> value or None (opt in, by name)
    repo.tristate("hypertension")     -> True / False / None(unknown)
    repo.numeric("creatinine")        -> float, or ABSENT
    repo.unit("hba1c")                -> "%", or ABSENT
    repo.source("hba1c")              -> "lab_report" | "patient_profile"
    repo.provenance("hba1c")          -> FeatureProvenance, intact
    repo.feature("hba1c")             -> the whole StoredFeature record
    repo.available() / repo.missing() -> tuple[str, ...]
    repo.values()                     -> {name: value} for everything usable
    repo.why_unavailable("creatinine")-> UnavailableFeature (reason, no value)

--------------------------------------------------------------------------
ABSENCE IS NEVER SILENTLY COERCED
--------------------------------------------------------------------------

This is the property the whole module is built around. Across this project,
"absent" has repeatedly been at risk of collapsing into false / zero / normal,
and a fabricated negative clinical finding is worse than no finding.

Three mechanisms, together:

1. `get()` returns `ABSENT`, a singleton that RAISES on `bool()`, `float()`,
   `int()` and arithmetic. `if repo.get("hypertension"):` does not quietly take
   the false branch -- it raises. There is no way to write the classic bug.
2. `require()` raises `FeatureUnavailableError`, carrying the reason, for
   callers that want the failure at the read.
3. `get_or_none()` exists for callers that genuinely want `None`, but they have
   to ask for it by name. Nothing hands out `None` by default.

An unknown feature NAME is a different failure from an absent VALUE: a typo
raises `UnknownFeatureError`, never "absent".

--------------------------------------------------------------------------
REJECTED FEATURES ARE STRUCTURALLY UNREADABLE
--------------------------------------------------------------------------

`app/schemas/rules.py` makes this structural for the rule engine by not parsing
Module 6's `rejected` map at all. The repository has to keep the reasons -- a
user is owed "we could not use your creatinine, the printed value was
physiologically impossible" -- so it goes one level deeper: rejections are
parsed into `UnavailableFeature`, which HAS NO `value` FIELD, and the value is
dropped at the parse boundary. No accessor here reads `unavailable`; `get`,
`require`, `values`, `numeric`, `tristate` and `unit` all read `features` only.
"""

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

#: Short, quotable statement of what this module will and will not do.
REPOSITORY_POLICY = (
    "The Feature Repository stores only what Module 6 accepted. It never "
    "repairs, converts, derives or defaults a value; a feature with no usable "
    "value is ABSENT, never false, zero or normal; a rejected feature is kept "
    "as a reason with no value field, so it cannot be read as one; provenance "
    "and every upstream warning are carried through intact."
)

REPOSITORY_VERSION = "1.0.0"


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------


class RepositoryError(Exception):
    """Base for every error this module raises. Never carries a value."""


class UnknownFeatureError(RepositoryError, KeyError):
    """The name is not in the canonical catalogue -- i.e. a caller typo.

    Deliberately NOT the same error as an absent value. "You asked for
    something that does not exist" and "we do not have a reading for that" are
    different problems and must not be handled by the same branch.
    """


class FeatureUnavailableError(RepositoryError, LookupError):
    """The feature is canonical but has no usable value in this snapshot."""

    def __init__(
        self, name: str, reason: Optional[UnavailableFeature] = None
    ) -> None:
        self.name = name
        self.detail = reason
        self.reason_code = reason.reason_code if reason else REASON_NOT_REPORTED
        # The message names the FEATURE and the REASON CODE only. Never the
        # value, never the printed report line -- this string reaches logs and
        # HTTP responses.
        super().__init__(
            f"feature {name!r} has no usable value in this snapshot "
            f"({self.reason_code})"
        )


class FeatureTypeError(RepositoryError, TypeError):
    """A typed accessor was used on a feature of the wrong type."""


class AbsentValueError(RepositoryError, TypeError):
    """Something tried to use the ABSENT sentinel as if it were a value."""


# --------------------------------------------------------------------------
# The ABSENT sentinel
# --------------------------------------------------------------------------


class _AbsentType:
    """The value returned for "we have no reading for that".

    It is NOT `None`, NOT `False` and NOT `0`, and it refuses to become any of
    them. Every implicit coercion Python offers is overridden to raise, so the
    single most dangerous line in this codebase --

        if repo.get("hypertension"):   # absent would look like "no"

    -- raises `AbsentValueError` instead of silently fabricating a negative
    clinical finding.
    """

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
        # Identity equality only, so `x == ABSENT` is a legitimate test while
        # `x == 0` / `x == False` / `x is None` all stay false.
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


#: The singleton. Import this, do not instantiate `_AbsentType`.
ABSENT = _AbsentType()


def is_absent(value: Any) -> bool:
    """`value is ABSENT`, spelled out. Safe on anything, coerces nothing."""
    return value is ABSENT


# --------------------------------------------------------------------------
# Building a snapshot from Module 6's output
# --------------------------------------------------------------------------


def _coerce_validated(source: Any) -> Optional[ValidatedFeatureSetInput]:
    """Accept Module 6's result object, a parsed input model, or a dict.

    Mirrors the coercion in `rule_engine` and `ml.features` so every consumer
    of Module 6 tolerates exactly the same shapes.
    """
    if source is None:
        return None
    if isinstance(source, ValidatedFeatureSetInput):
        return source
    if hasattr(source, "model_dump"):
        return ValidatedFeatureSetInput.model_validate(source.model_dump())
    return ValidatedFeatureSetInput.model_validate(source)


def _carried_warnings(data: ValidatedFeatureSetInput) -> List[StageWarning]:
    """Every upstream warning, origins intact.

    Same helper, same reason, as `rule_engine._carried_warnings` and
    `ml.features._carried_warnings`: dropping upstream warnings has already
    been a real defect on this project twice. `all_warnings` is authoritative
    when the caller supplied it; otherwise it is rebuilt from
    `upstream_warnings` plus Module 6's own strings.
    """
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
    """Module 6's validated output -> one `FeatureSnapshot`.

    Framework-independent: no FastAPI, no I/O, no global state, nothing stored.
    `engineered` is accepted for the same reason Modules 8 and 9 accept it --
    it is validated in-process first, so the repository still only ever stores
    values Module 6 accepted.

    When both are supplied, `validated` wins.
    """
    data = _coerce_validated(validated)
    if data is None and engineered is not None:
        data = _coerce_validated(validate_features(engineered))
    if data is None:
        data = ValidatedFeatureSetInput()

    partial_document = bool(data.upstream.pages_unreadable)

    features: Dict[str, StoredFeature] = {}
    unavailable: Dict[str, UnavailableFeature] = {}
    own_warnings: List[str] = []

    # ---- the usable set -------------------------------------------------
    for name, incoming in data.valid.items():
        if name not in CANONICAL_FEATURES:
            # Not silently ignored: a non-canonical key means upstream naming
            # drift, and the repository says so rather than quietly storing a
            # feature nothing downstream can address.
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
            # A value Module 6 marked valid but that is not a storable scalar.
            # It becomes UNAVAILABLE -- never a stored value, never a default,
            # and never an exception that discards the rest of the payload.
            # The offending value is NOT put in the message (it is PHI).
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

    # ---- rejections: reasons only, never values -------------------------
    for name, rejection in data.rejected.items():
        if name in features:
            # Module 6 guarantees the partitions are disjoint. If they ever are
            # not, the SAFE resolution is to drop the usable value, not to keep
            # a value something refused.
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

    # ---- everything else that is simply not there -----------------------
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

    # ---- warnings -------------------------------------------------------
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


# --------------------------------------------------------------------------
# The repository itself
# --------------------------------------------------------------------------


class FeatureRepository:
    """The common interface every analytical component reads through.

    A `FeatureRepository` is a typed, read-only view over ONE `FeatureSnapshot`
    -- one patient, one report. A patient's history is several snapshots; see
    `history()` and `latest()`.

    Read-only on purpose: Module 8, the ML layer, Module 15 and Module 20 all
    read the same object, and a shared mutable feature set would let one
    consumer change what another sees mid-pipeline. Storing new data means
    building a new snapshot.
    """

    __slots__ = ("_snapshot",)

    def __init__(self, snapshot: FeatureSnapshot) -> None:
        self._snapshot = snapshot

    # -- construction ------------------------------------------------------

    @classmethod
    def from_validated(cls, validated: Any = None, **kwargs: Any) -> "FeatureRepository":
        """Build directly from Module 6's output. See `build_snapshot`."""
        return cls(build_snapshot(validated, **kwargs))

    @classmethod
    def empty(cls) -> "FeatureRepository":
        """A repository holding nothing. Every feature reads as absent."""
        return cls(build_snapshot())

    # -- identity ----------------------------------------------------------

    @property
    def snapshot(self) -> FeatureSnapshot:
        """The underlying snapshot. Treat as immutable."""
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
        """The longitudinal sort key. Modules 28-30 order on this."""
        return self._snapshot.identity.ordering_key

    # -- name checking -----------------------------------------------------

    @staticmethod
    def _check_name(name: str) -> str:
        """A name outside the catalogue is a caller bug, not an absent value."""
        if name not in CANONICAL_FEATURES:
            raise UnknownFeatureError(
                f"{name!r} is not a canonical feature. Known features: "
                f"{', '.join(CANONICAL_FEATURES)}"
            )
        return name

    # -- presence ----------------------------------------------------------

    def has(self, name: str) -> bool:
        """True when a USABLE value is held. The safe thing to branch on."""
        return self._check_name(name) in self._snapshot.features

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name in self._snapshot.features

    def __len__(self) -> int:
        return len(self._snapshot.features)

    def __iter__(self) -> Iterator[str]:
        return iter(self.available())

    def __repr__(self) -> str:
        # Shape only. No values, no patient reference.
        return (
            f"<FeatureRepository features={len(self._snapshot.features)} "
            f"unavailable={len(self._snapshot.unavailable)}>"
        )

    # -- values ------------------------------------------------------------

    def get(self, name: str, default: Any = ABSENT) -> Any:
        """The value, or `default` (the ABSENT sentinel unless you say otherwise).

        The default default is `ABSENT`, which raises on every implicit
        coercion, so a caller that forgets to check cannot read a missing
        feature as false or zero.
        """
        self._check_name(name)
        found = self._snapshot.features.get(name)
        return default if found is None else found.value

    def require(self, name: str) -> FeatureValue:
        """The value, or `FeatureUnavailableError` carrying the reason."""
        self._check_name(name)
        found = self._snapshot.features.get(name)
        if found is None:
            raise FeatureUnavailableError(name, self.why_unavailable(name))
        return found.value

    def get_or_none(self, name: str) -> Optional[FeatureValue]:
        """The value, or `None`.

        Collapsing absence to `None` is safe ONLY where the caller has thought
        about it, so it has its own name rather than being what `get()` does.
        """
        return self.get(name, default=None)

    def tristate(self, name: str) -> Optional[bool]:
        """`True` / `False` / `None` for a tri-state boolean feature.

        `None` means UNKNOWN and never means "no". Raises `FeatureTypeError` on
        a non-boolean feature, so this accessor cannot be pointed at a number
        whose zero would then look like a negative finding.
        """
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
        """The value as a `float`, or `default`.

        Booleans are refused rather than silently becoming 1.0 / 0.0, and a
        feature whose unit could not be recognised (`canonical_unit: false`)
        is refused too -- its magnitude is meaningless, which is exactly why
        Module 6 flags it.
        """
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
        """`{name: value}` for everything usable -- the whole set, once.

        This is the call that stops each analytical component re-deriving the
        same laboratory values. Questionable features ARE included: they are
        usable by definition. Use `questionable()` to down-weight them.
        """
        return {name: f.value for name, f in self._snapshot.features.items()}

    # -- metadata ----------------------------------------------------------

    def feature(self, name: str, default: Any = ABSENT) -> Any:
        """The whole `StoredFeature` record, or `default`."""
        self._check_name(name)
        found = self._snapshot.features.get(name)
        return default if found is None else found

    def require_feature(self, name: str) -> StoredFeature:
        found = self.feature(name, default=None)
        if found is None:
            raise FeatureUnavailableError(name, self.why_unavailable(name))
        return found

    def unit(self, name: str, default: Any = ABSENT) -> Any:
        """The unit, or `default`.

        A present feature may legitimately have `unit is None` (booleans and
        categories have no unit), which is why absence must not be signalled
        with `None` here.
        """
        self._check_name(name)
        found = self._snapshot.features.get(name)
        return default if found is None else found.unit

    def canonical_unit(self, name: str) -> bool:
        """False means `value` is NOT in the canonical unit. Raises if absent."""
        return self.require_feature(name).canonical_unit

    def source(self, name: str, default: Any = ABSENT) -> Any:
        """`lab_report` or `patient_profile`.

        Consumers do not need to know this to READ a feature -- that is the
        point of the repository -- but Module 20 and the report need to be able
        to ask.
        """
        self._check_name(name)
        found = self._snapshot.features.get(name)
        return default if found is None else found.source

    def provenance(self, name: str, default: Any = ABSENT) -> Any:
        """The full `FeatureProvenance`, unflattened.

        Module 20 reads this to show which printed report line produced which
        feature, so it is passed through whole -- never summarised, never
        reduced to a string.
        """
        self._check_name(name)
        found = self._snapshot.features.get(name)
        return default if found is None else found.provenance

    def require_provenance(self, name: str) -> FeatureProvenance:
        return self.require_feature(name).provenance

    def is_questionable(self, name: str) -> bool:
        """True only for a PRESENT feature that is flagged. Absent is not flagged."""
        found = self.feature(name, default=None)
        return bool(found is not None and found.questionable)

    def is_clinically_extreme(self, name: str) -> bool:
        found = self.feature(name, default=None)
        return bool(found is not None and found.clinically_extreme)

    # -- set-level views ---------------------------------------------------

    def available(self) -> Tuple[str, ...]:
        """Every feature with a usable value, in catalogue order."""
        held = self._snapshot.features
        return tuple(name for name in CANONICAL_FEATURES if name in held)

    def missing(self) -> Tuple[str, ...]:
        """Every canonical feature with NO usable value, in catalogue order.

        Derived from what is actually held, so it can never disagree with
        `available()`. `snapshot.missing_features` is Module 5/6's own list,
        carried through unchanged for the report; this is the authoritative
        answer to "can I read it?".
        """
        held = self._snapshot.features
        return tuple(name for name in CANONICAL_FEATURES if name not in held)

    def questionable(self) -> Tuple[str, ...]:
        return tuple(n for n in self.available() if self._snapshot.features[n].questionable)

    def clinically_extreme(self) -> Tuple[str, ...]:
        return tuple(
            n for n in self.available() if self._snapshot.features[n].clinically_extreme
        )

    def rejected(self) -> Tuple[str, ...]:
        """Names Module 6 refused. Reasons only -- there are no values to read."""
        return tuple(
            name
            for name in sorted(self._snapshot.unavailable)
            if self._snapshot.unavailable[name].availability == AVAILABILITY_REJECTED
        )

    def from_source(self, source: str) -> Tuple[str, ...]:
        """Available features that came from `lab_report` / `patient_profile`."""
        return tuple(
            n for n in self.available() if self._snapshot.features[n].source == source
        )

    def units(self) -> Dict[str, Optional[str]]:
        return {name: f.unit for name, f in self._snapshot.features.items()}

    # -- unavailability ----------------------------------------------------

    def why_unavailable(self, name: str) -> Optional[UnavailableFeature]:
        """Why there is no usable value, or `None` when there IS one.

        The returned record has no `value` field by construction, so asking
        why cannot become a way of reading what was refused.
        """
        self._check_name(name)
        if name in self._snapshot.features:
            return None
        return self._snapshot.unavailable.get(name)

    def availability(self, name: str) -> str:
        """`available` | `rejected` | `not_reported` | `unusable`."""
        reason = self.why_unavailable(name)
        return "available" if reason is None else reason.availability

    def is_rejected(self, name: str) -> bool:
        reason = self.why_unavailable(name)
        return bool(reason is not None and reason.availability == AVAILABILITY_REJECTED)

    # -- carried context ---------------------------------------------------

    def warnings(self) -> List[StageWarning]:
        """EVERY warning from every stage, origins intact. Never filtered."""
        return list(self._snapshot.all_warnings)

    def upstream(self) -> UpstreamExtraction:
        """Module 4 context: source, metadata, confidence, unreadable pages."""
        return self._snapshot.upstream

    @property
    def extraction_confidence(self) -> Optional[float]:
        return self._snapshot.upstream.extraction_confidence

    @property
    def pages_unreadable(self) -> List[int]:
        return list(self._snapshot.upstream.pages_unreadable)

    @property
    def partial_document(self) -> bool:
        """True when Module 4 could not read every page.

        An absent feature may then be UNREAD rather than absent from the
        report -- the distinction the final report has to keep.
        """
        return self._snapshot.summary.partial_document

    def summary(self) -> SnapshotSummary:
        """Counts only. No values, no identifiers -- safe to log."""
        return self._snapshot.summary

    def reference(self) -> SnapshotReference:
        """Identity + shape, without the values. What a listing returns."""
        return SnapshotReference(
            identity=self._snapshot.identity,
            summary=self._snapshot.summary,
            available=list(self.available()),
            unavailable=list(self.missing()),
        )

    # -- handing the set to a consumer ------------------------------------

    def to_validated_input(self) -> Dict[str, Any]:
        """The set in the shape Modules 8 and 9 already parse.

        This is what makes the repository the SINGLE ACCESS POINT instead of a
        parallel one: `evaluate_rules(repo.to_validated_input())` and
        `predict_all(repo.to_validated_input())` work today, without either
        consumer changing and without anything re-extracting the values.

        It carries NO `rejected` key -- there is no value to put there, and
        `app.schemas.rules.ValidatedFeaturesInput` would not parse it anyway.
        """
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


# --------------------------------------------------------------------------
# The process-default backend and the framework-independent entry points
# --------------------------------------------------------------------------

_default_backend: Optional[RepositoryBackend] = None
_backend_lock = threading.RLock()


def default_backend() -> RepositoryBackend:
    """The process-wide backend, created on first use.

    In-memory, therefore process-local and lost on restart -- see
    `app/services/repository_backend.py` for why that is the right shape for
    Module 7 today. Pass an explicit `backend=` to any function below to use a
    different one; nothing here reaches for the default when given one.
    """
    global _default_backend
    with _backend_lock:
        if _default_backend is None:
            _default_backend = InMemoryRepositoryBackend()
        return _default_backend


def set_default_backend(backend: Optional[RepositoryBackend]) -> None:
    """Swap the process-wide backend. `None` restores the lazy default.

    This is the whole swappability story: a persistent backend is installed
    here, and not one consumer of `FeatureRepository` changes.
    """
    global _default_backend
    with _backend_lock:
        _default_backend = backend


def reset_default_backend() -> None:
    """Forget everything the default backend holds. Used by tests."""
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
    """Module 6's validated output -> a stored, readable `FeatureRepository`.

    THE PRIMARY ENTRY POINT, and framework-independent in exactly the way
    `engineer_features()`, `validate_features()`, `evaluate_rules()` and
    `predict_all()` are: importable, no FastAPI, no HTTP.

        repo = load_features(validation_result, patient_ref="...",
                             report_date="2024-03-12")
        repo.require("hba1c")

    `engineered` is accepted and validated in-process first, so the repository
    only ever stores values Module 6 accepted. `validated` wins if both are
    given. `store=False` builds a repository without persisting it.
    """
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
        # Shape only. No patient reference, no feature name, no value.
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
    """One stored snapshot as a repository, or `None`."""
    snapshot = _resolve(backend).get(snapshot_id)
    return None if snapshot is None else FeatureRepository(snapshot)


def history(
    patient_ref: Optional[str], *, backend: Optional[RepositoryBackend] = None
) -> List[FeatureRepository]:
    """Every stored snapshot for one patient, CHRONOLOGICAL, oldest first.

    The groundwork Modules 28 (trends), 29 (comparison) and 30 (progress) need:
    an ordered sequence of feature sets for one patient. Module 7 provides the
    ORDER AND THE DATA ONLY -- it computes no trend, no delta and no score.
    """
    return [FeatureRepository(s) for s in _resolve(backend).for_patient(patient_ref)]


def latest(
    patient_ref: Optional[str], *, backend: Optional[RepositoryBackend] = None
) -> Optional[FeatureRepository]:
    """The most recent snapshot for one patient, or `None`."""
    snapshot = _resolve(backend).latest_for_patient(patient_ref)
    return None if snapshot is None else FeatureRepository(snapshot)


def references(
    patient_ref: Optional[str], *, backend: Optional[RepositoryBackend] = None
) -> List[SnapshotReference]:
    """Identity + shape for a patient's snapshots. No values."""
    return [repo.reference() for repo in history(patient_ref, backend=backend)]


def repository_document() -> Dict[str, Any]:
    """Machine-readable description of the repository interface.

    Introspection in the spirit of `GET /api/v1/ml/predictors`: shape only, no
    PHI, so a deployment can be checked without submitting a report.
    """
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
