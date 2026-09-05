"""The Module 7 storage-backend contract and its in-memory implementation.

The point of the contract is that a SECOND implementation can satisfy it and
nothing above it changes. So the contract tests below are parametrised over two
independent backends: the shipped `InMemoryRepositoryBackend`, and a
deliberately different second implementation written here (list-based, and
storing JSON rather than model objects, the way a persistent backend would).
If the interface were secretly assuming the in-memory internals, the second one
would fail.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pytest

from app.data.feature_catalog import FEATURES
from app.schemas.repository import FeatureSnapshot, SnapshotIdentity
from app.services.feature_repository import build_snapshot, history, load_features
from app.services.repository_backend import (
    InMemoryRepositoryBackend,
    RepositoryBackend,
    SnapshotNotFoundError,
    snapshot_sort_key,
)


# --------------------------------------------------------------------------
# A second, deliberately different implementation of the same interface
# --------------------------------------------------------------------------


class JsonListBackend(RepositoryBackend):
    """Stores JSON documents in a list. Nothing in common with the shipped one.

    This is roughly the shape a persistent backend takes: serialise on write,
    deserialise on read, no shared object identity with the caller.
    """

    def __init__(self) -> None:
        self._rows: List[Dict[str, Any]] = []
        self._sequence = 0

    def put(self, snapshot: FeatureSnapshot) -> FeatureSnapshot:
        self._sequence += 1
        stored = snapshot.model_copy(deep=True)
        stored.identity = stored.identity.model_copy(
            update={"sequence": self._sequence}
        )
        document = json.loads(json.dumps(stored.model_dump(mode="json")))
        self._rows = [
            row
            for row in self._rows
            if row["identity"]["snapshot_id"] != stored.identity.snapshot_id
        ]
        self._rows.append(document)
        return FeatureSnapshot.model_validate(document)

    def get(self, snapshot_id: str) -> Optional[FeatureSnapshot]:
        for row in self._rows:
            if row["identity"]["snapshot_id"] == snapshot_id:
                return FeatureSnapshot.model_validate(row)
        return None

    def delete(self, snapshot_id: str) -> bool:
        before = len(self._rows)
        self._rows = [
            row for row in self._rows if row["identity"]["snapshot_id"] != snapshot_id
        ]
        return len(self._rows) != before

    def for_patient(self, patient_ref: Optional[str]) -> List[FeatureSnapshot]:
        found = [
            FeatureSnapshot.model_validate(row)
            for row in self._rows
            if row["identity"]["patient_ref"] == patient_ref
        ]
        found.sort(key=snapshot_sort_key)
        return found

    def patients(self) -> List[Optional[str]]:
        seen: List[Optional[str]] = []
        for row in self._rows:
            ref = row["identity"]["patient_ref"]
            if ref not in seen:
                seen.append(ref)
        return seen

    def count(self) -> int:
        return len(self._rows)


BACKENDS = [InMemoryRepositoryBackend, JsonListBackend]


@pytest.fixture(params=BACKENDS, ids=[b.__name__ for b in BACKENDS])
def backend(request) -> RepositoryBackend:
    return request.param()


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def make(
    value: float = 6.8,
    *,
    patient: Optional[str] = "p1",
    date: Optional[str] = None,
    snapshot_id: Optional[str] = None,
) -> FeatureSnapshot:
    definition = FEATURES["hba1c"]
    payload = {
        "valid": {
            "hba1c": {
                "name": "hba1c",
                "value": value,
                "unit": definition.canonical_unit,
                "canonical_unit": True,
                "source": definition.source,
                "provenance": {"source": definition.source},
            }
        }
    }
    return build_snapshot(
        payload, patient_ref=patient, report_date=date, snapshot_id=snapshot_id
    )


# --------------------------------------------------------------------------
# The contract -- every backend must satisfy all of this
# --------------------------------------------------------------------------


def test_put_then_get_round_trips_the_snapshot(backend):
    stored = backend.put(make(6.8))
    fetched = backend.get(stored.identity.snapshot_id)
    assert fetched is not None
    assert fetched.features["hba1c"].value == 6.8
    assert fetched.identity.snapshot_id == stored.identity.snapshot_id


def test_get_returns_none_for_an_unknown_id_and_never_raises(backend):
    assert backend.get("nothing-here") is None


def test_require_raises_for_an_unknown_id(backend):
    with pytest.raises(SnapshotNotFoundError):
        backend.require("nothing-here")


def test_put_assigns_a_monotonic_sequence(backend):
    first = backend.put(make(6.1))
    second = backend.put(make(6.4))
    assert second.identity.sequence > first.identity.sequence


def test_a_repeated_snapshot_id_overwrites_rather_than_duplicating(backend):
    backend.put(make(6.1, snapshot_id="same"))
    backend.put(make(6.8, snapshot_id="same"))
    assert backend.count() == 1
    assert backend.get("same").features["hba1c"].value == 6.8


def test_delete_removes_and_reports_whether_it_existed(backend):
    stored = backend.put(make())
    assert backend.delete(stored.identity.snapshot_id) is True
    assert backend.delete(stored.identity.snapshot_id) is False
    assert backend.get(stored.identity.snapshot_id) is None


def test_for_patient_returns_snapshots_oldest_first(backend):
    backend.put(make(6.8, date="2024-09-01"))
    backend.put(make(6.1, date="2024-01-15"))
    backend.put(make(6.4, date="2024-05-20"))
    values = [s.features["hba1c"].value for s in backend.for_patient("p1")]
    assert values == [6.1, 6.4, 6.8]


def test_for_patient_none_means_the_unattributed_snapshots_not_all_of_them(backend):
    backend.put(make(6.8, patient="p1"))
    backend.put(make(5.1, patient=None))
    assert len(backend.for_patient(None)) == 1
    assert backend.for_patient(None)[0].features["hba1c"].value == 5.1


def test_for_patient_is_empty_for_an_unknown_patient(backend):
    backend.put(make(patient="p1"))
    assert backend.for_patient("p2") == []


def test_latest_for_patient_uses_the_ordering_key(backend):
    backend.put(make(6.1, date="2024-01-15"))
    backend.put(make(6.8, date="2024-09-01"))
    backend.put(make(6.4, date="2024-05-20"))
    assert backend.latest_for_patient("p1").features["hba1c"].value == 6.8
    assert backend.latest_for_patient("nobody") is None


def test_patients_lists_every_distinct_reference(backend):
    backend.put(make(patient="p1"))
    backend.put(make(patient="p2"))
    backend.put(make(patient="p1"))
    assert set(backend.patients()) == {"p1", "p2"}


def test_count_contains_and_len(backend):
    stored = backend.put(make())
    assert backend.count() == 1
    assert len(backend) == 1
    assert stored.identity.snapshot_id in backend
    assert "not-an-id" not in backend
    assert 12345 not in backend


def test_a_backend_never_shares_mutable_state_with_its_caller(backend):
    """A caller mutating what it got back must not corrupt the store."""
    original = make(6.8)
    stored = backend.put(original)
    original.features.pop("hba1c")
    fetched = backend.get(stored.identity.snapshot_id)
    assert "hba1c" in fetched.features
    fetched.features.pop("hba1c")
    assert "hba1c" in backend.get(stored.identity.snapshot_id).features


def test_ordering_falls_back_to_record_time_when_undated(backend):
    early = make(6.1)
    early.identity = SnapshotIdentity(
        recorded_at=datetime(2024, 1, 1, tzinfo=timezone.utc), patient_ref="p1"
    )
    late = make(6.8)
    late.identity = SnapshotIdentity(
        recorded_at=datetime(2024, 9, 1, tzinfo=timezone.utc), patient_ref="p1"
    )
    backend.put(late)
    backend.put(early)
    assert [s.features["hba1c"].value for s in backend.for_patient("p1")] == [6.1, 6.8]


def test_a_dated_snapshot_sorts_by_its_report_date_not_its_record_time(backend):
    """`report_date` is the ordering key; load order must not decide."""
    backend.put(make(6.8, date="2024-09-01"))
    backend.put(make(6.1, date="2024-01-15"))
    assert [s.features["hba1c"].value for s in backend.for_patient("p1")] == [6.1, 6.8]


def test_the_sort_key_is_total_and_stable(backend):
    same = "2024-03-12"
    ids = [backend.put(make(v, date=same)).identity.snapshot_id for v in (1.0, 2.0, 3.0)]
    assert [s.identity.snapshot_id for s in backend.for_patient("p1")] == ids


# --------------------------------------------------------------------------
# The in-memory implementation's own behaviour
# --------------------------------------------------------------------------


def test_clear_drops_everything():
    store = InMemoryRepositoryBackend()
    store.put(make())
    store.clear()
    assert store.count() == 0


def test_the_per_patient_cap_evicts_the_oldest():
    store = InMemoryRepositoryBackend(max_snapshots_per_patient=2)
    store.put(make(6.1, date="2024-01-15"))
    store.put(make(6.4, date="2024-05-20"))
    store.put(make(6.8, date="2024-09-01"))
    values = [s.features["hba1c"].value for s in store.for_patient("p1")]
    assert values == [6.4, 6.8]
    assert store.count() == 2


def test_the_cap_is_per_patient_not_global():
    store = InMemoryRepositoryBackend(max_snapshots_per_patient=1)
    store.put(make(patient="p1"))
    store.put(make(patient="p2"))
    assert store.count() == 2


def test_an_invalid_cap_is_refused():
    with pytest.raises(ValueError):
        InMemoryRepositoryBackend(max_snapshots_per_patient=0)


def test_concurrent_writes_do_not_lose_snapshots():
    store = InMemoryRepositoryBackend()

    def write(index: int) -> None:
        store.put(make(float(index), patient="p1"))

    threads = [threading.Thread(target=write, args=(i,)) for i in range(25)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert store.count() == 25
    assert len(store.for_patient("p1")) == 25


# --------------------------------------------------------------------------
# The interface really is abstract
# --------------------------------------------------------------------------


def test_the_backend_interface_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        RepositoryBackend()  # type: ignore[abstract]


def test_an_incomplete_implementation_is_refused():
    class Half(RepositoryBackend):
        def put(self, snapshot):  # pragma: no cover - never constructed
            return snapshot

    with pytest.raises(TypeError):
        Half()  # type: ignore[abstract]


def test_the_service_layer_works_unchanged_over_a_foreign_backend():
    """The swappability claim, exercised rather than asserted."""
    foreign = JsonListBackend()
    load_features(
        {"valid": {"hba1c": {"name": "hba1c", "value": 6.1, "source": "lab_report",
                             "provenance": {"source": "lab_report"}}}},
        patient_ref="p1",
        report_date="2024-01-15",
        backend=foreign,
    )
    load_features(
        {"valid": {"hba1c": {"name": "hba1c", "value": 6.8, "source": "lab_report",
                             "provenance": {"source": "lab_report"}}}},
        patient_ref="p1",
        report_date="2024-09-01",
        backend=foreign,
    )
    timeline = history("p1", backend=foreign)
    assert [r.require("hba1c") for r in timeline] == [6.1, 6.8]
    assert timeline[0].provenance("hba1c").source == "lab_report"
