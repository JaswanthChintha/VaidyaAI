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

EDUCATIONAL_CATEGORIES: Tuple[str, ...] = (
    CATEGORY_LIFESTYLE,
    CATEGORY_MONITORING,
    CATEGORY_RETEST,
    CATEGORY_CONSULTATION,
    CATEGORY_INFORMATION,
)

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


class GuidanceItem(BaseModel):

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    text: str
    category: str
    because_of_conditions: Tuple[str, ...] = ()
    because_of_features: Tuple[str, ...] = ()
    always_included: bool = False


class GuidanceReading(BaseModel):

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
    text: Optional[str] = None
    fallback: Optional[SafeFallback] = None
    unknown_conditions: Tuple[str, ...] = ()
    unknown_features: Tuple[str, ...] = ()
    unknown_codes: Tuple[str, ...] = ()
    safety_verdict: Optional[str] = None


def _rule_sources() -> List[Tuple[str, Optional[str], Tuple[str, ...]]]:
    out: List[Tuple[str, Optional[str], Tuple[str, ...]]] = []
    for rule in THRESHOLD_RULES:
        out.append((rule.condition, rule.feature, tuple(rule.always_recommend)))
    for composite in COMPOSITE_RULES:
        out.append((composite.condition, None, tuple(composite.always_recommend)))
    return out


def _educational_codes() -> Tuple[str, ...]:
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
    wanted_conditions = set(conditions or ())
    wanted_features = set(features or ())
    out: List[KnowledgeDocument] = []
    for doc in documents_for_topic(TOPIC_LIFESTYLE):
        if set(doc.conditions) & wanted_conditions or set(doc.features) & wanted_features:
            out.append(doc)
    return out


def lifestyle_guidance(
    *,
    conditions: Sequence[str] = (),
    features: Sequence[str] = (),
    codes: Sequence[str] = (),
) -> LifestyleGuidance:
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
