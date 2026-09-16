"""What a raised or lowered test is generally associated with.

Module 34. The reader asked, of the results already marked out of range: say
what these may cause. This answers that question in the only form that can be
asked safely, and the difference is the whole module.

==========================================================================
GENERAL, NEVER ABOUT THIS READER -- AND ENFORCED, NOT PROMISED
==========================================================================

"Your CRP of 38.9 suggests significant inflammation" is one prompt away, and
it is the thing this architecture exists to prevent: a conclusion about a
named person, drawn by a model, with no rule, no threshold and no evidence
chain, rendered beside findings that have all three.

So the question is narrowed until it is safe to ask, exactly as
`parameter_glossary` narrows its own (§6v):

  1. THE PROMPT CONTAINS NO PATIENT DATA. Not the value, not the reference
     range, not the age or sex. It contains a test NAME and a DIRECTION --
     the word "raised" or "lowered", which the rule engine or the laboratory
     already decided and the page already prints. The answer is therefore
     about what such a result is generally associated with, and the model is
     not in a position to interpret anyone.

  2. NO NUMBER MAY APPEAR, enforced here. The shared validator's numeric
     control is INACTIVE for a context with no grounding and no permitted
     numbers -- `active = bool(grounding_sources) or bool(permitted_numbers)`
     -- so a context carrying neither gets no numeric control at all rather
     than a total prohibition. Rather than loosen a shared default, the rule
     is local and stricter: the prompt carried no figures, so any digit in
     the answer was invented.

  3. NO SECOND PERSON. The answer may not contain "you", "your", "yours" or
     "yourself". This is the gate that makes the difference in the module's
     title mechanical rather than aspirational: a sentence that cannot
     address the reader cannot be a statement about the reader's health. It
     is checkable, unlike "is this inference correct", which is not.

  4. NO CERTAINTY ABOUT A PERSON. "means", "indicates", "confirms",
     "diagnoses" and "is caused by" are refused; "associated with", "can be a
     sign of", "commonly seen in" are what a general statement sounds like.

  5. MODULE 24, the same validator every other model text passes.

A refusal yields NO TEXT. There is no placeholder and no partial sentence,
because the page renders nothing at all when there is nothing approved -- the
reader loses a paragraph they never saw, and no absence is created.

==========================================================================
WHAT IS NOT ATTRIBUTED, AND WHY THAT IS SAFE HERE
==========================================================================

The reader asked for no "written by a model" line on these. That is a
legitimate call and it costs less than it would elsewhere, because this text
makes no claim about them: it is the same sentence for every reader with a
raised CRP, and it is true independently of whose report it sits on. The
page's own standing provenance line still covers the section.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, Field

from app.config import Settings, get_settings
from app.core.logging import get_logger, safe_meta
from app.safety import SafetyContext, guarded_generation

logger = get_logger(__name__)

CONTEXT_VERSION = "1.0.0"

DIRECTION_RAISED = "raised"
DIRECTION_LOWERED = "lowered"
DIRECTIONS = (DIRECTION_RAISED, DIRECTION_LOWERED)

#: Cap per report. The free tier is twenty calls a day per model and a real
#: report can carry a dozen out-of-range results; without this one upload
#: spends the day.
MAX_PER_REPORT = 6

#: A MEASUREMENT, NOT MERELY A DIGIT.
#:
#: This was `\d` -- any digit anywhere -- and on a real report it refused three
#: quarters of everything this module produced. The refusals were not
#: measurements: `vitamin B12`, `low T4`, `type 2 diabetes` and "one of several
#: causes" are two analyte names, a condition name and a quantifier. The
#: vocabulary of this domain is full of them.
#:
#: THE PURPOSE IS UNCHANGED and is the one in the module docstring: the prompt
#: carries no figures, so a FIGURE in the answer was invented. What follows is
#: that rule stated precisely instead of approximated by "contains a digit".
#:
#: ALLOWED: a digit bound into a name -- preceded by a letter (`B12`, `T4`,
#: `D3`, `HbA1c`, `COVID-19`) or following the word "type" (`type 2`).
#: A digit after a LETTER-HYPHEN is a name too (`COVID-19`); a range like
#: `10-20` is still refused, because its FIRST digit follows a space.
#:
#: A SEPARATE DECIMAL CHECK STOOD HERE AND WAS REMOVED: every mutation of it
#: survived, because no input reaches it. `12.5` is caught at its FIRST digit,
#: which follows a space; even `B12.5` is caught at the `5`, whose preceding
#: character is a dot. A dead control that reads like a live one is worse than
#: no control -- this codebase has lost a regex and a CSS block that way.
#: REFUSED: every standalone numeral, every decimal, and every digit reached
#: through a comparison. `above 20`, `12.5`, `a level of 7` all still refuse.
_MEASUREMENT_DIGIT = re.compile(r"(?<![A-Za-z0-9])(?<![A-Za-z]-)(?<!type )\d")

#: Spelled numbers exist to stop the digit rule being evaded by writing "below
#: twelve". ONLY REFUSED IN QUANTITATIVE USE -- reached by a comparison, paired
#: with another number, or followed by a unit -- because "one of several
#: causes" is a quantifier and not a value.
_SPELLED = (
    r"(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"twenty|thirty|forty|fifty|hundred|thousand)"
)
_COMPARISON = (
    r"(?:above|below|over|under|exceeds|exceeding|exceed|greater|less|more|"
    r"fewer|at least|at most|between|around|approximately|roughly|nearly|"
    r"up to|of)"
)
_UNIT_WORD = (
    r"(?:grams?|milligrams?|micrograms?|litres?|liters?|decilitres?|"
    r"deciliters?|millimoles?|micromoles?|percent|per cent|units?|"
    r"millimetres?|millimeters?|hours?)"
)
_SPELLED_NUMBER = re.compile(
    _COMPARISON + r"\s+" + _SPELLED + r"\b"
    r"|\b" + _SPELLED + r"\s+" + _SPELLED + r"\b"
    r"|\b" + _SPELLED + r"\s+" + _UNIT_WORD + r"\b",
    re.IGNORECASE,
)

#: THE GATE THAT MAKES "GENERAL" MECHANICAL. A sentence that cannot address
#: the reader cannot be a statement about the reader's health.
_SECOND_PERSON = re.compile(r"\b(you|your|yours|yourself|you're|youre)\b", re.IGNORECASE)

#: Words that turn an association into a finding about a person.
_CERTAINTY = re.compile(
    r"\b(means|indicates|indicating|confirms|confirming|diagnoses|diagnosis|"
    r"diagnostic|proves|demonstrates|shows that|is caused by|you have)\b",
    re.IGNORECASE,
)


class FindingContext(BaseModel):
    """One out-of-range test, put in general context -- or explicitly not."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    test_name: str
    direction: str
    #: None whenever nothing was approved. NEVER a placeholder: the caller
    #: renders nothing, and the reader loses a paragraph they never saw.
    text: Optional[str] = None
    available: bool = False
    #: Which gate stopped it. Names the GATE, never the text.
    refused_by: Optional[str] = None


class FindingContextData(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: str = CONTEXT_VERSION
    entries: Tuple[FindingContext, ...] = ()
    generated_count: int = 0
    withheld_count: int = 0
    skipped_over_limit: int = 0
    policy: str = Field(
        default=(
            "General context for a test already marked out of range. The "
            "prompt carries the test NAME and the DIRECTION only -- no value, "
            "no reference range, no profile answer -- so the answer is about "
            "what such a result is generally associated with and never about "
            "the reader. No number may appear, the text may not address the "
            "reader in the second person, and every answer passes the Module "
            "24 safety validator. Nothing here is a diagnosis and no condition "
            "is derived from it."
        )
    )


SYSTEM_INSTRUCTION = (
    "You explain, for a patient reading their own laboratory report, what a "
    "raised or lowered result for a named test is GENERALLY associated with. "
    "You are given only the test name and the direction. You never address the "
    "reader, never say what their result means, never state that anyone has or "
    "does not have a condition, never give numbers or ranges, and never "
    "mention treatment, management or what should be done next -- not even in "
    "passing, and not even about the condition rather than the reader."
)


def _prompt(test_name: str, direction: str, feedback: Optional[str] = None) -> str:
    prompt = (
        "In at most two sentences of plain language, say what a "
        f"{direction} result for this test is commonly associated with.\n\n"
        f"Test name as printed on the report: {test_name}\n"
        f"Direction: {direction}\n\n"
        "Rules you must follow:\n"
        "- Write in general terms. Do NOT address the reader. Never use the "
        "words 'you' or 'your'.\n"
        "- Say what it is COMMONLY ASSOCIATED WITH or CAN BE A SIGN OF. Never "
        "say what it means, indicates, confirms or is caused by.\n"
        "- Do not state any number, range, threshold or cut-off.\n"
        "- Do not say anyone has, likely has, or does not have a condition.\n"
        "- Do not give advice or recommend a test or next step.\n"
        # NAMING THE WORDS, because "do not recommend treatment" was not
        # enough. Module 24's `UNSAFE_TREATMENT_INSTRUCTION` is a VOCABULARY
        # rule at PROHIBITED severity: it fires on `treat`, `therapy`,
        # `medication`, `drug` and the rest wherever they appear, including in
        # plain description -- "iron deficiency, which is often treated with
        # supplements" is refused on the word alone. The model was obeying the
        # old instruction (it was advising nobody) and being refused anyway,
        # four times out of six on a real report. The prompt now forbids the
        # WORDS, which is what the validator actually measures.
        "- Never use any of these words, in any form and for any reason, "
        "including about a condition rather than about the reader: treat, "
        "treatment, therapy, medication, medicine, drug, cure, regimen, "
        "surgery, injection, infusion, dialysis, chemotherapy, prescribe, "
        "supplement, dose, tablet, capsule, pill.\n"
        "- Name only what the result is associated with, and stop there. Do "
        "not continue into what is done about it.\n"
        "- If the name is not a laboratory test you recognise, reply exactly: "
        "NOT RECOGNISED"
    )
    if feedback:
        prompt += f"\n\nA previous attempt was rejected: {feedback}. Answer again."
    return prompt


def _refuse(test_name: str, direction: str, gate: str) -> FindingContext:
    logger.warning("finding_context_refused %s", safe_meta(gate=gate, module=34))
    return FindingContext(
        test_name=test_name, direction=direction, text=None, refused_by=gate
    )


def _check(text: str) -> Optional[str]:
    """Which local gate refuses this text, or None."""
    if _MEASUREMENT_DIGIT.search(text) or _SPELLED_NUMBER.search(text):
        return "number"
    if _SECOND_PERSON.search(text):
        return "second_person"
    if _CERTAINTY.search(text):
        return "certainty"
    if "NOT RECOGNISED" in text.upper():
        return "not_recognised"
    return None


def _one(test_name: str, direction: str, client: Any) -> FindingContext:
    def generate(feedback: Any = None) -> str:
        return client.generate_text(
            _prompt(test_name, direction, feedback if isinstance(feedback, str) else None),
            system_instruction=SYSTEM_INSTRUCTION,
        )

    result = guarded_generation(
        generate,
        context=SafetyContext(
            # NOTHING grounded, NOTHING permitted numerically: the prompt
            # carried no figures, so any number in the answer was invented.
            # See the module docstring -- the shared control is inactive here
            # and the local one in `_check` is what actually refuses.
            grounding_sources=(),
            permitted_numbers=(),
            require_grounding=False,
            # A fragment. The referral framing lives in the surrounding page.
            require_referral=False,
            purpose="finding_context",
        ),
        attempts=2,
    )

    text = getattr(result, "approved_text", None)
    if not isinstance(text, str) or not text.strip():
        return _refuse(test_name, direction, "safety")

    cleaned = " ".join(text.split())
    gate = _check(cleaned)
    if gate is not None:
        return _refuse(test_name, direction, gate)

    return FindingContext(
        test_name=test_name, direction=direction, text=cleaned, available=True
    )


def _resolve_llm(llm: Any, settings: Optional[Settings]) -> Optional[Any]:
    if llm is not None:
        return llm
    settings = settings or get_settings()
    if not getattr(settings, "gemini_api_key", None):
        return None
    from app.services.gemini_text import GeminiTextClient

    return GeminiTextClient(settings=settings)


def describe_findings(
    findings: Sequence[Dict[str, str]],
    *,
    llm: Any = None,
    settings: Optional[Settings] = None,
) -> FindingContextData:
    """General context for tests already marked out of range.

    `findings` are `{"test_name": ..., "direction": "raised"|"lowered"}`. A
    direction this module does not know is SKIPPED rather than guessed at: the
    prompt turns on that one word, and inventing it would be inventing the
    finding.
    """
    client = _resolve_llm(llm, settings)
    if client is None:
        return FindingContextData()

    entries = []
    generated = withheld = 0
    seen = set()
    over_limit = 0

    for item in findings or []:
        name = (item or {}).get("test_name")
        direction = (item or {}).get("direction")
        if not name or direction not in DIRECTIONS:
            continue
        key = (name.strip().lower(), direction)
        if key in seen:
            continue
        seen.add(key)
        if len(entries) >= MAX_PER_REPORT:
            over_limit += 1
            continue
        entry = _one(name, direction, client)
        entries.append(entry)
        if entry.available:
            generated += 1
        else:
            withheld += 1

    return FindingContextData(
        entries=tuple(entries),
        generated_count=generated,
        withheld_count=withheld,
        skipped_over_limit=over_limit,
    )
