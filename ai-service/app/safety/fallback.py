from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict

from app.core.logging import get_logger, safe_meta
from app.safety.policy import SAFETY_LAYER_VERSION, ViolationCode
from app.safety.validator import (
    REJECT,
    SafetyContext,
    SafetyVerdict,
    validate_text,
)

logger = get_logger(__name__)

FALLBACK_NOTICE = (
    "A plain-language explanation could not be prepared for this report. The "
    "structured findings above were produced by the analysis itself and are "
    "unaffected. A qualified healthcare professional can go through them with "
    "you."
)


class SafeFallback(BaseModel):

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: str = SAFETY_LAYER_VERSION
    generated_explanation_available: bool = False
    notice: str = FALLBACK_NOTICE
    use_structured_report: bool = True
    recommendation_codes: Tuple[str, ...] = ()
    recommendations: Tuple[Dict[str, str], ...] = ()
    violation_codes: Tuple[str, ...] = ()


def safe_fallback(verdict: Optional[SafetyVerdict] = None) -> SafeFallback:
    from app.data.recommendation_catalog import (
        DISCUSS_WITH_CLINICIAN,
        INFORMATION_INCOMPLETE,
        NOT_A_DIAGNOSIS,
        recommendations,
    )

    codes = (NOT_A_DIAGNOSIS, DISCUSS_WITH_CLINICIAN, INFORMATION_INCOMPLETE)
    resolved = tuple(
        {"code": r.code, "text": r.text, "category": r.category}
        for r in recommendations(codes)
    )
    violation_codes: Tuple[str, ...] = ()
    if verdict is not None:
        violation_codes = tuple(sorted(set(verdict.codes)))
    return SafeFallback(
        recommendation_codes=codes,
        recommendations=resolved,
        violation_codes=violation_codes,
    )


class GuardedGenerationResult(BaseModel):

    model_config = ConfigDict(frozen=True, extra="forbid")

    approved_text: Optional[str] = None
    fallback: Optional[SafeFallback] = None
    verdict: SafetyVerdict
    attempts: int = 1
    history: Tuple[SafetyVerdict, ...] = ()


def guarded_generation(
    generate: Callable[..., object],
    *,
    context: Optional[SafetyContext] = None,
    attempts: int = 2,
) -> GuardedGenerationResult:
    ctx = context if context is not None else SafetyContext()
    attempts = max(1, int(attempts))
    history: List[SafetyVerdict] = []
    verdict: Optional[SafetyVerdict] = None

    for attempt in range(1, attempts + 1):
        try:
            if attempt == 1:
                produced = generate()
            else:
                try:
                    produced = generate(feedback=verdict)
                except TypeError:
                    produced = generate()
        except Exception:
            produced = None
        verdict = validate_text(produced, ctx)
        history.append(verdict)
        if verdict.approved and verdict.approved_text is not None:
            logger.info(
                "safety_guarded_generation %s",
                safe_meta(outcome="approved", attempts=attempt, module=24),
            )
            return GuardedGenerationResult(
                approved_text=verdict.approved_text,
                fallback=None,
                verdict=verdict,
                attempts=attempt,
                history=tuple(history),
            )

    assert verdict is not None
    logger.warning(
        "safety_guarded_generation %s",
        safe_meta(
            outcome="fallback",
            attempts=len(history),
            codes=",".join(sorted(set(verdict.codes))),
            module=24,
        ),
    )
    return GuardedGenerationResult(
        approved_text=None,
        fallback=safe_fallback(verdict),
        verdict=verdict,
        attempts=len(history),
        history=tuple(history),
    )


__all__ = [
    "FALLBACK_NOTICE",
    "GuardedGenerationResult",
    "REJECT",
    "SafeFallback",
    "ViolationCode",
    "guarded_generation",
    "safe_fallback",
]
