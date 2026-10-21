from __future__ import annotations

import re
from typing import Any, List, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, Field

from app.config import Settings, get_settings
from app.core.logging import get_logger, safe_meta
from app.safety import SafetyContext, guarded_generation
from app.safety.policy import SAFETY_LAYER_VERSION

logger = get_logger(__name__)

PROSE_VERSION = "1.0.0"

OUTCOME_GENERATED = "generated"
OUTCOME_NO_MODEL = "model_unavailable"
OUTCOME_WITHHELD_BY_SAFETY = "withheld_by_safety"
OUTCOME_FACTS_MISSING = "facts_missing"
OUTCOME_FACTS_INVENTED = "facts_invented"
OUTCOME_NOTHING_TO_WRITE = "nothing_to_write"

OUTCOME_VALUES = (
    OUTCOME_GENERATED,
    OUTCOME_NO_MODEL,
    OUTCOME_WITHHELD_BY_SAFETY,
    OUTCOME_FACTS_MISSING,
    OUTCOME_FACTS_INVENTED,
    OUTCOME_NOTHING_TO_WRITE,
)

VERDICT_WORDS: Tuple[str, ...] = (
    "abnormal",
    "alarming",
    "benign",
    "borderline",
    "concerning",
    "critical",
    "dangerous",
    "elevated",
    "excellent",
    "favourable",
    "favorable",
    "fine",
    "good",
    "healthy",
    "high",
    "low",
    "mild",
    "moderate",
    "normal",
    "reassuring",
    "safe",
    "serious",
    "severe",
    "stable",
    "typical",
    "unremarkable",
    "urgent",
    "worrying",
)


class ProseSafety(BaseModel):

    model_config = ConfigDict(frozen=True, extra="forbid")

    validated: bool
    verdict: Optional[str] = None
    version: str = SAFETY_LAYER_VERSION
    violation_codes: Tuple[str, ...] = ()
    attempts: int = 0


class SummaryProse(BaseModel):

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: str = PROSE_VERSION
    outcome: str = Field(description="See OUTCOME_VALUES.")
    text: Optional[str] = None
    missing_facts: Tuple[str, ...] = ()
    invented_facts: Tuple[str, ...] = ()
    llm_calls_made: int = 0
    safety: ProseSafety


_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")


def numbers_in(text: str) -> Tuple[str, ...]:
    return tuple(_NUMBER_RE.findall(text or ""))


def words_in(text: str) -> set:
    return set(re.findall(r"[a-z]+", (text or "").lower()))


def _missing(text: str, sentences: Sequence[str], names: Sequence[str]) -> Tuple[str, ...]:
    gaps: List[str] = []
    lowered = (text or "").lower()

    for sentence in sentences:
        for number in numbers_in(sentence):
            if number not in (text or ""):
                gaps.append(f"number:{number}")

    for name in names:
        if name and name.lower() not in lowered:
            gaps.append(f"name:{name}")

    return tuple(sorted(set(gaps)))


def _invented(text: str, sentences: Sequence[str]) -> Tuple[str, ...]:
    added: List[str] = []
    source = " ".join(sentences)
    source_numbers = set(numbers_in(source))
    source_words = words_in(source)

    for number in numbers_in(text):
        if number not in source_numbers:
            added.append(f"number:{number}")

    for word in sorted(words_in(text) & set(VERDICT_WORDS)):
        if word not in source_words:
            added.append(f"verdict:{word}")

    return tuple(sorted(set(added)))


def build_prompt(
    sentences: Sequence[str],
    feedback: Any = None,
    missing: Sequence[str] = (),
    invented: Sequence[str] = (),
) -> str:
    numbered = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(sentences))
    parts = [
        "You are rewriting a short summary that will be shown to a patient "
        "about their own laboratory report.",
        "",
        "Rewrite the numbered sentences below as a few flowing sentences of "
        "plain English. Keep the same order and the same meaning.",
        "",
        "RULES, and the rewrite is discarded if any is broken:",
        "- Use only the facts in the sentences. Add nothing.",
        "- Keep every number exactly as written, including decimals.",
        "- Keep every test name and every condition name exactly as written.",
        "- Do not say whether the results are good, bad, normal, reassuring "
        "or worrying. Do not add an opinion, a conclusion or advice.",
        "- Do not drop any sentence, however minor it looks.",
        "- Write for an ordinary reader. No medical jargon that is not "
        "already in the sentences.",
        "",
        "SENTENCES:",
        numbered,
    ]
    if feedback:
        parts += ["", f"A previous attempt was refused: {feedback}"]
    if missing:
        parts += [
            "",
            "A previous attempt DROPPED these and must not: " + ", ".join(missing),
        ]
    if invented:
        parts += [
            "",
            "A previous attempt ADDED these, which were not in the sentences, "
            "and must not: " + ", ".join(invented),
        ]
    return "\n".join(parts)


def _resolve_llm(llm: Any, settings: Optional[Settings]) -> Optional[Any]:
    if llm is not None:
        return llm
    settings = settings or get_settings()
    if not getattr(settings, "gemini_api_key", None):
        return None
    from app.services.gemini_text import GeminiTextClient

    return GeminiTextClient(settings=settings)


def _refusal(outcome: str, safety: ProseSafety, **kw: Any) -> SummaryProse:
    return SummaryProse(outcome=outcome, text=None, safety=safety, **kw)


def rewrite_summary(
    sentences: Sequence[str],
    *,
    names: Sequence[str] = (),
    llm: Any = None,
    settings: Optional[Settings] = None,
) -> SummaryProse:
    sentences = [s for s in (sentences or []) if s and s.strip()]
    if not sentences:
        return _refusal(OUTCOME_NOTHING_TO_WRITE, ProseSafety(validated=False))

    client = _resolve_llm(llm, settings)
    if client is None:
        return _refusal(OUTCOME_NO_MODEL, ProseSafety(validated=False))

    source = " ".join(sentences)
    permitted = tuple(float(n) for n in numbers_in(source))

    context = SafetyContext(
        grounding_sources=tuple(sentences),
        permitted_numbers=permitted,
        purpose="patient_summary_prose",
    )

    gaps: Tuple[str, ...] = ()
    added: Tuple[str, ...] = ()
    result = None
    calls = 0

    for round_index in (0, 1):
        if round_index == 1 and not (gaps or added):
            break

        def generate(feedback: Any = None, _m=gaps, _a=added) -> Any:
            return client.generate_text(build_prompt(sentences, feedback, _m, _a))

        result = guarded_generation(generate, context=context, attempts=2)
        calls += result.attempts
        if not result.approved_text:
            break
        gaps = _missing(result.approved_text, sentences, names)
        added = _invented(result.approved_text, sentences)
        if not gaps and not added:
            break

    safety = ProseSafety(
        validated=True,
        verdict="approved" if result and result.approved_text else "rejected",
        violation_codes=tuple(sorted(set(result.verdict.codes)))
        if result and result.verdict
        else (),
        attempts=calls,
    )

    if not result or not result.approved_text:
        logger.warning("summary_prose %s", safe_meta(outcome=OUTCOME_WITHHELD_BY_SAFETY))
        return _refusal(OUTCOME_WITHHELD_BY_SAFETY, safety, llm_calls_made=calls)

    if gaps:
        logger.warning(
            "summary_prose %s",
            safe_meta(outcome=OUTCOME_FACTS_MISSING, dropped=len(gaps)),
        )
        return _refusal(
            OUTCOME_FACTS_MISSING, safety, missing_facts=gaps, llm_calls_made=calls
        )

    if added:
        logger.warning(
            "summary_prose %s",
            safe_meta(outcome=OUTCOME_FACTS_INVENTED, added=len(added)),
        )
        return _refusal(
            OUTCOME_FACTS_INVENTED, safety, invented_facts=added, llm_calls_made=calls
        )

    return SummaryProse(
        outcome=OUTCOME_GENERATED,
        text=result.approved_text.strip(),
        llm_calls_made=calls,
        safety=safety,
    )
