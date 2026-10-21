from __future__ import annotations

import re
from typing import Any, List

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from tests.conftest import TEST_SERVICE_KEY
from tests.test_explanation import _APPROVABLE, _UNSAFE, FakeTextClient

HEADERS = {"X-Service-Key": TEST_SERVICE_KEY}


def _build_app(llm: Any, **settings_overrides: Any):
    from app.config import Settings, get_settings
    from app.core.errors import ServiceError
    from app.api import routes_explain

    settings_overrides.setdefault("ai_service_api_key", TEST_SERVICE_KEY)
    settings_overrides.setdefault("allow_unauthenticated", False)
    test_settings = Settings(_env_file=None, **settings_overrides)

    app = FastAPI()
    app.include_router(routes_explain.router)

    @app.exception_handler(ServiceError)
    async def _service_error(_: Request, exc: ServiceError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=exc.to_dict())

    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[routes_explain.get_explanation_llm] = lambda: llm
    return app


@pytest.fixture()
def client_factory(_isolate_env: Any):
    created: List[TestClient] = []

    def _factory(llm: Any = None, **overrides: Any) -> TestClient:
        tc = TestClient(_build_app(llm, **overrides), raise_server_exceptions=False)
        created.append(tc)
        return tc

    yield _factory
    for tc in created:
        tc.close()


@pytest.fixture()
def explain_client(client_factory: Any) -> TestClient:
    return client_factory(FakeTextClient(_APPROVABLE))


@pytest.fixture(autouse=True)
def _clear_lab_polarity_cache():
    from app.services import lab_name_match, lab_polarity

    lab_polarity.reset_cache()
    lab_name_match.reset_cache()
    yield
    lab_polarity.reset_cache()
    lab_name_match.reset_cache()


FEATURE_BODY = {
    "feature": "hba1c",
    "value": 6.8,
    "unit": "%",
    "conditions": ["Diabetes"],
    "reference_low": 4.0,
    "reference_high": 5.6,
    "status": "valid",
}


ROUTES = [
    ("post", "/api/v1/explain/feature", FEATURE_BODY),
    ("post", "/api/v1/explain/report", {"report": {}}),
    ("post", "/api/v1/explain/term", {"term": "HbA1c"}),
    ("get", "/api/v1/explain/terms", None),
    ("post", "/api/v1/explain/guidance", {"conditions": ["Diabetes"]}),
    ("get", "/api/v1/explain/policy", None),
    ("post", "/api/v1/explain/glossary", {"test_names": ["Blood Urea"]}),
    (
        "post",
        "/api/v1/explain/lab-polarity",
        {"series": [{"test_name": "Blood Urea", "first_value": 1.0, "last_value": 2.0}]},
    ),
    (
        "post",
        "/api/v1/explain/lab-name-match",
        {"names": ["Blood Urea", "Urea Nitrogen"]},
    ),
    ("post", "/api/v1/explain/clinician-summary", {"summary": {}}),
    (
        "post",
        "/api/v1/explain/summary-prose",
        {"sentences": ["This tool checked 8 conditions."], "names": []},
    ),
    (
        "post",
        "/api/v1/explain/finding-context",
        {"findings": [{"test_name": "CRP", "direction": "raised"}]},
    ),
]


@pytest.mark.parametrize("method,path,body", ROUTES, ids=lambda v: str(v))
def test_every_route_requires_the_service_key(method, path, body, explain_client):
    call = getattr(explain_client, method)
    response = call(path) if body is None else call(path, json=body)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.parametrize("method,path,body", ROUTES, ids=lambda v: str(v))
def test_every_route_answers_with_the_key(method, path, body, explain_client):
    call = getattr(explain_client, method)
    response = (
        call(path, headers=HEADERS)
        if body is None
        else call(path, json=body, headers=HEADERS)
    )
    assert response.status_code == 200
    assert response.json()["success"] is True


def test_every_route_declares_the_dependency_on_the_router_itself():
    from app.api.routes_explain import router
    from app.core.auth import require_service_key

    assert any(
        getattr(d, "dependency", None) is require_service_key
        for d in router.dependencies
    )


def test_the_router_is_mounted_when_main_includes_it():
    from app.main import app

    def walk(routes):
        for route in routes:
            original = getattr(route, "original_router", None)
            if original is not None:
                yield from walk(original.routes)
            elif str(getattr(route, "path", "")).startswith("/api/v1"):
                yield route

    paths = {r.path for r in walk(app.routes)}
    if "/api/v1/explain/feature" not in paths:
        pytest.skip(
            "app/main.py does not yet include routes_explain.router -- add "
            "`app.include_router(routes_explain.router)` alongside the other "
            "include_router calls"
        )
    from app.core.auth import require_service_key

    for route in walk(app.routes):
        if route.path.startswith("/api/v1/explain"):
            assert any(
                getattr(d, "dependency", None) is require_service_key
                for d in route.dependencies
            ), route.path


def test_an_approved_explanation_comes_back_with_its_sources(explain_client):
    response = explain_client.post(
        "/api/v1/explain/feature", json=FEATURE_BODY, headers=HEADERS
    )
    data = response.json()["data"]

    assert data["outcome"] == "generated"
    assert data["explanation"] == _APPROVABLE
    assert data["fallback"] is None
    assert data["sources"] and data["sources"][0]["basis"]
    assert data["safety"]["validated"] is True


def test_a_refused_generation_returns_200_with_the_fallback(client_factory):
    client = client_factory(FakeTextClient(_UNSAFE))
    response = client.post(
        "/api/v1/explain/feature", json=FEATURE_BODY, headers=HEADERS
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["outcome"] == "withheld_by_safety"
    assert data["explanation"] is None
    assert data["fallback"]["generated_explanation_available"] is False
    assert data["fallback"]["recommendations"]
    assert "metformin" not in response.text


def test_no_model_configured_returns_200_and_the_notice(client_factory):
    client = client_factory(None)
    response = client.post(
        "/api/v1/explain/feature", json=FEATURE_BODY, headers=HEADERS
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["outcome"] == "model_unavailable"
    assert data["notice"]


@pytest.mark.parametrize(
    "failure",
    [
        "ModelTimeoutError",
        "ModelRateLimitedError",
        "ModelError",
        "RuntimeError",
    ],
)
def test_a_model_failure_is_never_a_500(failure, client_factory):
    from app.core import errors

    exception = {
        "ModelTimeoutError": errors.ModelTimeoutError("t"),
        "ModelRateLimitedError": errors.ModelRateLimitedError("r"),
        "ModelError": errors.ModelError("m"),
        "RuntimeError": RuntimeError("boom"),
    }[failure]

    client = client_factory(FakeTextClient(exception))
    response = client.post(
        "/api/v1/explain/feature", json=FEATURE_BODY, headers=HEADERS
    )
    assert response.status_code == 200
    assert response.json()["data"]["explanation"] is None


def test_an_unknown_field_is_a_422_not_a_silent_default(explain_client):
    body = dict(FEATURE_BODY, featrue="hba1c")
    response = explain_client.post(
        "/api/v1/explain/feature", json=body, headers=HEADERS
    )
    assert response.status_code == 422


def test_free_text_is_not_accepted_as_a_feature(explain_client):
    response = explain_client.post(
        "/api/v1/explain/feature",
        json={"feature": "what does my TSH mean"},
        headers=HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["data"]["outcome"] == "unknown_subject"


def test_the_report_route_explains_a_module_17_report(explain_client):
    body = {
        "report": {
            "laboratory_values": [
                {
                    "feature": "hba1c",
                    "value": 6.8,
                    "unit": "%",
                    "status": "valid",
                    "usable": True,
                    "reference_low": 4.0,
                    "reference_high": 5.6,
                }
            ],
            "conditions": [],
        }
    }
    response = explain_client.post(
        "/api/v1/explain/report", json=body, headers=HEADERS
    )
    data = response.json()["data"]
    assert data["generated_count"] == 1
    assert data["explanations"][0]["feature"] == "hba1c"


def test_the_report_route_caps_the_number_of_model_calls(explain_client):
    response = explain_client.post(
        "/api/v1/explain/report",
        json={"report": {}, "max_explanations": 99},
        headers=HEADERS,
    )
    assert response.status_code == 422


@pytest.mark.parametrize("term", ["TSH", "ferritin", "PSA"])
def test_an_uncovered_term_is_refused_over_http(term, explain_client):
    response = explain_client.post(
        "/api/v1/explain/term", json={"term": term}, headers=HEADERS
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["covered"] is False
    assert data["outcome"] == "term_not_covered"
    assert data["explanation"] is None
    assert data["sources"] == []


def test_a_covered_term_is_served_over_http(explain_client):
    response = explain_client.post(
        "/api/v1/explain/term", json={"term": "eGFR"}, headers=HEADERS
    )
    data = response.json()["data"]
    assert data["covered"] is True
    assert data["source_kind"] == "curated_knowledge_base"
    assert data["canonical_feature"] == "creatinine"


def test_an_oversized_term_is_rejected_by_the_schema(explain_client):
    response = explain_client.post(
        "/api/v1/explain/term", json={"term": "x" * 5000}, headers=HEADERS
    )
    assert response.status_code == 422


def test_the_terms_route_publishes_the_vocabulary_and_the_gaps(explain_client):
    data = explain_client.get("/api/v1/explain/terms", headers=HEADERS).json()["data"]
    assert data["free_text_retrieval"] is False
    assert "hba1c" in data["covered_terms"]
    assert data["known_gaps"]


def test_guidance_is_served_without_any_model(client_factory):
    client = client_factory(None)
    response = client.post(
        "/api/v1/explain/guidance",
        json={"conditions": ["Diabetes"], "features": ["hba1c"]},
        headers=HEADERS,
    )
    data = response.json()["data"]
    assert data["generated"] is False
    assert data["items"]
    assert data["text"]


def test_guidance_reports_unknown_names(explain_client):
    response = explain_client.post(
        "/api/v1/explain/guidance",
        json={"conditions": ["diabetes"], "codes": ["NOPE"]},
        headers=HEADERS,
    )
    data = response.json()["data"]
    assert data["unknown_conditions"] == ["diabetes"]
    assert data["unknown_codes"] == ["NOPE"]


def test_the_policy_route_publishes_all_three_modules(explain_client):
    data = explain_client.get("/api/v1/explain/policy", headers=HEADERS).json()["data"]

    assert data["patient_explanation"]["module"] == 23
    assert data["terminology"]["module"] == 25
    assert data["lifestyle_guidance"]["module"] == 26
    assert data["never"] == "LLM output shown directly to a patient"
    assert data["lifestyle_guidance"]["uses_llm"] is False


def test_the_glossary_answers_inside_the_standard_envelope(explain_client):
    response = explain_client.post(
        "/api/v1/explain/glossary",
        json={"test_names": ["Blood Urea"]},
        headers=HEADERS,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert isinstance(body["data"], dict)
    assert body["data"]["entries"][0]["test_name"] == "Blood Urea"


def test_the_glossary_answers_with_no_model_configured(client_factory):
    client = client_factory(None)
    response = client.post(
        "/api/v1/explain/glossary",
        json={"test_names": ["Blood Urea"]},
        headers=HEADERS,
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["entries"] == []
    assert data["generated_count"] == 0


def test_the_glossary_request_has_nowhere_to_put_a_patient_value(explain_client):
    response = explain_client.post(
        "/api/v1/explain/glossary",
        json={"test_names": ["Potassium"], "value": 5.2, "unit": "mmol/L"},
        headers=HEADERS,
    )
    assert response.status_code == 422


_POLARITY_JSON = (
    '{"polarity":"higher_is_worse","analytical_cv_pct":4.0,'
    '"within_subject_cv_pct":20.0}'
)

LAB_POLARITY_BODY = {
    "series": [
        {
            "test_name": "Zorblex",
            "first_value": 12.1,
            "last_value": 38.9,
            "unit": "mg/L",
        }
    ]
}


def test_lab_polarity_answers_inside_the_standard_envelope(client_factory):
    client = client_factory(FakeTextClient(_POLARITY_JSON))
    response = client.post(
        "/api/v1/explain/lab-polarity", json=LAB_POLARITY_BODY, headers=HEADERS
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert isinstance(body["data"], dict)

    verdict = body["data"]["verdicts"][0]
    assert verdict["test_name"] == "Zorblex"
    assert verdict["trend"] == "worsening"


def test_lab_polarity_answers_with_no_model_configured(client_factory):
    client = client_factory(None)
    response = client.post(
        "/api/v1/explain/lab-polarity", json=LAB_POLARITY_BODY, headers=HEADERS
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["verdicts"] == []
    assert data["generated"] == 0


def test_lab_polarity_refuses_a_field_it_does_not_declare(client_factory):
    client = client_factory(FakeTextClient(_POLARITY_JSON))
    body = {
        "series": [
            {
                "test_name": "Zorblex",
                "first_value": 12.1,
                "last_value": 38.9,
                "age": 58,
            }
        ]
    }
    response = client.post("/api/v1/explain/lab-polarity", json=body, headers=HEADERS)
    assert response.status_code == 422


def test_lab_polarity_sends_no_patient_data_to_the_model(client_factory):
    fake = FakeTextClient(_POLARITY_JSON)
    client = client_factory(fake)
    client.post(
        "/api/v1/explain/lab-polarity",
        json={
            "series": [
                {
                    "test_name": "Zorblex",
                    "first_value": 12.1,
                    "last_value": 38.9,
                    "unit": "mg/L",
                    "reference_low": 0.0,
                    "reference_high": 6.0,
                }
            ]
        },
        headers=HEADERS,
    )

    assert fake.prompts, "the model was never called"
    for prompt in fake.prompts:
        assert "Zorblex" in prompt
        for leaked in ["12.1", "38.9", "6.0", "mg/L"]:
            assert leaked not in prompt


def test_the_glossary_sends_no_patient_data_to_the_model(client_factory):
    llm = FakeTextClient(_APPROVABLE)
    client = client_factory(llm)
    client.post(
        "/api/v1/explain/glossary",
        json={"test_names": ["Potassium, Serum"]},
        headers=HEADERS,
    )

    assert llm.prompts, "the route did not call the model at all"
    prompt = "\n".join(llm.prompts)
    assert "Potassium, Serum" in prompt
    for forbidden in ("5.2", "mmol/L", "3.5 - 5.1"):
        assert forbidden not in prompt


def test_an_oversized_name_list_is_rejected_by_the_schema(explain_client):
    response = explain_client.post(
        "/api/v1/explain/glossary",
        json={"test_names": [f"Test {index}" for index in range(65)]},
        headers=HEADERS,
    )
    assert response.status_code == 422


_NAME_MATCH_JSON = '{"groups": [["Zorblex Factor", "Frimbulin"]]}'

LAB_NAME_MATCH_BODY = {"names": ["Zorblex Factor", "Frimbulin"]}


def test_lab_name_match_answers_inside_the_standard_envelope(client_factory):
    client = client_factory(FakeTextClient(_NAME_MATCH_JSON))
    response = client.post(
        "/api/v1/explain/lab-name-match", json=LAB_NAME_MATCH_BODY, headers=HEADERS
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert isinstance(body["data"], dict)

    group = body["data"]["groups"][0]
    assert sorted(group["names"]) == ["Frimbulin", "Zorblex Factor"]
    assert body["data"]["accepted"] == 1


def test_lab_name_match_answers_with_no_model_configured(client_factory):
    client = client_factory(None)
    response = client.post(
        "/api/v1/explain/lab-name-match", json=LAB_NAME_MATCH_BODY, headers=HEADERS
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["groups"] == []
    assert data["accepted"] == 0


def test_lab_name_match_has_nowhere_to_put_a_patient_value(client_factory):
    client = client_factory(FakeTextClient(_NAME_MATCH_JSON))
    response = client.post(
        "/api/v1/explain/lab-name-match",
        json={"names": ["Zorblex Factor"], "first_value": 12.1},
        headers=HEADERS,
    )
    assert response.status_code == 422


def test_lab_name_match_sends_no_figure_to_the_model(client_factory):
    fake = FakeTextClient(_NAME_MATCH_JSON)
    client = client_factory(fake)
    client.post(
        "/api/v1/explain/lab-name-match", json=LAB_NAME_MATCH_BODY, headers=HEADERS
    )

    assert fake.prompts, "the model was never called, so this proves nothing"
    prompt = fake.prompts[-1]
    assert "Zorblex Factor" in prompt
    assert re.search(r"\d", prompt) is None


def test_an_oversized_lab_name_list_is_rejected_by_the_schema(explain_client):
    response = explain_client.post(
        "/api/v1/explain/lab-name-match",
        json={"names": [f"Test {index}" for index in range(65)]},
        headers=HEADERS,
    )
    assert response.status_code == 422


def test_the_http_layer_logs_no_phi(caplog, explain_client):
    import logging

    caplog.set_level(logging.DEBUG)
    explain_client.post("/api/v1/explain/feature", json=FEATURE_BODY, headers=HEADERS)
    explain_client.post(
        "/api/v1/explain/term", json={"term": "CANARY-TERM-XYZ"}, headers=HEADERS
    )

    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert "CANARY-TERM-XYZ" not in logged
    assert "6.8" not in logged
    assert TEST_SERVICE_KEY not in logged
