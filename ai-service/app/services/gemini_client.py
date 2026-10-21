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

_RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}

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


_MODEL_COOLDOWN: Dict[str, float] = {}
_COOLDOWN_LOCK = threading.Lock()


class GeminiClient:

    def __init__(self, settings: Settings, client: Optional[Any] = None) -> None:
        self._settings = settings
        self._client = client
        self._model = settings.gemini_model


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
        chain = [self._model] + self._settings.fallback_model_list
        usable = [m for m in chain if not self._in_cooldown(m)]
        return usable or [self._model]


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
                timeout=int(self._settings.gemini_timeout_seconds * 1000)
            ),
        )
        return self._client


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
        return isinstance(exc, genai_errors.ServerError)

    @classmethod
    def _to_service_error(cls, exc: BaseException) -> ModelError:
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
            return ModelNotConfiguredError(
                "The extraction model rejected the service credentials."
            )
        if status == 400:
            return ModelError(
                "The extraction model rejected the request.",
                code=ErrorCode.MODEL_REQUEST_FAILED,
                status_code=502,
            )
        return ModelError("The extraction model request failed.")


    @staticmethod
    def _extract_text(response: Any) -> str:
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
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1] if "\n" in cleaned else ""
            if cleaned.rstrip().endswith("```"):
                cleaned = cleaned.rstrip()[:-3]
            cleaned = cleaned.strip()

        try:
            parsed = json.loads(cleaned)
        except (json.JSONDecodeError, ValueError):
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


    def extract_page(
        self, image_bytes: bytes, mime_type: str, prompt: str
    ) -> dict:
        client = self._ensure_client()

        config_kwargs = dict(
            system_instruction=SYSTEM_INSTRUCTION,
            temperature=self._settings.gemini_temperature,
            max_output_tokens=self._settings.gemini_max_output_tokens,
            response_mime_type="application/json",
            response_schema=gemini_response_schema(),
        )
        if self._settings.gemini_seed is not None:
            config_kwargs["seed"] = self._settings.gemini_seed
        try:
            config = genai_types.GenerateContentConfig(**config_kwargs)
        except Exception:
            config_kwargs.pop("seed", None)
            config = genai_types.GenerateContentConfig(**config_kwargs)
        contents = [
            genai_types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            genai_types.Part.from_text(text=prompt),
        ]

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
                        model=model,
                        fell_back=fell_back or None,
                    ),
                )
                return parsed

            except ModelError as exc:
                retryable_body = exc.code in {
                    ErrorCode.MODEL_RESPONSE_MALFORMED,
                    ErrorCode.MODEL_RESPONSE_EMPTY,
                }
                if not retryable_body or attempt >= attempts:
                    raise
                last_error = exc

            except Exception as exc:
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
                "gemini_retry %s",
                safe_meta(
                    attempt=attempt,
                    error_type=type(last_error).__name__ if last_error else None,
                    delay_seconds=round(delay, 2),
                    model=model,
                ),
            )
            time.sleep(delay)

        raise self._to_service_error(last_error or RuntimeError("unknown"))
