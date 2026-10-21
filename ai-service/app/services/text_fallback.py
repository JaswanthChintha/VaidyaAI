from __future__ import annotations

from typing import Any, Optional

from app.config import Settings
from app.core.errors import ModelError, ModelRateLimitedError
from app.core.logging import get_logger, safe_meta
from app.prompts.explanation_prompt import SYSTEM_INSTRUCTION
from app.services.gemini_text import (
    EXPLANATION_MAX_OUTPUT_TOKENS,
    EXPLANATION_TEMPERATURE,
    GeminiTextClient,
)

logger = get_logger(__name__)


class FallbackTextClient:

    def __init__(
        self,
        settings: Settings,
        primary: GeminiTextClient,
        secondary: Optional[Any] = None,
    ) -> None:
        self._settings = settings
        self._primary = primary
        self._secondary = secondary

    @property
    def primary(self) -> GeminiTextClient:
        return self._primary

    @property
    def secondary(self) -> Optional[Any]:
        return self._secondary

    def generate_text(
        self,
        prompt: str,
        *,
        system_instruction: str = SYSTEM_INSTRUCTION,
        temperature: float = EXPLANATION_TEMPERATURE,
        max_output_tokens: int = EXPLANATION_MAX_OUTPUT_TOKENS,
    ) -> str:
        try:
            return self._primary.generate_text(
                prompt,
                system_instruction=system_instruction,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
            )
        except ModelRateLimitedError as exhausted:
            if self._secondary is None:
                raise
            logger.warning(
                "text_provider_fallback %s",
                safe_meta(
                    from_provider="gemini",
                    to_provider="openrouter",
                    reason="rate_limited",
                ),
            )
            try:
                return self._secondary.generate_text(
                    prompt,
                    system_instruction=system_instruction,
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                )
            except ModelError as secondary_error:
                logger.warning(
                    "text_provider_fallback_failed %s",
                    safe_meta(
                        provider="openrouter",
                        error_type=type(secondary_error).__name__,
                    ),
                )
                raise exhausted from secondary_error


def build_fallback_text_client(
    settings: Settings,
    primary: GeminiTextClient,
    secondary: Optional[Any] = None,
) -> FallbackTextClient:
    if secondary is None and settings.openrouter_available:
        from app.services.openrouter_text import build_openrouter_client

        secondary = build_openrouter_client(settings)
    return FallbackTextClient(settings, primary, secondary)


__all__ = ["FallbackTextClient", "build_fallback_text_client"]
