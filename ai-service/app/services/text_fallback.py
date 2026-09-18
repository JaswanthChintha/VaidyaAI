"""The crossing policy: when a spent Gemini chain may reach a second provider.

This module exists so that ONE RULE LIVES IN ONE PLACE and can be read without
reading a transport. It holds no HTTP, no SDK, no prompt and no retry loop --
`gemini_text.GeminiTextClient` owns the primary transport and
`openrouter_text.OpenRouterTextClient` owns the secondary one. What is here is
only the decision about when the second may be asked at all.

==========================================================================
THE RULE: EXHAUSTION CROSSES, A REFUSAL NEVER DOES
==========================================================================

`gemini_text.py` already records this for MODELS:

    a provider safety block is an ANSWER, and shopping it around models until
    one complies is precisely what a safety layer must never do.

CROSSING PROVIDERS MAKES THAT SHARPER, NOT WEAKER. A second provider is a
second set of safety behaviours, so "ask someone else" is exactly the move
that would let a refused generation through. Therefore:

  * `ModelRateLimitedError` from the primary -- and ONLY that -- may cross.
    It means every Gemini model in the chain answered 429, which says the
    quota is gone, not that the request was wrong.
  * EVERY OTHER FAILURE IS RE-RAISED UNCHANGED. A timeout, a truncation, an
    empty body, a 400, a credentials rejection, and above all a safety block
    are the primary provider's answer about THIS REQUEST, and asking a
    different provider the same question would be shopping for a better one.

==========================================================================
WHERE THIS SITS RELATIVE TO MODULE 24
==========================================================================

BELOW IT. Callers reach this class through `generate_text`, which
`guarded_generation` invokes as its `generate` callable. So the secondary
provider's prose is validated by `validate_text` with the calling module's own
`SafetyContext`, and then by that module's own local gates -- Module 35's CV
bounds, the glossary's no-digits rule, Module 36's echo validation. **A
different provider does not get a different safety pipeline.**

A test pins this by asserting the fallback text is still refused when it
violates policy.

==========================================================================
NO KEY MEANS NOTHING CHANGES
==========================================================================

With no `OPENROUTER_API_KEY` the secondary is never constructed and never
called, and this class degrades to exactly the primary's behaviour -- which is
the state every pre-existing test in this repository runs in, and why they did
not have to be rewritten.
"""

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
    """The primary text client, with a secondary provider behind exhaustion.

    Duck-typed against `GeminiTextClient.generate_text`, which is the only
    method any caller uses. It is NOT a subclass of either client: it is a
    policy object holding two transports, and inheriting from one of them
    would imply it IS that transport.
    """

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
        """Exposed so a caller or test can reach the Gemini client itself."""
        return self._primary

    @property
    def secondary(self) -> Optional[Any]:
        """The secondary provider, or None when it is not configured."""
        return self._secondary

    def generate_text(
        self,
        prompt: str,
        *,
        system_instruction: str = SYSTEM_INSTRUCTION,
        temperature: float = EXPLANATION_TEMPERATURE,
        max_output_tokens: int = EXPLANATION_MAX_OUTPUT_TOKENS,
    ) -> str:
        """Prose from the primary, or from the secondary if the primary is spent.

        THE DEFAULTS ARE THE PRIMARY'S, imported rather than restated. Both are
        documented in `gemini_text.py` against measured behaviour -- the output
        budget in particular records a live truncation outage -- and a second
        copy here would drift from the reasoning that produced them.
        """
        try:
            return self._primary.generate_text(
                prompt,
                system_instruction=system_instruction,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
            )
        except ModelRateLimitedError as exhausted:
            # THE ONLY BRANCH THAT CROSSES. See the module docstring; every
            # other exception propagates from the line above untouched, which
            # is what keeps a refusal from being re-asked elsewhere.
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
                # THE PRIMARY'S ERROR IS WHAT THE CALLER HEARS when the
                # secondary also fails. The caller asked the service for prose,
                # and "the model is rate limited" describes the situation it is
                # actually in; a message about a provider it never chose would
                # send a reader debugging the wrong thing.
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
    """Construct the policy object, wiring a secondary only if one is usable.

    `secondary` is injected by tests. Otherwise it is built ONLY when
    `openrouter_available` -- a key AND at least one model -- so an absent or
    half-configured secondary can never reach the transport and fail there.
    """
    if secondary is None and settings.openrouter_available:
        from app.services.openrouter_text import build_openrouter_client

        secondary = build_openrouter_client(settings)
    return FallbackTextClient(settings, primary, secondary)


__all__ = ["FallbackTextClient", "build_fallback_text_client"]
