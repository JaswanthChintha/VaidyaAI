"""Storage backends for the Feature Repository (spec Module 7).

`backend/src/storage/` did this for uploaded files: one small interface, one
local implementation behind it, so the store can be swapped without touching a
single caller. This is the same idea for validated features.

    RepositoryBackend            the interface. Six methods, nothing else.
    InMemoryRepositoryBackend    the shipped implementation.

WHY IN-MEMORY, AND ONLY IN-MEMORY
---------------------------------

`backend/` currently persists analysis results on the `Report` document, and
MEMORY.md records that as an explicitly INTERIM arrangement that Module 7 is
meant to formalise. Formalising it means defining the interface first. This
module deliberately adds no database and takes no dependency on MongoDB: a
persistent backend is a new class implementing `RepositoryBackend`, and the
`FeatureRepository` API above it does not change.

`FeatureSnapshot` is fully JSON round-trippable
(`model_dump(mode="json")` / `model_validate`), so a persistent backend needs
no serialisation logic of its own.

ORDERING
--------

Every snapshot has a total, stable order given by
`(identity.ordering_key, identity.sequence)` -- the report date when known,
otherwise the time it was recorded, with the backend's monotonic insertion
counter breaking ties. Modules 28-30 need a defined order to walk a patient's
history; they do NOT get any trend or comparison logic from here, only the
ordered data.

CAVEATS OF THE IN-MEMORY BACKEND (documented, not hidden)
---------------------------------------------------------

* It holds PHI in process memory and loses everything on restart. That is
  correct for a not-yet-persistent module and wrong for production.
* It is process-local: two uvicorn workers do not share it.
* It is unbounded. `max_snapshots_per_patient` (default: unlimited) evicts the
  oldest per patient when set, so a long-running process cannot grow forever.
* It is guarded by a re-entrant lock, so concurrent requests cannot interleave
  a write with a listing, but it offers no cross-process transactionality.
"""

from __future__ import annotations

import abc
import threading
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from app.schemas.repository import FeatureSnapshot

#: Sort key: report date (or record time), then insertion order.
SortKey = Tuple[datetime, int]


class RepositoryBackendError(RuntimeError):
    """A backend could not satisfy a request. Never carries a feature value."""


class SnapshotNotFoundError(RepositoryBackendError, LookupError):
    """No snapshot with that id."""


def snapshot_sort_key(snapshot: FeatureSnapshot) -> SortKey:
    """Total, stable ordering for one snapshot.

    Kept here rather than on the schema so every backend orders identically
    and a second implementation cannot drift.
    """
    return (snapshot.identity.ordering_key, snapshot.identity.sequence)


class RepositoryBackend(abc.ABC):
    """The storage contract. Implement these six methods and nothing else.

    An implementation MUST:

    * treat snapshots as opaque -- never inspect, transform or re-derive a
      feature value;
    * assign `identity.sequence` from its own monotonic counter in `put`, so
      that ordering is stable even when two snapshots share a timestamp;
    * return snapshots from `for_patient` in ascending `snapshot_sort_key`
      order, oldest first;
    * treat a repeated `snapshot_id` in `put` as an overwrite of that snapshot,
      not as a duplicate;
    * never log a feature value or any report text.

    An implementation MUST NOT assume the caller holds a lock.
    """

    @abc.abstractmethod
    def put(self, snapshot: FeatureSnapshot) -> FeatureSnapshot:
        """Store (or overwrite) a snapshot. Returns the stored object.

        The returned snapshot carries the identity the backend actually
        assigned, including `sequence`.
        """

    @abc.abstractmethod
    def get(self, snapshot_id: str) -> Optional[FeatureSnapshot]:
        """One snapshot, or None. Never raises for an unknown id."""

    @abc.abstractmethod
    def delete(self, snapshot_id: str) -> bool:
        """Remove one snapshot. True if it existed."""

    @abc.abstractmethod
    def for_patient(self, patient_ref: Optional[str]) -> List[FeatureSnapshot]:
        """Every snapshot for one patient, CHRONOLOGICAL, oldest first.

        `patient_ref=None` selects the snapshots stored without a patient
        reference -- it does NOT mean "all patients".
        """

    @abc.abstractmethod
    def patients(self) -> List[Optional[str]]:
        """Every distinct `patient_ref` currently held."""

    @abc.abstractmethod
    def count(self) -> int:
        """Total snapshots held."""

    # -- provided, not abstract: derivable from the six above --------------

    def latest_for_patient(
        self, patient_ref: Optional[str]
    ) -> Optional[FeatureSnapshot]:
        """The most recent snapshot for a patient, by ordering key."""
        snapshots = self.for_patient(patient_ref)
        return snapshots[-1] if snapshots else None

    def require(self, snapshot_id: str) -> FeatureSnapshot:
        """`get`, but raises `SnapshotNotFoundError` instead of returning None."""
        snapshot = self.get(snapshot_id)
        if snapshot is None:
            raise SnapshotNotFoundError(f"no snapshot with id {snapshot_id!r}")
        return snapshot

    def __contains__(self, snapshot_id: object) -> bool:
        return isinstance(snapshot_id, str) and self.get(snapshot_id) is not None

    def __len__(self) -> int:
        return self.count()


class InMemoryRepositoryBackend(RepositoryBackend):
    """A dict. Deliberately.

    Snapshots are stored as pydantic models and returned as DEEP COPIES, so a
    caller mutating what it got back cannot corrupt the store -- the same
    isolation a real database gives for free, and the difference between this
    and a naive dict that silently shares state.
    """

    def __init__(self, *, max_snapshots_per_patient: Optional[int] = None) -> None:
        if max_snapshots_per_patient is not None and max_snapshots_per_patient < 1:
            raise ValueError("max_snapshots_per_patient must be >= 1 or None")
        self._snapshots: Dict[str, FeatureSnapshot] = {}
        self._max_per_patient = max_snapshots_per_patient
        self._sequence = 0
        self._lock = threading.RLock()

    # -- interface ---------------------------------------------------------

    def put(self, snapshot: FeatureSnapshot) -> FeatureSnapshot:
        with self._lock:
            self._sequence += 1
            stored = snapshot.model_copy(deep=True)
            stored.identity = stored.identity.model_copy(
                update={"sequence": self._sequence}
            )
            self._snapshots[stored.identity.snapshot_id] = stored
            self._evict(stored.identity.patient_ref)
            return stored.model_copy(deep=True)

    def get(self, snapshot_id: str) -> Optional[FeatureSnapshot]:
        with self._lock:
            found = self._snapshots.get(snapshot_id)
            return found.model_copy(deep=True) if found is not None else None

    def delete(self, snapshot_id: str) -> bool:
        with self._lock:
            return self._snapshots.pop(snapshot_id, None) is not None

    def for_patient(self, patient_ref: Optional[str]) -> List[FeatureSnapshot]:
        with self._lock:
            matches = [
                s
                for s in self._snapshots.values()
                if s.identity.patient_ref == patient_ref
            ]
        matches.sort(key=snapshot_sort_key)
        return [s.model_copy(deep=True) for s in matches]

    def patients(self) -> List[Optional[str]]:
        with self._lock:
            seen: List[Optional[str]] = []
            for snapshot in self._snapshots.values():
                ref = snapshot.identity.patient_ref
                if ref not in seen:
                    seen.append(ref)
            return seen

    def count(self) -> int:
        with self._lock:
            return len(self._snapshots)

    # -- in-memory extras --------------------------------------------------

    def clear(self) -> None:
        """Drop everything. Exists for tests and for process shutdown."""
        with self._lock:
            self._snapshots.clear()

    def _evict(self, patient_ref: Optional[str]) -> None:
        """Drop the oldest snapshots for a patient past the configured cap."""
        if self._max_per_patient is None:
            return
        matches = [
            s
            for s in self._snapshots.values()
            if s.identity.patient_ref == patient_ref
        ]
        if len(matches) <= self._max_per_patient:
            return
        matches.sort(key=snapshot_sort_key)
        for stale in matches[: len(matches) - self._max_per_patient]:
            self._snapshots.pop(stale.identity.snapshot_id, None)


__all__ = [
    "InMemoryRepositoryBackend",
    "RepositoryBackend",
    "RepositoryBackendError",
    "SnapshotNotFoundError",
    "snapshot_sort_key",
]
