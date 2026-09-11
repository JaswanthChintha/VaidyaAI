"""GeminiClient: response parsing, error classification, retry/backoff.

Nothing here touches the network. A stub `models.generate_content` stands in
for the SDK, and `time.sleep` is patched so backoff does not slow the suite.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, List, Optional

import pytest

from app.config import Settings
from app.core.errors import (
    ServiceError,
    ErrorCode,
    ModelError,
    ModelNotConfiguredError,
    ModelRateLimitedError,
    ModelTimeoutError,
)
from app.services.gemini_client import GeminiClient


# --------------------------------------------------------------------------
# SDK stubs
# --------------------------------------------------------------------------


def make_response(
    text: Optional[str] = None,
    finish_reason: str = "STOP",
    candidates: Optional[List[Any]] = None,
    block_reason: Optional[str] = None,
) -> Any:
    """Build an object shaped like a GenerateContentResponse."""
    if candidates is None:
        part = SimpleNamespace(text=text)
        content = SimpleNamespace(parts=[part])
        candidates = [
            SimpleNamespace(
                content=content,
                finish_reason=SimpleNamespace(name=finish_reason),
            )
        ]
    return SimpleNamespace(
        text=text,
        candidates=candidates,
        prompt_feedback=SimpleNamespace(block_reason=block_reason),
    )


class StubModels:
    def __init__(self, results: List[Any]) -> None:
        self._results = results
        self.calls = 0
        self.last_kwargs: dict = {}

    def generate_content(self, **kwargs: Any) -> Any:
        self.last_kwargs = kwargs
        index = min(self.calls, len(self._results) - 1)
        self.calls += 1
        result = self._results[index]
        if isinstance(result, BaseException):
            raise result
        return result


class StubSDKClient:
    def __init__(self, results: List[Any]) -> None:
        self.models = StubModels(results)


class FakeAPIError(Exception):
    """Mimics google.genai errors that carry a `code` attribute."""

    def __init__(self, code: int) -> None:
        super().__init__(f"api error {code}")
        self.code = code


class FakeReadTimeout(Exception):
    """Matched by name, the way httpx timeouts are classified."""

    pass


FakeReadTimeout.__name__ = "ReadTimeout"


GOOD_JSON = json.dumps(
    {
        "raw_text": "HbA1c 6.8 %",
        "parameters": [
            {"test_name": "HbA1c", "value_raw": "6.8", "value_numeric": 6.8}
        ],
        "page_confidence": 0.9,
    }
)


@pytest.fixture()
def settings() -> Settings:
    return Settings(
        _env_file=None,
        gemini_api_key="test-key-not-real",
        gemini_max_retries=3,
        gemini_retry_base_delay_seconds=0.0,
    )


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: Any) -> None:
    monkeypatch.setattr("app.services.gemini_client.time.sleep", lambda _s: None)


@pytest.fixture(autouse=True)
def _clear_model_cooldown() -> Any:
    """THE COOLDOWN IS A MODULE-LEVEL GLOBAL, so it leaks between tests.

    `_mark_exhausted` records a 429 in `_MODEL_COOLDOWN` so later calls skip
    that model -- correct in production, and in a test process it means every
    429 test permanently shrinks the chain for everything that runs after it.
    Tests here passed only because of the order they happened to run in, and
    a new one asserting a call count against the FULL chain failed while
    passing in isolation.

    Cleared before and after, so this file cannot depend on its own ordering
    and cannot poison another file.
    """
    from app.services import gemini_client

    gemini_client._MODEL_COOLDOWN.clear()
    yield
    gemini_client._MODEL_COOLDOWN.clear()


def build(settings: Settings, results: List[Any]) -> tuple:
    sdk = StubSDKClient(results)
    return GeminiClient(settings, client=sdk), sdk


def call(client: GeminiClient) -> dict:
    return client.extract_page(b"\x89PNG-bytes", "image/png", "prompt")


# --------------------------------------------------------------------------
# Happy path
# --------------------------------------------------------------------------


def test_well_formed_json_is_parsed(settings):
    client, sdk = build(settings, [make_response(GOOD_JSON)])
    result = call(client)
    assert result["parameters"][0]["test_name"] == "HbA1c"
    assert sdk.models.calls == 1


def test_request_uses_json_mode_low_temperature_and_the_configured_model(settings):
    client, sdk = build(settings, [make_response(GOOD_JSON)])
    call(client)
    kwargs = sdk.models.last_kwargs
    assert kwargs["model"] == settings.gemini_model
    config = kwargs["config"]
    assert config.response_mime_type == "application/json"
    assert config.response_schema is not None
    assert config.temperature == 0.0
    assert config.system_instruction


def test_markdown_fenced_json_is_recovered(settings):
    fenced = f"```json\n{GOOD_JSON}\n```"
    client, _ = build(settings, [make_response(fenced)])
    assert call(client)["parameters"][0]["test_name"] == "HbA1c"


def test_json_with_surrounding_prose_is_recovered(settings):
    noisy = f"Here is the result:\n{GOOD_JSON}\nHope that helps."
    client, _ = build(settings, [make_response(noisy)])
    assert call(client)["parameters"][0]["test_name"] == "HbA1c"


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------


def test_missing_api_key_raises_not_configured():
    unconfigured = Settings(_env_file=None, gemini_api_key="")
    client = GeminiClient(unconfigured)  # no injected SDK client
    with pytest.raises(ModelNotConfiguredError) as exc:
        call(client)
    assert exc.value.code == ErrorCode.MODEL_NOT_CONFIGURED
    assert exc.value.status_code == 503


# --------------------------------------------------------------------------
# Malformed / unusable responses
# --------------------------------------------------------------------------


def test_malformed_json_is_retried_then_reported(settings):
    client, sdk = build(settings, [make_response("this is not json at all")])
    with pytest.raises(ModelError) as exc:
        call(client)
    assert exc.value.code == ErrorCode.MODEL_RESPONSE_MALFORMED
    assert exc.value.status_code == 502
    assert sdk.models.calls == settings.gemini_max_retries  # retried


def test_malformed_then_valid_response_succeeds(settings):
    client, sdk = build(
        settings, [make_response("garbage"), make_response(GOOD_JSON)]
    )
    assert call(client)["parameters"][0]["test_name"] == "HbA1c"
    assert sdk.models.calls == 2


def test_json_array_instead_of_object_is_rejected(settings):
    client, _ = build(settings, [make_response('[{"test_name": "x"}]')])
    with pytest.raises(ModelError) as exc:
        call(client)
    assert exc.value.code == ErrorCode.MODEL_RESPONSE_MALFORMED


def test_truncated_json_is_reported_as_malformed(settings):
    client, _ = build(settings, [make_response(GOOD_JSON[: len(GOOD_JSON) // 2])])
    with pytest.raises(ModelError) as exc:
        call(client)
    assert exc.value.code == ErrorCode.MODEL_RESPONSE_MALFORMED


def test_max_tokens_finish_reason_is_reported_as_truncated(settings):
    client, sdk = build(
        settings, [make_response(GOOD_JSON[:40], finish_reason="MAX_TOKENS")]
    )
    with pytest.raises(ModelError) as exc:
        call(client)
    assert exc.value.code == ErrorCode.MODEL_RESPONSE_TRUNCATED
    # Truncation is deterministic -- retrying the same page would just burn
    # quota, so it must NOT be retried.
    assert sdk.models.calls == 1


def test_safety_finish_reason_is_reported_as_blocked(settings):
    client, sdk = build(settings, [make_response("", finish_reason="SAFETY")])
    with pytest.raises(ModelError) as exc:
        call(client)
    assert exc.value.code == ErrorCode.MODEL_RESPONSE_BLOCKED
    assert sdk.models.calls == 1


def test_prompt_level_block_is_reported_as_blocked(settings):
    blocked = make_response(None, candidates=[], block_reason="SAFETY")
    client, _ = build(settings, [blocked])
    with pytest.raises(ModelError) as exc:
        call(client)
    assert exc.value.code == ErrorCode.MODEL_RESPONSE_BLOCKED


def test_no_candidates_is_reported_as_empty(settings):
    empty = make_response(None, candidates=[], block_reason=None)
    client, _ = build(settings, [empty])
    with pytest.raises(ModelError) as exc:
        call(client)
    assert exc.value.code == ErrorCode.MODEL_RESPONSE_EMPTY


def test_empty_text_is_reported_as_empty(settings):
    client, _ = build(settings, [make_response("   ")])
    with pytest.raises(ModelError) as exc:
        call(client)
    assert exc.value.code == ErrorCode.MODEL_RESPONSE_EMPTY


def test_text_is_recovered_from_parts_when_the_shortcut_is_absent(settings):
    """Some SDK responses expose text only via candidate parts."""
    response = make_response(GOOD_JSON)
    response.text = None  # force the parts fallback
    client, _ = build(settings, [response])
    assert call(client)["parameters"][0]["test_name"] == "HbA1c"


# --------------------------------------------------------------------------
# Transport / API errors
# --------------------------------------------------------------------------


def test_timeout_is_classified_and_retried(settings):
    client, sdk = build(settings, [FakeReadTimeout("timed out")])
    with pytest.raises(ModelTimeoutError) as exc:
        call(client)
    assert exc.value.code == ErrorCode.MODEL_TIMEOUT
    assert exc.value.status_code == 504
    assert sdk.models.calls == settings.gemini_max_retries


def test_builtin_timeout_error_is_classified(settings):
    client, _ = build(settings, [TimeoutError("slow")])
    with pytest.raises(ModelTimeoutError):
        call(client)


def test_rate_limit_walks_the_model_chain_then_reports(settings):
    """A 429 everywhere still raises 429 -- after trying every model once.

    REPLACES an older assertion that a 429 cost exactly `gemini_max_retries`
    requests against the ONE configured model. That is no longer the policy:
    Google meters the free tier per model per day, so a sibling model is the
    only thing that can actually clear a 429, and retrying the exhausted one
    just spends another of the twenty requests the key gets. So each model in
    the chain is tried ONCE and abandoned, and only the LAST one -- where a
    short per-minute limit is the only remaining hope -- gets the retries.
    """
    client, sdk = build(settings, [FakeAPIError(429)])
    with pytest.raises(ModelRateLimitedError) as exc:
        call(client)
    assert exc.value.code == ErrorCode.MODEL_RATE_LIMITED
    assert exc.value.status_code == 429

    fallbacks = len(settings.fallback_model_list)
    # One doomed request per fallback, plus the full retry budget on the last.
    assert sdk.models.calls == fallbacks + settings.gemini_max_retries


def test_rate_limited_primary_falls_back_to_a_working_model(settings):
    """The point of the chain: an exhausted primary must not fail the request."""
    client, sdk = build(settings, [FakeAPIError(429), make_response(GOOD_JSON)])
    assert call(client)["parameters"][0]["test_name"] == "HbA1c"
    # Exactly two: the primary's single 429, then the fallback's success.
    assert sdk.models.calls == 2


def test_a_deterministic_4xx_does_not_shop_around_the_chain(settings):
    """Only quota exhaustion may cross models.

    A 400 fails identically on every model, so walking the chain would spend
    a request per model to reach the same answer.
    """
    client, sdk = build(settings, [FakeAPIError(400)])
    with pytest.raises(ServiceError):
        call(client)
    assert sdk.models.calls == 1


def test_transient_error_then_success(settings):
    client, sdk = build(settings, [FakeAPIError(503), make_response(GOOD_JSON)])
    assert call(client)["parameters"][0]["test_name"] == "HbA1c"
    assert sdk.models.calls == 2


@pytest.mark.parametrize("status", [500, 502, 503, 504])
def test_server_errors_are_reported_as_unavailable(settings, status):
    client, _ = build(settings, [FakeAPIError(status)])
    with pytest.raises(ModelError) as exc:
        call(client)
    assert exc.value.code == ErrorCode.MODEL_UNAVAILABLE
    assert exc.value.status_code == 503


@pytest.mark.parametrize("status", [401, 403])
def test_auth_errors_are_reported_as_not_configured(settings, status):
    client, sdk = build(settings, [FakeAPIError(status)])
    with pytest.raises(ModelNotConfiguredError):
        call(client)
    assert sdk.models.calls == 1  # never retried: a bad key stays bad


def test_bad_request_is_not_retried(settings):
    client, sdk = build(settings, [FakeAPIError(400)])
    with pytest.raises(ModelError) as exc:
        call(client)
    assert exc.value.code == ErrorCode.MODEL_REQUEST_FAILED
    assert sdk.models.calls == 1


def test_unknown_exception_is_wrapped_not_leaked(settings):
    client, _ = build(settings, [RuntimeError("something odd")])
    with pytest.raises(ModelError) as exc:
        call(client)
    assert exc.value.status_code == 502


# --------------------------------------------------------------------------
# Never leak internals to the caller
# --------------------------------------------------------------------------


def test_upstream_error_text_is_not_echoed_to_the_caller(settings):
    """Upstream messages can embed request fragments -- keep them internal."""
    secret = "PATIENT-JORDAN-SAMPLE-HBA1C-6.8"
    client, _ = build(settings, [FakeAPIError(500)])
    try:
        call(client)
    except ModelError as exc:
        assert secret not in exc.message
        assert "api error" not in exc.message.lower()


def test_error_messages_never_contain_the_api_key(settings):
    client, _ = build(settings, [FakeAPIError(403)])
    with pytest.raises(ModelNotConfiguredError) as exc:
        call(client)
    assert settings.gemini_api_key.get_secret_value() not in exc.value.message


def test_api_key_is_redacted_in_settings_repr(settings):
    assert "test-key-not-real" not in repr(settings)
    assert "test-key-not-real" not in str(settings)


# --------------------------------------------------------------------------
# A 5xx crosses the model chain; a safety block still does not
# --------------------------------------------------------------------------
#
# THE CHAIN ORIGINALLY ADVANCED ONLY ON 429, and a server error aborted it
# outright -- so a flaky primary failed the whole request while three healthy
# siblings sat unused. It showed up the first time the provider had a bad
# afternoon: two extractions of the same one-page document failed ninety
# seconds apart, with a third succeeding between them, on the same model.
#
# A 503 from one endpoint says nothing about whether another is healthy. That
# is what separates it from a deterministic 4xx, which fails identically
# everywhere and must NOT be shopped around.


def test_an_unavailable_primary_falls_back_to_a_working_model(settings):
    # The primary must exhaust its OWN retry budget first -- a single 503
    # followed by success is handled on the same model, which is what
    # `test_transient_error_then_success` already covers. The fallback is for
    # an endpoint that is down rather than momentarily hiccuping.
    responses = [FakeAPIError(503)] * settings.gemini_max_retries
    responses.append(make_response(GOOD_JSON))
    client, sdk = build(settings, responses)
    assert call(client)["parameters"][0]["test_name"] == "HbA1c"
    # The primary's full budget, then the fallback answers first time.
    assert sdk.models.calls == settings.gemini_max_retries + 1


def test_unavailable_everywhere_still_reports_unavailable(settings):
    client, _ = build(settings, [FakeAPIError(503)])
    with pytest.raises(ModelError) as exc:
        call(client)
    assert exc.value.code == ErrorCode.MODEL_UNAVAILABLE
    assert exc.value.status_code == 503


def test_a_rate_limit_is_reported_ahead_of_an_unavailability(settings):
    """Which reason surfaces when the chain fails for two different reasons.

    "Out of quota" is actionable by waiting; "temporarily unavailable" only by
    retrying, and a caller told the weaker of the two retries into a wall.
    """
    # The primary is out of quota and hands straight on; every remaining
    # model is unavailable and burns its budget.
    budget = (len(settings.fallback_model_list) + 1) * settings.gemini_max_retries
    responses = [FakeAPIError(429)] + [FakeAPIError(503)] * (budget + 4)
    client, _ = build(settings, responses)
    with pytest.raises(ModelRateLimitedError):
        call(client)


def test_a_deterministic_4xx_still_does_not_shop_around(settings):
    """Unchanged by the 5xx fallback, and the reason they differ."""
    client, sdk = build(settings, [FakeAPIError(400)])
    with pytest.raises(ServiceError):
        call(client)
    assert sdk.models.calls == 1
