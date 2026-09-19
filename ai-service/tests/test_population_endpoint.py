"""Module 31 over HTTP -- `POST /api/v1/population/context`, `GET .../policy`.

The router is a thin wrapper, so this file tests the things a wrapper can get
wrong and the service cannot:

  * AUTH. `/context` carries medical values and is therefore PHI-bearing.
    `tests/test_auth.py` walks the route tree and would catch a missing
    dependency; this file additionally checks that a real unauthenticated call
    is actually refused, and that `/policy` -- which carries no patient data --
    is behind the same key because the whole `/api/v1` surface is.

  * THE ENVELOPE. `{success, data}` on success, `{success, error}` on
    rejection, like every other endpoint in this service.

  * A REFUSAL IS A 200. "No population group matches you" is the answer
    Module 31 was built to give, not an error. A 4xx here would make a backend
    render an outage where the truth was a documented absence.

  * WHAT IS ACTUALLY A 422: a malformed request that has no honest answer --
    two sources for the same value, no source at all, or the same feature
    twice. Everything else (a bad unit, a non-numeric value, an unknown
    feature name) is answered per feature and must NOT discard the request.

  * THE SERIALISED SHAPE. `response_model_exclude_none=False`, so an
    unavailable entry serialises `"comparison": null` -- and null is the whole
    point: there is no object there for a percentile to be in.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

import pytest
from fastapi.testclient import TestClient

from app.core.auth import SERVICE_KEY_HEADER
from app.data.feature_catalog import CANONICAL_FEATURES
from app.population.policy import EXCLUDED_FEATURES, REASON_CODES
from app.population.tables import COVERED_FEATURES, TABLES
from tests.conftest import TEST_SERVICE_KEY

CONTEXT = "/api/v1/population/context"
POLICY = "/api/v1/population/policy"

GOOD_VALUE = {
    "hba1c": 5.5,
    "hemoglobin": 14.0,
    "vitamin_d": 70.0,
    "vitamin_b12": 450.0,
    "creatinine": 0.9,
    "cholesterol": 190.0,
    "bmi": 27.0,
    # ---- the complete blood count ----
    # Near the published median for the 40-49 cohorts, in the TABLE's own
    # unit. Total over COVERED_FEATURES by design: a new table with no row
    # here fails with a KeyError rather than being skipped.
    "hematocrit": 42.0,
    "rbc_count": 4.7,
    "mcv": 89.0,
    "mch": 30.0,
    "mchc": 33.5,
    "wbc_count": 7.0,
    "neutrophils": 58.0,
    "lymphocytes": 30.0,
    "monocytes": 7.5,
    "eosinophils": 2.5,
    "basophils": 0.7,
    "platelet_count": 250.0,
}


def measurement(feature: str, **overrides: Any) -> Dict[str, Any]:
    payload = {
        "feature": feature,
        "value": GOOD_VALUE[feature],
        "unit": TABLES[feature].unit,
    }
    payload.update(overrides)
    return payload


def body(measurements: List[Dict[str, Any]], **kwargs: Any) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"age": 45, "gender": "male", "measurements": measurements}
    payload.update(kwargs)
    return payload


def numbers_in(blob: Any) -> List[float]:
    found: List[float] = []
    if isinstance(blob, dict):
        for value in blob.values():
            found.extend(numbers_in(value))
    elif isinstance(blob, list):
        for value in blob:
            found.extend(numbers_in(value))
    elif isinstance(blob, bool):
        pass
    elif isinstance(blob, (int, float)):
        found.append(float(blob))
    return found


# --------------------------------------------------------------------------
# Authentication
# --------------------------------------------------------------------------


@pytest.mark.parametrize("path", [CONTEXT, POLICY])
def test_both_endpoints_refuse_an_unauthenticated_call(authed_client, path):
    """`/context` carries medical values; `/policy` is behind the same key
    because the whole `/api/v1` surface is."""
    response = (
        authed_client.post(path, json=body([measurement("hba1c")]))
        if path == CONTEXT
        else authed_client.get(path)
    )
    assert response.status_code == 401
    assert response.json()["success"] is False


@pytest.mark.parametrize("key", ["", "   ", "wrong-key", TEST_SERVICE_KEY + "x"])
def test_a_wrong_key_is_refused_and_never_echoed(authed_client, key):
    response = authed_client.post(
        CONTEXT,
        json=body([measurement("hba1c")]),
        headers={SERVICE_KEY_HEADER: key},
    )
    assert response.status_code == 401
    assert key.strip() not in response.text or not key.strip()


def test_the_correct_key_is_accepted_on_both_endpoints(authed_client):
    headers = {SERVICE_KEY_HEADER: TEST_SERVICE_KEY}
    assert authed_client.get(POLICY, headers=headers).status_code == 200
    assert (
        authed_client.post(
            CONTEXT, json=body([measurement("hba1c")]), headers=headers
        ).status_code
        == 200
    )


def test_authentication_is_checked_before_the_body_is_read(authed_client):
    """An unauthenticated caller learns nothing about the request contract."""
    response = authed_client.post(CONTEXT, json={"garbage": True})
    assert response.status_code == 401


# --------------------------------------------------------------------------
# The success envelope
# --------------------------------------------------------------------------


def test_a_successful_call_returns_the_services_standard_envelope(client):
    response = client.post(CONTEXT, json=body([measurement("hba1c")]))
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    data = payload["data"]
    assert data["module"] == 31
    assert data["policy_version"]
    assert set(data) == {
        "patient_ref",
        "module",
        "policy_version",
        "generated_at",
        "subject",
        "features",
        "summary",
        "what_this_means",
        "what_this_does_not_mean",
        "limitations",
        "disclaimer",
        "warnings",
    }


def test_the_full_comparison_survives_serialisation_intact(client):
    """The band must be checkable from the JSON, not only from the model."""
    response = client.post(CONTEXT, json=body([measurement("vitamin_d", value=30, unit="ng/mL")]))
    comparison = response.json()["data"]["features"]["vitamin_d"]["comparison"]
    assert comparison["unit"] == "nmol/l"
    assert comparison["value"] == pytest.approx(74.88, abs=0.005)
    assert comparison["submitted"] == {"value": 30.0, "unit": "ng/ml"}
    assert len(comparison["percentile_grid"]) == len(
        comparison["cohort_percentile_values"]
    )
    assert comparison["table"]["data_file_sha256"]
    assert comparison["table"]["citation"]
    assert comparison["cohort"]["n_unweighted"] > 0
    assert set(comparison["band"]) == {
        "position",
        "lower_percentile",
        "upper_percentile",
        "lower_value",
        "upper_value",
        "label",
    }


# --------------------------------------------------------------------------
# A refusal is a 200
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload,expected",
    [
        (body([measurement("hba1c")], gender="other"), "SEX_COHORT_NOT_AVAILABLE"),
        (body([measurement("hba1c")], age=None), "AGE_NOT_PROVIDED"),
        (body([measurement("hba1c")], age=9), "AGE_BELOW_ADULT_TABLE"),
        (body([measurement("hba1c", value="Not Detected")]), "VALUE_NOT_NUMERIC"),
        (body([measurement("hba1c", unit=None)]), "UNIT_NOT_PROVIDED"),
        (body([measurement("hba1c", unit="bananas")]), "UNIT_NOT_RECOGNISED"),
        (body([measurement("hba1c", unit="mg/dl")]), "UNIT_NOT_CONVERTIBLE"),
    ],
)
def test_every_refusal_is_a_200_with_a_reason_code(client, payload, expected):
    """A 4xx would make a backend render an outage where the truth was a
    documented absence -- the answer Module 31 was built to give."""
    response = client.post(CONTEXT, json=payload)
    assert response.status_code == 200
    entry = response.json()["data"]["features"]["hba1c"]
    assert entry["available"] is False
    assert entry["reason_code"] == expected
    assert entry["message"].strip()


def test_an_unavailable_entry_serialises_a_null_comparison_and_no_number(client):
    """`response_model_exclude_none=False` keeps the key -- and null is the
    point: there is no object there for a percentile to be in."""
    response = client.post(CONTEXT, json=body([measurement("hba1c")], gender="other"))
    entry = response.json()["data"]["features"]["hba1c"]
    assert "comparison" in entry
    assert entry["comparison"] is None
    assert numbers_in(entry) == []


def test_a_whole_unmatched_response_carries_no_population_number(client):
    """The end-to-end no-value guarantee, over the wire."""
    response = client.post(
        CONTEXT,
        json=body(
            [measurement(name) for name in COVERED_FEATURES],
            age=None,
            gender="prefer_not_to_say",
        ),
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["summary"]["available"] == 0
    for entry in data["features"].values():
        assert entry["comparison"] is None
        assert numbers_in(entry) == []
    assert "cohort_id" not in response.text
    assert "percentile_values" not in response.text


def test_an_excluded_feature_is_a_200_with_its_own_reason(client):
    response = client.post(
        CONTEXT, json=body([{"feature": "blood_glucose", "value": 100, "unit": "mg/dl"}])
    )
    assert response.status_code == 200
    entry = response.json()["data"]["features"]["blood_glucose"]
    assert entry["reason_code"] == "NO_VERIFIED_DISTRIBUTION"
    assert entry["message"] == EXCLUDED_FEATURES["blood_glucose"]["message"]


def test_an_unknown_feature_name_does_not_discard_the_rest_of_the_request(client):
    """One odd row must not turn into an opaque 422 that throws away seven
    perfectly good values."""
    response = client.post(
        CONTEXT,
        json=body([measurement("hba1c"), {"feature": "banana", "value": 1, "unit": "%"}]),
    )
    assert response.status_code == 200
    features = response.json()["data"]["features"]
    assert features["hba1c"]["available"] is True
    assert features["banana"]["reason_code"] == "UNKNOWN_FEATURE"


@pytest.mark.parametrize("code", sorted(REASON_CODES))
def test_no_reason_code_the_schema_accepts_is_missing_from_the_policy(client, code):
    """A code the router could emit with no published wording would reach a
    client as a bare identifier."""
    document = client.get(POLICY).json()["data"]
    assert code in document["policy"]["reason_codes"]


# --------------------------------------------------------------------------
# What IS a 422
# --------------------------------------------------------------------------


def test_sending_both_measurements_and_a_snapshot_is_a_422(client):
    """Two sources for the same feature would make the answer depend on which
    one the service happened to read first."""
    response = client.post(
        CONTEXT,
        json={
            "age": 45,
            "gender": "male",
            "measurements": [measurement("hba1c")],
            "snapshot": {"features": {}},
        },
    )
    assert response.status_code == 422
    assert response.json() == {
        "success": False,
        "error": {"code": "INVALID_REQUEST", "message": "The request was not valid."},
    }


def test_sending_neither_source_is_a_422(client):
    """An empty request would return an empty answer that looks like a fault."""
    assert client.post(CONTEXT, json={"age": 45, "gender": "male"}).status_code == 422
    assert client.post(CONTEXT, json={"measurements": []}).status_code == 422
    assert client.post(CONTEXT, json={}).status_code == 422


def test_the_same_feature_twice_is_a_422(client):
    """Picking one silently would hide the disagreement between them."""
    response = client.post(
        CONTEXT,
        json=body([measurement("hba1c"), measurement("hba1c", value=9.9)]),
    )
    assert response.status_code == 422


def test_a_duplicate_is_rejected_even_when_the_two_values_agree(client):
    response = client.post(
        CONTEXT, json=body([measurement("bmi"), measurement("bmi")])
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        {"age": -1},
        {"age": 500},
        {"age": "middle-aged"},
        {"gender": "x" * 40},
        {"patient_ref": "p" * 200},
    ],
)
def test_a_field_outside_its_declared_bounds_is_a_422(client, payload):
    response = client.post(CONTEXT, json=body([measurement("hba1c")], **payload))
    assert response.status_code == 422


def test_more_measurements_than_the_cap_is_a_422(client):
    response = client.post(
        CONTEXT,
        json=body([{"feature": f"f{i}", "value": 1, "unit": "%"} for i in range(65)]),
    )
    assert response.status_code == 422


def test_a_measurement_with_no_feature_name_is_a_422(client):
    response = client.post(CONTEXT, json=body([{"value": 1, "unit": "%"}]))
    assert response.status_code == 422
    response = client.post(CONTEXT, json=body([{"feature": "", "value": 1}]))
    assert response.status_code == 422


def test_a_relayed_envelope_is_unwrapped_rather_than_read_as_empty(client):
    """The Node backend relays `{data: {...}}`; that must not be a 422."""
    response = client.post(
        CONTEXT,
        json={
            "age": 45,
            "gender": "female",
            "data": {"measurements": [measurement("hba1c")]},
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["subject"]["sex_cohort"] == "female"
    assert data["features"]["hba1c"]["available"] is True


# --------------------------------------------------------------------------
# GET /policy
# --------------------------------------------------------------------------


def test_the_policy_endpoint_publishes_the_rules_and_the_evidence(client):
    """A percentile is only meaningful if a reader can see which population
    it describes and which file it came from."""
    response = client.get(POLICY)
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    policy = payload["data"]["policy"]
    service = payload["data"]["service"]

    assert policy["module"] == 31
    assert policy["makes_clinical_claims"] is False
    assert policy["calls_an_llm"] is False
    assert policy["percentile_reporting"]["interpolated"] is False
    assert policy["matching"]["unmatched_cohort_offered"] is False

    tables = service["tables"]
    assert sorted(tables["covered_features"]) == sorted(COVERED_FEATURES)
    for name in COVERED_FEATURES:
        entry = tables["tables"][name]
        assert entry["source"]["data_file_sha256"]
        assert entry["source"]["citation"]
        assert entry["cohort_count"] == 14


def test_the_policy_endpoint_names_what_is_not_covered_and_why(client):
    """A module that silently omits a feature is indistinguishable from one
    that forgot it."""
    excluded = client.get(POLICY).json()["data"]["service"]["tables"][
        "excluded_features"
    ]
    assert set(excluded) == set(EXCLUDED_FEATURES)
    assert "fasting" in excluded["blood_glucose"]["message"].lower()
    assert "fasting" in excluded["triglycerides"]["message"].lower()
    covered = client.get(POLICY).json()["data"]["service"]["covered_features"]
    assert set(covered) | set(excluded) == set(CANONICAL_FEATURES)


def test_the_policy_endpoint_returns_no_patient_data(client):
    """It is the reviewer-facing endpoint; it must be safe to share."""
    text = client.get(POLICY).text
    for token in ("patient_ref", "snapshot_id", "Jordan", "value_raw"):
        assert token not in text


def test_the_policy_endpoint_is_stable_across_calls(client):
    """Static, reviewable data -- not a report about a request."""
    first = client.get(POLICY).json()
    second = client.get(POLICY).json()
    assert first == second


def test_the_endpoints_do_not_appear_twice_in_the_route_table():
    """A double mount would make behaviour depend on registration order."""
    from app.main import app

    def walk(routes):
        flat = []
        for route in routes:
            nested = getattr(getattr(route, "original_router", None), "routes", None)
            if nested:
                flat.extend(walk(nested))
            else:
                flat.append(route)
        return flat

    paths = [getattr(r, "path", "") for r in walk(app.routes)]
    assert paths.count(CONTEXT) == 1
    assert paths.count(POLICY) == 1
