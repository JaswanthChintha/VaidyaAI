"""Module 7 -- the Feature Repository, exercised through its real interface.

The framework-independent entry points, which is what Module 15 will call.

Covered here: loading a genuine Module 6 result; every accessor; absent staying
distinct from false, zero, None and "normal" for both the tri-state booleans and
numerics; a rejected feature having no readable value anywhere; provenance
surviving unflattened; warnings and `upstream` carried through with origins;
several snapshots per patient held and returned in order; empty and all-rejected
inputs; and handing the stored set straight to Modules 8 and 9.
"""

from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import pytest

from app.data.feature_catalog import CANONICAL_FEATURES, FEATURES
from app.schemas.features import FeatureProvenance
from app.schemas.repository import (
    AVAILABILITY_NOT_REPORTED,
    AVAILABILITY_REJECTED,
    REASON_NOT_REPORTED,
    REASON_NOT_REPORTED_PARTIAL_DOCUMENT,
    FeatureSnapshot,
    StoredFeature,
    UnavailableFeature,
)
from app.services.feature_engineer import engineer_features
from app.services.feature_repository import (
    ABSENT,
    FeatureRepository,
    FeatureTypeError,
    FeatureUnavailableError,
    UnknownFeatureError,
    AbsentValueError,
    build_snapshot,
    default_backend,
    get_snapshot,
    history,
    is_absent,
    latest,
    load_features,
    references,
    repository_document,
    reset_default_backend,
    set_default_backend,
)
from app.services.repository_backend import InMemoryRepositoryBackend
from app.services.validator import validate_features

# --------------------------------------------------------------------------
# Isolation -- the default backend is process-wide state
# --------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_backend():
    reset_default_backend()
    yield
    reset_default_backend()


# --------------------------------------------------------------------------
# Builders -- one entry of Module 6's `valid` / `rejected` maps
# --------------------------------------------------------------------------


def vf(
    name: str,
    value: Any,
    *,
    questionable: bool = False,
    extreme: bool = False,
    direction: Optional[str] = None,
    test_name: Optional[str] = None,
    canonical_unit: bool = True,
    unit: Any = "__default__",
) -> Dict[str, Any]:
    definition = FEATURES[name]
    provenance: Dict[str, Any] = {"source": definition.source}
    if test_name:
        provenance["original_test_name"] = test_name
        provenance["original_value_raw"] = str(value)
        provenance["page_number"] = 1
        provenance["confidence"] = 0.94
    return {
        "name": name,
        "value": value,
        "unit": definition.canonical_unit if unit == "__default__" else unit,
        "canonical_unit": canonical_unit,
        "source": definition.source,
        "provenance": provenance,
        "status": "questionable" if questionable else "valid",
        "questionable": questionable,
        "clinically_extreme": extreme,
        "extreme_direction": direction,
        "flags": [],
    }


def rf(name: str, value: Any, *, code: str = "IMPLAUSIBLE_VALUE_HIGH") -> Dict[str, Any]:
    """One entry of Module 6's `rejected` map -- WITH its original value."""
    definition = FEATURES[name]
    return {
        "name": name,
        "value": value,
        "unit": definition.canonical_unit,
        "canonical_unit": True,
        "source": definition.source,
        "provenance": {
            "source": definition.source,
            "original_test_name": "Creatinine",
            "original_value_raw": str(value),
        },
        "status": "rejected",
        "reason_code": code,
        "reason": "The value is outside the physiologically possible range.",
        "findings": [],
    }


def validated(
    features: Optional[Dict[str, Any]] = None,
    rejected: Optional[Dict[str, Any]] = None,
    **overrides: Any,
) -> Dict[str, Any]:
    """Module 6's `data` object."""
    features = features or {}
    rejected = rejected or {}
    payload: Dict[str, Any] = {
        "valid": features,
        "questionable": {k: v for k, v in features.items() if v["questionable"]},
        "rejected": rejected,
        "clinically_extreme": [
            k for k, v in features.items() if v["clinically_extreme"]
        ],
        "missing_features": [
            n
            for n in CANONICAL_FEATURES
            if n not in features and n not in rejected
        ],
        "unmapped": [],
        "warnings": [],
        "upstream_warnings": [],
        "all_warnings": [],
        "upstream": {"provided": True},
        "summary": {},
    }
    payload.update(overrides)
    return payload


REALISTIC = validated(
    {
        "hba1c": vf("hba1c", 6.8, test_name="HbA1c"),
        "blood_glucose": vf("blood_glucose", 112.0, test_name="Fasting Blood Glucose"),
        "hemoglobin": vf("hemoglobin", 14.2, questionable=True, test_name="Hb"),
        "age": vf("age", 45),
        "gender": vf("gender", "male"),
        "heart_disease": vf("heart_disease", False),
    },
    {"creatinine": rf("creatinine", 9999.0)},
)


def repo(payload: Optional[Dict[str, Any]] = None, **kwargs: Any) -> FeatureRepository:
    return load_features(payload if payload is not None else REALISTIC, **kwargs)


# --------------------------------------------------------------------------
# Loading a real Module 6 result, end to end from Module 5
# --------------------------------------------------------------------------


def test_loads_a_genuine_module_6_result_produced_by_module_5():
    extraction = {
        "extracted_parameters": [
            {
                "test_name": "HbA1c",
                "value_raw": "6.8",
                "value_numeric": 6.8,
                "unit": "%",
                "confidence": 0.94,
                "reference_low": 4.0,
                "reference_high": 5.6,
            },
            {
                "test_name": "Creatinine",
                "value_raw": "9999",
                "value_numeric": 9999.0,
                "unit": "mg/dL",
            },
        ],
        "extraction_confidence": 0.99,
        "warnings": ["page 1 was recovered by the PDF repairer"],
        "pages": [{"page_number": 1, "raw_text_available": True}],
    }
    profile = {"age": 45, "gender": "male", "heartDisease": False}

    result = validate_features(engineer_features(extraction=extraction, profile=profile))
    r = load_features(result, patient_ref="patient-1", report_date="2024-03-12")

    assert r.require("hba1c") == 6.8
    assert r.unit("hba1c") == "%"
    assert r.require("age") == 45
    # Module 6 rejected the impossible creatinine; it is not usable here.
    assert r.has("creatinine") is False
    assert r.is_rejected("creatinine") is True
    # Module 4's warning survived four module boundaries with its origin.
    assert ("extraction", 4) in [(w.stage, w.module) for w in r.warnings()]
    assert r.extraction_confidence == 0.99


def test_accepts_module_5_output_and_validates_it_in_process():
    """`engineered=` must go through Module 6 -- never stored unvalidated."""
    engineered = engineer_features(
        extraction={
            "extracted_parameters": [
                {
                    "test_name": "Creatinine",
                    "value_raw": "9999",
                    "value_numeric": 9999.0,
                    "unit": "mg/dL",
                }
            ]
        }
    )
    r = load_features(engineered=engineered)
    assert r.has("creatinine") is False
    assert r.is_rejected("creatinine") is True


def test_validated_wins_when_both_inputs_are_supplied():
    engineered = engineer_features(
        extraction={
            "extracted_parameters": [
                {"test_name": "HbA1c", "value_raw": "9.9", "value_numeric": 9.9, "unit": "%"}
            ]
        }
    )
    r = load_features(REALISTIC, engineered=engineered)
    assert r.require("hba1c") == 6.8


def test_accepts_a_plain_dict_a_model_and_a_parsed_input_alike():
    result = validate_features(
        engineer_features(
            extraction={
                "extracted_parameters": [
                    {"test_name": "HbA1c", "value_raw": "6.1", "value_numeric": 6.1, "unit": "%"}
                ]
            }
        )
    )
    from_model = load_features(result, store=False)
    from_dict = load_features(result.model_dump(), store=False)
    assert from_model.values() == from_dict.values() == {"hba1c": 6.1}


# --------------------------------------------------------------------------
# ABSENCE -- the property this module exists to protect
# --------------------------------------------------------------------------


def test_get_returns_the_absent_sentinel_not_none_false_or_zero():
    r = repo()
    value = r.get("vitamin_d")
    assert is_absent(value)
    assert value is not None
    assert value is not False
    assert value != 0
    assert value != False  # noqa: E712 -- the point is that it is not equal
    assert value != ""


def test_the_absent_sentinel_refuses_to_be_a_boolean():
    """`if repo.get(x):` must not quietly take the false branch."""
    r = repo()
    with pytest.raises(AbsentValueError):
        bool(r.get("hypertension"))
    with pytest.raises(AbsentValueError):
        if r.get("hypertension"):  # pragma: no cover - raises before the body
            pass


@pytest.mark.parametrize(
    "operation",
    [
        lambda v: float(v),
        lambda v: int(v),
        lambda v: len(v),
        lambda v: list(v),
        lambda v: v + 1,
        lambda v: 1 + v,
        lambda v: v * 2,
        lambda v: v / 2,
        lambda v: v - 1,
        lambda v: v < 5,
        lambda v: v > 5,
        lambda v: v <= 5,
        lambda v: v >= 5,
        lambda v: [0, 1][v],
    ],
)
def test_the_absent_sentinel_refuses_every_numeric_coercion(operation):
    r = repo()
    with pytest.raises(TypeError):
        operation(r.get("vitamin_d"))


def test_the_absent_sentinel_is_a_singleton_that_survives_copying():
    assert ABSENT is copy.copy(ABSENT)
    assert ABSENT is copy.deepcopy(ABSENT)
    assert repr(ABSENT) == "ABSENT"
    assert (ABSENT == ABSENT) is True
    assert (ABSENT != ABSENT) is False


def test_require_raises_and_the_error_names_the_reason_not_the_value():
    r = repo()
    with pytest.raises(FeatureUnavailableError) as excinfo:
        r.require("creatinine")
    assert excinfo.value.reason_code == "IMPLAUSIBLE_VALUE_HIGH"
    # The message reaches logs and HTTP responses: no value may be in it.
    assert "9999" not in str(excinfo.value)


def test_get_or_none_is_the_only_way_to_get_none_and_it_must_be_asked_for():
    r = repo()
    assert r.get_or_none("vitamin_d") is None
    assert r.get("vitamin_d", default=None) is None
    assert is_absent(r.get("vitamin_d"))


def test_an_unknown_feature_name_is_a_different_failure_from_an_absent_value():
    r = repo()
    for call in (
        lambda: r.get("banana"),
        lambda: r.has("banana"),
        lambda: r.require("banana"),
        lambda: r.unit("banana"),
        lambda: r.why_unavailable("banana"),
        lambda: r.tristate("banana"),
    ):
        with pytest.raises(UnknownFeatureError):
            call()


# --------------------------------------------------------------------------
# ABSENT vs FALSE vs ZERO -- tri-states and numerics
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["hypertension", "heart_disease"])
def test_tristate_keeps_true_false_and_unknown_apart(name):
    present_false = repo(validated({name: vf(name, False)}))
    present_true = repo(validated({name: vf(name, True)}))
    absent = repo(validated({}))

    assert present_false.tristate(name) is False
    assert present_true.tristate(name) is True
    assert absent.tristate(name) is None

    # And the distinction is visible without `tristate` too.
    assert present_false.has(name) is True
    assert absent.has(name) is False
    assert present_false.require(name) is False
    assert is_absent(absent.get(name))


@pytest.mark.parametrize("name", ["hypertension", "heart_disease"])
def test_an_absent_tristate_is_never_reported_as_a_negative_finding(name):
    r = repo(validated({}))
    assert name not in r.values()
    assert name in r.missing()
    assert r.values().get(name, "sentinel") == "sentinel"
    assert r.why_unavailable(name).availability == AVAILABILITY_NOT_REPORTED


def test_tristate_refuses_to_be_pointed_at_a_number():
    """A numeric zero must never be readable through the boolean accessor."""
    r = repo(validated({"blood_glucose": vf("blood_glucose", 0.0)}))
    with pytest.raises(FeatureTypeError):
        r.tristate("blood_glucose")


def test_a_stored_zero_is_a_value_and_an_absent_number_is_not():
    zero = repo(validated({"blood_glucose": vf("blood_glucose", 0.0)}))
    absent = repo(validated({}))

    assert zero.has("blood_glucose") is True
    assert zero.require("blood_glucose") == 0.0
    assert zero.numeric("blood_glucose") == 0.0
    assert zero.values()["blood_glucose"] == 0.0

    assert absent.has("blood_glucose") is False
    assert is_absent(absent.numeric("blood_glucose"))
    assert "blood_glucose" not in absent.values()


def test_numeric_refuses_to_turn_a_boolean_into_one_or_zero():
    r = repo(validated({"heart_disease": vf("heart_disease", True)}))
    with pytest.raises(FeatureTypeError):
        r.numeric("heart_disease")


def test_numeric_refuses_a_value_that_is_not_in_its_canonical_unit():
    r = repo(
        validated(
            {"hba1c": vf("hba1c", 48.0, canonical_unit=False, unit="mmol/mol")}
        )
    )
    assert r.has("hba1c") is True  # still stored, still readable as raw
    assert r.require("hba1c") == 48.0
    assert r.canonical_unit("hba1c") is False
    with pytest.raises(FeatureTypeError):
        r.numeric("hba1c")


def test_absent_is_distinct_from_present_across_the_whole_catalogue():
    r = repo()
    assert set(r.available()) | set(r.missing()) == set(CANONICAL_FEATURES)
    assert set(r.available()) & set(r.missing()) == set()
    for name in r.missing():
        assert is_absent(r.get(name))
        assert r.why_unavailable(name) is not None
    for name in r.available():
        assert not is_absent(r.get(name))
        assert r.why_unavailable(name) is None


# --------------------------------------------------------------------------
# REJECTED features are not readable as values
# --------------------------------------------------------------------------


def test_a_rejected_feature_is_not_readable_as_a_usable_value():
    r = repo()
    assert r.has("creatinine") is False
    assert "creatinine" not in r.values()
    assert "creatinine" not in r.available()
    assert "creatinine" in r.missing()
    assert is_absent(r.get("creatinine"))
    assert is_absent(r.numeric("creatinine"))
    assert is_absent(r.unit("creatinine"))
    assert is_absent(r.feature("creatinine"))
    with pytest.raises(FeatureUnavailableError):
        r.require("creatinine")


def test_the_rejected_value_has_no_field_to_be_read_from():
    """Structural, in the way `ValidatedFeaturesInput` has no `rejected`."""
    assert "value" not in UnavailableFeature.model_fields
    from app.schemas.repository import IncomingRejection

    assert "value" not in IncomingRejection.model_fields


def test_the_rejected_value_is_dropped_at_the_parse_boundary():
    r = repo()
    entry = r.why_unavailable("creatinine")
    assert entry.availability == AVAILABILITY_REJECTED
    assert entry.reason_code == "IMPLAUSIBLE_VALUE_HIGH"
    assert not hasattr(entry, "value")
    # The number 9999 must not survive as a value anywhere in the stored maps.
    stored = r.snapshot.model_dump(mode="json")
    assert "creatinine" not in stored["features"]
    assert "value" not in stored["unavailable"]["creatinine"]


def test_the_rejection_reason_is_still_retrievable_for_module_20():
    r = repo()
    entry = r.why_unavailable("creatinine")
    assert entry.reason
    # Provenance is kept so the refusal can be explained against the printed
    # line -- explanation metadata, reached only through `provenance`.
    assert entry.provenance.original_test_name == "Creatinine"
    assert r.rejected() == ("creatinine",)
    assert r.availability("creatinine") == AVAILABILITY_REJECTED


def test_a_feature_in_both_partitions_resolves_to_unavailable_not_usable():
    """If Module 6's disjointness ever broke, the safe answer is 'no value'."""
    payload = validated({"creatinine": vf("creatinine", 1.0)}, {"creatinine": rf("creatinine", 9999.0)})
    r = load_features(payload, store=False)
    assert r.has("creatinine") is False
    assert r.is_rejected("creatinine") is True
    assert any("valid and rejected" in w for w in r.snapshot.warnings)


def test_an_all_rejected_input_yields_an_empty_but_explaining_repository():
    payload = validated({}, {"creatinine": rf("creatinine", 9999.0), "hba1c": rf("hba1c", 500.0)})
    r = load_features(payload, store=False)
    assert r.values() == {}
    assert len(r) == 0
    assert set(r.rejected()) == {"creatinine", "hba1c"}
    assert r.summary().feature_count == 0
    assert r.summary().rejected_count == 2
    for name in CANONICAL_FEATURES:
        assert r.why_unavailable(name) is not None


# --------------------------------------------------------------------------
# PROVENANCE
# --------------------------------------------------------------------------


def test_provenance_survives_intact_and_unflattened():
    r = repo()
    provenance = r.provenance("hba1c")
    assert isinstance(provenance, FeatureProvenance)
    assert provenance.original_test_name == "HbA1c"
    assert provenance.original_value_raw == "6.8"
    assert provenance.page_number == 1
    assert provenance.confidence == 0.94
    assert r.require_provenance("hba1c") == provenance


def test_provenance_of_an_absent_feature_is_absent_not_an_empty_object():
    r = repo()
    assert is_absent(r.provenance("vitamin_d"))
    with pytest.raises(FeatureUnavailableError):
        r.require_provenance("vitamin_d")


def test_provenance_round_trips_through_json_unchanged():
    r = repo()
    rebuilt = FeatureSnapshot.model_validate(
        json.loads(json.dumps(r.snapshot.model_dump(mode="json")))
    )
    assert (
        rebuilt.features["hba1c"].provenance == r.snapshot.features["hba1c"].provenance
    )


# --------------------------------------------------------------------------
# ACCESSORS
# --------------------------------------------------------------------------


def test_reading_a_feature_needs_no_knowledge_of_where_it_came_from():
    r = repo()
    # Lab value and profile value read identically.
    assert r.require("hba1c") == 6.8
    assert r.require("age") == 45


def test_but_the_source_can_still_be_asked_for():
    r = repo()
    assert r.source("hba1c") == "lab_report"
    assert r.source("age") == "patient_profile"
    assert r.from_source("patient_profile") == ("age", "heart_disease", "gender")
    assert set(r.from_source("lab_report")) == {"hba1c", "blood_glucose", "hemoglobin"}
    assert is_absent(r.source("vitamin_d"))


def test_unit_accessors():
    r = repo()
    assert r.unit("hba1c") == "%"
    assert r.unit("blood_glucose") == "mg/dl"
    # A present boolean legitimately has no unit -- which is why absence is
    # NOT signalled with None here.
    assert r.unit("heart_disease") is None
    assert is_absent(r.unit("vitamin_d"))
    assert r.canonical_unit("hba1c") is True
    assert r.units()["hba1c"] == "%"


def test_feature_record_and_quality_flags():
    r = repo()
    record = r.require_feature("hemoglobin")
    assert isinstance(record, StoredFeature)
    assert record.questionable is True
    assert r.is_questionable("hemoglobin") is True
    assert r.is_questionable("hba1c") is False
    # An ABSENT feature is not "flagged" -- it is not there at all.
    assert r.is_questionable("vitamin_d") is False
    assert r.questionable() == ("hemoglobin",)


def test_clinically_extreme_is_carried_but_stays_usable():
    payload = validated(
        {"blood_glucose": vf("blood_glucose", 400.0, extreme=True, direction="high")}
    )
    r = load_features(payload, store=False)
    assert r.has("blood_glucose") is True
    assert r.require("blood_glucose") == 400.0
    assert r.clinically_extreme() == ("blood_glucose",)
    assert r.is_clinically_extreme("blood_glucose") is True


def test_the_whole_usable_set_comes_back_in_one_call():
    r = repo()
    assert r.values() == {
        "hba1c": 6.8,
        "blood_glucose": 112.0,
        "hemoglobin": 14.2,
        "age": 45,
        "gender": "male",
        "heart_disease": False,
    }
    assert len(r) == 6
    assert "hba1c" in r
    assert "creatinine" not in r
    assert list(r) == list(r.available())


def test_available_and_missing_are_in_catalogue_order():
    r = repo()
    assert list(r.available()) == [n for n in CANONICAL_FEATURES if n in r.values()]
    assert list(r.missing()) == [
        n for n in CANONICAL_FEATURES if n not in r.values()
    ]


def test_repr_leaks_no_values_and_no_patient_reference():
    r = repo(patient_ref="patient-42")
    text = repr(r)
    assert "patient-42" not in text
    assert "6.8" not in text
    assert "hba1c" not in text


# --------------------------------------------------------------------------
# WARNINGS and UPSTREAM
# --------------------------------------------------------------------------


def test_all_warnings_are_carried_with_their_origins():
    payload = validated(
        {"hba1c": vf("hba1c", 6.8)},
        all_warnings=[
            {"stage": "extraction", "module": 4, "message": "page 2 unreadable"},
            {"stage": "feature_engineering", "module": 5, "message": "unit assumed"},
            {"stage": "validation", "module": 6, "message": "low confidence"},
        ],
    )
    r = load_features(payload, store=False)
    assert [(w.stage, w.module, w.message) for w in r.warnings()] == [
        ("extraction", 4, "page 2 unreadable"),
        ("feature_engineering", 5, "unit assumed"),
        ("validation", 6, "low confidence"),
    ]


def test_warnings_are_rebuilt_when_all_warnings_was_not_supplied():
    payload = validated(
        {"hba1c": vf("hba1c", 6.8)},
        upstream_warnings=[
            {"stage": "extraction", "module": 4, "message": "repaired page 1"}
        ],
        warnings=["hba1c unit was assumed"],
    )
    r = load_features(payload, store=False)
    stages = [(w.stage, w.message) for w in r.warnings()]
    assert ("extraction", "repaired page 1") in stages
    assert ("validation", "hba1c unit was assumed") in stages


def test_module_7_stamps_its_own_warnings_without_touching_upstream_ones():
    payload = validated(
        {"hba1c": vf("hba1c", 6.8)},
        all_warnings=[{"stage": "extraction", "module": 4, "message": "repaired"}],
    )
    payload["valid"]["not_a_feature"] = vf("hba1c", 1.0)
    payload["valid"]["not_a_feature"]["name"] = "not_a_feature"
    r = load_features(payload, store=False)
    origins = [(w.stage, w.module) for w in r.warnings()]
    assert ("extraction", 4) in origins
    assert ("repository", 7) in origins
    assert r.has("hba1c") is True


def test_upstream_context_is_carried_through_unchanged():
    payload = validated(
        {"hba1c": vf("hba1c", 6.8)},
        upstream={
            "provided": True,
            "extraction_confidence": 0.71,
            "pages": [
                {"page_number": 1, "raw_text_available": True},
                {"page_number": 2, "raw_text_available": False},
            ],
            "pages_unreadable": [2],
            "warning_count": 1,
        },
    )
    r = load_features(payload, store=False)
    assert r.extraction_confidence == 0.71
    assert r.pages_unreadable == [2]
    assert r.partial_document is True
    assert r.upstream().pages[1].raw_text_available is False
    assert r.summary().pages_unreadable_count == 1


def test_a_partial_document_changes_why_a_feature_is_missing():
    """An unread row is not the same finding as an absent test."""
    clean = load_features(validated({}), store=False)
    damaged = load_features(
        validated({}, upstream={"provided": True, "pages_unreadable": [2]}),
        store=False,
    )
    assert clean.why_unavailable("hba1c").reason_code == REASON_NOT_REPORTED
    assert (
        damaged.why_unavailable("hba1c").reason_code
        == REASON_NOT_REPORTED_PARTIAL_DOCUMENT
    )
    assert "UNREAD" in damaged.why_unavailable("hba1c").reason


def test_module_6_missing_features_list_is_preserved_verbatim():
    payload = validated({"hba1c": vf("hba1c", 6.8)}, missing_features=["vitamin_d"])
    r = load_features(payload, store=False)
    assert r.snapshot.missing_features == ["vitamin_d"]
    # And the authoritative "can I read it?" answer is still complete.
    assert "vitamin_b12" in r.missing()


# --------------------------------------------------------------------------
# EMPTY input
# --------------------------------------------------------------------------


def test_an_empty_input_gives_an_empty_repository_that_still_answers():
    r = FeatureRepository.empty()
    assert r.values() == {}
    assert r.available() == ()
    assert set(r.missing()) == set(CANONICAL_FEATURES)
    assert r.warnings() == []
    assert r.summary().feature_count == 0
    assert r.tristate("hypertension") is None
    for name in CANONICAL_FEATURES:
        assert r.why_unavailable(name).availability == AVAILABILITY_NOT_REPORTED


def test_load_features_with_no_argument_at_all():
    r = load_features()
    assert len(r) == 0
    assert r.snapshot_id


# --------------------------------------------------------------------------
# MULTIPLE SNAPSHOTS PER PATIENT (the Modules 28-30 groundwork)
# --------------------------------------------------------------------------


def snap(value: float, date: str, patient: str = "p1") -> FeatureRepository:
    return load_features(
        validated({"hba1c": vf("hba1c", value)}),
        patient_ref=patient,
        report_date=date,
    )


def test_several_snapshots_per_patient_are_held_and_returned_in_order():
    snap(6.8, "2024-09-01")
    snap(6.1, "2024-01-15")
    snap(6.4, "2024-05-20")

    timeline = history("p1")
    assert [r.require("hba1c") for r in timeline] == [6.1, 6.4, 6.8]
    assert [r.report_date.date().isoformat() for r in timeline] == [
        "2024-01-15",
        "2024-05-20",
        "2024-09-01",
    ]


def test_the_latest_snapshot_is_the_one_with_the_latest_report_date():
    snap(6.1, "2024-01-15")
    snap(6.8, "2024-09-01")
    snap(6.4, "2024-05-20")
    assert latest("p1").require("hba1c") == 6.8


def test_snapshots_of_different_patients_do_not_mix():
    snap(6.8, "2024-09-01", patient="p1")
    snap(5.1, "2024-09-01", patient="p2")
    assert [r.require("hba1c") for r in history("p1")] == [6.8]
    assert [r.require("hba1c") for r in history("p2")] == [5.1]
    assert history("p3") == []
    assert latest("p3") is None


def test_undated_snapshots_fall_back_to_record_time_and_stay_ordered():
    first = load_features(validated({"hba1c": vf("hba1c", 6.1)}), patient_ref="p1")
    second = load_features(validated({"hba1c": vf("hba1c", 6.4)}), patient_ref="p1")
    third = load_features(validated({"hba1c": vf("hba1c", 6.8)}), patient_ref="p1")
    assert [r.snapshot_id for r in history("p1")] == [
        first.snapshot_id,
        second.snapshot_id,
        third.snapshot_id,
    ]


def test_snapshots_sharing_an_ordering_timestamp_stay_in_insertion_order():
    same = "2024-03-12T00:00:00+00:00"
    ids = [snap(v, same).snapshot_id for v in (6.1, 6.4, 6.8)]
    assert [r.snapshot_id for r in history("p1")] == ids
    assert [r.require("hba1c") for r in history("p1")] == [6.1, 6.4, 6.8]


def test_report_date_is_normalised_to_utc_so_snapshots_are_always_comparable():
    naive = load_features(validated({}), patient_ref="p1", report_date=datetime(2024, 3, 12))
    aware = load_features(
        validated({}),
        patient_ref="p1",
        report_date=datetime(2024, 6, 1, tzinfo=timezone(timedelta(hours=5, minutes=30))),
    )
    assert naive.report_date.tzinfo is not None
    assert aware.report_date.tzinfo is not None
    assert [r.snapshot_id for r in history("p1")] == [
        naive.snapshot_id,
        aware.snapshot_id,
    ]


def test_a_snapshot_can_be_fetched_back_by_its_id():
    stored = snap(6.8, "2024-09-01")
    fetched = get_snapshot(stored.snapshot_id)
    assert fetched is not None
    assert fetched.require("hba1c") == 6.8
    assert get_snapshot("no-such-id") is None


def test_supplying_a_snapshot_id_overwrites_rather_than_duplicating():
    first = load_features(
        validated({"hba1c": vf("hba1c", 6.1)}), patient_ref="p1", snapshot_id="fixed"
    )
    assert first.snapshot_id == "fixed"
    load_features(
        validated({"hba1c": vf("hba1c", 6.8)}), patient_ref="p1", snapshot_id="fixed"
    )
    assert len(history("p1")) == 1
    assert get_snapshot("fixed").require("hba1c") == 6.8


def test_references_expose_identity_and_shape_but_no_values():
    snap(6.8, "2024-09-01")
    listing = references("p1")
    assert len(listing) == 1
    payload = json.dumps(listing[0].model_dump(mode="json"))
    assert "6.8" not in payload
    assert listing[0].available == ["hba1c"]
    assert listing[0].summary.feature_count == 1


def test_store_false_builds_a_repository_without_persisting_it():
    r = load_features(validated({"hba1c": vf("hba1c", 6.8)}), patient_ref="p1", store=False)
    assert r.require("hba1c") == 6.8
    assert history("p1") == []
    assert default_backend().count() == 0


# --------------------------------------------------------------------------
# The repository as the SINGLE ACCESS POINT for the analysis modules
# --------------------------------------------------------------------------


def test_the_stored_set_feeds_the_rule_engine_without_re_extraction():
    from app.services.rule_engine import evaluate_rules

    r = repo()
    result = evaluate_rules(r.to_validated_input())
    assert result.decisions
    assert all(d.condition for d in result.decisions)


def test_the_stored_set_feeds_the_ml_engine_without_re_extraction():
    from app.ml.engine import predict_all

    r = repo()
    result = predict_all(r.to_validated_input())
    assert result is not None


def test_what_is_handed_to_consumers_carries_no_rejected_values():
    from app.schemas.rules import ValidatedFeaturesInput

    handed = repo().to_validated_input()
    assert "rejected" not in handed
    parsed = ValidatedFeaturesInput.model_validate(handed)
    assert "creatinine" not in parsed.valid
    assert set(parsed.valid) == {
        "hba1c",
        "blood_glucose",
        "hemoglobin",
        "age",
        "gender",
        "heart_disease",
    }


def test_what_is_handed_to_consumers_keeps_questionable_and_warnings():
    handed = repo().to_validated_input()
    assert set(handed["questionable"]) == {"hemoglobin"}
    assert isinstance(handed["all_warnings"], list)
    assert handed["upstream"]["provided"] is True


# --------------------------------------------------------------------------
# Snapshot integrity and introspection
# --------------------------------------------------------------------------


def test_the_snapshot_maps_are_disjoint_by_construction():
    r = repo()
    assert set(r.snapshot.features) & set(r.snapshot.unavailable) == set()
    with pytest.raises(ValueError):
        FeatureSnapshot(
            features={"hba1c": StoredFeature(
                name="hba1c", value=6.8, source="lab_report",
                provenance=FeatureProvenance(source="lab_report"),
            )},
            unavailable={"hba1c": UnavailableFeature(
                name="hba1c", availability=AVAILABILITY_REJECTED,
                reason_code="X", reason="y",
            )},
        )


def test_a_snapshot_rejects_a_non_canonical_feature_key():
    with pytest.raises(ValueError):
        FeatureSnapshot(
            features={"banana": StoredFeature(
                name="banana", value=1.0, source="lab_report",
                provenance=FeatureProvenance(source="lab_report"),
            )}
        )


def test_a_snapshot_rejects_a_key_that_disagrees_with_the_feature_name():
    with pytest.raises(ValueError):
        FeatureSnapshot(
            features={"hba1c": StoredFeature(
                name="blood_glucose", value=6.8, source="lab_report",
                provenance=FeatureProvenance(source="lab_report"),
            )}
        )


def test_an_unusable_value_in_the_valid_map_never_becomes_a_stored_value():
    payload = validated({"hba1c": vf("hba1c", 6.8)})
    payload["valid"]["blood_glucose"] = vf("blood_glucose", None)
    r = load_features(payload, store=False)
    assert r.has("blood_glucose") is False
    assert is_absent(r.get("blood_glucose"))
    assert r.availability("blood_glucose") == "unusable"
    assert r.has("hba1c") is True  # the rest of the payload survives


def test_the_interface_document_is_shape_only():
    document = repository_document()
    assert document["module"] == 7
    assert document["canonical_features"] == list(CANONICAL_FEATURES)
    assert document["absent_sentinel"] == "ABSENT"
    assert "get" in document["accessors"] and "require" in document["accessors"]


def test_the_snapshot_round_trips_through_json_completely():
    r = repo(patient_ref="p1", report_date="2024-03-12")
    payload = json.dumps(r.snapshot.model_dump(mode="json"))
    rebuilt = FeatureRepository(FeatureSnapshot.model_validate(json.loads(payload)))
    assert rebuilt.values() == r.values()
    assert rebuilt.rejected() == r.rejected()
    assert rebuilt.warnings() == r.warnings()
    assert rebuilt.identity.patient_ref == "p1"


def test_a_caller_cannot_corrupt_the_store_by_mutating_what_it_got_back():
    stored = snap(6.8, "2024-09-01")
    stored.snapshot.features.pop("hba1c")
    assert get_snapshot(stored.snapshot_id).require("hba1c") == 6.8


def test_an_explicit_backend_is_used_instead_of_the_process_default():
    private = InMemoryRepositoryBackend()
    load_features(validated({"hba1c": vf("hba1c", 6.8)}), patient_ref="p1", backend=private)
    assert private.count() == 1
    assert default_backend().count() == 0
    assert history("p1", backend=private)[0].require("hba1c") == 6.8


def test_the_default_backend_can_be_swapped_without_touching_consumers():
    private = InMemoryRepositoryBackend()
    set_default_backend(private)
    load_features(validated({"hba1c": vf("hba1c", 6.8)}), patient_ref="p1")
    assert private.count() == 1
    assert latest("p1").require("hba1c") == 6.8


# --------------------------------------------------------------------------
# PHI must never reach the logs
# --------------------------------------------------------------------------


def test_storing_a_snapshot_logs_no_values_names_or_identifiers(caplog):
    payload = validated(
        {"hba1c": vf("hba1c", 6.8, test_name="CANARY-TEST-NAME")},
        {"creatinine": rf("creatinine", 424242.0)},
    )
    with caplog.at_level("DEBUG"):
        load_features(payload, patient_ref="CANARY-PATIENT-REF", report_ref="CANARY-REPORT")
    text = caplog.text
    for canary in ("CANARY-TEST-NAME", "CANARY-PATIENT-REF", "CANARY-REPORT",
                   "424242", "6.8", "hba1c", "creatinine"):
        assert canary not in text, f"{canary!r} reached the logs"


def test_error_messages_carry_no_medical_values(caplog):
    payload = validated({}, {"creatinine": rf("creatinine", 424242.0)})
    r = load_features(payload, store=False)
    with pytest.raises(FeatureUnavailableError) as excinfo:
        r.require("creatinine")
    assert "424242" not in str(excinfo.value)
    with pytest.raises(AbsentValueError) as absent:
        bool(r.get("creatinine"))
    assert "424242" not in str(absent.value)


def test_build_snapshot_stores_nothing():
    snapshot = build_snapshot(validated({"hba1c": vf("hba1c", 6.8)}), patient_ref="p1")
    assert isinstance(snapshot, FeatureSnapshot)
    assert default_backend().count() == 0
