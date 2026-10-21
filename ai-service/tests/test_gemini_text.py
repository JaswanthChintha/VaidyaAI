from __future__ import annotations

from typing import Any

import pytest

from app.config import Settings
from app.core.errors import (
    ErrorCode,
    ModelError,
    ModelNotConfiguredError,
    ModelRateLimitedError,
    ModelTimeoutError,
)
from app.services.gemini_text import (
    EXPLANATION_MAX_OUTPUT_TOKENS,
    EXPLANATION_TEMPERATURE,
    GeminiTextClient,
    build_text_client,
)
from tests.test_gemini_client import (
    FakeAPIError,
    FakeReadTimeout,
    StubSDKClient,
    make_response,
)

PROSE = "Your result may be worth discussing with a qualified healthcare professional."


@pytest.fixture()
def settings() -> Settings:
    return Settings(
        _env_file=None,
        gemini_api_key="test-key-not-real",
        gemini_max_retries=3,
        gemini_retry_base_delay_seconds=0.0,
    )


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr("app.services.gemini_text.time.sleep", lambda _s: None)


def _client(settings: Settings, *results: Any) -> GeminiTextClient:
    return GeminiTextClient(settings, StubSDKClient(list(results)))


def test_it_is_the_existing_client_with_one_extra_method():
    from app.services.gemini_client import GeminiClient

    assert issubclass(GeminiTextClient, GeminiClient)
    for name in ("_to_service_error", "_is_retryable", "_extract_text", "_ensure_client"):
        inherited = getattr(GeminiTextClient, name)
        original = getattr(GeminiClient, name)
        assert getattr(inherited, "__func__", inherited) is getattr(
            original, "__func__", original
        ), name
    assert "generate_text" in GeminiTextClient.__dict__
    added = {
        name
        for name in GeminiTextClient.__dict__
        if not name.startswith("_")
    }
    assert added == {"generate_text"}, added


def test_build_text_client_returns_the_fallback_wrapper_around_this_client(settings):
    from app.services.text_fallback import FallbackTextClient

    client = build_text_client(settings, StubSDKClient([]))
    assert isinstance(client, FallbackTextClient)
    assert isinstance(client.primary, GeminiTextClient)


def test_the_wrapper_is_built_even_with_no_secondary_configured(settings):
    from app.services.text_fallback import FallbackTextClient

    client = build_text_client(settings, StubSDKClient([]))
    assert isinstance(client, FallbackTextClient)
    assert settings.has_openrouter_key is False
    assert client.secondary is None


def test_prose_comes_back_unchanged(settings):
    client = _client(settings, make_response(PROSE))
    assert client.generate_text("prompt") == PROSE


def test_the_temperature_is_low_and_the_output_is_bounded(settings):
    stub = StubSDKClient([make_response(PROSE)])
    GeminiTextClient(settings, stub).generate_text("prompt")

    config = stub.models.last_kwargs["config"]
    assert config.temperature == EXPLANATION_TEMPERATURE
    assert config.temperature <= 0.3
    assert config.max_output_tokens == EXPLANATION_MAX_OUTPUT_TOKENS


def test_the_system_instruction_comes_from_the_prompt_module(settings):
    from app.prompts.explanation_prompt import SYSTEM_INSTRUCTION

    stub = StubSDKClient([make_response(PROSE)])
    GeminiTextClient(settings, stub).generate_text("prompt")
    assert stub.models.last_kwargs["config"].system_instruction == SYSTEM_INSTRUCTION


def test_no_json_schema_is_requested_for_prose(settings):
    stub = StubSDKClient([make_response(PROSE)])
    GeminiTextClient(settings, stub).generate_text("prompt")
    config = stub.models.last_kwargs["config"]
    assert getattr(config, "response_schema", None) is None


def test_it_refuses_to_run_without_a_key():
    settings = Settings(_env_file=None)
    with pytest.raises(ModelNotConfiguredError):
        GeminiTextClient(settings).generate_text("prompt")


def test_a_timeout_is_classified(settings):
    client = _client(settings, FakeReadTimeout(), FakeReadTimeout(), FakeReadTimeout())
    with pytest.raises(ModelTimeoutError):
        client.generate_text("prompt")


def test_rate_limiting_is_classified(settings):
    client = _client(settings, *[FakeAPIError(429)] * 3)
    with pytest.raises(ModelRateLimitedError):
        client.generate_text("prompt")


def test_a_truncated_response_is_not_returned_as_an_answer(settings):
    client = _client(settings, make_response("half a sen", finish_reason="MAX_TOKENS"))
    with pytest.raises(ModelError) as excinfo:
        client.generate_text("prompt")
    assert excinfo.value.code == ErrorCode.MODEL_RESPONSE_TRUNCATED


def test_a_blocked_response_is_not_returned_as_an_answer(settings):
    client = _client(settings, make_response("", finish_reason="SAFETY"))
    with pytest.raises(ModelError) as excinfo:
        client.generate_text("prompt")
    assert excinfo.value.code == ErrorCode.MODEL_RESPONSE_BLOCKED


def test_an_empty_response_raises_after_resampling(settings):
    client = _client(settings, make_response(""), make_response(""), make_response(""))
    with pytest.raises(ModelError) as excinfo:
        client.generate_text("prompt")
    assert excinfo.value.code == ErrorCode.MODEL_RESPONSE_EMPTY


def test_an_empty_response_is_resampled_once_and_then_succeeds(settings):
    stub = StubSDKClient([make_response(""), make_response(PROSE)])
    assert GeminiTextClient(settings, stub).generate_text("prompt") == PROSE
    assert stub.models.calls == 2


def test_a_truncation_is_never_resampled(settings):
    stub = StubSDKClient([make_response("x", finish_reason="MAX_TOKENS")])
    with pytest.raises(ModelError):
        GeminiTextClient(settings, stub).generate_text("prompt")
    assert stub.models.calls == 1


def test_a_provider_block_is_never_resampled(settings):
    stub = StubSDKClient([make_response("", finish_reason="SAFETY")])
    with pytest.raises(ModelError):
        GeminiTextClient(settings, stub).generate_text("prompt")
    assert stub.models.calls == 1


def test_transient_server_errors_are_retried(settings):
    stub = StubSDKClient([FakeAPIError(503), make_response(PROSE)])
    assert GeminiTextClient(settings, stub).generate_text("prompt") == PROSE
    assert stub.models.calls == 2


def test_neither_the_prompt_nor_the_response_is_logged(caplog, settings):
    import logging

    caplog.set_level(logging.DEBUG)
    stub = StubSDKClient([FakeAPIError(503), make_response(PROSE)])
    GeminiTextClient(settings, stub).generate_text("CANARY-PROMPT-TEXT")

    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert "CANARY-PROMPT-TEXT" not in logged
    assert PROSE not in logged
    assert "test-key-not-real" not in logged
