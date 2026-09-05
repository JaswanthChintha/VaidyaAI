"""Module 26 -- Educational Lifestyle Guidance.

Spec Module 26: safe, general educational guidance associated with certain
findings -- healthy eating, physical activity, hydration, monitoring, and
encouragement to consult a healthcare professional -- and, in the spec's own
words, "PRE-APPROVED EDUCATIONAL GUIDANCE RATHER THAN UNRESTRICTED
AI-GENERATED MEDICAL TREATMENT ADVICE".

==========================================================================
THIS MODULE DOES NOT CALL AN LLM. AT ALL.
==========================================================================

That is a decision, and here is the reasoning, because "we could have gated it
and chose not to" is the part worth writing down.

Module 26 is the module most likely to drift into treatment advice. Everything
it says is of the form "here is something you might do", which is one careless
sentence away from "here is what you should do about your result". The safety
property that has held across this entire project is structural rather than
inspected:

    RECOMMENDATION TEXT HAS NO FREE-TEXT ENTRY POINT.

`recommendation(code)` takes a CODE. There is no `Recommendation(text=...)`
call anywhere in the decision chain, every entry in
`app/data/recommendation_catalog.py` is scanned by the safety scanner at
IMPORT time, and an unsafe addition is an ImportError rather than a bad report.
Adding a generator here would be the first crack in that property, and it would
be the first crack in the module where the property matters most.

The offsetting question is what generation would BUY. The catalogue already
holds the guidance the spec lists, in reviewed wording, and the Module 22
corpus holds twelve `life_*` educational documents behind it. A model rewriting
"a qualified healthcare professional can advise whether repeat testing is
appropriate" produces, at best, the same sentence. So: no generation. If a
future finding needs guidance the catalogue lacks, the fix is a reviewed
catalogue entry, not a prompt.

==========================================================================
WHERE THE CODES COME FROM
==========================================================================

Not from a mapping invented here. `app/data/clinical_rules.py` already records,
per rule, the recommendations that attach to EVERY decision that rule produces
(`always_recommend`) -- as opposed to the band-specific ones, which depend on
how abnormal a value was. This module reads the `always_recommend` sets only.

That distinction is exactly the general/personalised line the spec draws:

* `always_recommend` is general education attached to a topic. "Physical
  activity is discussed alongside glucose findings" is true of the topic, not
  of the reader.
* band recommendations are the risk-tier response to a particular value
  ("results in this range are usually reviewed promptly"). Those belong to the
  decision that produced them and are reported by Modules 17-19. Repeating
  them here, detached from the value that earned them, would be presenting a
  risk-tier response as general advice.

So Module 26 cannot become personalised even by accident: the codes it can
reach do not include the ones that depend on a patient's value.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, Field

from app.core.logging import get_logger, safe_meta
from app.data.clinical_rules import COMPOSITE_RULES, THRESHOLD_RULES
from app.data.conditions import CONDITIONS
from app.data.feature_catalog import FEATURES
from app.data.knowledge_base import documents_for_topic
from app.data.knowledge_types import TOPIC_LIFESTYLE, KnowledgeDocument
from app.data.recommendation_catalog import (
    CATEGORY_CONSULTATION,
    CATEGORY_INFORMATION,
    CATEGORY_LIFESTYLE,
    CATEGORY_MONITORING,
    CATEGORY_RETEST,
    DISCUSS_WITH_CLINICIAN,
    MONITOR_OVER_TIME,
    NOT_A_DIAGNOSIS,
    RECOMMENDATIONS,
    is_known_code,
    recommendation,
)
from app.safety import SafeFallback, SafetyContext, safe_fallback, validate_text

logger = get_logger(__name__)

GUIDANCE_VERSION = "1.0.0"

#: Categories Module 26 may serve. `data_quality` is excluded: "this value was
#: less reliable" is a report caveat, not lifestyle education.
EDUCATIONAL_CATEGORIES: Tuple[str, ...] = (
    CATEGORY_LIFESTYLE,
    CATEGORY_MONITORING,
    CATEGORY_RETEST,
    CATEGORY_CONSULTATION,
    CATEGORY_INFORMATION,
)

#: Attached to every response, in this order, whatever else was selected. The
#: spec lists "monitoring suggestions" and "encouragement to consult healthcare
#: professionals" as Module 26 content in their own right.
ALWAYS_INCLUDED: Tuple[str, ...] = (
    MONITOR_OVER_TIME,
    DISCUSS_WITH_CLINICIAN,
    NOT_A_DIAGNOSIS,
)

GUIDANCE_POLICY = (
    "Every sentence this module returns is read from the reviewed "
    "recommendation catalogue by CODE, or is curated Module 22 educational "
    "text. No language model is called, and there is no parameter through "
    "which a caller can supply wording. The codes reachable here are the "
    "`always_recommend` sets of the clinical rule table -- the guidance "
    "attached to a topic -- and never the band-specific recommendations that "
    "depend on how abnormal a particular value was, so the output is general "
    "education and cannot become personalised treatment advice."
)


# --------------------------------------------------------------------------
# Returned shapes
# --------------------------------------------------------------------------


class GuidanceItem(BaseModel):
    """One approved recommendation, with what caused it to be selected."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    text: str
    category: str
    #: Conditions and features whose rules attach this code. Module 20's
    #: principle: whatever justified showing this travels with it.
    because_of_conditions: Tuple[str, ...] = ()
    because_of_features: Tuple[str, ...] = ()
    always_included: bool = False


class GuidanceReading(BaseModel):
    """One curated educational document offered as further reading."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    doc_id: str
    title: str
    topic: str
    summary: str
    basis: str
    last_reviewed: str
    features: Tuple[str, ...] = ()
    conditions: Tuple[str, ...] = ()


class LifestyleGuidance(BaseModel):
    """Module 26's answer. Entirely catalogue- and corpus-sourced."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    module: int = 26
    version: str = GUIDANCE_VERSION
    generated: bool = Field(
        default=False,
        description=(
            "Always False. Present so a renderer, an auditor and Module 20 can "
            "assert the absence of generation from the payload rather than "
            "from a promise in a docstring."
        ),
    )
    source: str = "recommendation_catalog"
    conditions: Tuple[str, ...] = ()
    features: Tuple[str, ...] = ()
    items: Tuple[GuidanceItem, ...] = ()
    further_reading: Tuple[GuidanceReading, ...] = ()
    #: The concatenated item text, after Module 24 has seen it. None only if
    #: the safety layer refused catalogue text, which would be a defect.
    text: Optional[str] = None
    fallback: Optional[SafeFallback] = None
    unknown_conditions: Tuple[str, ...] = ()
    unknown_features: Tuple[str, ...] = ()
    unknown_codes: Tuple[str, ...] = ()
    safety_verdict: Optional[str] = None


# --------------------------------------------------------------------------
# Code selection -- read out of the rule table, never invented here
# --------------------------------------------------------------------------


def _rule_sources() -> List[Tuple[str, Optional[str], Tuple[str, ...]]]:
    """`(condition, feature, always_recommend)` for every rule in the table."""
    out: List[Tuple[str, Optional[str], Tuple[str, ...]]] = []
    for rule in THRESHOLD_RULES:
        out.append((rule.condition, rule.feature, tuple(rule.always_recommend)))
    for composite in COMPOSITE_RULES:
        out.append((composite.condition, None, tuple(composite.always_recommend)))
    return out


def _educational_codes() -> Tuple[str, ...]:
    """The COMPLETE set of codes this module can ever serve.

    Computed once, at import, from the rule table's `always_recommend` sets
    plus `ALWAYS_INCLUDED`. It is the same set whether a caller asks by
    condition, by feature, or by explicit code -- so the `codes` parameter
    cannot reach anything the derived path could not, and a band-specific
    recommendation such as `SEEK_PROMPT_MEDICAL_ADVICE` (reserved for HIGH-risk
    bands) is unreachable through every entry point rather than just one.
    """
    out: List[str] = []
    for _condition, _feature, codes in _rule_sources():
        for code in codes:
            entry = RECOMMENDATIONS.get(code)
            if entry is not None and entry.category in EDUCATIONAL_CATEGORIES:
                out.append(code)
    out.extend(ALWAYS_INCLUDED)
    return tuple(sorted(set(out)))


def guidance_codes(
    *, conditions: Sequence[str] = (), features: Sequence[str] = ()
) -> Dict[str, Dict[str, Tuple[str, ...]]]:
    """Which educational codes attach to these conditions/features, and why.

    Returns `{code: {"conditions": (...), "features": (...)}}`. Order is the
    rule table's order, which is stable and reviewed, so the same request
    always produces the same guidance.
    """
    wanted_conditions = set(conditions or ())
    wanted_features = set(features or ())
    selected: Dict[str, Dict[str, List[str]]] = {}

    for condition, feature, codes in _rule_sources():
        matched_condition = condition in wanted_conditions
        matched_feature = feature is not None and feature in wanted_features
        if not (matched_condition or matched_feature):
            continue
        for code in codes:
            entry = RECOMMENDATIONS.get(code)
            if entry is None or entry.category not in EDUCATIONAL_CATEGORIES:
                continue
            bucket = selected.setdefault(code, {"conditions": [], "features": []})
            if matched_condition and condition not in bucket["conditions"]:
                bucket["conditions"].append(condition)
            if matched_feature and feature and feature not in bucket["features"]:
                bucket["features"].append(feature)

    return {
        code: {
            "conditions": tuple(why["conditions"]),
            "features": tuple(why["features"]),
        }
        for code, why in selected.items()
    }


def _readings(
    conditions: Sequence[str], features: Sequence[str]
) -> List[KnowledgeDocument]:
    """Curated lifestyle documents tagged with any of these names."""
    wanted_conditions = set(conditions or ())
    wanted_features = set(features or ())
    out: List[KnowledgeDocument] = []
    for doc in documents_for_topic(TOPIC_LIFESTYLE):
        if set(doc.conditions) & wanted_conditions or set(doc.features) & wanted_features:
            out.append(doc)
    return out


# --------------------------------------------------------------------------
# Public entry point -- framework-independent
# --------------------------------------------------------------------------


def lifestyle_guidance(
    *,
    conditions: Sequence[str] = (),
    features: Sequence[str] = (),
    codes: Sequence[str] = (),
) -> LifestyleGuidance:
    """General educational guidance for a set of findings.

    `codes` lets a caller that already holds recommendation codes (Modules
    8/16/17 attach them to every decision) ask for exactly those. Unknown
    codes, unknown conditions and unknown features are REPORTED rather than
    silently dropped: a caller that misspells a condition must not receive a
    plausible-looking answer about nothing.
    """
    unknown_conditions = tuple(c for c in conditions or () if c not in CONDITIONS)
    unknown_features = tuple(f for f in features or () if f not in FEATURES)
    known_conditions = tuple(c for c in conditions or () if c in CONDITIONS)
    known_features = tuple(f for f in features or () if f in FEATURES)

    selected = guidance_codes(conditions=known_conditions, features=known_features)

    unknown_codes: List[str] = []
    for code in codes or ():
        if not is_known_code(code):
            unknown_codes.append(code)
            continue
        if code not in EDUCATIONAL_CODES:
            # A real catalogue code, but not general educational guidance --
            # either the wrong category, or one of the band-specific entries
            # that depend on how abnormal a patient's value was. Refused, so
            # this endpoint cannot be used to fetch arbitrary catalogue text or
            # to dress a risk-tier response as general advice.
            unknown_codes.append(code)
            continue
        selected.setdefault(code, {"conditions": (), "features": ()})

    items: List[GuidanceItem] = []
    for code, why in selected.items():
        if code in ALWAYS_INCLUDED:
            continue
        entry = recommendation(code)
        items.append(
            GuidanceItem(
                code=entry.code,
                text=entry.text,
                category=entry.category,
                because_of_conditions=tuple(why["conditions"]),
                because_of_features=tuple(why["features"]),
            )
        )
    # Category order, then code, so the reply reads consistently.
    items.sort(key=lambda i: (EDUCATIONAL_CATEGORIES.index(i.category), i.code))

    for code in ALWAYS_INCLUDED:
        entry = recommendation(code)
        items.append(
            GuidanceItem(
                code=entry.code,
                text=entry.text,
                category=entry.category,
                always_included=True,
            )
        )

    readings = _readings(known_conditions, known_features)
    text = "\n\n".join(item.text for item in items)

    # Defence in depth. This text is catalogue-sourced and already scanned at
    # import, so a rejection here means the catalogue changed under a broken
    # review -- in which case nothing is shown.
    verdict = validate_text(
        text,
        SafetyContext(
            require_grounding=False,
            require_referral=True,
            check_numeric_grounding=False,
            purpose="module_26_guidance",
        ),
    )
    if verdict.approved_text is None:
        logger.warning(
            "lifestyle_guidance_rejected %s",
            safe_meta(module=26, codes=",".join(sorted(set(verdict.codes)))),
        )
        return LifestyleGuidance(
            conditions=known_conditions,
            features=known_features,
            items=(),
            further_reading=(),
            text=None,
            fallback=safe_fallback(verdict),
            unknown_conditions=unknown_conditions,
            unknown_features=unknown_features,
            unknown_codes=tuple(unknown_codes),
            safety_verdict=verdict.verdict,
        )

    logger.info(
        "lifestyle_guidance %s",
        safe_meta(module=26, items=len(items), readings=len(readings), generated=False),
    )
    return LifestyleGuidance(
        conditions=known_conditions,
        features=known_features,
        items=tuple(items),
        further_reading=tuple(
            GuidanceReading(
                doc_id=d.doc_id,
                title=d.title,
                topic=d.topic,
                summary=d.summary,
                basis=d.basis,
                last_reviewed=d.last_reviewed,
                features=tuple(d.features),
                conditions=tuple(d.conditions),
            )
            for d in readings
        ),
        text=verdict.approved_text,
        fallback=None,
        unknown_conditions=unknown_conditions,
        unknown_features=unknown_features,
        unknown_codes=tuple(unknown_codes),
        safety_verdict=verdict.verdict,
    )


def guidance_policy_document() -> Dict[str, Any]:
    """What Module 26 serves, where it comes from, and what it will not do."""
    return {
        "module": 26,
        "version": GUIDANCE_VERSION,
        "policy": GUIDANCE_POLICY,
        "uses_llm": False,
        "source": "app/data/recommendation_catalog.py + Module 22 corpus",
        "code_source": (
            "the `always_recommend` sets of app/data/clinical_rules.py -- "
            "topic-level guidance only, never the band-specific "
            "recommendations that depend on a patient's value"
        ),
        "educational_categories": list(EDUCATIONAL_CATEGORIES),
        "always_included_codes": list(ALWAYS_INCLUDED),
        "available_codes": list(EDUCATIONAL_CODES),
        "unreachable_codes": sorted(
            set(RECOMMENDATIONS) - set(EDUCATIONAL_CODES)
        ),
    }


#: Computed at import so the reachable set is a constant a reviewer can read,
#: not the outcome of a request.
EDUCATIONAL_CODES: Tuple[str, ...] = _educational_codes()


__all__ = [
    "ALWAYS_INCLUDED",
    "EDUCATIONAL_CATEGORIES",
    "EDUCATIONAL_CODES",
    "GUIDANCE_POLICY",
    "GUIDANCE_VERSION",
    "GuidanceItem",
    "GuidanceReading",
    "LifestyleGuidance",
    "guidance_codes",
    "guidance_policy_document",
    "lifestyle_guidance",
]
