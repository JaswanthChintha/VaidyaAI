from __future__ import annotations

from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

from app.api import routes_rules
from app.core.auth import SERVICE_KEY_HEADER
from app.data import conditions as C
from app.main import app
from tests.conftest import TEST_SERVICE_KEY
from tests.test_rule_engine import REALISTIC_FEATURES, validated, vf

ENDPOINT = "/api/v1/rules/evaluate"
RULES_ENDPOINT = "/api/v1/rules/clinical-rules"
CONDITIONS_ENDPOINT = "/api/v1/rules/conditions"
RECOMMENDATIONS_ENDPOINT = "/api/v1/rules/recommendations"


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
    app.include_router(routes_rules.router)


_mount_once()


@pytest.fixture()
def api(client_factory) -> TestClient:
    return client_factory()


def post(api: TestClient, payload: dict):
    return api.post(ENDPOINT, json=payload)


def engineered_payload() -> Dict[str, Any]:
    return {
        "features": {
            "hba1c": {
                "name": "hba1c",
                "value": 7.4,
                "unit": "%",
                "canonical_unit": True,
                "source": "lab_report",
                "provenance": {"source": "lab_report", "original_test_name": "HbA1c"},
            }
        },
        "unmapped": [],
        "missing_features": [],
        "warnings": [],
        "upstream_warnings": [],
        "all_warnings": [],
        "upstream": {"provided": False},
        "summary": {},
    }


def test_endpoint_returns_the_success_envelope(api):
    response = post(api, {"validated": validated({})})
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert set(body["data"]) >= {
        "decisions",
        "warnings",
        "upstream_warnings",
        "all_warnings",
        "summary",
        "metadata",
    }


def test_decisions_carry_the_module_14_shape(api):
    response = post(api, {"validated": validated(REALISTIC_FEATURES())})
    assert response.status_code == 200
    decisions = response.json()["data"]["decisions"]
    assert decisions
    first = decisions[0]
    assert set(first) >= {
        "condition",
        "status",
        "risk",
        "confidence",
        "source",
        "source_kind",
        "evidence",
        "recommendations",
        "metadata",
        "created_at",
    }
    assert first["confidence"] is None
    assert first["source_kind"] == "clinical_rule"


def test_an_empty_body_is_accepted_and_accounts_for_every_topic(api):
    response = post(api, {})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["summary"]["highest_risk"] is None

    conditions = {d["condition"] for d in data["decisions"]}
    expected = {
        name
        for name, definition in C.CONDITIONS.items()
        if definition.always_assessed or definition.report_when_unread
    }
    assert conditions == expected
    assert set(C.FUSION_CONDITIONS) <= conditions

    for name, definition in C.CONDITIONS.items():
        if not definition.always_assessed and not definition.report_when_unread:
            assert name not in conditions

    for decision in data["decisions"]:
        assert decision["status"] == "Insufficient Data"
        assert decision["risk"] is None


def test_a_bare_module_6_object_is_accepted(api):
    response = post(api, validated({"hba1c": vf("hba1c", 7.4)}))
    assert response.status_code == 200
    assert response.json()["data"]["summary"]["input_kind"] == "validated"


def test_a_relayed_module_6_envelope_is_accepted(api):
    response = post(api, {"success": True, "data": validated({"hba1c": vf("hba1c", 7.4)})})
    assert response.status_code == 200
    assert response.json()["data"]["summary"]["flagged_count"] >= 1


def test_a_bare_module_5_object_is_accepted(api):
    response = post(api, engineered_payload())
    assert response.status_code == 200
    assert response.json()["data"]["summary"]["input_kind"] == "engineered"


def test_a_relayed_module_5_envelope_is_accepted(api):
    response = post(api, {"success": True, "data": engineered_payload()})
    assert response.status_code == 200
    assert response.json()["data"]["summary"]["input_kind"] == "engineered"


def test_an_envelope_plus_a_bare_object_is_422_not_a_guess(api):
    body = dict(validated({"hba1c": vf("hba1c", 7.4)}))
    body["data"] = engineered_payload()
    response = post(api, body)
    assert response.status_code == 422
    assert response.json()["success"] is False


def test_an_object_carrying_both_valid_and_features_is_422(api):
    body = dict(validated({}))
    body["features"] = {}
    response = post(api, body)
    assert response.status_code == 422


def test_an_envelope_carrying_both_valid_and_features_is_422(api):
    inner = dict(validated({}))
    inner["features"] = {}
    response = post(api, {"success": True, "data": inner})
    assert response.status_code == 422


def test_explicit_validated_wins_over_explicit_engineered(api):
    response = post(
        api,
        {"validated": validated({"hba1c": vf("hba1c", 5.0)}), "engineered": engineered_payload()},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["summary"]["input_kind"] == "validated"
    assert data["summary"]["flagged_count"] == 0


def test_a_non_object_body_is_rejected(api):
    response = api.post(ENDPOINT, json=["not", "an", "object"])
    assert response.status_code == 422


def test_upstream_warnings_survive_the_http_boundary(api):
    payload = validated(
        {"hba1c": vf("hba1c", 7.4)},
        all_warnings=[
            {"stage": "extraction", "module": 4, "message": "page 2 was unreadable"},
            {"stage": "validation", "module": 6, "message": "creatinine was rejected"},
        ],
    )
    response = post(api, {"validated": payload})
    data = response.json()["data"]
    assert [w["stage"] for w in data["upstream_warnings"]] == ["extraction", "validation"]
    assert data["all_warnings"][0]["message"] == "page 2 was unreadable"


def test_the_rule_table_is_published_for_review(api):
    response = api.get(RULES_ENDPOINT)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["threshold_rules"]
    assert all(entry["basis"] for entry in data["threshold_rules"])
    assert "policy" in data


def test_the_condition_vocabulary_is_published(api):
    response = api.get(CONDITIONS_ENDPOINT)
    assert response.status_code == 200
    assert response.json()["data"]["fusion_conditions"] == list(C.FUSION_CONDITIONS)


def test_the_recommendation_catalogue_is_published(api):
    response = api.get(RECOMMENDATIONS_ENDPOINT)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["recommendations"]
    assert "medication_name" in data["forbidden_patterns"]


def test_every_rules_route_is_registered_under_the_expected_prefix():
    paths = {getattr(r, "path", "") for r in walk_routes(app.routes)}
    assert ENDPOINT in paths
    assert RULES_ENDPOINT in paths


@pytest.mark.parametrize(
    "path,method", [(ENDPOINT, "post"), (RULES_ENDPOINT, "get"), (CONDITIONS_ENDPOINT, "get")]
)
def test_a_missing_service_key_is_rejected(authed_client, path, method):
    call = getattr(authed_client, method)
    response = call(path, json={}) if method == "post" else call(path)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


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
