"""Thin wrapper around the google-genai SDK for vision extraction.

Responsibilities
  * build the client once, from configuration
  * send one page image + prompt, requesting structured JSON output
  * classify SDK/transport failures into this service's error taxonomy
  * retry transient failures (429 / 5xx / timeouts) with exponential backoff

PRIVACY: this module never logs prompts, image bytes, or response text. Only
status codes, attempt counts and durations.
"""

from __future__ import annotations

import json
import random
import threading
import time
from typing import Any, Dict, List, Optional

from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

from app.config import Settings
from app.core.errors import (
    ErrorCode,
    ModelError,
    ModelNotConfiguredError,
    ModelRateLimitedError,
    ModelTimeoutError,
)
from app.core.logging import get_logger, safe_meta
from app.prompts.extraction_prompt import SYSTEM_INSTRUCTION
from app.schemas.extraction import gemini_response_schema

logger = get_logger(__name__)

# Status codes worth retrying: rate limit, and transient server-side failures.
_RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}

# Exception types that indicate a transport-level timeout. Matched by name so
# the module does not hard-depend on httpx internals.
_TIMEOUT_NAMES = {
    "ConnectTimeout",
    "ReadTimeout",
    "WriteTimeout",
    "PoolTimeout",
    "TimeoutException",
    "TimeoutError",
    "ConnectionError",
    "ConnectError",
    "RemoteProtocolError",
}


# Models known to be out of quota, as {model_name: monotonic time it may be
# retried}. PROCESS-WIDE ON PURPOSE. A client is built per request, so
# per-instance state would forget the exhaustion between pages and spend one
# doomed request per page rediscovering it. The free tier's cap is daily, so
# what is learned on page 1 is still true on page 13.
_MODEL_COOLDOWN: Dict[str, float] = {}
_COOLDOWN_LOCK = threading.Lock()


class GeminiClient:
    """Wraps a `genai.Client` and exposes one method: extract a page."""

    def __init__(self, settings: Settings, client: Optional[Any] = None) -> None:
        self._settings = settings
        self._client = client
        self._model = settings.gemini_model

    # -- model fallback ------------------------------------------------------

    @staticmethod
    def _in_cooldown(model: str) -> bool:
        with _COOLDOWN_LOCK:
            until = _MODEL_COOLDOWN.get(model)
            if until is None:
                return False
            if time.monotonic() >= until:
                del _MODEL_COOLDOWN[model]
                return False
            return True

    def _mark_exhausted(self, model: str) -> None:
        """Record that `model` answered 429, so later calls skip it."""
        with _COOLDOWN_LOCK:
            _MODEL_COOLDOWN[model] = (
                time.monotonic() + self._settings.gemini_model_cooldown_seconds
            )
        logger.warning(
            "gemini_model_exhausted %s",
            safe_meta(
                model=model,
                cooldown_seconds=self._settings.gemini_model_cooldown_seconds,
            ),
        )

    def _model_chain(self) -> List[str]:
        """Models to try, in order, skipping any known to be out of quota.

        NEVER RETURNS EMPTY. If every model is cooling down the primary is
        returned anyway, so the caller still makes a real request and still
        gets a real 429 to report -- rather than this layer inventing a
        failure the provider never gave, or the pipeline silently doing
        nothing. A cooldown is an optimisation, not a source of truth.
        """
        chain = [self._model] + self._settings.fallback_model_list
        usable = [m for m in chain if not self._in_cooldown(m)]
        return usable or [self._model]

    # -- client construction -------------------------------------------------

    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._settings.has_api_key:
            raise ModelNotConfiguredError(
                "The extraction model is not configured: GEMINI_API_KEY is not "
                "set on the service."
            )
        self._client = genai.Client(
            api_key=self._settings.gemini_api_key.get_secret_value(),
            http_options=genai_types.HttpOptions(
                # SDK expects milliseconds.
                timeout=int(self._settings.gemini_timeout_seconds * 1000)
            ),
        )
        return self._client

    # -- error classification ------------------------------------------------

    @staticmethod
    def _status_of(exc: BaseException) -> Optional[int]:
        for attr in ("code", "status_code"):
            value = getattr(exc, attr, None)
            if isinstance(value, int):
                return value
        response = getattr(exc, "response", None)
        value = getattr(response, "status_code", None)
        if isinstance(value, int):
            return value
        return None

    @classmethod
    def _is_timeout(cls, exc: BaseException) -> bool:
        if isinstance(exc, TimeoutError):
            return True
        names = {type(exc).__name__} | {
            base.__name__ for base in type(exc).__mro__
        }
        return bool(names & _TIMEOUT_NAMES)

    @classmethod
    def _is_retryable(cls, exc: BaseException) -> bool:
        if cls._is_timeout(exc):
            return True
        status = cls._status_of(exc)
        if status in _RETRYABLE_STATUS:
            return True
        # Server-side SDK errors are transient by definition.
        return isinstance(exc, genai_errors.ServerError)

    @classmethod
    def _to_service_error(cls, exc: BaseException) -> ModelError:
        """Map an SDK/transport exception onto this service's taxonomy.

        The upstream message is deliberately NOT echoed to the caller: it can
        contain request fragments. A stable generic message is returned instead.
        """
        if cls._is_timeout(exc):
            return ModelTimeoutError(
                "The extraction model did not respond in time. Try again with "
                "a smaller document."
            )
        status = cls._status_of(exc)
        if status == 429:
            return ModelRateLimitedError(
                "The extraction model is rate limited. Please retry shortly."
            )
        if status in (500, 502, 503, 504) or isinstance(
            exc, genai_errors.ServerError
        ):
            return ModelError(
                "The extraction model is temporarily unavailable.",
                code=ErrorCode.MODEL_UNAVAILABLE,
                status_code=503,
            )
        if status in (401, 403):
            return ModelNotConfiguredError(  # type: ignore[return-value]
                "The extraction model rejected the service credentials."
            )
        if status == 400:
            return ModelError(
                "The extraction model rejected the request.",
                code=ErrorCode.MODEL_REQUEST_FAILED,
                status_code=502,
            )
        return ModelError("The extraction model request failed.")

    # -- response handling ---------------------------------------------------

    @staticmethod
    def _extract_text(response: Any) -> str:
        """Pull JSON text out of a GenerateContentResponse, defensively.

        Also detects truncation (MAX_TOKENS) and safety blocks, which arrive as
        an empty or partial body rather than an exception.
        """
        candidates = getattr(response, "candidates", None) or []

        if not candidates:
            feedback = getattr(response, "prompt_feedback", None)
            reason = getattr(feedback, "block_reason", None)
            if reason:
                raise ModelError(
                    "The extraction model declined to process the document.",
                    code=ErrorCode.MODEL_RESPONSE_BLOCKED,
                    status_code=502,
                )
            raise ModelError(
                "The extraction model returned an empty response.",
                code=ErrorCode.MODEL_RESPONSE_EMPTY,
                status_code=502,
            )

        candidate = candidates[0]
        finish = getattr(candidate, "finish_reason", None)
        finish_name = getattr(finish, "name", None) or (
            str(finish) if finish is not None else ""
        )
        finish_name = finish_name.upper()

        if "MAX_TOKENS" in finish_name:
            raise ModelError(
                "The extraction model's response was truncated because the "
                "document produced more output than the configured limit.",
                code=ErrorCode.MODEL_RESPONSE_TRUNCATED,
                status_code=502,
            )
        if "SAFETY" in finish_name or "BLOCK" in finish_name or "PROHIBITED" in finish_name:
            raise ModelError(
                "The extraction model declined to process the document.",
                code=ErrorCode.MODEL_RESPONSE_BLOCKED,
                status_code=502,
            )

        text = getattr(response, "text", None)
        if not text:
            parts = getattr(getattr(candidate, "content", None), "parts", None) or []
            text = "".join(getattr(p, "text", "") or "" for p in parts)

        if not text or not text.strip():
            raise ModelError(
                "The extraction model returned an empty response.",
                code=ErrorCode.MODEL_RESPONSE_EMPTY,
                status_code=502,
            )
        return text

    @staticmethod
    def _parse_json(text: str) -> dict:
        """Parse the model's JSON. Tolerates markdown fencing, rejects prose."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            # Strip ```json ... ``` fencing.
            cleaned = cleaned.split("\n", 1)[-1] if "\n" in cleaned else ""
            if cleaned.rstrip().endswith("```"):
                cleaned = cleaned.rstrip()[:-3]
            cleaned = cleaned.strip()

        try:
            parsed = json.loads(cleaned)
        except (json.JSONDecodeError, ValueError):
            # Last resort: take the outermost {...} span. A truncated response
            # fails here too, which is the correct outcome.
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start != -1 and end > start:
                try:
                    parsed = json.loads(cleaned[start : end + 1])
                except (json.JSONDecodeError, ValueError):
                    raise ModelError(
                        "The extraction model returned a malformed or "
                        "incomplete JSON response.",
                        code=ErrorCode.MODEL_RESPONSE_MALFORMED,
                        status_code=502,
                    ) from None
            else:
                raise ModelError(
                    "The extraction model returned a malformed or incomplete "
                    "JSON response.",
                    code=ErrorCode.MODEL_RESPONSE_MALFORMED,
                    status_code=502,
                ) from None

        if not isinstance(parsed, dict):
            raise ModelError(
                "The extraction model returned JSON of an unexpected shape.",
                code=ErrorCode.MODEL_RESPONSE_MALFORMED,
                status_code=502,
            )
        return parsed

    # -- public API ----------------------------------------------------------

    def extract_page(
        self, image_bytes: bytes, mime_type: str, prompt: str
    ) -> dict:
        """Send one page image to Gemini and return the parsed JSON dict.

        Raises a `ServiceError` subclass on every failure path.
        """
        client = self._ensure_client()

        config_kwargs = dict(
            system_instruction=SYSTEM_INSTRUCTION,
            temperature=self._settings.gemini_temperature,
            max_output_tokens=self._settings.gemini_max_output_tokens,
            response_mime_type="application/json",
            response_schema=gemini_response_schema(),
        )
        # A fixed seed (see `Settings.gemini_seed`), sent only when set and
        # only if this SDK accepts the field -- otherwise the request goes out
        # exactly as it did before the seed existed.
        if self._settings.gemini_seed is not None:
            config_kwargs["seed"] = self._settings.gemini_seed
        try:
            config = genai_types.GenerateContentConfig(**config_kwargs)
        except Exception:  # noqa: BLE001 -- SDK without `seed`
            config_kwargs.pop("seed", None)
            config = genai_types.GenerateContentConfig(**config_kwargs)
        contents = [
            genai_types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            genai_types.Part.from_text(text=prompt),
        ]

        # TRY EACH MODEL IN TURN ON THE TWO FAILURES A SIBLING CAN FIX.
        #
        # A 429 is the obvious one: the free tier meters per model per day, so
        # the key is not spent even when this model is.
        #
        # A 5xx IS THE OTHER, and leaving it out was wrong. A 503 from
        # `gemini-3.6-flash` says nothing whatever about whether
        # `gemini-3.5-flash` is healthy -- it is a statement about one
        # endpoint at one moment. This originally sat under "every other
        # failure is deterministic or already handled by the retry loop",
        # which is true of a 4xx and false of a server error, and the
        # difference showed up as soon as the provider had a bad afternoon:
        # two extractions of the same one-page document failed ninety seconds
        # apart while a third, between them, succeeded. Two retries against a
        # flaky endpoint is not resilience when three healthy endpoints are
        # sitting unused.
        #
        # STILL NOT SHOPPED AROUND: a provider SAFETY BLOCK, and any
        # deterministic 4xx. A block is an ANSWER, and asking three more
        # models until one complies is exactly the thing this chain must never
        # do. Neither is a 5xx, so neither reaches the branch below.
        rate_limit_error: Optional[ModelError] = None
        unavailable_error: Optional[ModelError] = None
        chain = self._model_chain()

        for position, model in enumerate(chain):
            try:
                return self._extract_page_with(
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
            except ModelError as exc:
                if exc.code != ErrorCode.MODEL_UNAVAILABLE:
                    raise
                logger.warning(
                    "gemini_model_unavailable_falling_back %s",
                    safe_meta(model=model, position=position),
                )
                unavailable_error = exc
                continue

        # Nothing in the chain answered. Report the provider's own reason
        # rather than a synthesised one, preferring the rate limit: "out of
        # quota" is actionable by waiting, "temporarily unavailable" only by
        # retrying, and a caller told the weaker of the two would retry into
        # a wall.
        raise rate_limit_error or unavailable_error or self._to_service_error(
            RuntimeError("no model available")
        )

    def _extract_page_with(
        self,
        client: Any,
        model: str,
        contents: Any,
        config: Any,
        *,
        fell_back: bool,
        more_models: bool,
    ) -> dict:
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
                parsed = self._parse_json(text)
                logger.info(
                    "gemini_page_extracted %s",
                    safe_meta(
                        attempt=attempt,
                        duration_ms=int((time.monotonic() - started) * 1000),
                        # WHICH MODEL READ THIS PAGE. A report whose pages were
                        # read by different models is a fact a reader of these
                        # logs needs; silently substituting one is not.
                        model=model,
                        fell_back=fell_back or None,
                    ),
                )
                return parsed

            except ModelError as exc:
                # Response-shape problems (malformed JSON, truncation, empty)
                # are worth one more try -- a resample often succeeds.
                retryable_body = exc.code in {
                    ErrorCode.MODEL_RESPONSE_MALFORMED,
                    ErrorCode.MODEL_RESPONSE_EMPTY,
                }
                if not retryable_body or attempt >= attempts:
                    raise
                last_error = exc

            except Exception as exc:  # noqa: BLE001 - classified below
                # A 429 WITH SOMEWHERE ELSE TO GO IS NOT WORTH RETRYING HERE.
                # The free tier's cap is per model per day, so sleeping a
                # second and asking the same model again cannot succeed -- it
                # just spends another of the twenty requests this key gets.
                # Hand straight back to the chain, which has an untouched
                # model waiting. When nothing else is left the original
                # backoff still applies, because then the only hope IS that
                # this was a short per-minute limit rather than the daily cap.
                if more_models and self._status_of(exc) == 429:
                    raise self._to_service_error(exc) from exc
                if not self._is_retryable(exc) or attempt >= attempts:
                    raise self._to_service_error(exc) from exc
                last_error = exc

            delay = self._settings.gemini_retry_base_delay_seconds * (
                2 ** (attempt - 1)
            )
            delay += random.uniform(0, delay * 0.25)  # jitter
            logger.warning(
                "gemini_retry %s",
                safe_meta(
                    attempt=attempt,
                    error_type=type(last_error).__name__ if last_error else None,
                    delay_seconds=round(delay, 2),
                    model=model,
                ),
            )
            time.sleep(delay)

        # Unreachable in practice; the loop always raises or returns.
        raise self._to_service_error(last_error or RuntimeError("unknown"))
