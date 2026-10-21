from __future__ import annotations

import json
import re
import threading
from typing import Any, Dict, List, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, Field

from app.core.logging import get_logger, safe_meta
from app.safety.fallback import guarded_generation
from app.safety.validator import SafetyContext

logger = get_logger(__name__)

LAB_NAME_MATCH_VERSION = "1.0.0"

MAX_NAMES = 40

_QUALIFIERS: frozenset = frozenset(
    {
        "free",
        "bound",
        "direct",
        "indirect",
        "fasting",
        "random",
        "postprandial",
        "pp",
        "pre",
        "post",
        "left",
        "right",
    }
)

_CACHE: Dict[str, "NameMatchData"] = {}
_CACHE_LOCK = threading.Lock()

_WORD = re.compile(r"[a-z0-9]+")


class NameGroup(BaseModel):

    model_config = ConfigDict(extra="forbid")

    display_name: str
    names: List[str] = Field(default_factory=list)


class NameMatchData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    groups: List[NameGroup] = Field(default_factory=list)
    requested: int = 0
    proposed: int = 0
    accepted: int = 0
    refused_unknown_name: int = 0
    refused_too_small: int = 0
    refused_overlapping: int = 0
    refused_contrast: int = 0
    skipped_over_limit: int = 0
    version: str = LAB_NAME_MATCH_VERSION
    policy: str = Field(
        default=(
            "The model is given laboratory test NAMES only -- no value, unit, "
            "date, flag, reference range or anything about any patient -- and "
            "asked which of them name the same test. Every group it proposes "
            "is then checked locally: a name that was not sent is dropped, a "
            "name appearing in two groups drops both, a group of fewer than "
            "two names is dropped, and a group whose names contrast free with "
            "total, direct with indirect, or fasting with random is refused. "
            "A join only regroups rows the reader already has; no value is "
            "created and no unit is converted."
        )
    )


SYSTEM_INSTRUCTION = (
    "You are a clinical laboratory vocabulary reference. You are given ONLY a "
    "list of test names as they appear printed on laboratory reports. You say "
    "which of those names refer to the same measurement. You never mention any "
    "patient, any result, any value, any reference range or any diagnosis. You "
    "answer with JSON only."
)


def _prompt(names: Sequence[str]) -> str:
    listing = "\n".join(f"- {name}" for name in names)
    return (
        "Below is a list of laboratory test names, each exactly as printed on "
        "a report. Different laboratories print different names for the same "
        "measurement.\n\n"
        "Say which of these names refer to THE SAME measurement.\n\n"
        f"Names:\n{listing}\n\n"
        "Reply with JSON only, in exactly this form:\n"
        '{"groups": [["name one", "name two"], ["name three", "name four"]]}\n\n'
        "Rules you must follow:\n"
        "- Use the names EXACTLY as given above. Do not reword, expand, "
        "correct or abbreviate them.\n"
        "- Each group must contain two or more names from the list.\n"
        "- A name may appear in AT MOST ONE group.\n"
        "- Group two names only if they are the same measurement, reported "
        "under different wording. An abbreviation and its expansion are the "
        "same measurement; a synonym for the same analyte is the same "
        "measurement.\n"
        "- Do NOT group two names that measure different things, even when "
        "they are closely related. Free and total forms of a hormone are "
        "DIFFERENT. Direct and indirect forms are DIFFERENT. A fasting and a "
        "random sample of the same analyte are DIFFERENT. A count and a "
        "percentage of the same cell are DIFFERENT.\n"
        "- IF YOU ARE NOT SURE, LEAVE THE NAMES OUT. An omitted name is "
        "correct behaviour; a wrong group is not.\n"
        '- If none of the names match, reply {"groups": []}.\n'
        "- Do NOT mention any patient, value, result, range or diagnosis.\n"
        "- Output the JSON object and nothing else."
    )


_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


def _parse(text: str) -> Optional[dict]:
    match = _JSON_OBJECT.search(text or "")
    if match is None:
        return None
    try:
        parsed = json.loads(match.group(0))
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _fold(name: str) -> str:
    return " ".join(_WORD.findall(str(name or "").lower()))


def _words(name: str) -> frozenset:
    return frozenset(_WORD.findall(str(name or "").lower()))


def contrasts(first: str, second: str) -> bool:
    return (_words(first) & _QUALIFIERS) != (_words(second) & _QUALIFIERS)


def _accept(
    raw_groups: Any, names: Sequence[str], data: NameMatchData
) -> List[NameGroup]:
    if not isinstance(raw_groups, list):
        return []

    by_fold = {_fold(name): name for name in names}
    claimed: Dict[str, int] = {}
    candidates: List[List[str]] = []

    for entry in raw_groups:
        if not isinstance(entry, list):
            continue
        data.proposed += 1

        resolved: List[str] = []
        invented = False
        for item in entry:
            if not isinstance(item, str):
                invented = True
                break
            actual = by_fold.get(_fold(item))
            if actual is None:
                invented = True
                break
            resolved.append(actual)
        if invented:
            data.refused_unknown_name += 1
            continue

        unique = list(dict.fromkeys(resolved))
        if len(unique) < 2:
            data.refused_too_small += 1
            continue

        if any(
            contrasts(a, b)
            for i, a in enumerate(unique)
            for b in unique[i + 1 :]
        ):
            data.refused_contrast += 1
            logger.warning(
                "lab_name_match_contrast_refused %s",
                safe_meta(group_size=len(unique)),
            )
            continue

        for name in unique:
            claimed[name] = claimed.get(name, 0) + 1
        candidates.append(unique)

    accepted: List[NameGroup] = []
    for unique in candidates:
        if any(claimed[name] > 1 for name in unique):
            data.refused_overlapping += 1
            continue
        accepted.append(
            NameGroup(
                display_name=max(unique, key=lambda n: (len(n), n)),
                names=unique,
            )
        )

    data.accepted = len(accepted)
    return accepted


def _cache_key(names: Sequence[str]) -> str:
    return "|".join(sorted(_fold(name) for name in names))


def match_names(names: Sequence[str], client: Any) -> NameMatchData:
    cleaned = [str(n).strip() for n in (names or []) if str(n or "").strip()]
    deduped: Dict[str, str] = {}
    for name in cleaned:
        deduped.setdefault(_fold(name), name)
    unique_names = list(deduped.values())

    data = NameMatchData(requested=len(unique_names))
    if len(unique_names) < 2:
        return data

    if len(unique_names) > MAX_NAMES:
        data.skipped_over_limit = len(unique_names) - MAX_NAMES
        unique_names = unique_names[:MAX_NAMES]
        logger.warning(
            "lab_name_match_over_limit %s",
            safe_meta(skipped=data.skipped_over_limit, limit=MAX_NAMES),
        )

    key = _cache_key(unique_names)
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
    if hit is not None:
        return hit.model_copy(deep=True)

    def generate(feedback: Any = None) -> str:
        prompt = _prompt(unique_names)
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
        return data

    parsed = _parse(text)
    if parsed is None:
        logger.warning(
            "lab_name_match_unparsable %s", safe_meta(requested=data.requested)
        )
        return data

    data.groups = _accept(parsed.get("groups"), unique_names, data)

    with _CACHE_LOCK:
        _CACHE[key] = data.model_copy(deep=True)
    return data


def reset_cache() -> None:
    with _CACHE_LOCK:
        _CACHE.clear()
