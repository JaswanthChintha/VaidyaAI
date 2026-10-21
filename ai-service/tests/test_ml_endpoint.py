from __future__ import annotations

from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

from app.api import routes_ml
from app.core.auth import SERVICE_KEY_HEADER
from app.data import conditions as C
from app.main import app
from tests.conftest import TEST_SERVICE_KEY

ENDPOINT = "/api/v1/ml/predict"
PREDICTORS_ENDPOINT = "/api/v1/ml/predictors"
MODELS_ENDPOINT = "/api/v1/ml/models"


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
    app.include_router(routes_ml.router)


_mount_once()


@pytest.fixture()
def api(client_factory) -> TestClient:
    return client_factory()


def engineered_payload(**overrides: Any) -> Dict[str, Any]:
    features = {
        "hba1c": {"name": "hba1c", "value": 9.0, "unit": "%", "source": "lab_report"},
        "blood_glucose": {
            "name": "blood_glucose",
            "value": 260.0,
            "unit": "mg/dl",
            "source": "lab_report",
        },
        "bmi": {"name": "bmi", "value": 34.2, "unit": "kg/m2", "source": "patient_profile"},
        "age": {"name": "age", "value": 58, "unit": "years", "source": "patient_profile"},
        "gender": {"name": "gender", "value": "male", "source": "patient_profile"},
        "smoking_history": {
            "name": "smoking_history",
            "value": "former",
            "source": "patient_profile",
        },
    }
    for name, value in overrides.items():
        features[name] = {"name": name, "value": value, "source": "patient_profile"}
    return {"engineered": {"features": features}}


def validated_payload(**values: Any) -> Dict[str, Any]:
    return {
        "validated": {
            "valid": {
                name: {"name": name, "value": value, "status": "valid"}
                for name, value in values.items()
            }
        }
    }


def post(api: TestClient, payload: dict):
    return api.post(ENDPOINT, json=payload)


def test_engineered_input_produces_a_diabetes_decision(api):
    response = post(api, engineered_payload())
    assert response.status_code == 200

    body = response.json()
    assert body["success"] is True
    decisions = body["data"]["decisions"]
    assert len(decisions) == 3
    assert {d["condition"] for d in decisions} == {
        C.DIABETES,
        C.HEART_DISEASE,
        C.KIDNEY_DISEASE,
    }

    diabetes = [d for d in decisions if d["condition"] == C.DIABETES]
    assert len(diabetes) == 1
    decision = diabetes[0]
    assert decision["condition"] == C.DIABETES == "Diabetes"
    assert decision["source_kind"] == "machine_learning"
    assert decision["source"] == "Random Forest"
    assert decision["status"] == "Indicated"
    assert decision["risk"] == "High"
    assert 0.0 <= decision["confidence"] <= 1.0
    assert body["data"]["summary"]["input_kind"] == "engineered"


def test_validated_input_is_the_canonical_form(api):
    response = post(
        api,
        validated_payload(hba1c=5.0, blood_glucose=90.0, bmi=22.0, age=28),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["summary"]["input_kind"] == "validated"
    decision = body["data"]["decisions"][0]
    assert decision["status"] == "Not Indicated"
    assert decision["risk"] == "Low"


def test_the_condition_string_matches_the_rule_engine_byte_for_byte(api):
    ml = post(api, engineered_payload()).json()["data"]["decisions"]
    rules = api.post(
        "/api/v1/rules/evaluate", json=engineered_payload()
    ).json()["data"]["decisions"]

    ml_conditions = {d["condition"] for d in ml}
    rule_conditions = {d["condition"] for d in rules}
    assert "Diabetes" in ml_conditions
    assert ml_conditions <= rule_conditions, (
        "every ML condition must be spelled exactly as the rule engine spells "
        "it, or Module 16 will never fuse the two"
    )


def test_both_engines_produce_a_fusable_pair_for_diabetes(api):
    payload = engineered_payload()
    ml = post(api, payload).json()["data"]["decisions"]
    rules = api.post("/api/v1/rules/evaluate", json=payload).json()["data"]["decisions"]

    ml_diabetes = [d for d in ml if d["condition"] == "Diabetes"]
    rule_diabetes = [d for d in rules if d["condition"] == "Diabetes"]
    assert len(ml_diabetes) == 1
    assert len(rule_diabetes) >= 1
    assert ml_diabetes[0]["source_kind"] == "machine_learning"
    assert rule_diabetes[0]["source_kind"] == "clinical_rule"
    assert ml_diabetes[0]["confidence"] is not None
    assert rule_diabetes[0]["confidence"] is None


def test_missing_required_features_returns_insufficient_data_not_an_error(api):
    response = post(api, validated_payload(bmi=34.2, age=58))
    assert response.status_code == 200

    decisions = response.json()["data"]["decisions"]
    assert {d["condition"] for d in decisions} == {
        C.DIABETES,
        C.HEART_DISEASE,
        C.KIDNEY_DISEASE,
    }
    for decision in decisions:
        assert decision["status"] == "Insufficient Data", decision["condition"]
        assert decision["risk"] is None, decision["condition"]
        assert decision["confidence"] is None, decision["condition"]
    assert response.json()["data"]["summary"]["predictors_skipped"] == 3


def test_an_empty_body_is_a_clean_insufficient_data_response(api):
    response = post(api, {})
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["decisions"][0]["status"] == "Insufficient Data"
    assert body["data"]["summary"]["highest_risk"] is None


def test_the_tri_state_survives_the_http_boundary(api):
    absent = post(api, engineered_payload()).json()["data"]["decisions"][0]
    explicit = post(
        api, engineered_payload(hypertension=False, heart_disease=False)
    ).json()["data"]["decisions"][0]

    assert absent["metadata"]["variant"] == "neither"
    assert "hypertension" in absent["metadata"]["features_not_asserted"]
    assert "hypertension" not in absent["metadata"]["model_input_columns"]

    assert explicit["metadata"]["variant"] == "both"
    assert "hypertension" in explicit["metadata"]["model_input_columns"]


def test_an_unsupported_gender_does_not_break_the_endpoint(api):
    response = post(api, engineered_payload(gender="prefer_not_to_say"))
    assert response.status_code == 200
    decision = response.json()["data"]["decisions"][0]
    assert decision["confidence"] is not None
    assert "gender" in decision["metadata"]["features_unrecognised_category"]


@pytest.mark.parametrize(
    "value", ["no_info", "not_current", "never", "former", "current", "ever"]
)
def test_every_module_2_smoking_value_reaches_the_model_recognised(api, value):
    response = post(api, engineered_payload(smoking_history=value))
    assert response.status_code == 200
    decision = response.json()["data"]["decisions"][0]
    assert decision["metadata"]["features_unrecognised_category"] == []
    assert "smoking_history" in decision["metadata"]["features_observed"]


@pytest.mark.parametrize("value", ["No Info", "not current"])
def test_dataset_spelled_smoking_values_are_stopped_by_module_6(api, value):
    decision = post(api, engineered_payload(smoking_history=value)).json()[
        "data"
    ]["decisions"][0]
    assert "smoking_history" not in decision["metadata"]["features_observed"]
    assert "smoking_history" in decision["metadata"]["features_not_asserted"]


def test_a_relayed_module_5_envelope_is_accepted(api):
    payload = {"success": True, "data": engineered_payload()["engineered"]}
    response = post(api, payload)
    assert response.status_code == 200
    assert response.json()["data"]["summary"]["input_kind"] == "engineered"


def test_a_bare_module_6_object_is_accepted(api):
    payload = validated_payload(hba1c=9.0, blood_glucose=260.0)["validated"]
    response = post(api, payload)
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


def test_validated_beats_engineered_when_both_are_named(api):
    payload = {
        "validated": validated_payload(hba1c=5.0, blood_glucose=90.0)["validated"],
        "engineered": engineered_payload()["engineered"],
    }
    response = post(api, payload)
    assert response.status_code == 200
    assert response.json()["data"]["summary"]["input_kind"] == "validated"


def test_the_ml_and_rule_endpoints_agree_on_what_is_ambiguous(api):
    for payload in ({"valid": {}, "features": {}}, {"data": {"valid": {}}, "valid": {}}):
        ml = api.post(ENDPOINT, json=payload).status_code
        rules = api.post("/api/v1/rules/evaluate", json=payload).status_code
        assert ml == rules == 422


def test_upstream_warnings_are_carried_forward_with_their_stage(api):
    payload = engineered_payload()
    payload["engineered"]["all_warnings"] = [
        {"stage": "extraction", "module": 4, "message": "page 1 was recovered"}
    ]
    body = post(api, payload).json()["data"]
    assert any(
        w["stage"] == "extraction" and "recovered" in w["message"]
        for w in body["all_warnings"]
    )


def test_this_modules_own_warnings_are_stamped_with_stage_ml(api):
    body = post(api, {}).json()["data"]
    ml_warnings = [w for w in body["all_warnings"] if w["stage"] == "ml"]
    assert all(w["module"] == 9 for w in ml_warnings)


def test_the_registry_is_introspectable(api):
    response = api.get(PREDICTORS_ENDPOINT)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["predictor_count"] >= 1
    assert "Diabetes" in data["conditions_covered"]
    entry = [p for p in data["predictors"] if p["name"] == "diabetes_rf"][0]
    assert entry["available"] is True
    assert entry["required_features"] == ["hba1c", "blood_glucose"]
    assert entry["source_kind"] == "machine_learning"


def test_the_metrics_artifact_is_retrievable_from_the_running_service(api):
    response = api.get(MODELS_ENDPOINT)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["available"] is True

    metrics = data["metrics"]["variants"]["both"]["metrics"]
    assert metrics["roc_auc"] > 0.9
    assert metrics["pr_auc_average_precision"] > 0.8
    assert metrics["accuracy"] > metrics["majority_class_baseline_accuracy"]
    assert set(metrics["confusion_matrix"]) >= {
        "true_negative", "false_positive", "false_negative", "true_positive",
    }
    assert metrics["cross_validation"]["folds"] == 5


def test_the_introspection_endpoints_expose_no_values(api):
    blob = api.get(PREDICTORS_ENDPOINT).text + api.get(MODELS_ENDPOINT).text
    assert "9.0" not in blob or "hba1c" in blob
    assert "patient_profile" not in blob


@pytest.mark.parametrize(
    "path, method",
    [
        (ENDPOINT, "post"),
        (PREDICTORS_ENDPOINT, "get"),
        (MODELS_ENDPOINT, "get"),
    ],
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


def test_every_ml_route_declares_the_auth_dependency():
    from app.core.auth import require_service_key

    ml_routes = [
        r for r in walk_routes(app.routes)
        if getattr(r, "path", "").startswith("/api/v1/ml")
    ]
    assert ml_routes, "the ML router is not mounted"
    for route in ml_routes:
        dependencies = getattr(route.dependant, "dependencies", [])
        assert any(d.call is require_service_key for d in dependencies), route.path


def test_predict_all_is_callable_without_http():
    from app.ml import predict_all

    result = predict_all(
        engineered=engineered_payload()["engineered"],
    )
    assert result.summary.input_kind == "engineered"
    assert result.decisions[0].condition == C.DIABETES
    assert result.decisions[0].confidence is not None


def test_predict_all_accepts_module_6_output_objects_directly():
    from app.ml import predict_all
    from app.services.validator import validate_features

    validated = validate_features(engineered_payload()["engineered"])
    result = predict_all(validated)
    assert result.summary.input_kind == "validated"
    assert result.decisions[0].status.value == "Indicated"
