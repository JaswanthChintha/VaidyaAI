"""Module 22 -- the Medical Knowledge Base.

The corpus that Module 21 (RAG) chunks, indexes and retrieves from, and that
Module 23 (LLM explanation) is grounded on. Spec Module 22 lists its scope:

    laboratory tests, medical terminology, reference information, health
    conditions, general interpretation, educational explanations, lifestyle
    guidance -- indexed for semantic retrieval.

--------------------------------------------------------------------------
WHY THE CONTENT IS DATA AND NOT PROSE INSIDE A SERVICE
--------------------------------------------------------------------------
Exactly the reason `clinical_rules.py` holds thresholds and
`recommendation_catalog.py` holds sentences: a clinician has to be able to
AUDIT it. Every document here is a `KnowledgeDocument` with explicit metadata
-- what it is about, which canonical feature or condition it attaches to, what
guideline or reference it reflects, and when it was last reviewed. The
documents themselves live in `app/data/knowledge_documents/`, one file per
topic area, so a reviewer opens one file and reads prose rather than reading a
service.

--------------------------------------------------------------------------
VOCABULARY ALIGNMENT IS LOAD-BEARING, NOT TIDINESS
--------------------------------------------------------------------------
`features` must name entries of `app/data/feature_catalog.py::FEATURES`, and
`conditions` must name entries of `app/data/conditions.py::CONDITIONS`,
BYTE FOR BYTE. This is checked at import.

The reason is the same one `conditions.py` gives for its own existence.
Retrieval is driven by the patient's actual findings: Module 23 will ask for
"Diabetes" plus `hba1c`. A document tagged `"diabetes"` or `"HbA1c"` is not
wrong-looking, it is INVISIBLE -- it silently never joins the finding it exists
to explain, nothing raises, and the product is just quietly worse. So a typo
fails the service at startup instead.

--------------------------------------------------------------------------
SAFETY
--------------------------------------------------------------------------
Every user-facing field of every document is scanned by
`app/data/knowledge_safety.py` at IMPORT time, exactly as
`recommendation_catalog.py` scans its sentences. A violation raises and the
service refuses to start.

This corpus is the strictest place in the platform to get this right, because
grounding INVERTS the usual safety argument. Elsewhere an unsafe string is a
bug in one output. Here an unsafe string is a bug in every output that retrieves
it, and the downstream LLM will reproduce it FAITHFULLY -- repeating its source
is what a grounded model is supposed to do. Module 24 is the last line of
defence, not the first, and it should never be asked to catch something the
corpus should never have contained.

--------------------------------------------------------------------------
NOT IN SCOPE
--------------------------------------------------------------------------
This file holds NO chunking, NO embedding and NO retrieval. Those are Module 21
(`app/services/knowledge_index.py`). Module 22 is the corpus; Module 21 is what
is done to it. Keeping the split means the corpus can be reviewed by a
clinician who never reads a line of retrieval code.
"""

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

#: The corpus, keyed by `doc_id`, in a stable declared order.
DOCUMENTS: Dict[str, KnowledgeDocument] = {}
for _doc in ALL_DOCUMENTS:
    if _doc.doc_id in DOCUMENTS:
        raise ValueError(f"duplicate knowledge document id {_doc.doc_id!r}")
    DOCUMENTS[_doc.doc_id] = _doc

DOCUMENT_ORDER: Tuple[str, ...] = tuple(DOCUMENTS)


# --------------------------------------------------------------------------
# Accessors
# --------------------------------------------------------------------------


class UnknownDocumentError(KeyError):
    """Raised when a doc_id is not in the corpus. Never falls back to text."""


def document(doc_id: str) -> KnowledgeDocument:
    try:
        return DOCUMENTS[doc_id]
    except KeyError:
        raise UnknownDocumentError(
            f"unknown knowledge document {doc_id!r}; the corpus holds "
            f"{len(DOCUMENTS)} documents"
        ) from None


def documents_for_condition(condition: str) -> List[KnowledgeDocument]:
    """Every document tagged with `condition`, in declared order."""
    return [d for d in DOCUMENTS.values() if condition in d.conditions]


def documents_for_feature(feature: str) -> List[KnowledgeDocument]:
    """Every document tagged with canonical feature `feature`."""
    return [d for d in DOCUMENTS.values() if feature in d.features]


def documents_for_topic(topic: str) -> List[KnowledgeDocument]:
    return [d for d in DOCUMENTS.values() if d.topic == topic]


def coverage() -> Dict[str, object]:
    """Which parts of the shared vocabulary the corpus actually covers.

    Reported by the introspection endpoint. `uncovered_*` are always present
    and always lists: an empty list is a positive statement of full coverage,
    whereas an absent key would be indistinguishable from "not checked".
    """
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
    """Machine-readable dump of the whole corpus, for clinical review."""
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
                # Surfaced so a clinical review sees every carve-out without
                # having to read the scanner. Almost always an empty list.
                "safety_exemptions": [
                    {"pattern": n, "justification": j}
                    for n, j in d.safety_exemptions
                ],
            }
            for doc_id, d in DOCUMENTS.items()
        },
    }


# --------------------------------------------------------------------------
# Import-time enforcement
# --------------------------------------------------------------------------

_ID_ALLOWED = set("abcdefghijklmnopqrstuvwxyz0123456789_")

#: Minimum documents. A corpus that has quietly lost most of its content would
#: still pass every structural check below; it would just retrieve nothing
#: useful, which is the failure mode a reader cannot see.
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

    # ---- vocabulary alignment. See the module docstring for why this is fatal.
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

    # ---- reviewed safety exemptions, validated BEFORE they are honoured.
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

    # ---- safety. Every field a reader or an LLM can see.
    assert_safe(doc.title, f"{where} title", exempt)
    assert_safe(doc.summary, f"{where} summary", exempt)
    assert_safe(doc.body, f"{where} body", exempt)
    assert_safe(" ".join(doc.keywords), f"{where} keywords", exempt)

    # A `medication_name` exemption permits the NOUN and nothing else. The
    # hazard the pattern guards is instruction, so an exempted document is
    # re-scanned for a substance name sitting next to administration language.
    # "insulin is the hormone that..." passes; "taking insulin" does not.
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
    # `basis` is reviewer-facing metadata, but it is also returned as retrieval
    # provenance and may therefore reach a prompt, so it is scanned too. This
    # is STRICTER than recommendation_catalog.py, which leaves `basis` unscanned
    # because it never leaves the file. Guideline titles containing banned words
    # are cited by publisher and year rather than by full title.
    assert_safe(doc.basis, f"{where} basis")


def _self_check() -> None:
    """Fail at import if the corpus is inconsistent, unsafe, or too thin."""
    if len(DOCUMENTS) < _MIN_DOCUMENTS:
        raise ValueError(
            f"knowledge base holds only {len(DOCUMENTS)} documents; at least "
            f"{_MIN_DOCUMENTS} are expected. Content has probably been lost."
        )

    for doc in DOCUMENTS.values():
        _check_document(doc)

    # ---- coverage. The spec requires the corpus to cover what the pipeline
    # actually produces. An uncovered feature or condition means a real finding
    # would retrieve nothing, so it fails here rather than at request time.
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

    # ---- the scanner itself must not be vacuous. If a sentence built entirely
    # out of the things it exists to ban does not trip it, the scanner has been
    # broken and every check above it is theatre.
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
