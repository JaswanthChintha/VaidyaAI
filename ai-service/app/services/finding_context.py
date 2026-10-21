from __future__ import annotations

import re
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import wait as wait_for
from typing import Any, Dict, List, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, Field

from app.config import Settings, get_settings
from app.core.logging import get_logger, safe_meta
from app.safety import SafetyContext, guarded_generation

logger = get_logger(__name__)

CONTEXT_VERSION = "1.0.0"

DIRECTION_RAISED = "raised"
DIRECTION_LOWERED = "lowered"
DIRECTIONS = (DIRECTION_RAISED, DIRECTION_LOWERED)

_CACHE: Dict[Tuple[str, str], "FindingContext"] = {}
_CACHE_LOCK = threading.Lock()

_INFLIGHT: Dict[Tuple[str, str], "Future[FindingContext]"] = {}

_EXECUTORS: Dict[int, ThreadPoolExecutor] = {}

REFUSED_IN_PROGRESS = "in_progress"

MAX_PER_REPORT = 16

_MEASUREMENT_DIGIT = re.compile(r"(?<![A-Za-z0-9])(?<![A-Za-z]-)(?<!type )\d")

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

_SECOND_PERSON = re.compile(r"\b(you|your|yours|yourself|you're|youre)\b", re.IGNORECASE)

_CERTAINTY = re.compile(
    r"\b(?:"
    r"mean(?!\s+(?:corpuscular|cell|platelet|arterial))s?|meant|"
    r"indicate[sd]?|indicating|"
    r"confirm(?:s|ed)?|confirming|"
    r"diagnose[sd]?|diagnosing|diagnosis|diagnostic|"
    r"prove[sdn]?|proving|"
    r"demonstrate[sd]?|demonstrating|"
    r"shows? that|showed that|"
    r"is caused by|are caused by|"
    r"you have"
    r")\b",
    re.IGNORECASE,
)


_WHITESPACE = re.compile(r"\s+")


def _cache_key(test_name: str, direction: str) -> Tuple[str, str]:
    return (_WHITESPACE.sub(" ", test_name).strip().lower(), direction)


class FindingContext(BaseModel):

    model_config = ConfigDict(frozen=True, extra="forbid")

    test_name: str
    direction: str
    text: Optional[str] = None
    available: bool = False
    refused_by: Optional[str] = None
    cached: bool = False


class FindingContextData(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: str = CONTEXT_VERSION
    entries: Tuple[FindingContext, ...] = ()
    generated_count: int = 0
    cached_count: int = 0
    withheld_count: int = 0
    in_progress_count: int = 0
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
        "- Say what it is COMMONLY ASSOCIATED WITH or CAN BE A SIGN OF.\n"
        "- Never use any of these words, in any form -- including after a "
        "plural subject: mean, means, indicate, indicates, confirm, confirms, "
        "diagnose, diagnoses, diagnosis, prove, proves, demonstrate, "
        "demonstrates, 'shows that', 'is caused by'.\n"
        "- Do not state any number, range, threshold or cut-off.\n"
        "- Do not say anyone has, likely has, or does not have a condition.\n"
        "- Do not give advice or recommend a test or next step.\n"
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


_NAMED_TOKEN = re.compile(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*")


def _without_test_name_digits(text: str, test_name: str) -> str:
    tokens = [
        token
        for token in _NAMED_TOKEN.findall(test_name or "")
        if any(character.isdigit() for character in token)
    ]
    for token in tokens:
        text = re.sub(
            r"(?<![A-Za-z0-9])" + re.escape(token) + r"(?![A-Za-z0-9])",
            " ",
            text,
            flags=re.IGNORECASE,
        )
    return text


def _check(text: str, test_name: str = "") -> Optional[str]:
    text = _without_test_name_digits(text, test_name)
    if _MEASUREMENT_DIGIT.search(text) or _SPELLED_NUMBER.search(text):
        return "number"
    if _SECOND_PERSON.search(text):
        return "second_person"
    if _CERTAINTY.search(text):
        return "certainty"
    if "NOT RECOGNISED" in text.upper():
        return "not_recognised"
    return None


REFUSED_MODEL_UNAVAILABLE = "model_unavailable"


def _one(test_name: str, direction: str, client: Any) -> FindingContext:
    outcomes: List[bool] = []

    def generate(feedback: Any = None) -> str:
        try:
            produced = client.generate_text(
                _prompt(test_name, direction, feedback if isinstance(feedback, str) else None),
                system_instruction=SYSTEM_INSTRUCTION,
            )
        except Exception:
            outcomes.append(True)
            raise
        outcomes.append(False)
        return produced

    result = guarded_generation(
        generate,
        context=SafetyContext(
            grounding_sources=(),
            permitted_numbers=(),
            require_grounding=False,
            require_referral=False,
            purpose="finding_context",
        ),
        attempts=2,
    )

    text = getattr(result, "approved_text", None)
    if not isinstance(text, str) or not text.strip():
        if outcomes and all(outcomes):
            return _refuse(test_name, direction, REFUSED_MODEL_UNAVAILABLE)
        return _refuse(test_name, direction, "safety")

    cleaned = " ".join(text.split())
    gate = _check(cleaned, test_name)
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
    settings = settings or get_settings()
    client = _resolve_llm(llm, settings)
    if client is None:
        return FindingContextData()

    started = time.monotonic()
    deadline = max(0.0, float(settings.finding_context_deadline_seconds))
    executor = _executor(max(1, int(settings.finding_context_concurrency)))

    plan: List[Tuple[str, Tuple[str, str], Optional[FindingContext], Optional[Future], bool]] = []
    seen = set()
    over_limit = 0
    calls_left = MAX_PER_REPORT

    for item in findings or []:
        name = (item or {}).get("test_name")
        direction = (item or {}).get("direction")
        if not name or direction not in DIRECTIONS:
            continue
        key = _cache_key(name, direction)
        if key in seen:
            continue
        seen.add(key)

        with _CACHE_LOCK:
            hit = _CACHE.get(key)
            running = _INFLIGHT.get(key) if hit is None else None
            if hit is None and running is None and calls_left > 0:
                calls_left -= 1
                running = executor.submit(_job, key, name, direction, client)
                _INFLIGHT[key] = running
                plan.append((name, key, None, running, True))
                continue
        if hit is not None:
            plan.append((name, key, hit, None, False))
        elif running is not None:
            plan.append((name, key, None, running, False))
        else:
            over_limit += 1

    jobs = [job for (_, _, _, job, _) in plan if job is not None]
    if jobs:
        wait_for(jobs, timeout=max(0.0, deadline - (time.monotonic() - started)))

    entries: List[FindingContext] = []
    generated = cached = withheld = in_progress = 0
    for name, key, hit, job, mine in plan:
        if hit is not None:
            entries.append(hit.model_copy(update={"test_name": name, "cached": True}))
            cached += 1
            continue
        if job is None or not job.done():
            entries.append(
                FindingContext(
                    test_name=name,
                    direction=key[1],
                    text=None,
                    refused_by=REFUSED_IN_PROGRESS,
                )
            )
            in_progress += 1
            continue
        try:
            entry = job.result()
        except Exception:
            entry = FindingContext(
                test_name=name, direction=key[1], text=None, refused_by=REFUSED_MODEL_UNAVAILABLE
            )
        entry = entry.model_copy(update={"test_name": name, "cached": not mine})
        entries.append(entry)
        if not entry.available:
            withheld += 1
        elif mine:
            generated += 1
        else:
            cached += 1

    logger.info(
        "finding_context %s",
        safe_meta(
            requested=len(seen),
            generated=generated,
            cached=cached,
            withheld=withheld,
            in_progress=in_progress,
            skipped_over_limit=over_limit,
            ceiling=MAX_PER_REPORT,
        ),
    )
    return FindingContextData(
        entries=tuple(entries),
        generated_count=generated,
        cached_count=cached,
        withheld_count=withheld,
        in_progress_count=in_progress,
        skipped_over_limit=over_limit,
    )


def _executor(workers: int) -> ThreadPoolExecutor:
    with _CACHE_LOCK:
        pool = _EXECUTORS.get(workers)
        if pool is None:
            pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="finding-context")
            _EXECUTORS[workers] = pool
        return pool


def _job(key: Tuple[str, str], name: str, direction: str, client: Any) -> FindingContext:
    try:
        entry = _one(name, direction, client)
        if entry.available:
            with _CACHE_LOCK:
                _CACHE[key] = entry
        return entry
    finally:
        with _CACHE_LOCK:
            _INFLIGHT.pop(key, None)


def reset_cache() -> None:
    with _CACHE_LOCK:
        _CACHE.clear()
        _INFLIGHT.clear()
