"""The Modules 23/25/26 HTTP layer -- `app/api/routes_explain.py`.

WHY THIS FILE BUILDS ITS OWN APP
--------------------------------
`app/main.py` is owned by the integrator, who mounts the routers. Until the
`include_router` line lands there, mounting inside a test would mutate the
shared `app` object for the rest of the session. So these tests assemble a
minimal FastAPI app carrying only this router plus the same error handling
`main.py` installs.

`test_the_router_is_mounted_when_main_includes_it` closes the loop: once the
line is added, it asserts the routes are reachable on the real app, and
`tests/test_auth.py`'s recursive walk starts covering them automatically. It
skips (rather than fails) while the router is unmounted, so this file is honest
about which state it is in.
"""

from __future__ import annotations

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


FEATURE_BODY = {
    "feature": "hba1c",
    "value": 6.8,
    "unit": "%",
    "conditions": ["Diabetes"],
    "reference_low": 4.0,
    "reference_high": 5.6,
    "status": "valid",
}


# --------------------------------------------------------------------------
# Auth -- the same guarantee routes_report.py carries
# --------------------------------------------------------------------------


ROUTES = [
    ("post", "/api/v1/explain/feature", FEATURE_BODY),
    ("post", "/api/v1/explain/report", {"report": {}}),
    ("post", "/api/v1/explain/term", {"term": "HbA1c"}),
    ("get", "/api/v1/explain/terms", None),
    ("post", "/api/v1/explain/guidance", {"conditions": ["Diabetes"]}),
    ("get", "/api/v1/explain/policy", None),
    # ADDING THIS LINE IS THE WHOLE FIX FOR A FEATURE THAT WAS DEAD ON EVERY
    # CALL. `/glossary` shipped returning a bare payload instead of the
    # `{success, data}` envelope, so the backend rejected every 200 as
    # malformed and threw away descriptions it had already generated and
    # safety-validated. `test_every_route_answers_with_the_key` asserts
    # `success is True` and would have caught it on the first run -- the route
    # was simply never listed here.
    ("post", "/api/v1/explain/glossary", {"test_names": ["Blood Urea"]}),
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
    """Belt and braces: the dependency is on the router, not per-handler."""
    from app.api.routes_explain import router
    from app.core.auth import require_service_key

    assert any(
        getattr(d, "dependency", None) is require_service_key
        for d in router.dependencies
    )


def test_the_router_is_mounted_when_main_includes_it():
    """Skips while `main.py` has not yet been updated by the integrator."""
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


# --------------------------------------------------------------------------
# Module 23 over HTTP
# --------------------------------------------------------------------------


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


# --------------------------------------------------------------------------
# Module 25 over HTTP
# --------------------------------------------------------------------------


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


# --------------------------------------------------------------------------
# Module 26 over HTTP
# --------------------------------------------------------------------------


def test_guidance_is_served_without_any_model(client_factory):
    """No LLM is configured at all, and the route still answers in full."""
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


# --------------------------------------------------------------------------
# Policy
# --------------------------------------------------------------------------


def test_the_policy_route_publishes_all_three_modules(explain_client):
    data = explain_client.get("/api/v1/explain/policy", headers=HEADERS).json()["data"]

    assert data["patient_explanation"]["module"] == 23
    assert data["terminology"]["module"] == 25
    assert data["lifestyle_guidance"]["module"] == 26
    assert data["never"] == "LLM output shown directly to a patient"
    assert data["lifestyle_guidance"]["uses_llm"] is False


# --------------------------------------------------------------------------
# The glossary over HTTP
# --------------------------------------------------------------------------
#
# The module itself has its own suite. These are about the TRANSPORT, which is
# where it was broken: the descriptions were generated, validated and cached,
# and then discarded by the backend because the reply was not in the envelope
# every other route here uses.


def test_the_glossary_answers_inside_the_standard_envelope(explain_client):
    response = explain_client.post(
        "/api/v1/explain/glossary",
        json={"test_names": ["Blood Urea"]},
        headers=HEADERS,
    )
    assert response.status_code == 200
    body = response.json()
    # The two properties the backend's `unwrapEnvelope` requires, asserted
    # separately from the payload so a future change to either is visible.
    assert body["success"] is True
    assert isinstance(body["data"], dict)
    assert body["data"]["entries"][0]["test_name"] == "Blood Urea"


def test_the_glossary_answers_with_no_model_configured(client_factory):
    """An unconfigured key is a service state, not an error.

    The caller renders the values with no description, exactly as it does when
    a description is refused -- and it must be able to tell the difference,
    which is why `entries` is empty rather than carrying placeholder text.
    """
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
    """The safety property is the SHAPE, so it is asserted at the shape.

    A caller cannot send a value, a unit, a reference range or a flag even by
    accident: the request model forbids extra fields, so the model can never be
    asked what a particular person's number means.
    """
    response = explain_client.post(
        "/api/v1/explain/glossary",
        json={"test_names": ["Potassium"], "value": 5.2, "unit": "mmol/L"},
        headers=HEADERS,
    )
    assert response.status_code == 422


def test_the_glossary_sends_no_patient_data_to_the_model(client_factory):
    """What actually reaches the model is the test name and nothing else."""
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
    # This patient's actual result, from fixture 06. None of it can be in the
    # prompt, because none of it was ever sent to this route -- and the request
    # model has nowhere to put it even if a caller tried.
    for forbidden in ("5.2", "mmol/L", "3.5 - 5.1"):
        assert forbidden not in prompt


def test_an_oversized_name_list_is_rejected_by_the_schema(explain_client):
    response = explain_client.post(
        "/api/v1/explain/glossary",
        json={"test_names": [f"Test {index}" for index in range(65)]},
        headers=HEADERS,
    )
    assert response.status_code == 422


# --------------------------------------------------------------------------
# Logging
# --------------------------------------------------------------------------


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
