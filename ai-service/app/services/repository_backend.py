from __future__ import annotations

import abc
import threading
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from app.schemas.repository import FeatureSnapshot

SortKey = Tuple[datetime, int]


class RepositoryBackendError(RuntimeError):
    pass


class SnapshotNotFoundError(RepositoryBackendError, LookupError):
    pass


def snapshot_sort_key(snapshot: FeatureSnapshot) -> SortKey:
    return (snapshot.identity.ordering_key, snapshot.identity.sequence)


class RepositoryBackend(abc.ABC):

    @abc.abstractmethod
    def put(self, snapshot: FeatureSnapshot) -> FeatureSnapshot:
        pass

    @abc.abstractmethod
    def get(self, snapshot_id: str) -> Optional[FeatureSnapshot]:
        pass

    @abc.abstractmethod
    def delete(self, snapshot_id: str) -> bool:
        pass

    @abc.abstractmethod
    def for_patient(self, patient_ref: Optional[str]) -> List[FeatureSnapshot]:
        pass

    @abc.abstractmethod
    def patients(self) -> List[Optional[str]]:
        pass

    @abc.abstractmethod
    def count(self) -> int:
        pass


    def latest_for_patient(
        self, patient_ref: Optional[str]
    ) -> Optional[FeatureSnapshot]:
        snapshots = self.for_patient(patient_ref)
        return snapshots[-1] if snapshots else None

    def require(self, snapshot_id: str) -> FeatureSnapshot:
        snapshot = self.get(snapshot_id)
        if snapshot is None:
            raise SnapshotNotFoundError(f"no snapshot with id {snapshot_id!r}")
        return snapshot

    def __contains__(self, snapshot_id: object) -> bool:
        return isinstance(snapshot_id, str) and self.get(snapshot_id) is not None

    def __len__(self) -> int:
        return self.count()


class InMemoryRepositoryBackend(RepositoryBackend):

    def __init__(self, *, max_snapshots_per_patient: Optional[int] = None) -> None:
        if max_snapshots_per_patient is not None and max_snapshots_per_patient < 1:
            raise ValueError("max_snapshots_per_patient must be >= 1 or None")
        self._snapshots: Dict[str, FeatureSnapshot] = {}
        self._max_per_patient = max_snapshots_per_patient
        self._sequence = 0
        self._lock = threading.RLock()


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


    def clear(self) -> None:
        with self._lock:
            self._snapshots.clear()

    def _evict(self, patient_ref: Optional[str]) -> None:
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
