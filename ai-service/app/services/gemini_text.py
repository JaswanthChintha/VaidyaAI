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

EXPLANATION_TEMPERATURE = 0.2

EXPLANATION_MAX_OUTPUT_TOKENS = 4096

EXPLANATION_THINKING_LEVEL = "low"


def _thinking_config() -> Optional[genai_types.ThinkingConfig]:
    try:
        return genai_types.ThinkingConfig(thinking_level=EXPLANATION_THINKING_LEVEL)
    except Exception:
        try:
            return genai_types.ThinkingConfig(thinking_budget=512)
        except Exception:
            return None


class GeminiTextClient(GeminiClient):

    def generate_text(
        self,
        prompt: str,
        *,
        system_instruction: str = SYSTEM_INSTRUCTION,
        temperature: float = EXPLANATION_TEMPERATURE,
        max_output_tokens: int = EXPLANATION_MAX_OUTPUT_TOKENS,
    ) -> str:
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
        except Exception:
            config_kwargs.pop("thinking_config", None)
            config = genai_types.GenerateContentConfig(**config_kwargs)
        contents = [genai_types.Part.from_text(text=prompt)]

        rate_limit_error: Optional[ModelError] = None
        unavailable_error: Optional[ModelError] = None

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
            except ModelError as exc:
                if exc.code != ErrorCode.MODEL_UNAVAILABLE:
                    raise
                logger.warning(
                    "gemini_text_model_unavailable_falling_back %s",
                    safe_meta(model=model, position=position, module=23),
                )
                unavailable_error = exc
                continue

        raise rate_limit_error or unavailable_error or self._to_service_error(
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
                if exc.code != ErrorCode.MODEL_RESPONSE_EMPTY or attempt >= attempts:
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
    from app.services.text_fallback import build_fallback_text_client

    return build_fallback_text_client(settings, GeminiTextClient(settings, client))


__all__ = [
    "EXPLANATION_MAX_OUTPUT_TOKENS",
    "EXPLANATION_TEMPERATURE",
    "EXPLANATION_THINKING_LEVEL",
    "GeminiTextClient",
    "build_text_client",
]
