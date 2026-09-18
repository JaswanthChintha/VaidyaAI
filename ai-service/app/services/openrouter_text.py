"""The SECONDARY provider for prose: OpenRouter, reached only on exhaustion.

WHY THIS IS A SIBLING OF `GeminiTextClient` AND NOT A SUBCLASS
-------------------------------------------------------------
`GeminiTextClient` subclasses `GeminiClient` because it shares that class's
transport: the SDK client, the timeout, the retry policy, the exception
taxonomy. OpenRouter shares none of it -- it is an OpenAI-shaped HTTP API, not
the google-genai SDK -- so subclassing would inherit machinery that does not
apply and would have to be overridden away.

WHAT IS SHARED IS THE CONTRACT, which is the part that matters:

  * `generate_text(prompt, system_instruction=..., ...) -> str`
  * every failure raises a `ServiceError` subclass from `app.core.errors`
  * IT NEVER RETURNS A PLACEHOLDER. A caller must not be able to mistake a
    failure for an answer, and `guarded_generation` treats a raise as a failed
    attempt rather than as text to validate.

WHERE THE SAFETY LAYER SITS, AND WHY THAT IS THE WHOLE ARGUMENT
--------------------------------------------------------------
This client is called from BELOW `guarded_generation`. Whatever it returns is
handed to Module 24's `validate_text` with the calling module's own
`SafetyContext`, exactly as Gemini's output is -- and then to that module's own
local gates: the CV bounds in Module 35, the no-digits rule in the glossary,
the echo validation in Module 36. **A different provider does not get a
different safety pipeline**, and the fallback is placed where it cannot
acquire one.

QUOTA-ONLY, AND NEVER ON A REFUSAL
----------------------------------
`gemini_text.py` already records the rule for models: a provider safety block
is an ANSWER, and shopping it around models until one complies is precisely
what a safety layer must never do. CROSSING PROVIDERS MAKES THAT SHARPER, NOT
WEAKER. So only a 429 reaches this module. A timeout, a truncation, an empty
body, a 400 and above all a safety refusal are returned to the caller from the
primary provider, unchanged, and never re-asked here.

PRIVACY: like the Gemini clients, this module logs no prompt and no response
text, and the key is a `SecretStr` that is never logged.

MODEL SELECTION WAS PROBED, NOT ASSUMED. The default chain in `Settings` was
chosen by sending this codebase's real Module 35 and Module 27b prompts to
three candidates and checking the answers against the real `_parse`, the real
CV gate and the real Module 24 validator. See `config.py`.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any, Dict, List, Optional

import httpx

from app.config import Settings
from app.core.errors import (
    ErrorCode,
    ModelError,
    ModelNotConfiguredError,
    ModelRateLimitedError,
    ModelTimeoutError,
)
from app.core.logging import get_logger, safe_meta

logger = get_logger(__name__)

#: Models known to be rate limited, as {model: monotonic time it may be
#: retried}. PROCESS-WIDE, for the same reason `_MODEL_COOLDOWN` is in
#: `gemini_client.py`: a client is built per request, so per-instance state
#: would forget the exhaustion between calls and spend one doomed request per
#: call rediscovering it.
_COOLDOWN: Dict[str, float] = {}
_COOLDOWN_LOCK = threading.Lock()

#: The key under which an ACCOUNT-WIDE exhaustion is recorded.
#:
#: OPENROUTER HAS TWO DIFFERENT 429s AND THEY MEAN DIFFERENT THINGS. This was
#: established by probing, not assumed:
#:
#:   * the ACCOUNT's free-model daily allowance is spent -- every `:free`
#:     model is then unusable, because that allowance is metered per account
#:     and not per model. Trying the next model in the chain would spend a
#:     request proving what the first already proved.
#:   * an UPSTREAM PROVIDER is briefly busy -- observed live, with the
#:     account's own allowance untouched. That is specific to one model, and
#:     the rest of the chain is fine.
#:
#: Collapsing the two would either waste the whole chain on a transient blip
#: or keep hammering a spent account. `_is_account_exhausted` separates them.
_ACCOUNT_KEY = "*account*"


def _in_cooldown(key: str) -> bool:
    with _COOLDOWN_LOCK:
        until = _COOLDOWN.get(key)
        if until is None:
            return False
        if time.monotonic() >= until:
            del _COOLDOWN[key]
            return False
        return True


def reset_cooldowns() -> None:
    """Forget every recorded exhaustion. For tests only.

    Process-wide state that survives between tests makes one test's 429 change
    another test's verdict, which is how a suite starts lying about order.
    """
    with _COOLDOWN_LOCK:
        _COOLDOWN.clear()


def _is_account_exhausted(body: str) -> bool:
    """Does this 429 body say the ACCOUNT's free allowance is gone?

    Read off OpenRouter's actual error payloads rather than invented. An
    upstream-provider 429 carries `provider_name` and says the MODEL is
    rate-limited; an account-level refusal talks about the daily free request
    allowance. **When it cannot be told, the answer is False** -- treating a
    transient blip as an account-wide outage would disable a working chain for
    the whole cooldown, and the narrower claim is the safer error.
    """
    lowered = (body or "").lower()
    if "provider returned error" in lowered or "provider_name" in lowered:
        return False
    markers = (
        "free-model-per-day",
        "free_model_daily",
        "daily request limit",
        "daily limit",
        "add credits",
        "rate-limited by your account",
    )
    return any(m in lowered for m in markers)


class OpenRouterTextClient:
    """Prose generation through OpenRouter. Same contract as the Gemini one."""

    def __init__(self, settings: Settings, http_client: Optional[Any] = None) -> None:
        self._settings = settings
        # Injected for tests. A real one is built per call and closed, because
        # this client is constructed per request and holding a pooled
        # connection open across requests buys nothing at this call volume.
        self._http = http_client

    # -- chain ---------------------------------------------------------------

    def _model_chain(self) -> List[str]:
        """Models to try, in order, skipping any known to be rate limited.

        Returns EMPTY when the account itself is exhausted, which is the one
        case where making a request cannot help. That differs from
        `GeminiClient._model_chain`, which never returns empty -- there, a
        cooldown is only ever an optimisation over a per-model daily cap, so
        it is right to make a real request and get a real 429 to report. Here
        an account-level refusal has already told us about every model.
        """
        if _in_cooldown(_ACCOUNT_KEY):
            return []
        return [m for m in self._settings.openrouter_model_list if not _in_cooldown(m)]

    def _mark_exhausted(self, key: str, *, account: bool = False) -> None:
        with _COOLDOWN_LOCK:
            _COOLDOWN[key] = (
                time.monotonic() + self._settings.openrouter_model_cooldown_seconds
            )
        logger.warning(
            "openrouter_exhausted %s",
            safe_meta(
                provider="openrouter",
                scope="account" if account else "model",
                model=None if account else key,
                cooldown_seconds=self._settings.openrouter_model_cooldown_seconds,
            ),
        )

    # -- generation ----------------------------------------------------------

    def generate_text(
        self,
        prompt: str,
        *,
        system_instruction: str,
        temperature: float,
        max_output_tokens: int,
    ) -> str:
        """Send one text prompt and return the model's prose.

        Every keyword is REQUIRED and none has a default. The Gemini client
        owns the defaults for temperature and output budget, both of which it
        documents against measured behaviour; a second set of defaults here
        would be a second policy, and the two would drift.
        """
        if not self._settings.openrouter_available:
            raise ModelNotConfiguredError(
                "The secondary text provider is not configured."
            )

        chain = self._model_chain()
        if not chain:
            raise ModelRateLimitedError(
                "The secondary text provider is rate limited. Please retry "
                "shortly."
            )

        rate_limited: Optional[ModelError] = None
        for model in chain:
            try:
                return self._generate_with(model, prompt, system_instruction,
                                           temperature, max_output_tokens)
            except ModelRateLimitedError as exc:
                rate_limited = exc
                # THE ACCOUNT CHECK HAS TO BE RE-MADE HERE, not only when the
                # chain was built. `_generate_with` may have just learned that
                # the ACCOUNT's allowance is gone, and that is a fact about
                # every model -- continuing would spend a request proving what
                # this one already proved. Caught by a test that counts posts.
                if _in_cooldown(_ACCOUNT_KEY):
                    break
                continue

        raise rate_limited or ModelError(
            "The secondary text provider request failed."
        )

    def _generate_with(
        self,
        model: str,
        prompt: str,
        system_instruction: str,
        temperature: float,
        max_output_tokens: int,
    ) -> str:
        """One model, ONE attempt. Raises on every failure path.

        NO RETRY LOOP HERE, and that is deliberate. This client is already the
        fallback -- the primary provider has spent its own retries and its
        whole model chain before control arrives. Retrying again multiplies the
        worst-case latency of a request that a reader is waiting on, and the
        `analyze` endpoint is still synchronous.
        """
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_output_tokens,
        }
        headers = {
            "Authorization": "Bearer "
            + self._settings.openrouter_api_key.get_secret_value(),
            "Content-Type": "application/json",
        }
        url = self._settings.openrouter_base_url.rstrip("/") + "/chat/completions"
        started = time.monotonic()

        try:
            response = self._post(url, payload, headers)
        except Exception as exc:  # noqa: BLE001 -- classified below
            raise self._to_service_error(exc, model) from exc

        status = getattr(response, "status_code", None)
        body = self._body_text(response)

        if status == 429:
            account = _is_account_exhausted(body)
            self._mark_exhausted(_ACCOUNT_KEY if account else model, account=account)
            raise ModelRateLimitedError(
                "The secondary text provider is rate limited. Please retry "
                "shortly."
            )
        if status in (401, 403):
            raise ModelNotConfiguredError(
                "The secondary text provider rejected the service credentials."
            )
        if status in (500, 502, 503, 504):
            raise ModelError(
                "The secondary text provider is temporarily unavailable.",
                code=ErrorCode.MODEL_UNAVAILABLE,
                status_code=503,
            )
        if status != 200:
            raise ModelError(
                "The secondary text provider rejected the request.",
                code=ErrorCode.MODEL_REQUEST_FAILED,
                status_code=502,
            )

        text = self._extract_text(body)
        logger.info(
            "openrouter_text_generated %s",
            safe_meta(
                provider="openrouter",
                model=model,
                chars=len(text),
                duration_ms=int((time.monotonic() - started) * 1000),
                fell_back=True,
            ),
        )
        return text

    # -- transport -----------------------------------------------------------

    def _post(self, url: str, payload: dict, headers: dict) -> Any:
        if self._http is not None:
            return self._http.post(url, json=payload, headers=headers)
        timeout = self._settings.openrouter_timeout_seconds
        with httpx.Client(timeout=timeout) as client:
            return client.post(url, json=payload, headers=headers)

    @staticmethod
    def _body_text(response: Any) -> str:
        text = getattr(response, "text", None)
        if isinstance(text, str):
            return text
        return ""

    @staticmethod
    def _extract_text(body: str) -> str:
        """The assistant message, or raise. NEVER a placeholder.

        An unparsable body, a missing choice and an empty string are all the
        same thing to a caller -- no answer -- and all raise, so
        `guarded_generation` counts a failed attempt rather than validating
        something this function invented.
        """
        try:
            payload = json.loads(body or "")
        except Exception:  # noqa: BLE001
            raise ModelError(
                "The secondary text provider returned an unreadable response.",
                code=ErrorCode.MODEL_REQUEST_FAILED,
                status_code=502,
            )
        choices = payload.get("choices") if isinstance(payload, dict) else None
        message = (
            choices[0].get("message")
            if isinstance(choices, list) and choices and isinstance(choices[0], dict)
            else None
        )
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            # THE SAME CODE THE GEMINI CLIENT USES FOR THIS, not a new one.
            # `_generate_text_with` treats MODEL_RESPONSE_EMPTY as the one
            # body worth resampling, and a second spelling of "empty" would be
            # invisible to every consumer that already knows the first.
            raise ModelError(
                "The secondary text provider returned an empty response.",
                code=ErrorCode.MODEL_RESPONSE_EMPTY,
                status_code=502,
            )
        return content

    # -- error classification ------------------------------------------------

    @staticmethod
    def _to_service_error(exc: BaseException, model: str) -> ModelError:
        """Transport exception -> this service's taxonomy.

        The upstream message is deliberately NOT echoed: it can carry request
        fragments. Same rule as `GeminiClient._to_service_error`.
        """
        names = {type(exc).__name__} | {b.__name__ for b in type(exc).__mro__}
        if isinstance(exc, TimeoutError) or names & {
            "ConnectTimeout",
            "ReadTimeout",
            "WriteTimeout",
            "PoolTimeout",
            "TimeoutException",
            "TimeoutError",
        }:
            return ModelTimeoutError(
                "The secondary text provider did not respond in time."
            )
        return ModelError("The secondary text provider request failed.")


def build_openrouter_client(
    settings: Settings, http_client: Optional[Any] = None
) -> OpenRouterTextClient:
    """The single place an OpenRouter client is constructed."""
    return OpenRouterTextClient(settings, http_client)


__all__ = [
    "OpenRouterTextClient",
    "build_openrouter_client",
    "reset_cooldowns",
]
