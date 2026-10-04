"""Plain-language descriptions of laboratory tests this platform does NOT assess.

WHAT THIS IS FOR. A real report carries far more tests than the fourteen the
pipeline understands -- LDL cholesterol, blood urea, potassium, liver enzymes.
Those are read, listed, and shown with the laboratory's own high/low marking,
but nothing tells the reader what the test even measures. This module asks the
model that one question and nothing else.

==========================================================================
WHY THIS IS NOT "LETTING THE LLM INTERPRET UNKNOWN PARAMETERS"
==========================================================================

The obvious version of this feature -- hand the model a value and a reference
range and ask what it means -- is the thing this architecture exists to
prevent. It would produce a condition with no rule, no threshold, no model and
no evidence chain, rendered beside conditions that have all four and
indistinguishable from them.

So the question is narrowed until it is safe to ask:

  1. THE PROMPT CONTAINS NO PATIENT DATA. Not the value, not the reference
     range, not the laboratory's flag, not the age or sex. It contains a test
     NAME. The answer is therefore about the test, never about the person, and
     the model is not in a position to interpret anything.

  2. NO NUMBER MAY APPEAR IN THE ANSWER AT ALL, and that is enforced HERE.
     An invented reference range is the most plausible and most damaging
     hallucination for this feature, so it gets its own control.

     THE SHARED VALIDATOR DOES NOT COVER THIS CASE, and the obvious assumption
     that it does is wrong. `_check_numeric_grounding` activates only when the
     caller supplies grounding sources or permitted numbers
     (`active = bool(grounding_sources) or bool(permitted_numbers)`), so a
     context carrying neither -- exactly this one -- gets NO numeric control
     rather than a total prohibition. The validator documents that, and Module
     23 never hits it because it always supplies grounding.

     Rather than loosen a shared safety default to suit one caller, the rule
     is applied locally and is stricter than anything the validator offers:
     the prompt forbids every number, so a digit in the answer is a violation
     by construction and the answer is discarded.

  3. EVERY ANSWER PASSES THE SAME SAFETY VALIDATOR as Module 23's explanations.
     A description that asserts a diagnosis, recommends a treatment or states a
     threshold is discarded, not shown.

  4. THE PATIENT'S ACTUAL VALUE IS NEVER GENERATED. It is rendered by the
     client from the extraction, verbatim, next to the laboratory's own
     marking. Fact and description come from different places on purpose.

Because the prompt holds only a test name, the answer is identical for every
patient who ever has that test -- so it is cached by name. That is not only an
optimisation: on a free-tier key with twenty calls a day, a per-report
regeneration of sixty descriptions would be unusable.
"""

from __future__ import annotations

import re
import threading
from typing import Any, Dict, List, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, Field

from app.core.logging import get_logger, safe_meta
from app.safety.fallback import guarded_generation
from app.safety.validator import SafetyContext

logger = get_logger(__name__)

GLOSSARY_VERSION = "1.0.0"

#: A description is about a TEST, not a patient, so one answer serves everyone.
#: Process-local and unbounded-by-design: the key space is the set of test names
#: a laboratory can print, which is small and slow-moving.
_CACHE: Dict[str, "GlossaryEntry"] = {}
_CACHE_LOCK = threading.Lock()

#: Hard ceiling per request.
#:
#: RAISED FROM 8 ON THE READER'S INSTRUCTION: every test on the report is to
#: be described, not only the ones the laboratory marked abnormal. A real
#: report carries around twenty unassessed tests, and a ceiling below that
#: silently describes some of them and not others -- which is worse than the
#: old behaviour, because the rule deciding WHICH would be "whatever came
#: first in the extraction".
#:
#: THE CEILING IS STILL HERE, AND STILL MATTERS. The free tier is twenty calls
#: a day per model, so this is the one thing standing between a sixty-parameter
#: report and a spent day. What makes the higher number affordable is the cache
#: below: it is keyed on the NORMALISED TEST NAME and holds no patient data, so
#: "PCV" is described once for this process and every later report reuses it.
#: A cache hit does not consume the budget.
MAX_PER_REQUEST = 24

_WHITESPACE = re.compile(r"\s+")

#: Any digit at all. See point 2 of the module docstring: the prompt forbids
#: every number, so one appearing in the answer means the model ignored the
#: instruction -- and an invented reference range is precisely the failure this
#: feature must not have.
_ANY_DIGIT = re.compile(r"\d")

#: Spelled-out numbers, which sidestep a digit check.
#:
#: WORD BOUNDARIES ARE LOAD-BEARING HERE, IN BOTH DIRECTIONS. Without them
#: "one" matches inside "bone" and "hormone", and a perfectly good description
#: of vitamin D or a thyroid test would be thrown away as if it had invented a
#: figure. An earlier revision of this file lost the boundaries to a shell
#: escaping accident and compiled them as literal backspace characters, which
#: made the pattern match nothing at all -- the control was dead and the tests
#: that were supposed to prove it worked were reading a regex that could never
#: fire. Both failures are silent, which is why this list is asserted in tests
#: against known-good and known-bad strings rather than trusted by inspection.
_SPELLED_NUMBER = re.compile(
    r"\b(zero|one|two|three|four|five|six|seven|eight|nine|ten|"
    r"eleven|twelve|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|"
    r"hundred|thousand)\b",
    re.IGNORECASE,
)


def _cache_key(test_name: str) -> str:
    return _WHITESPACE.sub(" ", test_name).strip().lower()


class GlossaryEntry(BaseModel):
    """One test, described -- or explicitly not described."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    test_name: str
    #: None whenever the model did not answer or the safety validator refused.
    #: NEVER a placeholder: a caller must be able to tell silence from content.
    description: Optional[str] = None
    available: bool = False
    #: Why there is no description, when there is none.
    notice: Optional[str] = None
    cached: bool = False
    #: `model` -- written by the language model from the test name.
    #: `reviewed` -- the summary of a reviewed knowledge document, word for
    #: word; no model was asked. See `reviewed_entry`.
    origin: str = "model"
    #: The knowledge document a `reviewed` description was taken from.
    source_doc: Optional[str] = None


ORIGIN_MODEL = "model"
ORIGIN_REVIEWED = "reviewed"


class GlossaryData(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: str = GLOSSARY_VERSION
    entries: Tuple[GlossaryEntry, ...] = ()
    generated_count: int = 0
    cached_count: int = 0
    withheld_count: int = 0
    skipped_over_limit: int = 0
    reviewed_count: int = 0
    policy: str = Field(
        default=(
            "Descriptions answer 'what does this test measure' from the test "
            "NAME alone. No patient value, reference range or flag is sent to "
            "the model, no number is permitted in the answer, and every answer "
            "passes the Module 24 safety validator. These tests are NOT "
            "assessed by this platform and no condition is derived from them."
        )
    )


SYSTEM_INSTRUCTION = (
    "You describe what a laboratory test measures, for a patient reading their "
    "own report. You are given ONLY the name of the test. You never interpret "
    "a result, never state or imply that anyone has or does not have a "
    "condition, never give reference ranges or numeric thresholds, and never "
    "recommend treatment. If you do not recognise the test name, say so plainly."
)


def _prompt(test_name: str) -> str:
    return (
        "Describe, in at most two sentences and in plain language for a "
        "patient, what this laboratory test measures and which part of the "
        "body or which process it relates to.\n\n"
        f"Test name as printed on the report: {test_name}\n\n"
        "Rules you must follow:\n"
        "- Do not state any number, range, threshold or cut-off.\n"
        "- Do not say whether a result would be good, bad, high or low.\n"
        "- Do not name a condition as present, likely or absent.\n"
        "- Do not give advice.\n"
        "- If the name is not a laboratory test you recognise, reply exactly: "
        "NOT RECOGNISED"
    )


def describe_parameters(
    test_names: Sequence[str],
    client: Any,
    *,
    max_calls: int = MAX_PER_REQUEST,
) -> GlossaryData:
    """Describe each test name, using the cache and the safety validator.

    `client` is a Module 23 text client (`generate_text`). It is injected so
    this module has no transport of its own and the caller controls the model.
    """
    entries: List[GlossaryEntry] = []
    generated = cached = withheld = reviewed = 0
    calls_left = max(0, int(max_calls))
    skipped = 0

    seen: set = set()
    for raw_name in test_names:
        if not isinstance(raw_name, str) or not raw_name.strip():
            continue
        key = _cache_key(raw_name)
        if key in seen:
            continue
        seen.add(key)

        # A REVIEWED DESCRIPTION BEATS A GENERATED ONE, and costs no call.
        curated = reviewed_entry(raw_name)
        if curated is not None:
            entries.append(curated)
            reviewed += 1
            continue

        with _CACHE_LOCK:
            hit = _CACHE.get(key)
        if hit is not None:
            entries.append(hit.model_copy(update={"cached": True}))
            cached += 1
            continue

        if calls_left <= 0:
            skipped += 1
            continue
        calls_left -= 1

        entry = _describe_one(raw_name, client)
        with _CACHE_LOCK:
            # Only a real answer is cached. Caching a failure would make one
            # bad minute permanent for that test name.
            if entry.available:
                _CACHE[key] = entry
        entries.append(entry)
        if entry.available:
            generated += 1
        else:
            withheld += 1

    logger.info(
        "parameter_glossary %s",
        safe_meta(
            requested=len(seen),
            generated=generated,
            cached=cached,
            withheld=withheld,
            skipped_over_limit=skipped,
            reviewed=reviewed,
        ),
    )
    return GlossaryData(
        entries=tuple(entries),
        generated_count=generated,
        cached_count=cached,
        withheld_count=withheld,
        skipped_over_limit=skipped,
        reviewed_count=reviewed,
    )


def reviewed_entry(test_name: str) -> Optional[GlossaryEntry]:
    """The reviewed description for this printed test name, or None.

    Only for a name that maps, by the term explainer's EXACT alias table, onto
    ONE reviewed document and NO catalogue feature -- i.e. a test this
    platform does not assess but has reviewed text about (today: ALT/SGPT and
    AST/SGOT). An assessed test never reaches this module, and a near-miss
    spelling is not a match: it falls through to the model as before.

    The document's summary is used word for word and held to the same rule as
    a generated description -- no number of any kind -- so a later edit to
    the summary cannot slip a threshold onto the dashboard.
    """
    # Imported here: the terminology service imports the explanation stack,
    # which this module must not pull in at import time.
    from app.data.feature_catalog import normalize_test_name
    from app.data.knowledge_base import DOCUMENTS
    from app.services.terminology import TERM_ALIASES

    target = TERM_ALIASES.get(normalize_test_name(test_name or ""))
    if target is None or target.feature is not None or len(target.doc_ids) != 1:
        return None
    doc = DOCUMENTS.get(target.doc_ids[0])
    if doc is None:
        return None
    text = " ".join(doc.summary.split())
    if not text or _ANY_DIGIT.search(text) or _SPELLED_NUMBER.search(text):
        logger.warning(
            "parameter_glossary_reviewed_summary_refused %s",
            safe_meta(doc_id=doc.doc_id),
        )
        return None
    return GlossaryEntry(
        test_name=test_name,
        description=text,
        available=True,
        origin=ORIGIN_REVIEWED,
        source_doc=doc.doc_id,
    )


def _describe_one(test_name: str, client: Any) -> GlossaryEntry:
    def generate(feedback: Any = None) -> str:
        prompt = _prompt(test_name)
        if feedback is not None:
            prompt += (
                "\n\nA previous attempt was rejected by a safety check. "
                "Answer again, following the rules above exactly."
            )
        return client.generate_text(prompt, system_instruction=SYSTEM_INSTRUCTION)

    result = guarded_generation(
        generate,
        context=SafetyContext(
            # NOTHING is grounded and NOTHING is permitted numerically: the
            # prompt carried no figures, so any number in the answer was
            # invented and must be refused.
            grounding_sources=(),
            permitted_numbers=(),
            require_grounding=False,
            # This is a fragment. The referral framing lives in the surrounding
            # document, which states plainly that these tests were not assessed
            # and should be taken to a clinician.
            require_referral=False,
        ),
        attempts=2,
    )

    text = getattr(result, "approved_text", None)
    if not isinstance(text, str) or not text.strip():
        return GlossaryEntry(
            test_name=test_name,
            description=None,
            available=False,
            notice=(
                "No description could be prepared for this test. The value "
                "shown for it comes from your report and is unaffected."
            ),
        )

    cleaned = text.strip()

    # THE LOCAL NUMERIC CONTROL. The shared validator's numeric grounding is
    # inactive for a context with no grounding and no permitted numbers, so it
    # cannot catch this; see the module docstring.
    if _ANY_DIGIT.search(cleaned) or _SPELLED_NUMBER.search(cleaned):
        logger.warning(
            "parameter_glossary_number_refused %s",
            safe_meta(test_name_length=len(test_name)),
        )
        return GlossaryEntry(
            test_name=test_name,
            description=None,
            available=False,
            notice=(
                "A description was produced but contained a number, which is "
                "not permitted here, so it was discarded. The value shown for "
                "this test comes from your report and is unaffected."
            ),
        )

    if "NOT RECOGNISED" in cleaned.upper():
        return GlossaryEntry(
            test_name=test_name,
            description=None,
            available=False,
            notice="This test was not recognised, so no description is offered.",
        )

    return GlossaryEntry(
        test_name=test_name, description=cleaned, available=True
    )


def reset_cache() -> None:
    """Test hook. Never called by the service."""
    with _CACHE_LOCK:
        _CACHE.clear()


__all__ = [
    "GLOSSARY_VERSION",
    "MAX_PER_REQUEST",
    "ORIGIN_MODEL",
    "ORIGIN_REVIEWED",
    "GlossaryData",
    "GlossaryEntry",
    "describe_parameters",
    "reset_cache",
    "reviewed_entry",
]
