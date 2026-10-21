from __future__ import annotations

import io
import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.core.auth import (
    SERVICE_KEY_HEADER,
    keys_match,
    require_service_key,
)
from tests.conftest import TEST_SERVICE_KEY

EXTRACT = "/api/v1/ocr/extract"
ENGINEER = "/api/v1/features/engineer"
CATALOG = "/api/v1/features/catalog"
HEALTH = "/api/v1/health"

PROTECTED = [EXTRACT, ENGINEER, CATALOG]

SERVICE_ROOT = Path(__file__).resolve().parents[1]


def _call(client, path: str, headers=None, pdf: bytes = b""):
    if path == EXTRACT:
        return client.post(
            path,
            files={"file": ("r.pdf", io.BytesIO(pdf), "application/pdf")},
            headers=headers,
        )
    if path == ENGINEER:
        return client.post(
            path, json={"extraction": {"extracted_parameters": []}}, headers=headers
        )
    return client.get(path, headers=headers)


def test_keys_match_accepts_the_exact_key():
    assert keys_match("abc123", "abc123") is True


@pytest.mark.parametrize(
    "presented",
    [None, "", "   ", "\t\n", "abc12", "abc1234", "ABC123", "abc123 x"],
)
def test_keys_match_rejects_everything_else(presented):
    assert keys_match(presented, "abc123") is False


def test_keys_match_tolerates_surrounding_whitespace_on_a_correct_key():
    assert keys_match("  abc123  ", "abc123") is True


@pytest.mark.parametrize("expected", ["", "   "])
def test_an_unusable_configured_key_never_matches(expected):
    assert keys_match("", expected) is False
    assert keys_match("   ", expected) is False
    assert keys_match("anything", expected) is False


@pytest.mark.parametrize("path", PROTECTED)
def test_protected_endpoints_accept_the_right_key(
    authed_client, synthetic_pdf, path
):
    response = _call(
        authed_client, path, {SERVICE_KEY_HEADER: TEST_SERVICE_KEY}, synthetic_pdf
    )
    assert response.status_code == 200, response.text
    assert response.json()["success"] is True


def test_header_name_is_case_insensitive_as_http_requires(authed_client):
    response = authed_client.get(CATALOG, headers={"x-service-key": TEST_SERVICE_KEY})
    assert response.status_code == 200


@pytest.mark.parametrize("path", PROTECTED)
@pytest.mark.parametrize(
    "headers",
    [
        pytest.param(None, id="missing_header"),
        pytest.param({SERVICE_KEY_HEADER: "wrong-key-entirely-0123456789abcdef"},
                     id="wrong_key"),
        pytest.param({SERVICE_KEY_HEADER: ""}, id="empty_key"),
        pytest.param({SERVICE_KEY_HEADER: "   "}, id="whitespace_key"),
        pytest.param({SERVICE_KEY_HEADER: TEST_SERVICE_KEY[:-1]}, id="truncated_key"),
        pytest.param({SERVICE_KEY_HEADER: TEST_SERVICE_KEY + "x"}, id="extended_key"),
        pytest.param({SERVICE_KEY_HEADER: TEST_SERVICE_KEY.upper()},
                     id="wrong_case_key"),
    ],
)
def test_protected_endpoints_reject_bad_credentials(
    authed_client, synthetic_pdf, path, headers
):
    response = _call(authed_client, path, headers, synthetic_pdf)
    assert response.status_code == 401
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "UNAUTHORIZED"
    assert isinstance(body["error"]["message"], str)
    assert set(body) == {"success", "error"}
    assert set(body["error"]) == {"code", "message"}


def test_missing_and_wrong_keys_are_byte_identical(authed_client):
    missing = authed_client.get(CATALOG)
    wrong = authed_client.get(CATALOG, headers={SERVICE_KEY_HEADER: "nope"})
    empty = authed_client.get(CATALOG, headers={SERVICE_KEY_HEADER: ""})
    blank = authed_client.get(CATALOG, headers={SERVICE_KEY_HEADER: "   "})

    bodies = {r.text for r in (missing, wrong, empty, blank)}
    statuses = {r.status_code for r in (missing, wrong, empty, blank)}
    assert len(bodies) == 1, "401 bodies differ between failure modes"
    assert statuses == {401}


def test_rejection_never_echoes_the_presented_or_configured_key(authed_client):
    presented = "SECRET-PRESENTED-CANARY-0123456789"
    response = authed_client.get(CATALOG, headers={SERVICE_KEY_HEADER: presented})
    assert presented not in response.text
    assert TEST_SERVICE_KEY not in response.text


def test_auth_failure_path_logs_no_secret_and_no_phi(authed_client, caplog):
    presented = "SECRET-PRESENTED-CANARY-0123456789"
    with caplog.at_level(logging.DEBUG):
        authed_client.get(CATALOG, headers={SERVICE_KEY_HEADER: presented})
    logged = caplog.text
    assert "service_auth_rejected" in logged
    assert presented not in logged
    assert TEST_SERVICE_KEY not in logged
    assert presented[:8] not in logged
    assert TEST_SERVICE_KEY[:8] not in logged


def test_auth_failure_before_the_body_is_processed(authed_client):
    response = authed_client.post(
        ENGINEER,
        json={
            "extraction": {
                "extracted_parameters": [
                    {"test_name": "CANARY-TEST", "value_raw": "CANARY-VALUE"}
                ]
            }
        },
    )
    assert response.status_code == 401
    assert "CANARY-VALUE" not in response.text
    assert "CANARY-TEST" not in response.text


def test_a_configured_key_wins_over_the_escape_hatch(authed_client_factory):
    client = authed_client_factory(allow_unauthenticated=True)
    assert client.get(CATALOG).status_code == 401
    assert (
        client.get(CATALOG, headers={SERVICE_KEY_HEADER: TEST_SERVICE_KEY}).status_code
        == 200
    )


def test_health_is_reachable_without_authentication(authed_client):
    response = authed_client.get(HEALTH)
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "ok"


def test_health_still_works_when_a_key_is_supplied(authed_client):
    response = authed_client.get(HEALTH, headers={SERVICE_KEY_HEADER: TEST_SERVICE_KEY})
    assert response.status_code == 200


def test_health_discloses_no_credential_and_no_auth_state(authed_client):
    raw = authed_client.get(HEALTH).text
    assert TEST_SERVICE_KEY not in raw
    lowered = raw.lower()
    for forbidden in (
        "ai_service_api_key",
        "service_key",
        "x-service-key",
        "allow_unauthenticated",
        "gemini_api_key",
        "aiza",
    ):
        assert forbidden not in lowered, f"{forbidden} disclosed by /health"

    data = authed_client.get(HEALTH).json()["data"]
    assert set(data) == {
        "status",
        "service",
        "module",
        "environment",
        "model",
        "model_configured",
        "prompt_version",
        "limits",
    }
    assert isinstance(data["model_configured"], bool)


def test_the_root_index_is_not_a_phi_endpoint_and_stays_open(authed_client):
    assert authed_client.get("/").status_code == 200


def _import_app(**env_overrides) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    for name in ("AI_SERVICE_API_KEY", "ALLOW_UNAUTHENTICATED", "GEMINI_API_KEY"):
        env.pop(name, None)
    for name, value in env_overrides.items():
        if value is None:
            env.pop(name, None)
        else:
            env[name] = value
    env["ENVIRONMENT"] = "test"
    return subprocess.run(
        [sys.executable, "-c", "import app.main; print('STARTED-OK')"],
        cwd=str(SERVICE_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )


@pytest.fixture(scope="module")
def _no_dotenv():
    dotenv = SERVICE_ROOT / ".env"
    backup = SERVICE_ROOT / ".env.pytest-auth-backup"
    moved = False
    if dotenv.exists():
        dotenv.replace(backup)
        moved = True
    try:
        yield
    finally:
        if moved:
            backup.replace(dotenv)


def test_startup_is_refused_when_the_key_is_unconfigured(_no_dotenv):
    result = _import_app()
    assert result.returncode != 0, result.stdout
    assert "STARTED-OK" not in result.stdout
    combined = result.stdout + result.stderr
    assert "REFUSING TO START" in combined
    assert "AI_SERVICE_API_KEY" in combined
    assert "ALLOW_UNAUTHENTICATED" in combined


def test_startup_is_refused_when_the_key_is_blank(_no_dotenv):
    for blank in ("", "   "):
        result = _import_app(AI_SERVICE_API_KEY=blank)
        assert result.returncode != 0, f"blank key {blank!r} was accepted"
        assert "REFUSING TO START" in result.stdout + result.stderr


def test_startup_is_refused_for_a_too_short_key(_no_dotenv):
    result = _import_app(AI_SERVICE_API_KEY="short")
    assert result.returncode != 0
    assert "REFUSING TO START" in result.stdout + result.stderr


def test_startup_succeeds_with_a_configured_key(_no_dotenv):
    result = _import_app(AI_SERVICE_API_KEY=TEST_SERVICE_KEY)
    assert result.returncode == 0, result.stderr
    assert "STARTED-OK" in result.stdout
    assert TEST_SERVICE_KEY not in result.stdout + result.stderr
    assert "SECURITY WARNING" not in result.stdout + result.stderr


def test_the_escape_hatch_starts_the_service_and_warns_loudly(_no_dotenv):
    result = _import_app(ALLOW_UNAUTHENTICATED="true")
    assert result.returncode == 0, result.stderr
    assert "STARTED-OK" in result.stdout
    combined = result.stdout + result.stderr
    assert "SECURITY WARNING" in combined
    assert "ALLOW_UNAUTHENTICATED=true" in combined
    assert "UNAUTHENTICATED requests" in combined


def test_the_escape_hatch_must_be_set_deliberately(_no_dotenv):
    for value in ("false", "0", "no", "maybe"):
        result = _import_app(ALLOW_UNAUTHENTICATED=value)
        assert result.returncode != 0, f"ALLOW_UNAUTHENTICATED={value} opened it"


@pytest.mark.parametrize("blank", ["", "   "])
def test_a_blank_escape_hatch_refuses_with_the_clear_message(_no_dotenv, blank):
    result = _import_app(ALLOW_UNAUTHENTICATED=blank)
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "REFUSING TO START" in combined
    assert "bool_parsing" not in combined


def test_a_blank_escape_hatch_parses_as_false():
    from app.config import Settings

    assert Settings(_env_file=None, allow_unauthenticated="").allow_unauthenticated is False
    assert (
        Settings(_env_file=None, allow_unauthenticated="   ").allow_unauthenticated
        is False
    )


def test_the_escape_hatch_actually_serves_unauthenticated_requests(client):
    from app.config import get_settings

    assert client.get(CATALOG).status_code == 200
    assert client.get(HEALTH).status_code == 200
    del get_settings


def _walk_api_routes(routes):
    for route in routes:
        original = getattr(route, "original_router", None)
        if original is not None:
            yield from _walk_api_routes(original.routes)
        elif getattr(route, "path", "").startswith("/api/v1"):
            yield route


def test_the_route_walker_actually_finds_routes():
    from app.main import app

    found = [r.path for r in _walk_api_routes(app.routes)]
    assert found, "route walker found no /api/v1 routes -- it has gone blind"
    for expected in (EXTRACT, "/api/v1/features/engineer"):
        assert expected in found, f"{expected} missing from {found}"


def test_every_phi_route_declares_the_auth_dependency():
    from app.main import app

    unprotected = []
    for route in _walk_api_routes(app.routes):
        if route.path in (HEALTH, "/"):
            continue
        deps = getattr(route.dependant, "dependencies", [])
        if not any(d.call is require_service_key for d in deps):
            unprotected.append(route.path)
    assert unprotected == [], f"unprotected PHI routes: {unprotected}"


def test_cors_is_not_wide_open_by_default(settings):
    assert settings.cors_allow_origins == []
