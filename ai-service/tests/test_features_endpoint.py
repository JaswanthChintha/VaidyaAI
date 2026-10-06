"""POST /api/v1/features/engineer -- the Module 5 HTTP contract.

Response shapes must match the rest of the service: `{success, data}` on
success and `{success, error: {code, message}}` on failure.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.test_feature_engineer import OBSERVED_MODULE_4_PARAMETERS

ENDPOINT = "/api/v1/features/engineer"


@pytest.fixture()
def api(client_factory) -> TestClient:
    # The Module 5 route needs no Gemini client, but reusing the existing
    # factory keeps env isolation identical across the suite.
    return client_factory()


def post(api: TestClient, payload: dict):
    return api.post(ENDPOINT, json=payload)


# --------------------------------------------------------------------------
# Happy path
# --------------------------------------------------------------------------


def test_endpoint_returns_the_success_envelope(api):
    response = post(api, {"extraction": {"extracted_parameters": []}})
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert set(body["data"]) >= {
        "features",
        "unmapped",
        "conversions_applied",
        "duplicates_resolved",
        "missing_features",
        "warnings",
        "summary",
    }


def test_endpoint_accepts_module_4_data_object_verbatim(api):
    module4_data = {
        "source": {"filename": "report.pdf", "mime_type": "application/pdf"},
        "raw_text": "NORTHFIELD DIAGNOSTIC LABORATORY ...",
        "pages": [{"page_number": 1, "raw_text": "..."}],
        "extracted_parameters": OBSERVED_MODULE_4_PARAMETERS,
        "report_metadata": {"lab_name": "Northfield", "report_date": "12/03/2024"},
        "extraction_confidence": 0.94,
        "warnings": [],
    }
    body = post(api, {"extraction": module4_data}).json()
    assert body["success"] is True
    features = body["data"]["features"]
    assert set(features) == {
        "hba1c",
        "blood_glucose",
        "hemoglobin",
        "creatinine",
        "cholesterol",
        "vitamin_d",
    }
    assert features["hba1c"]["value"] == pytest.approx(6.8)
    assert features["hba1c"]["unit"] == "%"
    assert features["hba1c"]["source"] == "lab_report"
    assert features["hba1c"]["provenance"]["original_test_name"] == "HbA1c"


def test_endpoint_shape_matches_the_documented_contract(api):
    body = post(
        api,
        {
            "extraction": {
                "extracted_parameters": [
                    {
                        "test_name": "HbA1c",
                        "value_raw": "6.8",
                        "value_numeric": 6.8,
                        "unit": "%",
                    }
                ]
            }
        },
    ).json()
    feature = body["data"]["features"]["hba1c"]
    assert set(feature) == {"name", "value", "unit", "canonical_unit", "source",
                            "provenance"}
    provenance = feature["provenance"]
    for key in (
        "source",
        "original_test_name",
        "original_value_raw",
        "original_unit",
        "matched_synonym",
        "parameter_index",
        "confidence",
        "unit_converted",
        "conversion",
    ):
        assert key in provenance


def test_endpoint_merges_profile_context(api):
    body = post(
        api,
        {
            "extraction": {"extracted_parameters": OBSERVED_MODULE_4_PARAMETERS},
            "profile": {
                "age": 45,
                "gender": "male",
                "bmi": 27.4,
                "hypertension": True,
                "heartDisease": False,
                "smokingHistory": "never",
            },
        },
    ).json()
    features = body["data"]["features"]
    assert features["age"]["value"] == 45
    assert features["age"]["source"] == "patient_profile"
    assert features["hypertension"]["value"] is True
    assert features["heart_disease"]["value"] is False
    assert features["smoking_history"]["value"] == "never"
    assert body["data"]["summary"]["profile_provided"] is True


def test_endpoint_preserves_the_tri_state_over_json(api):
    """JSON round-trip must not turn an absent boolean into false."""
    body = post(
        api,
        {
            "extraction": {"extracted_parameters": []},
            "profile": {"age": 45, "hypertension": None},
        },
    ).json()
    features = body["data"]["features"]
    assert "hypertension" not in features
    assert "heart_disease" not in features
    assert "hypertension" in body["data"]["missing_features"]


def test_endpoint_reports_conversions(api):
    body = post(
        api,
        {
            "extraction": {
                "extracted_parameters": [
                    {
                        "test_name": "Creatinine",
                        "value_raw": "88.4017",
                        "value_numeric": 88.4017,
                        "unit": "µmol/L",
                    }
                ]
            }
        },
    ).json()
    conversion = body["data"]["conversions_applied"][0]
    assert conversion["feature"] == "creatinine"
    assert conversion["original_unit"] == "µmol/L"
    assert conversion["canonical_unit"] == "mg/dl"
    assert conversion["canonical_value"] == pytest.approx(1.0, abs=1e-5)
    assert "mg/dl = umol/l x" in conversion["formula"]


def test_endpoint_reports_unmapped_and_duplicates(api):
    body = post(
        api,
        {
            "extraction": {
                "extracted_parameters": [
                    {"test_name": "TSH", "value_raw": "2.1", "unit": "µIU/mL"},
                    {"test_name": "Fasting Blood Glucose", "value_raw": "112",
                     "value_numeric": 112.0, "unit": "mg/dL"},
                    {"test_name": "PPBS", "value_raw": "180",
                     "value_numeric": 180.0, "unit": "mg/dL"},
                ]
            }
        },
    ).json()
    data = body["data"]
    assert data["features"]["blood_glucose"]["value"] == pytest.approx(112.0)
    reasons = {u["test_name"]: u["reason"] for u in data["unmapped"]}
    assert reasons["TSH"] == "no_canonical_feature"
    assert reasons["PPBS"] == "duplicate_discarded"
    assert data["duplicates_resolved"][0]["feature"] == "blood_glucose"


def test_endpoint_defaults_to_an_empty_extraction(api):
    body = post(api, {}).json()
    assert body["success"] is True
    assert body["data"]["features"] == {}


# --------------------------------------------------------------------------
# Failure paths use the service-wide error envelope
# --------------------------------------------------------------------------


def test_invalid_row_returns_the_error_envelope(api):
    response = post(
        api, {"extraction": {"extracted_parameters": [{"value_raw": "6.8"}]}}
    )
    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "INVALID_REQUEST"
    assert isinstance(body["error"]["message"], str)


def test_invalid_profile_returns_the_error_envelope(api):
    response = post(
        api, {"extraction": {"extracted_parameters": []}, "profile": {"age": -5}}
    )
    assert response.status_code == 422
    assert response.json()["success"] is False


def test_error_message_does_not_echo_submitted_medical_values(api):
    response = post(
        api,
        {
            "extraction": {
                "extracted_parameters": [{"value_raw": "SECRETVALUE-12345"}]
            }
        },
    )
    assert "SECRETVALUE-12345" not in response.text


def test_get_is_not_allowed(api):
    response = api.get(ENDPOINT)
    assert response.status_code == 405
    assert response.json()["success"] is False


# --------------------------------------------------------------------------
# Catalog endpoint
# --------------------------------------------------------------------------


def test_catalog_publishes_the_canonical_feature_space(api):
    body = api.get("/api/v1/features/catalog").json()
    assert body["success"] is True
    data = body["data"]
    assert set(data["lab_features"]) == {
        "hba1c",
        "blood_glucose",
        "hemoglobin",
        "vitamin_d",
        "vitamin_b12",
        "creatinine",
        "cholesterol",
        "triglycerides",
        # ---- the complete blood count ----
        "hematocrit",
        "rbc_count",
        "mcv",
        "mch",
        "mchc",
        "wbc_count",
        "neutrophils",
        "lymphocytes",
        "monocytes",
        "eosinophils",
        "basophils",
        "platelet_count",
        # ---- the liver panel (2026-10-04) ----
        "alt",
        "ast",
        "bilirubin_total",
    }
    # The differentials are PERCENTAGES of the white cell count and accept no
    # other unit, which the published catalogue has to say out loud: a caller
    # sending an absolute count in 10^3/uL is sending a different quantity,
    # not the same one in another unit.
    assert data["features"]["neutrophils"]["canonical_unit"] == "%"
    assert list(data["features"]["neutrophils"]["accepted_units"]) == ["%"]
    assert data["features"]["creatinine"]["canonical_unit"] == "mg/dl"
    assert "umol/l" in data["features"]["creatinine"]["accepted_units"]
    assert data["features"]["hypertension"]["value_type"] == "boolean"
    assert data["duplicate_policy"].startswith("deterministic_rank")


def test_root_lists_the_module_5_endpoint(api):
    body = api.get("/").json()
    assert body["data"]["engineer_features"] == f"POST {ENDPOINT}"


def test_openapi_documents_the_module_5_route(api):
    schema = api.get("/openapi.json").json()
    assert ENDPOINT in schema["paths"]
    assert "post" in schema["paths"][ENDPOINT]
