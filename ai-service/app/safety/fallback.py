"""Module 24 -- what a patient sees when a generation is refused.

A rejection that produces an empty screen is not a safety feature; it is an
outage with a moral justification. The spec's own architecture already supplies
the answer: the STRUCTURED, CATALOGUE-SOURCED report of Modules 17-20 exists
independently of any LLM, and every word in it either came from
`app/data/recommendation_catalog.py` by code or was scanned at import. When the
prose layer is refused, that report is what remains -- and it is the part of
the system whose safety is structural rather than inspected.

So the fallback says three things, in fixed reviewed wording:

    1. a plain-language explanation was not produced this time,
    2. the structured findings are unaffected and still stand,
    3. the question belongs with a qualified healthcare professional.

and carries the catalogue recommendations that make (3) concrete. It never
invents a substitute explanation, never apologises in a way that implies the
findings are unreliable, and never hints at what the refused text said.
"""

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

#: Fixed, reviewed. Deliberately says the FINDINGS still stand -- a reader who
#: concludes "the analysis failed" would discard a real abnormality.
FALLBACK_NOTICE = (
    "A plain-language explanation could not be prepared for this report. The "
    "structured findings above were produced by the analysis itself and are "
    "unaffected. A qualified healthcare professional can go through them with "
    "you."
)


class SafeFallback(BaseModel):
    """What to render instead of a refused generation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: str = SAFETY_LAYER_VERSION
    #: Always False here. Present so a renderer branches on a field rather than
    #: on the presence of a string.
    generated_explanation_available: bool = False
    notice: str = FALLBACK_NOTICE
    #: The structured, catalogue-sourced report is the fallback content.
    use_structured_report: bool = True
    #: Catalogue recommendation codes a renderer should show alongside.
    recommendation_codes: Tuple[str, ...] = ()
    #: The reviewed text for those codes, resolved through `recommendation()`
    #: so it cannot diverge from the catalogue.
    recommendations: Tuple[Dict[str, str], ...] = ()
    #: Why the generation was withheld. Codes only -- never the refused text,
    #: never the offending span. This is patient- and reviewer-facing.
    violation_codes: Tuple[str, ...] = ()


def safe_fallback(verdict: Optional[SafetyVerdict] = None) -> SafeFallback:
    """Build the fallback for a refused (or absent) generation.

    Takes the verdict only to copy its CODES across. The refused text is not
    read, not echoed, and not summarised: a patient must never be shown a hint
    of the unsafe sentence, and a "we nearly told you X" is exactly that hint.
    """
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
    """The result of running a generator behind the safety layer.

    Exactly one of `approved_text` and `fallback` is populated. Module 23 does
    not have to decide anything: if `approved_text` is None, render `fallback`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    approved_text: Optional[str] = None
    fallback: Optional[SafeFallback] = None
    verdict: SafetyVerdict
    attempts: int = 1
    #: Every verdict, in order, so a reviewer can see what the retries did.
    history: Tuple[SafetyVerdict, ...] = ()


def guarded_generation(
    generate: Callable[..., object],
    *,
    context: Optional[SafetyContext] = None,
    attempts: int = 2,
) -> GuardedGenerationResult:
    """Generate, validate, retry, and fall back. The Module 23 entry point.

        result = guarded_generation(lambda feedback=None: llm(prompt, feedback),
                                    context=SafetyContext(grounding_sources=...))
        text = result.approved_text          # None => render result.fallback

    `generate` is called with no arguments the first time. On a retry it is
    called with `feedback=<the previous verdict>` if it accepts that keyword,
    so a generator can quote the offending spans back into its own prompt;
    generators that do not accept it are simply called again. A generator that
    raises is treated as a failed attempt, never as an approval.

    `attempts` is a cap, not a target: the loop stops at the first approval.
    """
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
                    produced = generate(feedback=verdict)  # type: ignore[call-arg]
                except TypeError:
                    produced = generate()
        except Exception:  # noqa: BLE001 -- a broken generator is not a pass
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
