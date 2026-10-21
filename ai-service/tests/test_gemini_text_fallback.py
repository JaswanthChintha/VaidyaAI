from __future__ import annotations

from types import SimpleNamespace

import pytest
from google.genai import errors as genai_errors

from app.config import Settings
from app.core.errors import ErrorCode, ModelError
from app.services import gemini_client
from app.services.gemini_text import GeminiTextClient


def _ok(text):
    candidate = SimpleNamespace(finish_reason=SimpleNamespace(name="STOP"), content=None)
    return SimpleNamespace(candidates=[candidate], text=text)


def _blocked():
    candidate = SimpleNamespace(finish_reason=SimpleNamespace(name="SAFETY"), content=None)
    return SimpleNamespace(candidates=[candidate], text=None)


def _server_error():
    return genai_errors.ServerError(503, {"error": {"message": "overloaded"}})


def _raise(exc):
    def call():
        raise exc

    return call


class _Models:
    def __init__(self, behaviour):
        self.behaviour = behaviour
        self.calls = []

    def generate_content(self, model, contents, config):
        self.calls.append(model)
        return self.behaviour[model]()


@pytest.fixture(autouse=True)
def _no_cooldown_leak():
    gemini_client._MODEL_COOLDOWN.clear()
    yield
    gemini_client._MODEL_COOLDOWN.clear()


def _client(behaviour):
    settings = Settings(
        _env_file=None,
        gemini_api_key="x",
        gemini_model="m-primary",
        gemini_fallback_models="m-backup",
        gemini_retry_base_delay_seconds=0,
        gemini_max_retries=2,
    )
    models = _Models(behaviour)
    return GeminiTextClient(settings, client=SimpleNamespace(models=models)), models


def test_a_server_error_on_the_primary_falls_back_to_the_backup():
    client, models = _client({"m-primary": _raise(_server_error()), "m-backup": lambda: _ok("hello")})
    assert client.generate_text("p") == "hello"
    assert models.calls[-1] == "m-backup"


def test_server_errors_everywhere_still_report_model_unavailable():
    client, models = _client({"m-primary": _raise(_server_error()), "m-backup": _raise(_server_error())})
    with pytest.raises(ModelError) as caught:
        client.generate_text("p")
    assert caught.value.code == ErrorCode.MODEL_UNAVAILABLE
    assert "m-backup" in models.calls


def test_a_safety_block_is_not_shopped_to_another_model():
    client, models = _client({"m-primary": _blocked, "m-backup": lambda: _ok("complied")})
    with pytest.raises(ModelError) as caught:
        client.generate_text("p")
    assert caught.value.code == ErrorCode.MODEL_RESPONSE_BLOCKED
    assert models.calls == ["m-primary"]


def test_a_healthy_primary_is_used_alone():
    client, models = _client({"m-primary": lambda: _ok("fine"), "m-backup": lambda: _ok("x")})
    assert client.generate_text("p") == "fine"
    assert models.calls == ["m-primary"]
