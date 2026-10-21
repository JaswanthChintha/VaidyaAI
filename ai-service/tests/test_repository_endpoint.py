from __future__ import annotations

import json
from typing import Any, Dict, Optional

import pytest

from app.core.auth import SERVICE_KEY_HEADER
from app.data.feature_catalog import CANONICAL_FEATURES, FEATURES
from app.services.feature_repository import reset_default_backend
from tests.conftest import TEST_SERVICE_KEY

LOAD = "/api/v1/repository/load"
INTERFACE = "/api/v1/repository/interface"


def _snapshot_url(snapshot_id: str) -> str:
    return f"/api/v1/repository/snapshots/{snapshot_id}"


def _feature_url(snapshot_id: str, name: str) -> str:
    return f"/api/v1/repository/snapshots/{snapshot_id}/features/{name}"


def _patient_url(patient_ref: str) -> str:
    return f"/api/v1/repository/patients/{patient_ref}/snapshots"


@pytest.fixture(autouse=True)
def _mounted():
    from app.api import routes_repository
    from app.main import app

    if not any(
        getattr(route, "path", "").startswith("/api/v1/repository")
        for route in app.routes
    ):
        app.include_router(routes_repository.router)
    reset_default_backend()
    yield
    reset_default_backend()


def vf(name: str, value: Any, **extra: Any) -> Dict[str, Any]:
    definition = FEATURES[name]
    entry = {
        "name": name,
        "value": value,
        "unit": definition.canonical_unit,
        "canonical_unit": True,
        "source": definition.source,
        "provenance": {
            "source": definition.source,
            "original_test_name": "HbA1c" if name == "hba1c" else None,
            "page_number": 1,
        },
        "status": "valid",
        "questionable": False,
        "clinically_extreme": False,
    }
    entry.update(extra)
    return entry


def validated_body(
    features: Optional[Dict[str, Any]] = None,
    rejected: Optional[Dict[str, Any]] = None,
    **overrides: Any,
) -> Dict[str, Any]:
    body: Dict[str, Any] = {
        "valid": features or {},
        "questionable": {},
        "rejected": rejected or {},
        "clinically_extreme": [],
        "missing_features": [],
        "warnings": [],
        "upstream_warnings": [],
        "all_warnings": [],
        "upstream": {"provided": True},
        "summary": {},
    }
    body.update(overrides)
    return body


REJECTED_CREATININE = {
    "creatinine": {
        "name": "creatinine",
        "value": 9999.0,
        "unit": "mg/dl",
        "source": "lab_report",
        "provenance": {"source": "lab_report", "original_test_name": "Creatinine"},
        "status": "rejected",
        "reason_code": "IMPLAUSIBLE_VALUE_HIGH",
        "reason": "Outside the physiologically possible range.",
    }
}


def post_load(client, **kwargs: Any):
    body = {
        "validated": validated_body(
            {"hba1c": vf("hba1c", 6.8)}, REJECTED_CREATININE
        ),
        "patient_ref": "patient-1",
        "report_ref": "report-1",
        "report_date": "2024-03-12",
    }
    body.update(kwargs)
    return client.post(LOAD, json=body)


def test_load_then_read_back_round_trips(client):
    created = post_load(client)
    assert created.status_code == 200, created.text
    payload = created.json()
    assert payload["success"] is True

    snapshot_id = payload["data"]["identity"]["snapshot_id"]
    assert payload["data"]["features"]["hba1c"]["value"] == 6.8
    assert payload["data"]["identity"]["patient_ref"] == "patient-1"
    assert payload["data"]["identity"]["report_date"].startswith("2024-03-12")

    read = client.get(_snapshot_url(snapshot_id))
    assert read.status_code == 200
    assert read.json()["data"]["features"]["hba1c"]["value"] == 6.8


def test_provenance_survives_the_http_boundary(client):
    data = post_load(client).json()["data"]
    provenance = data["features"]["hba1c"]["provenance"]
    assert provenance["original_test_name"] == "HbA1c"
    assert provenance["page_number"] == 1


def test_a_rejected_feature_is_returned_as_a_reason_with_no_value(client):
    data = post_load(client).json()["data"]
    assert "creatinine" not in data["features"]
    entry = data["unavailable"]["creatinine"]
    assert entry["availability"] == "rejected"
    assert entry["reason_code"] == "IMPLAUSIBLE_VALUE_HIGH"
    assert "value" not in entry
    assert "9999" not in json.dumps(data["features"])


def test_reading_one_feature_reports_availability_rather_than_a_default(client):
    snapshot_id = post_load(client).json()["data"]["identity"]["snapshot_id"]

    present = client.get(_feature_url(snapshot_id, "hba1c")).json()["data"]
    assert present["available"] is True
    assert present["feature"]["value"] == 6.8
    assert present["unavailable"] is None

    rejected = client.get(_feature_url(snapshot_id, "creatinine")).json()["data"]
    assert rejected["available"] is False
    assert rejected["feature"] is None
    assert rejected["unavailable"]["reason_code"] == "IMPLAUSIBLE_VALUE_HIGH"

    absent = client.get(_feature_url(snapshot_id, "hypertension")).json()["data"]
    assert absent["available"] is False
    assert absent["feature"] is None
    assert absent["unavailable"]["availability"] == "not_reported"


def test_an_absent_tristate_never_comes_back_as_false_over_http(client):
    snapshot_id = post_load(client).json()["data"]["identity"]["snapshot_id"]
    body = client.get(_feature_url(snapshot_id, "hypertension")).json()
    assert "false" not in json.dumps(body["data"]).lower().replace(
        '"available": false', ""
    ).replace('"canonical_unit": false', "")
    assert body["data"]["feature"] is None


def test_an_explicit_false_tristate_survives_the_boundary(client):
    response = post_load(
        client,
        validated=validated_body({"heart_disease": vf("heart_disease", False)}),
    )
    data = response.json()["data"]
    assert data["features"]["heart_disease"]["value"] is False
    assert "heart_disease" not in data["unavailable"]


def test_warnings_and_upstream_context_survive_the_boundary(client):
    response = post_load(
        client,
        validated=validated_body(
            {"hba1c": vf("hba1c", 6.8)},
            all_warnings=[
                {"stage": "extraction", "module": 4, "message": "page 2 unreadable"},
                {"stage": "validation", "module": 6, "message": "low confidence"},
            ],
            upstream={
                "provided": True,
                "extraction_confidence": 0.71,
                "pages_unreadable": [2],
            },
        ),
    )
    data = response.json()["data"]
    assert [w["stage"] for w in data["all_warnings"]] == ["extraction", "validation"]
    assert data["upstream"]["extraction_confidence"] == 0.71
    assert data["upstream"]["pages_unreadable"] == [2]
    assert data["summary"]["partial_document"] is True


def test_a_patients_snapshots_are_listed_in_chronological_order(client):
    for value, date in ((6.8, "2024-09-01"), (6.1, "2024-01-15"), (6.4, "2024-05-20")):
        post_load(
            client,
            validated=validated_body({"hba1c": vf("hba1c", value)}),
            report_date=date,
        )

    listing = client.get(_patient_url("patient-1")).json()["data"]
    assert listing["count"] == 3
    dates = [s["identity"]["report_date"][:10] for s in listing["snapshots"]]
    assert dates == ["2024-01-15", "2024-05-20", "2024-09-01"]


def test_a_listing_carries_no_feature_values(client):
    post_load(client)
    body = client.get(_patient_url("patient-1")).text
    listing = json.loads(body)["data"]["snapshots"][0]

    assert "6.8" not in json.dumps(listing.get("available"))
    assert "6.8" not in json.dumps(listing.get("unavailable"))
    assert "values" not in listing and "features" not in listing

    assert listing["available"] == ["hba1c"]
    assert "creatinine" in listing["unavailable"]


def test_an_unknown_patient_lists_nothing_rather_than_failing(client):
    response = client.get(_patient_url("nobody"))
    assert response.status_code == 200
    assert response.json()["data"] == {
        "patient_ref": "nobody",
        "count": 0,
        "snapshots": [],
    }


def test_reusing_a_snapshot_id_overwrites_over_http(client):
    post_load(client, snapshot_id="fixed", validated=validated_body({"hba1c": vf("hba1c", 6.1)}))
    post_load(client, snapshot_id="fixed", validated=validated_body({"hba1c": vf("hba1c", 6.8)}))
    assert client.get(_patient_url("patient-1")).json()["data"]["count"] == 1
    assert client.get(_snapshot_url("fixed")).json()["data"]["features"]["hba1c"]["value"] == 6.8


def test_module_5_output_is_accepted_and_validated_in_process(client):
    from app.services.feature_engineer import engineer_features

    engineered = engineer_features(
        extraction={
            "extracted_parameters": [
                {"test_name": "HbA1c", "value_raw": "6.8", "value_numeric": 6.8, "unit": "%"},
                {"test_name": "Creatinine", "value_raw": "9999", "value_numeric": 9999.0,
                 "unit": "mg/dL"},
            ]
        }
    )
    response = client.post(
        LOAD, json={"engineered": engineered.model_dump(mode="json")}
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["features"]["hba1c"]["value"] == 6.8
    assert "creatinine" not in data["features"]
    assert data["unavailable"]["creatinine"]["availability"] == "rejected"


def test_a_relayed_module_6_envelope_is_accepted(client):
    response = client.post(
        LOAD,
        json={"success": True, "data": validated_body({"hba1c": vf("hba1c", 6.8)})},
    )
    assert response.status_code == 200
    assert response.json()["data"]["features"]["hba1c"]["value"] == 6.8


def test_a_bare_module_6_object_is_accepted(client):
    response = client.post(LOAD, json=validated_body({"hba1c": vf("hba1c", 6.8)}))
    assert response.status_code == 200
    assert response.json()["data"]["features"]["hba1c"]["value"] == 6.8


def test_an_ambiguous_body_is_refused_rather_than_guessed_at(client):
    body = validated_body({"hba1c": vf("hba1c", 6.8)})
    body["data"] = {"valid": {}}
    response = client.post(LOAD, json=body)
    assert response.status_code == 422
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "INVALID_REQUEST"


def test_an_empty_body_stores_an_empty_but_complete_snapshot(client):
    response = client.post(LOAD, json={})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["features"] == {}
    assert set(data["unavailable"]) == set(CANONICAL_FEATURES)


def test_an_unknown_snapshot_is_a_clean_404(client):
    response = client.get(_snapshot_url("no-such-snapshot"))
    assert response.status_code == 404
    assert response.json() == {
        "success": False,
        "error": {
            "code": "SNAPSHOT_NOT_FOUND",
            "message": "No snapshot with that id is held.",
        },
    }


def test_a_non_canonical_feature_name_is_a_404_not_an_absent_value(client):
    snapshot_id = post_load(client).json()["data"]["identity"]["snapshot_id"]
    response = client.get(_feature_url(snapshot_id, "banana"))
    assert response.status_code == 404
    assert response.json()["success"] is False


def test_a_malformed_identifier_is_refused_by_the_path_pattern(client):
    response = client.get(_snapshot_url("a" * 200))
    assert response.status_code == 422
    assert response.json()["success"] is False


def test_the_interface_document_is_served_and_carries_no_phi(client):
    response = client.get(INTERFACE)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["module"] == 7
    assert data["absent_sentinel"] == "ABSENT"
    assert "InMemory" in data["backend"]


ROUTES = [
    ("post", LOAD),
    ("get", _snapshot_url("anything")),
    ("get", _feature_url("anything", "hba1c")),
    ("get", _patient_url("patient-1")),
    ("get", INTERFACE),
]


def _call(client, method: str, path: str, headers=None):
    if method == "post":
        return client.post(path, json={}, headers=headers)
    return client.get(path, headers=headers)


@pytest.mark.parametrize("method,path", ROUTES)
def test_every_repository_route_rejects_a_caller_without_the_key(
    authed_client, method, path
):
    response = _call(authed_client, method, path)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.parametrize("method,path", ROUTES)
def test_every_repository_route_accepts_the_right_key(authed_client, method, path):
    response = _call(
        authed_client, method, path, {SERVICE_KEY_HEADER: TEST_SERVICE_KEY}
    )
    assert response.status_code != 401


def test_the_router_declares_the_auth_dependency_on_every_route():
    from app.api import routes_repository
    from app.core.auth import require_service_key

    assert routes_repository.router.routes, "the router declares no routes"
    assert any(
        dependency.dependency is require_service_key
        for dependency in routes_repository.router.dependencies
    )
    for route in routes_repository.router.routes:
        assert any(
            d.call is require_service_key
            for d in getattr(route, "dependant").dependencies
        ), route.path
