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

_CACHE: Dict[str, "GlossaryEntry"] = {}
_CACHE_LOCK = threading.Lock()

MAX_PER_REQUEST = 24

_WHITESPACE = re.compile(r"\s+")

_ANY_DIGIT = re.compile(r"\d")

_SPELLED_NUMBER = re.compile(
    r"\b(zero|one|two|three|four|five|six|seven|eight|nine|ten|"
    r"eleven|twelve|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|"
    r"hundred|thousand)\b",
    re.IGNORECASE,
)


def _cache_key(test_name: str) -> str:
    return _WHITESPACE.sub(" ", test_name).strip().lower()


class GlossaryEntry(BaseModel):

    model_config = ConfigDict(frozen=True, extra="forbid")

    test_name: str
    description: Optional[str] = None
    available: bool = False
    notice: Optional[str] = None
    cached: bool = False
    origin: str = "model"
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
            grounding_sources=(),
            permitted_numbers=(),
            require_grounding=False,
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
