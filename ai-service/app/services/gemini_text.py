"""Text generation on top of the EXISTING Gemini client.

Module 4's `app/services/gemini_client.py` already owns everything hard about
talking to Gemini: client construction from `Settings`, the timeout, the
retry-on-transient policy, the exception -> `ServiceError` taxonomy, the
truncation/blocked/empty detection, and the rule that prompts and responses are
never logged.

None of that is re-implemented here. `GeminiTextClient` SUBCLASSES
`GeminiClient` and adds exactly one method, `generate_text`, which asks for
prose instead of schema-constrained JSON. If the transport policy changes in
`gemini_client.py`, this changes with it -- which is the point of subclassing
rather than writing a second client.

WHAT IS DIFFERENT FROM `extract_page`
-------------------------------------
* text in, text out -- no image part, no `response_schema`, no JSON parsing.
* `max_output_tokens` and a low thinking level, both sized around the fact
  that this is a THINKING model -- see `EXPLANATION_MAX_OUTPUT_TOKENS`, which
  documents a truncation outage only the live test could have found.
* the system instruction comes from `app/prompts/explanation_prompt.py`
  rather than the extraction prompt.
* temperature is pinned LOW and independently of `Settings.gemini_temperature`
  (which Module 4 sets to 0.0 for transcription). Explanation quality wants a
  hair above zero; safety wants nowhere near the default sampling temperature.

PRIVACY: like its parent, this module logs no prompt and no response text.
"""

from __future__ import annotations

import random
import time
from typing import Optional

from google.genai import types as genai_types

from app.config import Settings
from app.core.errors import ErrorCode, ModelError, ModelRateLimitedError
from app.core.logging import get_logger, safe_meta
from app.prompts.explanation_prompt import SYSTEM_INSTRUCTION
from app.services.gemini_client import GeminiClient

logger = get_logger(__name__)

#: Low, fixed, and deliberately not read from `Settings`. A patient-facing
#: explanation is not a place for sampling diversity.
EXPLANATION_TEMPERATURE = 0.2

#: MEASURED, not guessed. `gemini-3.6-flash` is a thinking model, and its
#: reasoning tokens are drawn from `max_output_tokens` BEFORE any prose is
#: emitted. A 700-token cap was spent entirely on thinking and every live call
#: came back `MODEL_RESPONSE_TRUNCATED` -- an outage that never appears offline,
#: because a mocked client has no thinking budget. The cap is therefore set
#: well above what the prose needs; the prompt, not the cap, is what keeps the
#: answer to a few sentences.
EXPLANATION_MAX_OUTPUT_TOKENS = 4096

#: Thinking is turned DOWN rather than off. `thinking_level="low"` is the
#: Gemini 3 control; older models take `thinking_budget`. Both are set, and an
#: SDK that rejects either is tolerated -- see `_thinking_config`. Restraint
#: here is not about cost: reasoning tokens are the thing that silently ate the
#: output budget above.
EXPLANATION_THINKING_LEVEL = "low"


def _thinking_config() -> Optional[genai_types.ThinkingConfig]:
    """A low-thinking config, or None if this SDK does not accept one.

    Built defensively because the field set has changed across SDK releases
    (`thinking_budget` predates `thinking_level`). A missing field must degrade
    to "no thinking config" -- the raised `max_output_tokens` above is what
    actually prevents the truncation, and this is the optimisation on top.
    """
    try:
        return genai_types.ThinkingConfig(thinking_level=EXPLANATION_THINKING_LEVEL)
    except Exception:  # noqa: BLE001 -- older/newer SDK field set
        try:
            return genai_types.ThinkingConfig(thinking_budget=512)
        except Exception:  # noqa: BLE001
            return None


class GeminiTextClient(GeminiClient):
    """`GeminiClient` plus prose generation. Same transport, same taxonomy."""

    def generate_text(
        self,
        prompt: str,
        *,
        system_instruction: str = SYSTEM_INSTRUCTION,
        temperature: float = EXPLANATION_TEMPERATURE,
        max_output_tokens: int = EXPLANATION_MAX_OUTPUT_TOKENS,
    ) -> str:
        """Send one text prompt and return the model's prose.

        Raises a `ServiceError` subclass on every failure path -- timeout, rate
        limit, blocked, truncated, empty. It NEVER returns a placeholder
        string: a caller must not be able to mistake a failure for an answer,
        and `guarded_generation` treats a raise as a failed attempt.
        """
        client = self._ensure_client()

        config_kwargs = {
            "system_instruction": system_instruction,
            "temperature": temperature,
            "max_output_tokens": max_output_tokens,
        }
        thinking = _thinking_config()
        if thinking is not None:
            config_kwargs["thinking_config"] = thinking
        try:
            config = genai_types.GenerateContentConfig(**config_kwargs)
        except Exception:  # noqa: BLE001 -- SDK rejected the thinking config
            config_kwargs.pop("thinking_config", None)
            config = genai_types.GenerateContentConfig(**config_kwargs)
        contents = [genai_types.Part.from_text(text=prompt)]

        # Same quota-only fallback as Module 4's extraction path, and for the
        # same reason: the free tier meters per model per day, so a 429 here
        # says this model is spent, not that the key is. Every other failure
        # is left exactly as it was -- in particular a provider safety block
        # is an ANSWER, and shopping it around models until one complies is
        # precisely what a safety layer must never do.
        rate_limit_error: Optional[ModelError] = None

        chain = self._model_chain()
        for position, model in enumerate(chain):
            try:
                return self._generate_text_with(
                    client,
                    model,
                    contents,
                    config,
                    fell_back=position > 0,
                    more_models=position < len(chain) - 1,
                )
            except ModelRateLimitedError as exc:
                self._mark_exhausted(model)
                rate_limit_error = exc
                continue

        raise rate_limit_error or self._to_service_error(
            RuntimeError("no model available")
        )

    def _generate_text_with(
        self,
        client: object,
        model: str,
        contents: object,
        config: object,
        *,
        fell_back: bool,
        more_models: bool,
    ) -> str:
        """One model's full retry loop. Raises on every failure path."""
        attempts = max(1, self._settings.gemini_max_retries)
        last_error: Optional[BaseException] = None

        for attempt in range(1, attempts + 1):
            started = time.monotonic()
            try:
                response = client.models.generate_content(
                    model=model, contents=contents, config=config
                )
                text = self._extract_text(response)
                logger.info(
                    "gemini_text_generated %s",
                    safe_meta(
                        attempt=attempt,
                        chars=len(text),
                        duration_ms=int((time.monotonic() - started) * 1000),
                        module=23,
                        model=model,
                        fell_back=fell_back or None,
                    ),
                )
                return text

            except ModelError as exc:
                # Only an EMPTY body is worth resampling. A truncation is
                # deterministic, and a safety block from the provider is an
                # answer, not a transport hiccup -- retrying either burns quota
                # for the same outcome. (Same policy as Module 4, minus the
                # malformed-JSON case, which cannot arise for prose.)
                if exc.code != ErrorCode.MODEL_RESPONSE_EMPTY or attempt >= attempts:
                    raise
                last_error = exc

            except Exception as exc:  # noqa: BLE001 -- classified by the parent
                # See Module 4's extraction path: a 429 with another model
                # still available is handed straight back to the chain rather
                # than retried here, because a per-model daily cap cannot clear
                # in a one-second backoff and the retry costs a real request.
                if more_models and self._status_of(exc) == 429:
                    raise self._to_service_error(exc) from exc
                if not self._is_retryable(exc) or attempt >= attempts:
                    raise self._to_service_error(exc) from exc
                last_error = exc

            delay = self._settings.gemini_retry_base_delay_seconds * (
                2 ** (attempt - 1)
            )
            delay += random.uniform(0, delay * 0.25)
            logger.warning(
                "gemini_text_retry %s",
                safe_meta(
                    attempt=attempt,
                    error_type=type(last_error).__name__ if last_error else None,
                    delay_seconds=round(delay, 2),
                    module=23,
                    model=model,
                ),
            )
            time.sleep(delay)

        raise self._to_service_error(last_error or RuntimeError("unknown"))


def build_text_client(
    settings: Settings, client: Optional[object] = None
) -> object:
    """Construct the client. The single place Modules 23/25 obtain one.

    RETURNS A `FallbackTextClient` WRAPPING A `GeminiTextClient`, not the
    Gemini client itself. Callers are unaffected -- `generate_text` is the only
    method any of them uses, and the wrapper's signature is this module's own,
    defaults included.

    WHY THE WRAPPER IS ALWAYS BUILT, even with no secondary configured: so
    that the configured and unconfigured paths are the SAME code path, differing
    only in whether `secondary` is None. A wrapper applied conditionally would
    mean the fallback ran through a class that the overwhelmingly common case
    never exercised, and the first real quota exhaustion would be its first
    execution.

    The import is local because `text_fallback` imports this module for the
    primary client's defaults, and a module-level import would be circular.
    """
    from app.services.text_fallback import build_fallback_text_client

    return build_fallback_text_client(settings, GeminiTextClient(settings, client))


__all__ = [
    "EXPLANATION_MAX_OUTPUT_TOKENS",
    "EXPLANATION_TEMPERATURE",
    "EXPLANATION_THINKING_LEVEL",
    "GeminiTextClient",
    "build_text_client",
]
