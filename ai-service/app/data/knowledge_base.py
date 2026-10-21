from __future__ import annotations

from typing import Dict, List, Tuple

from app.data.conditions import CONDITIONS
from app.data.feature_catalog import FEATURES
from app.data.knowledge_safety import (
    CANARY_MIN_MATCHES,
    CANARY_SENTENCE,
    EXEMPTIBLE_PATTERNS,
    UnsafeKnowledgeError,
    assert_safe,
    scan_administration,
    scan_text,
)

from app.data.knowledge_documents import ALL_DOCUMENTS
from app.data.knowledge_types import (
    KNOWLEDGE_BASE_VERSION,
    LAST_REVIEWED,
    TOPICS,
    TOPIC_CONDITION,
    TOPIC_EDUCATION,
    TOPIC_INTERPRETATION,
    TOPIC_LAB_TEST,
    TOPIC_LIFESTYLE,
    TOPIC_REFERENCE,
    TOPIC_TERMINOLOGY,
    KnowledgeDocument,
)

DOCUMENTS: Dict[str, KnowledgeDocument] = {}
for _doc in ALL_DOCUMENTS:
    if _doc.doc_id in DOCUMENTS:
        raise ValueError(f"duplicate knowledge document id {_doc.doc_id!r}")
    DOCUMENTS[_doc.doc_id] = _doc

DOCUMENT_ORDER: Tuple[str, ...] = tuple(DOCUMENTS)


class UnknownDocumentError(KeyError):
    pass


def document(doc_id: str) -> KnowledgeDocument:
    try:
        return DOCUMENTS[doc_id]
    except KeyError:
        raise UnknownDocumentError(
            f"unknown knowledge document {doc_id!r}; the corpus holds "
            f"{len(DOCUMENTS)} documents"
        ) from None


def documents_for_condition(condition: str) -> List[KnowledgeDocument]:
    return [d for d in DOCUMENTS.values() if condition in d.conditions]


def documents_for_feature(feature: str) -> List[KnowledgeDocument]:
    return [d for d in DOCUMENTS.values() if feature in d.features]


def documents_for_topic(topic: str) -> List[KnowledgeDocument]:
    return [d for d in DOCUMENTS.values() if d.topic == topic]


def coverage() -> Dict[str, object]:
    by_feature = {name: len(documents_for_feature(name)) for name in FEATURES}
    by_condition = {name: len(documents_for_condition(name)) for name in CONDITIONS}
    return {
        "documents": len(DOCUMENTS),
        "topics": {t: len(documents_for_topic(t)) for t in TOPICS},
        "features": by_feature,
        "conditions": by_condition,
        "uncovered_features": sorted(n for n, c in by_feature.items() if c == 0),
        "uncovered_conditions": sorted(n for n, c in by_condition.items() if c == 0),
    }


def knowledge_base_document() -> Dict[str, object]:
    return {
        "version": KNOWLEDGE_BASE_VERSION,
        "last_reviewed": LAST_REVIEWED,
        "topics": list(TOPICS),
        "coverage": coverage(),
        "documents": {
            doc_id: {
                "title": d.title,
                "topic": d.topic,
                "features": list(d.features),
                "conditions": list(d.conditions),
                "summary": d.summary,
                "body": d.body,
                "basis": d.basis,
                "keywords": list(d.keywords),
                "last_reviewed": d.last_reviewed,
                "paragraphs": len(d.paragraphs),
                "safety_exemptions": [
                    {"pattern": n, "justification": j}
                    for n, j in d.safety_exemptions
                ],
            }
            for doc_id, d in DOCUMENTS.items()
        },
    }


_ID_ALLOWED = set("abcdefghijklmnopqrstuvwxyz0123456789_")

_MIN_DOCUMENTS = 40


def _check_document(doc: KnowledgeDocument) -> None:
    where = f"knowledge document {doc.doc_id!r}"

    if not doc.doc_id or set(doc.doc_id) - _ID_ALLOWED:
        raise ValueError(
            f"{where}: doc_id must be non-empty lowercase [a-z0-9_]; ids are "
            "cited by Module 23 and appear in retrieval provenance"
        )
    if doc.topic not in TOPICS:
        raise ValueError(f"{where}: unknown topic {doc.topic!r}; expected one of {TOPICS}")
    for name, value in (("title", doc.title), ("summary", doc.summary),
                        ("body", doc.body), ("basis", doc.basis)):
        if not value.strip():
            raise ValueError(f"{where}: {name} is empty")

    for feature in doc.features:
        if feature not in FEATURES:
            raise ValueError(
                f"{where}: feature {feature!r} is not in feature_catalog.FEATURES. "
                "A document tagged with a name outside the catalogue is not "
                "merely untidy -- retrieval by finding will never reach it."
            )
    for condition in doc.conditions:
        if condition not in CONDITIONS:
            raise ValueError(
                f"{where}: condition {condition!r} is not in conditions.CONDITIONS. "
                "Condition strings are matched exactly; a near-miss is invisible."
            )
    if len(set(doc.features)) != len(doc.features):
        raise ValueError(f"{where}: duplicate feature tag")
    if len(set(doc.conditions)) != len(doc.conditions):
        raise ValueError(f"{where}: duplicate condition tag")

    if not doc.paragraphs:
        raise ValueError(f"{where}: body has no paragraphs")
    if not doc.last_reviewed.strip():
        raise ValueError(f"{where}: last_reviewed is empty")

    exempt = tuple(name for name, _ in doc.safety_exemptions)
    for name, justification in doc.safety_exemptions:
        if name not in EXEMPTIBLE_PATTERNS:
            raise ValueError(
                f"{where}: pattern {name!r} may never be exempted. Only "
                f"{EXEMPTIBLE_PATTERNS} are exemptible, because only those have "
                "a legitimate non-clinical sense. Rewrite the document instead."
            )
        if not justification.strip():
            raise ValueError(
                f"{where}: the {name!r} exemption has no written justification. "
                "An unexplained exemption is indistinguishable from someone "
                "silencing the scanner to make an import error go away."
            )
    if len(set(exempt)) != len(exempt):
        raise ValueError(f"{where}: duplicate safety exemption")

    assert_safe(doc.title, f"{where} title", exempt)
    assert_safe(doc.summary, f"{where} summary", exempt)
    assert_safe(doc.body, f"{where} body", exempt)
    assert_safe(" ".join(doc.keywords), f"{where} keywords", exempt)

    if "medication_name" in exempt:
        for field_name, text in (
            ("summary", doc.summary), ("body", doc.body),
            ("keywords", " ".join(doc.keywords)),
        ):
            if scan_administration(text):
                raise UnsafeKnowledgeError(
                    f"{where} {field_name}: holds a `medication_name` exemption "
                    "but places a medication name next to administration "
                    "language. The exemption permits naming a substance that is "
                    "also something the body makes; it never permits telling a "
                    "reader to take one."
                )
    assert_safe(doc.basis, f"{where} basis")


def _self_check() -> None:
    if len(DOCUMENTS) < _MIN_DOCUMENTS:
        raise ValueError(
            f"knowledge base holds only {len(DOCUMENTS)} documents; at least "
            f"{_MIN_DOCUMENTS} are expected. Content has probably been lost."
        )

    for doc in DOCUMENTS.values():
        _check_document(doc)

    gaps = coverage()
    if gaps["uncovered_features"]:
        raise ValueError(
            f"canonical features with no knowledge document: "
            f"{gaps['uncovered_features']}. Every feature the pipeline can "
            "produce must have something to say about it."
        )
    if gaps["uncovered_conditions"]:
        raise ValueError(
            f"canonical conditions with no knowledge document: "
            f"{gaps['uncovered_conditions']}."
        )

    fired = scan_text(CANARY_SENTENCE)
    if len(fired) < CANARY_MIN_MATCHES:
        raise UnsafeKnowledgeError(
            "the knowledge-base safety scanner no longer detects an obviously "
            f"unsafe sentence (fired {len(fired)} of at least "
            f"{CANARY_MIN_MATCHES}: {fired}) -- it has been broken"
        )


_self_check()


__all__ = [
    "DOCUMENTS",
    "DOCUMENT_ORDER",
    "KNOWLEDGE_BASE_VERSION",
    "LAST_REVIEWED",
    "TOPICS",
    "TOPIC_CONDITION",
    "TOPIC_EDUCATION",
    "TOPIC_INTERPRETATION",
    "TOPIC_LAB_TEST",
    "TOPIC_LIFESTYLE",
    "TOPIC_REFERENCE",
    "TOPIC_TERMINOLOGY",
    "KnowledgeDocument",
    "UnknownDocumentError",
    "coverage",
    "document",
    "documents_for_condition",
    "documents_for_feature",
    "documents_for_topic",
    "knowledge_base_document",
]
