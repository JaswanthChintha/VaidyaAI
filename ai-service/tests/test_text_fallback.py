"""The crossing policy, and the OpenRouter transport under it.

NOTHING HERE TOUCHES THE NETWORK. The primary is a stub that raises or
returns; the secondary is a stub HTTP client returning canned responses.

WHAT THESE TESTS ARE FOR. One rule carries the safety weight of this whole
feature -- EXHAUSTION CROSSES, A REFUSAL NEVER DOES -- because a second
provider is a second set of safety behaviours, and "ask someone else" is
exactly the move that would let a refused generation through. Most of this
file is that one rule, attacked from both sides.
"""

from __future__ import annotations

import json
from typing import Any, Optional

import pytest

from app.config import Settings
from app.core.errors import (
    ErrorCode,
    ModelError,
    ModelNotConfiguredError,
    ModelRateLimitedError,
    ModelTimeoutError,
)
from app.services import openrouter_text
from app.services.openrouter_text import OpenRouterTextClient
from app.services.text_fallback import FallbackTextClient

PRIMARY_PROSE = "Prose from the primary provider."
SECONDARY_PROSE = "Prose from the secondary provider."


@pytest.fixture(autouse=True)
def _clear_cooldowns():
    """Process-wide cooldown state must not leak between tests.

    Without this one test's 429 changes another test's verdict depending on
    the order they run in, which is how a suite starts lying.
    """
    openrouter_text.reset_cooldowns()
    yield
    openrouter_text.reset_cooldowns()


@pytest.fixture()
def settings() -> Settings:
    return Settings(
        _env_file=None,
        gemini_api_key="test-key-not-real",
        openrouter_api_key="test-openrouter-key-not-real",
        openrouter_models="model-a:free,model-b:free",
        openrouter_model_cooldown_seconds=300.0,
    )


class StubPrimary:
    """Stands in for `GeminiTextClient`. Returns prose, or raises."""

    def __init__(self, outcome: Any) -> None:
        self.outcome = outcome
        self.calls = 0

    def generate_text(self, prompt: str, **kwargs: Any) -> str:
        self.calls += 1
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


class StubSecondary:
    """Stands in for `OpenRouterTextClient`. Records that it was asked."""

    def __init__(self, outcome: Any = SECONDARY_PROSE) -> None:
        self.outcome = outcome
        self.calls = 0
        self.kwargs: Optional[dict] = None

    def generate_text(self, prompt: str, **kwargs: Any) -> str:
        self.calls += 1
        self.kwargs = kwargs
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


class StubResponse:
    def __init__(self, status_code: int, body: Any) -> None:
        self.status_code = status_code
        self.text = body if isinstance(body, str) else json.dumps(body)


class StubHTTP:
    """A stub `httpx.Client`. Returns queued responses, or raises them."""

    def __init__(self, *responses: Any) -> None:
        self.queue = list(responses)
        self.posts: list = []

    def post(self, url: str, json: Any = None, headers: Any = None):  # noqa: A002
        self.posts.append({"url": url, "json": json, "headers": headers})
        item = self.queue.pop(0) if self.queue else StubResponse(200, _ok(""))
        if isinstance(item, BaseException):
            raise item
        return item


def _ok(text: str) -> dict:
    return {"choices": [{"message": {"content": text}}]}


# ==========================================================================
# THE CROSSING RULE -- exhaustion crosses
# ==========================================================================


def test_a_spent_primary_reaches_the_secondary(settings):
    primary = StubPrimary(ModelRateLimitedError("spent"))
    secondary = StubSecondary()
    client = FallbackTextClient(settings, primary, secondary)

    assert client.generate_text("prompt") == SECONDARY_PROSE
    assert primary.calls == 1
    assert secondary.calls == 1


def test_a_working_primary_never_reaches_the_secondary(settings):
    primary = StubPrimary(PRIMARY_PROSE)
    secondary = StubSecondary()
    client = FallbackTextClient(settings, primary, secondary)

    assert client.generate_text("prompt") == PRIMARY_PROSE
    assert secondary.calls == 0


# ==========================================================================
# THE CROSSING RULE -- A REFUSAL NEVER CROSSES. This is the safety-critical half.
# ==========================================================================


@pytest.mark.parametrize(
    "failure",
    [
        # A SAFETY BLOCK IS AN ANSWER. Re-asking a different provider is
        # shopping for a more compliant one, which is the single worst thing
        # this feature could be built to do.
        ModelError(
            "blocked by the provider's safety filter",
            code=ErrorCode.MODEL_RESPONSE_BLOCKED,
            status_code=502,
        ),
        # Deterministic: a second provider would truncate too, or not, for
        # reasons unrelated to the first's budget.
        ModelError(
            "truncated",
            code=ErrorCode.MODEL_RESPONSE_TRUNCATED,
            status_code=502,
        ),
        ModelError("empty", code=ErrorCode.MODEL_RESPONSE_EMPTY, status_code=502),
        ModelError("rejected", code=ErrorCode.MODEL_REQUEST_FAILED, status_code=502),
        ModelTimeoutError("too slow"),
        ModelNotConfiguredError("no key"),
    ],
)
def test_no_failure_but_exhaustion_crosses(settings, failure):
    primary = StubPrimary(failure)
    secondary = StubSecondary()
    client = FallbackTextClient(settings, primary, secondary)

    with pytest.raises(type(failure)):
        client.generate_text("prompt")
    assert secondary.calls == 0, "a non-quota failure must never be re-asked"


def test_the_primarys_own_error_survives_the_crossing_attempt(settings):
    """When the secondary also fails, the caller hears about the exhaustion.

    The caller asked this service for prose and is rate limited; a message
    about a provider it never chose would send someone debugging the wrong
    thing. The secondary's failure is logged, not raised.
    """
    exhausted = ModelRateLimitedError("every model is spent")
    primary = StubPrimary(exhausted)
    secondary = StubSecondary(ModelError("secondary is down too"))
    client = FallbackTextClient(settings, primary, secondary)

    with pytest.raises(ModelRateLimitedError) as caught:
        client.generate_text("prompt")
    assert caught.value is exhausted


def test_with_no_secondary_the_exhaustion_propagates_unchanged(settings):
    """NO KEY MEANS NOTHING CHANGES -- the state every older test runs in."""
    exhausted = ModelRateLimitedError("spent")
    client = FallbackTextClient(settings, StubPrimary(exhausted), None)

    with pytest.raises(ModelRateLimitedError) as caught:
        client.generate_text("prompt")
    assert caught.value is exhausted


def test_the_primarys_defaults_are_passed_through_not_restated(settings):
    """The wrapper must not invent its own temperature or output budget.

    `EXPLANATION_MAX_OUTPUT_TOKENS` records a live truncation outage; a second
    copy of that number here would drift from the reasoning that produced it.
    """
    from app.services.gemini_text import (
        EXPLANATION_MAX_OUTPUT_TOKENS,
        EXPLANATION_TEMPERATURE,
    )

    secondary = StubSecondary()
    client = FallbackTextClient(
        settings, StubPrimary(ModelRateLimitedError("spent")), secondary
    )
    client.generate_text("prompt")

    assert secondary.kwargs["temperature"] == EXPLANATION_TEMPERATURE
    assert secondary.kwargs["max_output_tokens"] == EXPLANATION_MAX_OUTPUT_TOKENS


# ==========================================================================
# THE SECONDARY IS STILL BELOW MODULE 24
# ==========================================================================


#: Refused by `validate_text` under the very context Module 35 and the
#: glossary pass -- MEDICATION_REFERENCE, UNPERMITTED_DIRECTIVE and
#: UNSAFE_TREATMENT_INSTRUCTION. CHOSEN BY RUNNING THE VALIDATOR over
#: candidates rather than by assuming which rules fire; the first string tried
#: here was a flat diagnosis, and that is APPROVED today (see the note in the
#: symmetry test below).
UNSAFE_PROSE = "You should stop taking your metformin immediately."


def test_fallback_prose_is_still_refused_when_it_violates_policy(settings):
    """A DIFFERENT PROVIDER DOES NOT GET A DIFFERENT SAFETY PIPELINE.

    The whole design rests on the fallback sitting BELOW `guarded_generation`,
    so this drives the real thing: unsafe prose from the SECONDARY provider is
    refused exactly as the primary's would be.
    """
    from app.safety.fallback import guarded_generation
    from app.safety.validator import SafetyContext

    client = FallbackTextClient(
        settings,
        StubPrimary(ModelRateLimitedError("spent")),
        StubSecondary(UNSAFE_PROSE),
    )

    result = guarded_generation(
        lambda feedback=None: client.generate_text("prompt"),
        context=SafetyContext(),
        attempts=1,
    )
    assert result.approved_text is None
    assert result.fallback is not None


def test_the_verdict_does_not_depend_on_WHICH_provider_wrote_the_text(settings):
    """THE PROPERTY THIS FEATURE MUST GUARANTEE, stated directly.

    Not "the secondary is safe" -- this module cannot make a model safe. What
    it must guarantee is that introducing a second provider changes NOTHING
    about how the text is judged: identical prose gets an identical verdict
    whether Gemini or OpenRouter produced it.

    > A FLAT DIAGNOSIS IS APPROVED BY `validate_text` TODAY, under every
    > context tried including the one Module 35 and the glossary pass -- zero
    > violation codes. That is 6r's D1 and it is NOT introduced here and NOT
    > fixed here; this test deliberately does not pin it, because pinning
    > someone else's open defect as expected behaviour is how it becomes
    > permanent. It is recorded in MEMORY.md instead.
    """
    from app.safety.validator import SafetyContext, validate_text

    ctx = SafetyContext()
    for text in (UNSAFE_PROSE, "This test measures a protein that stores iron."):
        from_primary = FallbackTextClient(settings, StubPrimary(text), None)
        from_secondary = FallbackTextClient(
            settings,
            StubPrimary(ModelRateLimitedError("spent")),
            StubSecondary(text),
        )
        a = validate_text(from_primary.generate_text("p"), ctx)
        b = validate_text(from_secondary.generate_text("p"), ctx)
        assert a.approved == b.approved, text
        assert sorted(set(a.codes)) == sorted(set(b.codes)), text


def test_fallback_prose_that_is_safe_is_approved(settings):
    """The ANSWERING branch, not only the refusing one.

    This repository's own audit lesson: "the branch that refuses is tested,
    the branch that answers on thin evidence is not."
    """
    from app.safety.fallback import guarded_generation
    from app.safety.validator import SafetyContext

    safe = (
        "This test measures a protein that stores iron in the body. "
        "Please discuss your results with a qualified healthcare professional."
    )
    client = FallbackTextClient(
        settings,
        StubPrimary(ModelRateLimitedError("spent")),
        StubSecondary(safe),
    )

    result = guarded_generation(
        lambda feedback=None: client.generate_text("prompt"),
        context=SafetyContext(),
        attempts=1,
    )
    assert result.approved_text is not None


# ==========================================================================
# THE OPENROUTER TRANSPORT
# ==========================================================================


def _or_client(settings: Settings, *responses: Any) -> OpenRouterTextClient:
    return OpenRouterTextClient(settings, StubHTTP(*responses))


def _gen(client: OpenRouterTextClient) -> str:
    return client.generate_text(
        "prompt",
        system_instruction="system",
        temperature=0.2,
        max_output_tokens=512,
    )


def test_it_returns_the_assistant_message(settings):
    client = _or_client(settings, StubResponse(200, _ok(SECONDARY_PROSE)))
    assert _gen(client) == SECONDARY_PROSE


def test_an_unconfigured_secondary_raises_rather_than_returning_anything(settings):
    from pydantic import SecretStr

    bare = settings.model_copy(update={"openrouter_api_key": SecretStr("")})
    client = OpenRouterTextClient(bare, StubHTTP())
    with pytest.raises(ModelNotConfiguredError):
        _gen(client)


@pytest.mark.parametrize(
    "status,expected",
    [
        (401, ModelNotConfiguredError),
        (403, ModelNotConfiguredError),
        (500, ModelError),
        (503, ModelError),
        (400, ModelError),
    ],
)
def test_transport_statuses_map_onto_this_services_taxonomy(settings, status, expected):
    client = _or_client(settings, StubResponse(status, {"error": "x"}))
    with pytest.raises(expected):
        _gen(client)


def test_a_timeout_is_a_timeout(settings):
    class FakeReadTimeout(Exception):
        pass

    FakeReadTimeout.__name__ = "ReadTimeout"
    client = _or_client(settings, FakeReadTimeout("slow"))
    with pytest.raises(ModelTimeoutError):
        _gen(client)


@pytest.mark.parametrize(
    "body",
    [
        "not json at all",
        {"choices": []},
        {"choices": [{"message": {"content": ""}}]},
        {"choices": [{"message": {"content": "   "}}]},
        {"nothing": "useful"},
    ],
)
def test_it_never_returns_a_placeholder_for_an_unusable_body(settings, body):
    """A caller must not be able to mistake a failure for an answer.

    `guarded_generation` treats a raise as a failed attempt; a returned
    placeholder would be VALIDATED AND POSSIBLY APPROVED as though a model had
    written it.
    """
    client = _or_client(settings, StubResponse(200, body))
    with pytest.raises(ModelError):
        _gen(client)


def test_the_key_is_sent_as_a_bearer_token_and_never_logged(settings, caplog):
    http = StubHTTP(StubResponse(200, _ok(SECONDARY_PROSE)))
    client = OpenRouterTextClient(settings, http)
    with caplog.at_level("DEBUG"):
        _gen(client)

    secret = settings.openrouter_api_key.get_secret_value()
    assert http.posts[0]["headers"]["Authorization"] == "Bearer " + secret
    assert secret not in caplog.text


def test_the_prompt_is_never_logged(settings, caplog):
    client = _or_client(settings, StubResponse(200, _ok(SECONDARY_PROSE)))
    with caplog.at_level("DEBUG"):
        client.generate_text(
            "a very distinctive prompt string",
            system_instruction="system",
            temperature=0.2,
            max_output_tokens=512,
        )
    assert "a very distinctive prompt string" not in caplog.text
    assert SECONDARY_PROSE not in caplog.text


# ==========================================================================
# THE TWO KINDS OF 429, WHICH MEAN DIFFERENT THINGS
# ==========================================================================


UPSTREAM_429 = {
    "error": {
        "message": "Provider returned error",
        "code": 429,
        "metadata": {
            "raw": "model-a:free is temporarily rate-limited upstream.",
            "provider_name": "Google AI Studio",
        },
    }
}
ACCOUNT_429 = {
    "error": {
        "message": "Rate limit exceeded: free-model-per-day",
        "code": 429,
    }
}


def test_an_upstream_429_cools_down_only_that_model_and_tries_the_next(settings):
    """Observed live: a `:free` model 429s from its upstream provider while
    the account's own allowance is untouched. The rest of the chain is fine.
    """
    client = _or_client(
        settings,
        StubResponse(429, UPSTREAM_429),
        StubResponse(200, _ok(SECONDARY_PROSE)),
    )
    assert _gen(client) == SECONDARY_PROSE


def test_an_account_429_stops_the_whole_chain(settings):
    """The free allowance is metered PER ACCOUNT, not per model.

    Trying model-b after model-a reported the account is spent would burn a
    request proving what the first already proved.
    """
    http = StubHTTP(StubResponse(429, ACCOUNT_429), StubResponse(200, _ok("unreached")))
    client = OpenRouterTextClient(settings, http)

    with pytest.raises(ModelRateLimitedError):
        _gen(client)
    assert len(http.posts) == 1, "the second model must not be tried"


def test_an_account_429_is_remembered_across_clients(settings):
    """The cooldown is process-wide because a client is built per request.

    Per-instance state would forget the exhaustion between calls and spend one
    doomed request per call rediscovering it.
    """
    first = OpenRouterTextClient(settings, StubHTTP(StubResponse(429, ACCOUNT_429)))
    with pytest.raises(ModelRateLimitedError):
        _gen(first)

    second_http = StubHTTP(StubResponse(200, _ok("unreached")))
    with pytest.raises(ModelRateLimitedError):
        _gen(OpenRouterTextClient(settings, second_http))
    assert second_http.posts == [], "a spent account must make no request at all"


def test_an_ambiguous_429_is_treated_as_the_narrower_claim(settings):
    """When it cannot be told, it is the MODEL that is limited, not the account.

    Treating a transient blip as an account-wide outage would disable a working
    chain for the whole cooldown. The narrower claim is the safer error.
    """
    http = StubHTTP(
        StubResponse(429, {"error": {"message": "slow down"}}),
        StubResponse(200, _ok(SECONDARY_PROSE)),
    )
    assert _gen(OpenRouterTextClient(settings, http)) == SECONDARY_PROSE
    assert len(http.posts) == 2, "the next model must still be tried"


def test_every_model_rate_limited_raises_rate_limited(settings):
    client = _or_client(
        settings,
        StubResponse(429, UPSTREAM_429),
        StubResponse(429, UPSTREAM_429),
    )
    with pytest.raises(ModelRateLimitedError):
        _gen(client)


def test_it_does_not_retry_one_model(settings):
    """NO RETRY LOOP, deliberately: this client is already the fallback.

    The primary has spent its own retries and its whole chain before control
    arrives here, and `analyze` is still synchronous -- a reader is waiting.
    """
    http = StubHTTP(StubResponse(500, {"error": "x"}), StubResponse(200, _ok("nope")))
    client = OpenRouterTextClient(settings, http)
    with pytest.raises(ModelError):
        _gen(client)
    assert len(http.posts) == 1
