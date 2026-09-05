"""POST /api/v1/decisions/fuse -- the Module 15/16 HTTP contract.

Response shapes must match the rest of the service: `{success, data}` on
success and `{success, error: {code, message}}` on failure.

MOUNTING NOTE: the decisions router lives in its own file so it can be mounted
without editing `app/main.py` concurrently with another module. Until the
coordinator adds

    app.include_router(routes_decisions.router)

to `app/main.py`, this module mounts it itself, at import time, idempotently --
the same pattern `tests/test_ml_endpoint.py` already uses. Once the line is in
`main.py` the guard below makes this a no-op, so nothing gets double-registered.
Mounting at import time also means the route is present for
`tests/test_auth.py::test_every_phi_route_declares_the_auth_dependency`, which
is exactly the coverage we want.

NO TRAINING, no API key, no network.
"""

from __future__ import annotations

from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

from app.api import routes_decisions
from app.core.auth import SERVICE_KEY_HEADER
from app.data import conditions as C
from app.main import app
from tests.conftest import TEST_SERVICE_KEY

ENDPOINT = "/api/v1/decisions/fuse"
POLICY_ENDPOINT = "/api/v1/decisions/policy"


def walk_routes(routes) -> list:
    flat = []
    for route in routes:
        included = getattr(route, "original_router", None)
        nested = getattr(included, "routes", None) or getattr(route, "routes", None)
        if nested:
            flat.extend(walk_routes(nested))
        else:
            flat.append(route)
    return flat


def _mount_once() -> None:
    if any(getattr(r, "path", "") == ENDPOINT for r in walk_routes(app.routes)):
        return
    app.include_router(routes_decisions.router)


_mount_once()


@pytest.fixture()
def api(client_factory) -> TestClient:
    return client_factory()


# --------------------------------------------------------------------------
# Payloads -- hand-written, invented values, no real patient data
# --------------------------------------------------------------------------


def engineered_payload() -> Dict[str, Any]:
    return {
        "engineered": {
            "features": {
                "hba1c": {"name": "hba1c", "value": 6.8, "unit": "%", "source": "lab_report"},
                "blood_glucose": {
                    "name": "blood_glucose",
                    "value": 112.0,
                    "unit": "mg/dl",
                    "source": "lab_report",
                },
                "bmi": {"name": "bmi", "value": 31.4, "unit": "kg/m2", "source": "patient_profile"},
                "age": {"name": "age", "value": 54, "unit": "years", "source": "patient_profile"},
                "gender": {"name": "gender", "value": "male", "source": "patient_profile"},
                "creatinine": {
                    "name": "creatinine",
                    "value": 1.1,
                    "unit": "mg/dl",
                    "source": "lab_report",
                },
            }
        }
    }


def post(api: TestClient, payload: Dict[str, Any]):
    return api.post(ENDPOINT, json=payload)


# --------------------------------------------------------------------------
# The happy path
# --------------------------------------------------------------------------


def test_a_realistic_feature_set_returns_fused_decisions(api):
    response = post(api, engineered_payload())
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True

    data = body["data"]
    assert data["fused"], "no fused decision came back"
    conditions = [f["condition"] for f in data["fused"]]
    assert C.DIABETES in conditions
    assert len(conditions) == len(set(conditions)), "a condition was fused twice"


def test_the_fused_object_carries_everything_module_17_needs(api):
    data = post(api, engineered_payload()).json()["data"]
    summary = data["summary"]

    # Module 18
    assert summary["overall_status"] in (
        "Healthy",
        "Needs Monitoring",
        "Needs Medical Attention",
    )
    assert "overall_risk" in summary
    assert summary["any_assessed"] is True
    # Module 17's report sections
    assert "critical_conditions" in summary
    assert "abnormal_conditions" in summary
    assert "normal_conditions" in summary
    assert "unassessed_conditions" in summary
    # Module 19
    assert summary["prioritized"]
    # Module 17's validation warnings
    assert isinstance(data["all_warnings"], list)
    # Module 20's provenance
    assert data["collection"]["collected"]
    assert all(item["decision_id"] for item in data["collection"]["collected"])


def test_each_fused_decision_is_a_real_clinical_decision_object(api):
    from app.schemas.decisions import ClinicalDecision

    data = post(api, engineered_payload()).json()["data"]
    for fused in data["fused"]:
        decision = ClinicalDecision.model_validate(fused["decision"])
        assert decision.source_kind.value == "fusion"
        assert decision.condition == fused["condition"]


def test_sources_never_repeat_inside_one_fused_decision(api):
    data = post(api, engineered_payload()).json()["data"]
    for fused in data["fused"]:
        assert len(fused["sources"]) == len(set(fused["sources"]))


def test_the_rule_engines_two_diabetes_decisions_collapse_over_http(api):
    data = post(api, engineered_payload()).json()["data"]
    raw = [
        item
        for item in data["collection"]["collected"]
        if item["decision"]["condition"] == C.DIABETES
        and item["decision"]["source"] == "Clinical Rule Engine"
    ]
    assert len(raw) >= 2, "the rule engine no longer emits two Diabetes decisions"

    diabetes = next(f for f in data["fused"] if f["condition"] == C.DIABETES)
    assert diabetes["sources"].count("Clinical Rule Engine") == 1
    assert len(diabetes["decision_ids"]) >= 2


def test_an_empty_body_assesses_nothing_and_does_not_claim_health(api):
    response = post(api, {})
    assert response.status_code == 200
    summary = response.json()["data"]["summary"]
    assert summary["overall_status"] is None
    assert summary["any_assessed"] is False
    assert summary["overall_risk"] is None


# --------------------------------------------------------------------------
# Input tolerance -- identical to Modules 8 and 9, by inheritance
# --------------------------------------------------------------------------


def test_a_relayed_module_5_envelope_is_accepted(api):
    payload = {"success": True, "data": engineered_payload()["engineered"]}
    response = post(api, payload)
    assert response.status_code == 200
    assert response.json()["data"]["summary"]["input_kind"] == "engineered"


def test_a_bare_module_5_object_is_accepted(api):
    response = post(api, engineered_payload()["engineered"])
    assert response.status_code == 200
    assert response.json()["data"]["summary"]["input_kind"] == "engineered"


def test_a_validated_feature_set_is_the_canonical_form(api):
    validated = api.post(
        "/api/v1/features/validate", json=engineered_payload()
    ).json()["data"]
    response = post(api, {"validated": validated})
    assert response.status_code == 200
    assert response.json()["data"]["summary"]["input_kind"] == "validated"


@pytest.mark.parametrize(
    "payload",
    [
        {"valid": {}, "features": {}},
        {"data": {"valid": {}}, "valid": {}},
        {"data": {"valid": {}, "features": {}}},
    ],
)
def test_ambiguous_requests_are_422_and_never_guessed(api, payload):
    response = post(api, payload)
    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert set(body["error"]) >= {"code", "message"}


def test_all_three_decision_endpoints_agree_on_what_is_ambiguous(api):
    """Drift between the tolerances would be a silent 200 with `fused: []`."""
    for payload in (
        {"valid": {}, "features": {}},
        {"data": {"valid": {}}, "valid": {}},
        {"data": {"valid": {}, "features": {}}},
    ):
        fusion = api.post(ENDPOINT, json=payload).status_code
        rules = api.post("/api/v1/rules/evaluate", json=payload).status_code
        ml = api.post("/api/v1/ml/predict", json=payload).status_code
        assert fusion == rules == ml == 422, payload


# --------------------------------------------------------------------------
# Introspection
# --------------------------------------------------------------------------


def test_the_fusion_policy_is_retrievable_from_the_running_service(api):
    response = api.get(POLICY_ENDPOINT)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["decision_engine"]["module"] == 15
    assert data["decision_engine"]["grouped_by"] == ["condition", "source"]
    assert data["fusion_engine"]["module"] == 16
    assert "Low < Medium < High" in data["fusion_engine"]["risk_rule"]
    assert "INSUFFICIENT_DATA" in data["fusion_engine"]["status_rule"]
    assert "0.0" in data["fusion_engine"]["confidence_rule"]


def test_the_policy_endpoint_exposes_no_values(api):
    """Shape and policy only -- it is reachable with any valid key, always."""
    blob = api.get(POLICY_ENDPOINT).text
    for value in ("6.8", "112", "31.4", "patient"):
        assert value not in blob


# --------------------------------------------------------------------------
# Auth -- the same dependency as every other PHI-bearing route
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path, method", [(ENDPOINT, "post"), (POLICY_ENDPOINT, "get")]
)
def test_a_missing_service_key_is_rejected(authed_client, path, method):
    call = getattr(authed_client, method)
    response = call(path, json={}) if method == "post" else call(path)
    assert response.status_code == 401
    assert response.json()["success"] is False


def test_a_wrong_service_key_is_rejected(authed_client):
    response = authed_client.post(
        ENDPOINT, json={}, headers={SERVICE_KEY_HEADER: "not-the-key"}
    )
    assert response.status_code == 401


def test_the_correct_service_key_is_accepted(authed_client):
    response = authed_client.post(
        ENDPOINT, json={}, headers={SERVICE_KEY_HEADER: TEST_SERVICE_KEY}
    )
    assert response.status_code == 200


def test_every_decisions_route_declares_the_auth_dependency():
    """Local guard, in addition to the service-wide one in test_auth.py."""
    from app.core.auth import require_service_key

    routes = [
        r
        for r in walk_routes(app.routes)
        if getattr(r, "path", "").startswith("/api/v1/decisions")
    ]
    assert routes, "the decisions router is not mounted"
    for route in routes:
        dependencies = getattr(route.dependant, "dependencies", [])
        assert any(d.call is require_service_key for d in dependencies), route.path


# --------------------------------------------------------------------------
# The framework-independent surface Module 17 will use
# --------------------------------------------------------------------------


def test_collect_and_fuse_are_callable_without_http():
    from app.services.decision_engine import collect_decisions
    from app.services.fusion_engine import fuse_decisions

    collection = collect_decisions(engineered=engineered_payload()["engineered"])
    data = fuse_decisions(collection)
    assert data.fused
    assert data.summary.overall_status


def test_the_endpoint_and_the_in_process_call_agree():
    """The HTTP layer must be a wrapper, not a second implementation."""
    from fastapi.testclient import TestClient

    from app.services.fusion_engine import run_decision_fusion

    with TestClient(app, raise_server_exceptions=False) as client:
        over_http = client.post(ENDPOINT, json=engineered_payload()).json()["data"]
    in_process = run_decision_fusion(
        engineered=engineered_payload()["engineered"]
    ).model_dump(mode="json")

    assert [f["condition"] for f in over_http["fused"]] == [
        f["condition"] for f in in_process["fused"]
    ]
    assert [f["risk"] for f in over_http["fused"]] == [
        f["risk"] for f in in_process["fused"]
    ]
    assert over_http["summary"]["overall_status"] == (
        in_process["summary"]["overall_status"]
    )
