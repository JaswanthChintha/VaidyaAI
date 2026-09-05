"""POST /api/v1/report/generate -- the Module 17-20 HTTP contract.

Response shapes must match the rest of the service: `{success, data}` on
success and `{success, error: {code, message}}` on failure.

MOUNTING NOTE: the report router lives in its own file so it can be mounted
without editing `app/main.py` concurrently with another module. Until the
coordinator adds

    app.include_router(routes_report.router)

to `app/main.py`, this module mounts it itself, at import time, idempotently --
the same pattern `tests/test_ml_endpoint.py` and `tests/test_decisions_endpoint.py`
already use. Once the line is in `main.py` the guard below makes this a no-op,
so nothing gets double-registered. Mounting at import time also means the route
is present for
`tests/test_auth.py::test_every_phi_route_declares_the_auth_dependency`, which
is exactly the coverage we want.

NO TRAINING, no API key, no network.
"""

from __future__ import annotations

from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

from app.api import routes_report
from app.core.auth import SERVICE_KEY_HEADER
from app.data import conditions as C
from app.main import app
from app.schemas.report import ClinicalReport
from tests.conftest import TEST_SERVICE_KEY

ENDPOINT = "/api/v1/report/generate"
POLICY_ENDPOINT = "/api/v1/report/policy"


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
    app.include_router(routes_report.router)


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
                "hba1c": {
                    "name": "hba1c",
                    "value": 8.4,
                    "unit": "%",
                    "source": "lab_report",
                },
                "blood_glucose": {
                    "name": "blood_glucose",
                    "value": 186.0,
                    "unit": "mg/dl",
                    "source": "lab_report",
                },
                "creatinine": {
                    "name": "creatinine",
                    "value": 2.1,
                    "unit": "mg/dl",
                    "source": "lab_report",
                },
                "hemoglobin": {
                    "name": "hemoglobin",
                    "value": 10.4,
                    "unit": "g/dl",
                    "source": "lab_report",
                },
                "cholesterol": {
                    "name": "cholesterol",
                    "value": 268.0,
                    "unit": "mg/dl",
                    "source": "lab_report",
                },
                "bmi": {
                    "name": "bmi",
                    "value": 33.8,
                    "unit": "kg/m2",
                    "source": "patient_profile",
                },
                "age": {
                    "name": "age",
                    "value": 62,
                    "unit": "years",
                    "source": "patient_profile",
                },
                "gender": {
                    "name": "gender",
                    "value": "male",
                    "source": "patient_profile",
                },
                "hypertension": {
                    "name": "hypertension",
                    "value": True,
                    "source": "patient_profile",
                },
                "smoking_history": {
                    "name": "smoking_history",
                    "value": "current",
                    "source": "patient_profile",
                },
            }
        }
    }


def validated_with_rejection() -> Dict[str, Any]:
    """A relayed Module 6 response, including its `rejected` map."""
    return {
        "validated": {
            "valid": {
                "hba1c": {
                    "name": "hba1c",
                    "value": 6.8,
                    "unit": "%",
                    "source": "lab_report",
                    "status": "valid",
                }
            },
            "questionable": {},
            "rejected": {
                "creatinine": {
                    "name": "creatinine",
                    "value": 884.0,
                    "unit": "umol/L",
                    "canonical_unit": False,
                    "source": "lab_report",
                    "status": "rejected",
                    "reason_code": "NON_CANONICAL_UNIT",
                    "reason": (
                        "'creatinine' was reported in a unit that could not be "
                        "converted to the canonical one"
                    ),
                }
            },
        }
    }


def post(api: TestClient, payload: Dict[str, Any]):
    return api.post(ENDPOINT, json=payload)


# --------------------------------------------------------------------------
# The happy path
# --------------------------------------------------------------------------


def test_a_realistic_feature_set_returns_a_full_report(api):
    response = post(api, engineered_payload())
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True

    data = body["data"]
    assert data["report_version"]
    assert data["laboratory_values"]
    assert data["conditions"]
    assert data["overall"]["status_label"]
    assert data["prioritized"]
    assert data["explainability"]["conditions"]
    assert data["recommendations"]
    assert isinstance(data["validation_warnings"], list)
    assert data["metadata"]["modules"]["clinical_report"] == 17


def test_the_response_validates_against_the_declared_schema(api):
    data = post(api, engineered_payload()).json()["data"]
    report = ClinicalReport.model_validate(data)
    assert report.conditions
    assert report.overall.status_label


def test_the_dashboard_sections_module_27_needs_are_all_present(api):
    data = post(api, engineered_payload()).json()["data"]
    # Overall health card
    assert data["overall"]["status_label"]
    assert "overall_risk" in data
    # Condition cards
    for condition in data["conditions"]:
        assert condition["condition"]
        assert condition["status"]
        assert condition["priority"]
        assert "sources" in condition
    # Laboratory cards
    for value in data["laboratory_values"]:
        assert value["feature"]
        assert "usable" in value
    # Evidence section, recommendations section
    assert data["explainability"]["chain"] == ["Input", "Evidence", "Decision"]
    assert data["recommendations"]


def test_one_row_per_condition_over_http(api):
    data = post(api, engineered_payload()).json()["data"]
    conditions = [row["condition"] for row in data["prioritized"]]
    assert len(conditions) == len(set(conditions))
    assert C.DIABETES in conditions

    diabetes = next(c for c in data["conditions"] if c["condition"] == C.DIABETES)
    assert diabetes["contributing_decision_count"] >= 2
    assert diabetes["sources"].count("Clinical Rule Engine") == 1


def test_an_empty_body_does_not_claim_health(api):
    response = post(api, {})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["overall"]["status"] is None
    assert data["overall"]["status_label"] == "Not Assessed"
    assert data["overall"]["any_assessed"] is False
    assert data["overall_risk"] is None
    assert data["overall"]["caveat"]


def test_a_relayed_module_6_response_carries_its_rejections_through(api):
    """The rejected map survives the hop even though the decision chain drops it."""
    data = post(api, validated_with_rejection()).json()["data"]

    assert "creatinine" in data["document"]["rejected_features"]
    assert "creatinine" in data["explainability"]["rejected_features_joined"]

    row = next(v for v in data["laboratory_values"] if v["feature"] == "creatinine")
    assert row["usable"] is False
    assert row["rejection_code"] == "NON_CANONICAL_UNIT"

    lines = [
        line
        for explanation in data["explainability"]["conditions"]
        for line in explanation["evidence"]
        if line["feature"] == "creatinine"
    ]
    assert lines
    for line in lines:
        assert line["availability"] == "found_but_not_trusted"
        assert line["rejected"] is True
        assert "not found in the submitted report" not in line["explanation"]


def test_the_rejected_map_can_also_be_sent_explicitly(api):
    payload = {
        "validated": {"valid": {}},
        "rejected_features": {
            "hemoglobin": {
                "name": "hemoglobin",
                "value": 142.0,
                "unit": "g/L",
                "reason_code": "IMPLAUSIBLE_VALUE_HIGH",
                "reason": "above the physiologically possible band",
            }
        },
    }
    data = post(api, payload).json()["data"]
    assert "hemoglobin" in data["document"]["rejected_features"]


def test_ml_importance_is_never_presented_as_per_patient_over_http(api):
    data = post(api, engineered_payload()).json()["data"]
    mls = [
        source["ml"]
        for explanation in data["explainability"]["conditions"]
        for source in explanation["sources"]
        if source["ml"]
    ]
    assert mls
    for ml in mls:
        assert ml["importance_is_per_patient"] is False
        assert ml["importance_scope"] == "global_model_level"


def test_basis_conflict_is_rendered_side_by_side_over_http(api):
    data = post(api, engineered_payload()).json()["data"]
    conflicted = [c for c in data["conditions"] if c["basis_conflict"]]
    assert conflicted
    for condition in conflicted:
        assert condition["render_contributions_separately"] is True
        assert condition["basis_note"]
        assert len(condition["contributions"]) >= 2
        assert all(c["band_labels"] for c in condition["contributions"])


def test_warnings_keep_their_origin_over_http(api):
    payload = engineered_payload()
    payload["engineered"]["all_warnings"] = [
        {"stage": "extraction", "module": 4, "message": "CANARY-HTTP-4"}
    ]
    payload["engineered"]["upstream"] = {
        "provided": True,
        "extraction_confidence": 0.55,
        "pages": [
            {"page_number": 1, "raw_text_available": True},
            {"page_number": 2, "raw_text_available": False},
        ],
        "pages_unreadable": [2],
    }
    data = post(api, payload).json()["data"]

    origins = {w["message"]: w for w in data["validation_warnings"]}
    assert origins["CANARY-HTTP-4"]["stage"] == "extraction"
    assert origins["CANARY-HTTP-4"]["module"] == 4
    assert data["document"]["pages_unreadable"] == [2]
    assert data["document"]["extraction_confidence"] == pytest.approx(0.55)


# --------------------------------------------------------------------------
# Input tolerance -- identical to Modules 8, 9 and 15/16, by inheritance
# --------------------------------------------------------------------------


def test_a_relayed_module_5_envelope_is_accepted(api):
    payload = {"success": True, "data": engineered_payload()["engineered"]}
    response = post(api, payload)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["conditions"]
    # What the CALLER sent, recorded separately from what the DECISION CHAIN
    # saw: this layer runs Module 6 in-process first, so the chain always sees
    # validated features and the report's rejected map is the real one.
    assert data["metadata"]["input_received"] == "engineered"
    assert data["summary"]["input_kind"] == "validated"


def test_a_bare_module_5_object_is_accepted(api):
    response = post(api, engineered_payload()["engineered"])
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["conditions"]
    assert data["metadata"]["input_received"] == "engineered"


def test_posting_module_5_output_and_module_6_output_agree(api):
    """Running Module 6 in-process must not change the clinical outcome."""
    from_module_5 = post(api, engineered_payload()).json()["data"]

    validated = api.post(
        "/api/v1/features/validate",
        json={"engineered": engineered_payload()["engineered"]},
    )
    assert validated.status_code == 200
    from_module_6 = post(
        api, {"validated": validated.json()["data"]}
    ).json()["data"]

    assert (
        from_module_5["overall"]["status_label"]
        == from_module_6["overall"]["status_label"]
    )
    assert [c["condition"] for c in from_module_5["conditions"]] == [
        c["condition"] for c in from_module_6["conditions"]
    ]
    assert [c["risk"] for c in from_module_5["conditions"]] == [
        c["risk"] for c in from_module_6["conditions"]
    ]


@pytest.mark.parametrize(
    "payload",
    [
        {"data": {"valid": {}}, "valid": {}},
        {"valid": {}, "features": {}},
        {"data": {"valid": {}, "features": {}}},
    ],
)
def test_an_ambiguous_body_is_422_and_never_guessed(api, payload):
    response = post(api, payload)
    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"]


def test_a_non_object_body_is_422(api):
    response = api.post(ENDPOINT, json=[1, 2, 3])
    assert response.status_code == 422
    assert response.json()["success"] is False


# --------------------------------------------------------------------------
# Auth -- the same dependency as every other PHI-bearing route
# --------------------------------------------------------------------------


def test_the_endpoint_requires_the_service_key(authed_client):
    response = authed_client.post(ENDPOINT, json=engineered_payload())
    assert response.status_code == 401
    assert response.json()["success"] is False


def test_the_endpoint_accepts_the_service_key(authed_client):
    response = authed_client.post(
        ENDPOINT,
        json=engineered_payload(),
        headers={SERVICE_KEY_HEADER: TEST_SERVICE_KEY},
    )
    assert response.status_code == 200


def test_the_policy_endpoint_requires_the_service_key(authed_client):
    assert authed_client.get(POLICY_ENDPOINT).status_code == 401


def test_the_report_router_declares_the_auth_dependency():
    """`tests/test_auth.py` walks routers recursively; this is the local check."""
    assert routes_report.router.dependencies, "the router declares no dependency"


# --------------------------------------------------------------------------
# The policy endpoint
# --------------------------------------------------------------------------


def test_the_policy_endpoint_documents_all_four_modules(api):
    response = api.get(POLICY_ENDPOINT)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["clinical_report"]["module"] == 17
    assert data["overall_health_status"]["module"] == 18
    assert data["risk_prioritization"]["module"] == 19
    assert data["evidence_and_explainability"]["module"] == 20
    assert "Not Assessed" in data["overall_health_status"]["labels"]
    assert data["risk_prioritization"]["prioritised_by"] == ["condition"]
    assert (
        data["evidence_and_explainability"]["ml_feature_importance_is_per_patient"]
        is False
    )


def test_the_policy_endpoint_carries_no_patient_values(api):
    body = api.get(POLICY_ENDPOINT).text
    for canary in ("8.4", "186", "33.8", "62"):
        assert canary not in body
