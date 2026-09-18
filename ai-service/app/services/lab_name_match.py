"""Module 36 -- which of these printed test names are the SAME test.

WHAT THIS IS FOR. `labSeriesService` groups a report's laboratory rows by
`nameKey`, a sorted word set, so `CRP (C-REACTIVE PROTEIN)` and
`C-REACTIVE PROTEIN(CRP)` join as one test. Word-set equality cannot join names
that use DIFFERENT words for one test, and on this account's two real reports
that leaves ten parameters stranded as single readings which are really five
tests measured twice:

    AVERAGE BLOOD GLUCOSE   |  Estimated Average Glucose
    TOTAL WBC COUNT         |  WBC Count
    RBC COUNT               |  T.RBC
    TSH                     |  TSH (Thyroid Stim Hormone)
    NEUTROPHILS             |  Polymorphs

A single reading has no first and no latest, so none of them can carry a trend
at all -- not because anything refused, but because a change needs two numbers.
Joining them is the only way those rows get a direction.

==========================================================================
WHY THIS IS NOT "LETTING THE LLM MATCH MEDICAL DATA"
==========================================================================

`NEUTROPHILS` and `Polymorphs` are the same cell line under two names. That is
clinical knowledge, and the alternatives to asking for it are both worse:
subset matching would make `Free Frimbulator` match `Frimbulator`, and free
versus total hormone are DIFFERENT TESTS; a hand-written synonym table only
ever covers the spellings someone has already seen, and this platform has no
list of known tests anywhere by design.

So the question is narrowed the way Module 27b and Module 35 narrow theirs:

  1. THE PROMPT CONTAINS NAMES AND NOTHING ELSE. No value, no unit, no date,
     no flag, no reference range, no age, no sex, no report. The answer is
     therefore a statement about VOCABULARY -- true for every laboratory that
     prints those words -- and the model is not in a position to know that a
     patient exists, let alone reason about one.

  2. THE MODEL PROPOSES; THIS MODULE DISPOSES. Every group comes back through
     five local gates below. A name the model invented, a name sent twice, a
     group of one, and a group that contrasts `free` with `total` are all
     dropped HERE, by code a reviewer can read, not by trusting the answer.

  3. A JOIN IS ONLY EVER A REGROUPING. It merges two rows the reader already
     has into one series. It creates no value, edits no number and converts no
     unit -- and when the two rows turn out to disagree about units,
     `labSeriesService` blocks the series and draws no line, which is the
     behaviour that already exists for that case.

  4. THE WORST OUTCOME IS NAMED AND GUARDED. A wrong join puts two different
     tests on one chart and could show a trend that never happened. That is
     why `_CONTRASTS` exists, why echo validation is unconditional, and why
     anything the model is unsure about is expected to be left out rather than
     guessed -- the prompt says so explicitly.

  5. NOTHING IS JOINED SILENTLY. Every accepted group is returned with the
     names it merged, so the caller can show a reader that two rows on their
     report were treated as one test, and a reviewer can see what was decided.

WHAT IT DELIBERATELY DOES NOT DO. It does not convert units, it does not pick
which name is "correct" beyond choosing the longest for display, and it does
not decide that two tests are DIFFERENT -- a name left out of every group is
simply not joined, which is exactly what happens today.
"""

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

#: Names accepted in one request. A real report's unjoined tail is a handful of
#: rows; this is a ceiling on the prompt, and going over it is REPORTED rather
#: than truncating in silence -- §6at's lesson, and Module 35 does the same.
MAX_NAMES = 40

#: WORDS THAT CHANGE WHAT IS MEASURED, not merely how it is spelled.
#:
#: THE RULE IS EQUALITY, AND THE FIRST VERSION OF IT WAS TOO WEAK. It was a set
#: of contrast pairs refused only when BOTH names carried a different member --
#: which caught `Free Frimbulator` against `Total Frimbulator` and let
#: `Free T3` against `T3` straight through, because `T3` carries no member at
#: all. Free T3 and total T3 are different tests, and 6au names that exact pair
#: as the reason not to subset-match. Leaving it to the prompt would be a
#: control living in an instruction, which this project has learned twice is
#: not a control.
#:
#: So: the qualifiers present in the two names must be THE SAME SET. One name
#: carrying `free` and the other carrying nothing is a difference, and refused.
#:
#: `total` IS DELIBERATELY ABSENT. It is a clarifier rather than a qualifier --
#: `TOTAL WBC COUNT` and `WBC Count` are one test, as are `Total Cholesterol`
#: and `Cholesterol` -- and it is exactly the join this module was built for.
#: The asymmetry is real: adding `free` selects a different analyte, while
#: adding `total` names the whole of the one already meant. A name carrying
#: `total` against one carrying `free` is still refused, because `free` differs.
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

#: One answer about vocabulary serves every reader, so the cache is keyed on the
#: NAME SET and holds nothing patient-specific by construction.
_CACHE: Dict[str, "NameMatchData"] = {}
_CACHE_LOCK = threading.Lock()

_WORD = re.compile(r"[a-z0-9]+")


class NameGroup(BaseModel):
    """Names the model asserted are one test, after every gate below."""

    model_config = ConfigDict(extra="forbid")

    #: The name shown to the reader. The LONGEST of the group, because a
    #: longer printed name is the more explicit one (`TSH (Thyroid Stim
    #: Hormone)` over `TSH`) and because picking by length is a rule rather
    #: than a judgement.
    display_name: str
    #: Every name merged into it, INCLUDING the display name, as printed.
    names: List[str] = Field(default_factory=list)


class NameMatchData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    groups: List[NameGroup] = Field(default_factory=list)
    requested: int = 0
    proposed: int = 0
    accepted: int = 0
    #: Groups the model proposed and the gates below threw out, by reason.
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
    """The JSON object in the answer, or None. Same tolerance as Module 35."""
    match = _JSON_OBJECT.search(text or "")
    if match is None:
        return None
    try:
        parsed = json.loads(match.group(0))
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _fold(name: str) -> str:
    """A name reduced for COMPARISON ONLY. Never shown and never stored."""
    return " ".join(_WORD.findall(str(name or "").lower()))


def _words(name: str) -> frozenset:
    return frozenset(_WORD.findall(str(name or "").lower()))


def contrasts(first: str, second: str) -> bool:
    """Do these two names qualify the measurement DIFFERENTLY?

    True means refuse the join. The 6au example, enforced in both its shapes:
    `Free Frimbulator` against `Total Frimbulator` AND `Free T3` against `T3`.
    `TOTAL WBC COUNT` against `WBC Count` is allowed, because `total` is not a
    qualifier and neither name carries one.
    """
    return (_words(first) & _QUALIFIERS) != (_words(second) & _QUALIFIERS)


def _accept(
    raw_groups: Any, names: Sequence[str], data: NameMatchData
) -> List[NameGroup]:
    """Every gate, applied to what the model proposed.

    THE COUNTS ARE KEPT PER REASON, because "the model proposed nine groups and
    we took five" is a different fact from "it proposed five", and a stage that
    cannot say which is a stage nobody can tell has started failing.
    """
    if not isinstance(raw_groups, list):
        return []

    by_fold = {_fold(name): name for name in names}
    claimed: Dict[str, int] = {}
    candidates: List[List[str]] = []

    for entry in raw_groups:
        if not isinstance(entry, list):
            continue
        data.proposed += 1

        # ECHO VALIDATION, UNCONDITIONAL. A name the model did not receive is
        # a name it made up, and folding is comparison only -- the name kept
        # is the one the report printed.
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

        # THE CONTRAST GUARD, over every pair in the group.
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

    # A NAME IN TWO GROUPS INVALIDATES BOTH, not just the second one. There is
    # no basis for preferring whichever the model happened to emit first, and
    # putting one test's readings on another test's chart is the worst thing
    # this module can do.
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
    """Group the names that are one test. Never raises; refuses instead.

    An empty result means "nothing was joined", which is exactly the behaviour
    before this module existed -- so a spent quota, an unconfigured key and a
    model that recognised nothing all land on the same safe outcome.
    """
    cleaned = [str(n).strip() for n in (names or []) if str(n or "").strip()]
    # Deduplicated on the FOLDED form so one report's `TSH` and another's `tsh`
    # do not consume two slots, while the printed spelling is what is sent.
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
            # NOTHING IS GROUNDED AND NOTHING SHOULD BE. The answer is a list
            # of names, carries no figure at all, and any number appearing in
            # it would be the model adding something to a name it was told to
            # echo -- which echo validation then throws out.
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
    """Test hook. Never called by the service."""
    with _CACHE_LOCK:
        _CACHE.clear()
