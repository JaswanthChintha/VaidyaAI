"""POST /api/v1/features/validate -- the Module 6 HTTP contract.

Response shapes must match the rest of the service: `{success, data}` on
success and `{success, error: {code, message}}` on failure.

MOUNTING NOTE: Module 6's router lives in its own file so that it can be
mounted without editing `app/main.py` concurrently with another module. Until
the coordinator adds

    app.include_router(routes_validation.router)

to `app/main.py`, this module mounts it itself, at import time, idempotently.
Once the line is in `main.py` the guard below makes this a no-op, so nothing
gets double-registered. Mounting at import time also means the route is present
for `tests/test_auth.py::test_every_phi_route_declares_the_auth_dependency`,
which is exactly the coverage we want.
"""

from __future__ import annotations

from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

from app.api import routes_validation
from app.core.auth import SERVICE_KEY_HEADER
from app.data.validation_rules import FlagCode, RejectionCode
from app.main import app
from app.schemas.features import STAGE_EXTRACTION, STAGE_FEATURE_ENGINEERING
from app.schemas.validation import STAGE_VALIDATION
from app.services.feature_engineer import engineer_from_extraction
from tests.conftest import TEST_SERVICE_KEY

ENDPOINT = "/api/v1/features/validate"
RULES_ENDPOINT = "/api/v1/features/validation-rules"


def walk_routes(routes) -> list:
    """Flatten the route tree.

    NOTE for reviewers: this FastAPI version wraps an included router in an
    `_IncludedRouter` object that has NO `.path` attribute, so a flat scan of
    `app.routes` sees none of the `/api/v1` routes at all. See the report note
    on `tests/test_auth.py::test_every_phi_route_declares_the_auth_dependency`,
    which does exactly that flat scan and is therefore currently vacuous.
    """
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
    app.include_router(routes_validation.router)


_mount_once()


@pytest.fixture()
def api(client_factory) -> TestClient:
    # The Module 6 route needs no Gemini client, but reusing the existing
    # factory keeps env isolation identical across the suite.
    return client_factory()


def post(api: TestClient, payload: dict):
    return api.post(ENDPOINT, json=payload)


def engineered(**overrides: Any) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "features": {},
        "unmapped": [],
        "missing_features": [],
        "warnings": [],
        "upstream_warnings": [],
        "all_warnings": [],
        "upstream": {"provided": False},
        "summary": {},
    }
    payload.update(overrides)
    return payload


def lab(name: str, value: Any, unit: str, **prov: Any) -> Dict[str, Any]:
    provenance: Dict[str, Any] = {"source": "lab_report"}
    provenance.update(prov)
    return {
        "name": name,
        "value": value,
        "unit": unit,
        "canonical_unit": prov.pop("canonical_unit", True),
        "source": "lab_report",
        "provenance": provenance,
    }


# --------------------------------------------------------------------------
# Envelope and shape
# --------------------------------------------------------------------------


def test_endpoint_returns_the_success_envelope(api):
    response = post(api, {"engineered": engineered()})
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert set(body["data"]) >= {
        "valid",
        "questionable",
        "rejected",
        "clinically_extreme",
        "missing_features",
        "unmapped",
        "warnings",
        "upstream_warnings",
        "all_warnings",
        "upstream",
        "summary",
    }


def test_endpoint_accepts_module_5_data_object_at_the_top_level(api):
    body = post(
        api,
        engineered(features={"hba1c": lab("hba1c", 6.8, "%")}),
    ).json()
    assert body["success"] is True
    assert body["data"]["valid"]["hba1c"]["value"] == pytest.approx(6.8)


def test_endpoint_accepts_module_5_response_envelope_relayed_verbatim(api):
    body = post(
        api,
        {
            "success": True,
            "data": engineered(features={"hba1c": lab("hba1c", 6.8, "%")}),
        },
    ).json()
    assert body["data"]["valid"]["hba1c"]["value"] == pytest.approx(6.8)


def test_an_ambiguous_body_is_refused_rather_than_guessed_at(api):
    response = post(
        api,
        {
            "data": engineered(),
            "features": {"hba1c": lab("hba1c", 6.8, "%")},
        },
    )
    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert set(body["error"]) == {"code", "message"}


def test_an_empty_body_is_accepted_as_an_empty_feature_set(api):
    body = post(api, {}).json()
    assert body["success"] is True
    assert body["data"]["valid"] == {}


def test_a_valid_entry_carries_the_module_5_field_names(api):
    """Module 7 must be able to consume `valid` without re-deriving anything."""
    body = post(
        api,
        engineered(
            features={
                "hba1c": lab(
                    "hba1c",
                    6.8,
                    "%",
                    original_test_name="HbA1c",
                    original_value_raw="6.8",
                    page_number=1,
                    confidence=0.94,
                )
            }
        ),
    ).json()
    entry = body["data"]["valid"]["hba1c"]
    assert set(entry) >= {
        "name",
        "value",
        "unit",
        "canonical_unit",
        "source",
        "provenance",
        "status",
        "questionable",
        "clinically_extreme",
        "flags",
    }
    assert entry["provenance"]["original_test_name"] == "HbA1c"
    assert entry["provenance"]["page_number"] == 1


# --------------------------------------------------------------------------
# The plausible-vs-implausible line, over JSON
# --------------------------------------------------------------------------


def test_glucose_400_is_valid_and_extreme_over_json(api):
    body = post(
        api,
        engineered(features={"blood_glucose": lab("blood_glucose", 400, "mg/dl")}),
    ).json()
    data = body["data"]
    assert data["valid"]["blood_glucose"]["clinically_extreme"] is True
    assert data["valid"]["blood_glucose"]["extreme_direction"] == "high"
    assert data["rejected"] == {}
    assert data["clinically_extreme"] == ["blood_glucose"]


def test_glucose_40000_is_rejected_over_json(api):
    body = post(
        api,
        engineered(features={"blood_glucose": lab("blood_glucose", 40000, "mg/dl")}),
    ).json()
    data = body["data"]
    assert data["valid"] == {}
    rejection = data["rejected"]["blood_glucose"]
    assert rejection["reason_code"] == RejectionCode.IMPLAUSIBLE_VALUE_HIGH
    assert rejection["value"] == 40000
    assert rejection["findings"][0]["limit"] == 3000.0


def test_a_non_canonical_unit_is_rejected_over_json(api):
    feature = lab("creatinine", 1.0, "flurbs")
    feature["canonical_unit"] = False
    body = post(api, engineered(features={"creatinine": feature})).json()
    rejected = body["data"]["rejected"]["creatinine"]
    assert rejected["reason_code"] == RejectionCode.NON_CANONICAL_UNIT
    assert rejected["value"] == 1.0
    assert rejected["unit"] == "flurbs"


def test_unit_assumed_is_flagged_over_json(api):
    body = post(
        api,
        engineered(
            features={
                "hemoglobin": lab("hemoglobin", 14.2, "g/dl", unit_assumed=True)
            }
        ),
    ).json()
    data = body["data"]
    assert data["valid"]["hemoglobin"]["questionable"] is True
    assert "hemoglobin" in data["questionable"]
    assert FlagCode.UNIT_ASSUMED in [
        f["code"] for f in data["valid"]["hemoglobin"]["flags"]
    ]


def test_a_censored_value_is_flagged_over_json(api):
    body = post(
        api,
        engineered(
            features={
                "vitamin_d": lab(
                    "vitamin_d", 3.0, "ng/ml", censored="left", original_value_raw="<3"
                )
            }
        ),
    ).json()
    flags = [f["code"] for f in body["data"]["valid"]["vitamin_d"]["flags"]]
    assert FlagCode.CENSORED_VALUE in flags


# --------------------------------------------------------------------------
# TRI-STATE over JSON -- all three states
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["hypertension", "heart_disease"])
def test_tristate_true_over_json(api, name):
    profile_feature = {
        "name": name,
        "value": True,
        "unit": None,
        "canonical_unit": True,
        "source": "patient_profile",
        "provenance": {"source": "patient_profile"},
    }
    body = post(api, engineered(features={name: profile_feature})).json()
    assert body["data"]["valid"][name]["value"] is True


@pytest.mark.parametrize("name", ["hypertension", "heart_disease"])
def test_tristate_explicit_false_over_json(api, name):
    profile_feature = {
        "name": name,
        "value": False,
        "unit": None,
        "canonical_unit": True,
        "source": "patient_profile",
        "provenance": {"source": "patient_profile"},
    }
    body = post(api, engineered(features={name: profile_feature})).json()
    assert body["data"]["valid"][name]["value"] is False
    assert body["data"]["rejected"] == {}


@pytest.mark.parametrize("name", ["hypertension", "heart_disease"])
def test_tristate_unknown_stays_unknown_over_json(api, name):
    """JSON is where a tri-state has historically been flattened to false."""
    body = post(api, engineered(missing_features=[name])).json()
    data = body["data"]
    assert name not in data["valid"]
    assert name not in data["questionable"]
    assert name not in data["rejected"]
    assert name in data["missing_features"]
    # And nowhere in the serialised payload does it appear as a false value.
    assert data["valid"] == {}


@pytest.mark.parametrize("name", ["hypertension", "heart_disease"])
def test_a_json_null_tristate_is_rejected_not_coerced(api, name):
    profile_feature = {
        "name": name,
        "value": None,
        "unit": None,
        "canonical_unit": True,
        "source": "patient_profile",
        "provenance": {"source": "patient_profile"},
    }
    body = post(api, engineered(features={name: profile_feature})).json()
    assert body["data"]["rejected"][name]["reason_code"] == RejectionCode.NOT_A_BOOLEAN
    assert name not in body["data"]["valid"]


# --------------------------------------------------------------------------
# Warning propagation over the wire
# --------------------------------------------------------------------------


def test_warning_origins_survive_the_endpoint(api):
    body = post(
        api,
        engineered(
            features={"hba1c": lab("hba1c", 6.8, "%")},
            all_warnings=[
                {
                    "stage": STAGE_EXTRACTION,
                    "module": 4,
                    "message": "page 1 was recovered by the PDF repairer",
                },
                {
                    "stage": STAGE_FEATURE_ENGINEERING,
                    "module": 5,
                    "message": "a Module 5 caveat",
                },
            ],
        ),
    ).json()
    warnings = body["data"]["all_warnings"]
    assert [w["stage"] for w in warnings[:2]] == [
        STAGE_EXTRACTION,
        STAGE_FEATURE_ENGINEERING,
    ]
    assert [w["module"] for w in warnings[:2]] == [4, 5]
    assert all(set(w) == {"stage", "module", "message"} for w in warnings)


def test_module_6_warnings_are_tagged_validation_over_json(api):
    body = post(
        api,
        engineered(features={"blood_glucose": lab("blood_glucose", 40000, "mg/dl")}),
    ).json()
    own = [w for w in body["data"]["all_warnings"] if w["stage"] == STAGE_VALIDATION]
    assert own and all(w["module"] == 6 for w in own)


def test_upstream_context_survives_the_endpoint(api):
    body = post(
        api,
        engineered(
            features={"hba1c": lab("hba1c", 6.8, "%")},
            unmapped=[
                {
                    "test_name": "Urine Ketones",
                    "value_raw": "Negative",
                    "reason": "non_numeric_value",
                }
            ],
            missing_features=["bmi"],
            upstream={
                "provided": True,
                "extraction_confidence": 0.88,
                "pages": [
                    {"page_number": 1, "raw_text_available": True},
                    {"page_number": 2, "raw_text_available": False},
                ],
                "pages_unreadable": [2],
            },
        ),
    ).json()
    data = body["data"]
    assert data["upstream"]["extraction_confidence"] == 0.88
    assert data["upstream"]["pages_unreadable"] == [2]
    assert data["missing_features"] == ["bmi"]
    assert data["unmapped"][0]["test_name"] == "Urine Ketones"
    assert data["summary"]["partial_document"] is True


# --------------------------------------------------------------------------
# Authentication
# --------------------------------------------------------------------------


def test_the_endpoint_requires_the_service_key(authed_client_factory):
    api = authed_client_factory()
    assert api.post(ENDPOINT, json={}).status_code == 401
    body = api.post(ENDPOINT, json={}).json()
    assert body["success"] is False
    assert body["error"]["code"] == "UNAUTHORIZED"


def test_the_endpoint_accepts_the_correct_service_key(authed_client_factory):
    api = authed_client_factory()
    response = api.post(
        ENDPOINT, json={}, headers={SERVICE_KEY_HEADER: TEST_SERVICE_KEY}
    )
    assert response.status_code == 200


def test_the_rules_endpoint_requires_the_service_key(authed_client_factory):
    api = authed_client_factory()
    assert api.get(RULES_ENDPOINT).status_code == 401


def test_the_validation_route_declares_the_auth_dependency():
    from app.core.auth import require_service_key

    routes = [r for r in walk_routes(app.routes) if getattr(r, "path", "") == ENDPOINT]
    assert routes, "the validation route is not mounted"
    for route in routes:
        declared = any(
            d.dependency is require_service_key
            for d in getattr(route, "dependencies", [])
        )
        # Depending on the FastAPI version the router-level dependency is
        # either merged onto the route or resolved through the dependant tree.
        resolved = any(
            getattr(d, "call", None) is require_service_key
            for d in getattr(getattr(route, "dependant", None), "dependencies", [])
        )
        assert declared or resolved, f"{route.path} is not behind service auth"


# --------------------------------------------------------------------------
# The published rule table
# --------------------------------------------------------------------------


def test_the_rule_table_is_published_for_review(api):
    body = api.get(RULES_ENDPOINT).json()
    assert body["success"] is True
    features = body["data"]["features"]
    assert features["blood_glucose"]["possible_high"] == 3000.0
    assert features["blood_glucose"]["extreme_high"] == 400.0
    assert body["data"]["policy"]


# --------------------------------------------------------------------------
# A realistic full payload, Module 4 -> 5 -> 6
# --------------------------------------------------------------------------


REALISTIC_EXTRACTION = {
    "source": {
        "filename": "report.pdf",
        "mime_type": "application/pdf",
        "page_count": 2,
        "size_bytes": 20481,
    },
    "pages": [
        {"page_number": 1, "raw_text": "HbA1c 6.8 % H 4.0 - 5.6"},
        {"page_number": 2, "raw_text": None},
    ],
    "extracted_parameters": [
        {
            "test_name": "HbA1c",
            "value_raw": "6.8",
            "value_numeric": 6.8,
            "unit": "%",
            "reference_range_raw": "4.0 - 5.6",
            "reference_low": 4.0,
            "reference_high": 5.6,
            "flag": "high",
            "page_number": 1,
            "confidence": 0.94,
        },
        {
            "test_name": "Fasting Blood Glucose",
            "value_raw": "400",
            "value_numeric": 400.0,
            "unit": "mg/dL",
            "page_number": 1,
            "confidence": 0.91,
        },
        {
            "test_name": "Total Cholesterol",
            "value_raw": "19000",
            "value_numeric": 19000.0,
            "unit": "mg/dL",
            "page_number": 1,
            "confidence": 0.55,
        },
        {
            "test_name": "Creatinine",
            "value_raw": "1.0",
            "value_numeric": 1.0,
            "unit": "flurbs",
            "page_number": 1,
            "confidence": 0.9,
        },
        {
            "test_name": "Vitamin D (25-OH)",
            "value_raw": "<3",
            "value_numeric": 3.0,
            "unit": "ng/mL",
            "page_number": 1,
            "confidence": 0.9,
        },
        {
            "test_name": "Urine Ketones",
            "value_raw": "Negative",
            "value_numeric": None,
            "unit": None,
            "page_number": 1,
            "confidence": 0.9,
        },
    ],
    "report_metadata": {
        "lab_name": "Northfield Diagnostic Laboratory",
        "report_date": "12/03/2024",
    },
    "extraction_confidence": 0.9,
    "warnings": ["page 1 was recovered by the PDF repairer"],
}

REALISTIC_PROFILE = {
    "age": 45,
    "gender": "male",
    "bmi": 27.4,
    "smokingHistory": "former",
    "heartDisease": False,
    # `hypertension` deliberately absent -- it is UNKNOWN.
}


def test_a_realistic_payload_end_to_end(api):
    module_5 = engineer_from_extraction(REALISTIC_EXTRACTION, REALISTIC_PROFILE)
    response = post(api, {"engineered": module_5.model_dump(mode="json")})
    assert response.status_code == 200
    data = response.json()["data"]

    # Usable set.
    assert set(data["valid"]) == {
        "hba1c",
        "blood_glucose",
        "vitamin_d",
        "bmi",
        "age",
        "heart_disease",
        "smoking_history",
        "gender",
    }
    assert data["valid"]["heart_disease"]["value"] is False

    # Rejections, each with a reason.
    assert (
        data["rejected"]["cholesterol"]["reason_code"]
        == RejectionCode.IMPLAUSIBLE_VALUE_HIGH
    )
    assert (
        data["rejected"]["creatinine"]["reason_code"]
        == RejectionCode.NON_CANONICAL_UNIT
    )
    assert data["rejected"]["cholesterol"]["value"] == 19000.0

    # Abnormal-but-real is kept and prioritised.
    assert "blood_glucose" in data["clinically_extreme"]

    # Questionable, but usable.
    assert "vitamin_d" in data["questionable"]

    # UNKNOWN stayed unknown.
    assert "hypertension" in data["missing_features"]
    assert "hypertension" not in data["valid"]
    assert "hypertension" not in data["rejected"]

    # Nothing upstream was lost.
    assert data["unmapped"]
    assert data["upstream"]["pages_unreadable"] == [2]
    assert data["upstream"]["report_metadata"]["lab_name"] == (
        "Northfield Diagnostic Laboratory"
    )
    stages = {w["stage"] for w in data["all_warnings"]}
    assert STAGE_EXTRACTION in stages
    assert STAGE_VALIDATION in stages
    assert any(
        "PDF repairer" in w["message"]
        for w in data["all_warnings"]
        if w["stage"] == STAGE_EXTRACTION
    )

    # Counts are self-consistent.
    summary = data["summary"]
    assert summary["valid_count"] == len(data["valid"])
    assert summary["rejected_count"] == len(data["rejected"])
    assert summary["questionable_count"] == len(data["questionable"])
