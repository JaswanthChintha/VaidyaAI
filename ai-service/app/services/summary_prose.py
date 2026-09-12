"""The patient's closing summary, rewritten for flow by the model.

==========================================================================
A REWRITE, NOT A SUMMARY. THE DIFFERENCE IS THE WHOLE SAFETY ARGUMENT
==========================================================================

`Dashboard.jsx`'s `InShort` carries a comment refusing exactly one thing:

    "Summarise this report for the patient" is one prompt away and it would
    be the single most dangerous string on this screen. A generated overall
    summary is a new patient-facing conclusion with no rule, no threshold,
    no model and no evidence chain behind it -- rendered underneath fourteen
    findings that have all four, and indistinguishable from them.

That refusal still stands and this module does not weaken it. The model is
never shown the report. It is shown SENTENCES THE PAGE HAS ALREADY COMPOSED
from decisions other stages made, and asked to make them read better. Every
number, name and verdict in the output has to have been in the input, and
anything else throws the rewrite away.

The distinction is not cosmetic. "Summarise this payload" lets a model decide
what matters; a report carrying SGPT 101.9, CRP 12.1 and ESR 35 -- all
abnormal, none of them feeding any verdict -- can be summarised as "broadly
reassuring" without a single false statement in it. "Rewrite these sentences"
cannot, because there is no sentence in the input for it to come from.

==========================================================================
FIVE GATES. THE WORST CASE IS THE COMPOSED TEXT, EXACTLY AS IT IS TODAY
==========================================================================

1. NO MODEL, NO REWRITE. Without a key this returns `model_unavailable`
   without touching the network, so the caller's fallback is the normal path
   rather than an error path -- and the suite runs offline.
2. MODULE 24, the same `guarded_generation` every other model text goes
   through.
3. NOTHING MAY BE LOST. Every number and every supplied name in the input
   must appear in the output. A summariser drops qualifying clauses first.
4. NOTHING MAY BE ADDED. Every number in the OUTPUT must appear in the input,
   and no verdict or reassurance word may appear that was not already there.
   This is the gate the clinician narrative does not have and this one needs:
   it rewrites finished patient-facing text, so anything new is by definition
   a conclusion nobody made.
5. NO SILENT SUBSTITUTION. `text` is None on every refusal and `outcome` says
   which gate stopped it. A caller cannot render half a summary and cannot
   mistake a refusal for an empty one.

The caller renders the composed sentences on every refusal. That is not a
degraded mode -- it is what the page shows today.
"""

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

#: Words that state a finding or a reassurance. One of these in the output
#: that was not in the input is a verdict the page never reached.
#:
#: REASSURANCE IS THE DANGEROUS HALF and it is easy to forget, because it
#: does not look like a claim. "Nothing to worry about" over a report with
#: three abnormal results nobody assessed is the exact failure this codebase
#: is built against, and it contains no number and names no condition.
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
    """What the safety layer did. Codes and counts only -- never the text."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    validated: bool
    verdict: Optional[str] = None
    version: str = SAFETY_LAYER_VERSION
    violation_codes: Tuple[str, ...] = ()
    attempts: int = 0


class SummaryProse(BaseModel):
    """The rewritten summary, or the stated reason there is not one."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: str = PROSE_VERSION
    outcome: str = Field(description="See OUTCOME_VALUES.")
    #: The ONLY string a caller may render. None on every refusal, and the
    #: caller then renders the sentences it supplied.
    text: Optional[str] = None
    #: What was dropped, or what was invented. Names the FACT, never the text.
    missing_facts: Tuple[str, ...] = ()
    invented_facts: Tuple[str, ...] = ()
    llm_calls_made: int = 0
    safety: ProseSafety


# --------------------------------------------------------------------------
# What must survive, and what may not appear
# --------------------------------------------------------------------------


_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")


def numbers_in(text: str) -> Tuple[str, ...]:
    """Every figure in a string, as written.

    Compared as STRINGS, not as floats: "5.0" and "5" are the same number and
    different figures, and a summary that turns one into the other has changed
    what is printed beside a reference range.
    """
    return tuple(_NUMBER_RE.findall(text or ""))


def words_in(text: str) -> set:
    return set(re.findall(r"[a-z]+", (text or "").lower()))


def _missing(text: str, sentences: Sequence[str], names: Sequence[str]) -> Tuple[str, ...]:
    """Facts in the input that did not survive the rewrite."""
    gaps: List[str] = []
    lowered = (text or "").lower()

    for sentence in sentences:
        for number in numbers_in(sentence):
            if number not in (text or ""):
                gaps.append(f"number:{number}")

    for name in names:
        if name and name.lower() not in lowered:
            gaps.append(f"name:{name}")

    # Stable, and each fact reported once however many sentences carried it.
    return tuple(sorted(set(gaps)))


def _invented(text: str, sentences: Sequence[str]) -> Tuple[str, ...]:
    """Facts in the rewrite that were not in the input.

    THIS IS THE GATE THAT MAKES A REWRITE DIFFERENT FROM A SUMMARY. Without
    it the model may state a figure nothing measured, or -- far more likely --
    close on a verdict of its own.
    """
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


# --------------------------------------------------------------------------
# The prompt
# --------------------------------------------------------------------------


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


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------


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
    """Rewrite already-composed summary sentences, or say why there is not one.

    `sentences` are the exact strings the page would otherwise render, in
    order. `names` are the condition and test names that must survive -- they
    are passed separately because a name may legitimately be reordered out of
    the sentence that carried it, and because the caller knows which tokens
    are names and this module must not guess.
    """
    sentences = [s for s in (sentences or []) if s and s.strip()]
    if not sentences:
        return _refusal(OUTCOME_NOTHING_TO_WRITE, ProseSafety(validated=False))

    client = _resolve_llm(llm, settings)
    if client is None:
        return _refusal(OUTCOME_NO_MODEL, ProseSafety(validated=False))

    source = " ".join(sentences)
    # §6v: AN EMPTY `permitted_numbers` TURNS THE SHARED NUMERIC CONTROL OFF
    # rather than forbidding all numbers. A summary with no figures in it
    # would therefore reach the model with that control disabled. The rule is
    # enforced HERE instead of by loosening the shared default: `_invented`
    # rejects any figure in the output that was not in the input, empty
    # permitted set or not.
    permitted = tuple(float(n) for n in numbers_in(source))

    context = SafetyContext(
        # THE COMPOSED SENTENCES ARE THE GROUNDING. There is no other source,
        # which is the point: nothing may be said that they do not say.
        grounding_sources=tuple(sentences),
        permitted_numbers=permitted,
        purpose="patient_summary_prose",
    )

    gaps: Tuple[str, ...] = ()
    added: Tuple[str, ...] = ()
    result = None
    calls = 0

    # TWO ROUNDS, FOR THE SAME REASON THE CLINICIAN NARRATIVE HAS THEM. The
    # safety layer retries its own refusals; a fact check failure owns no loop,
    # so without a second round a model that drops one name fails permanently
    # for that report. Both are capped.
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
