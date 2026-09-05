"""The Module 22 document TYPE and topic vocabulary.

Split out of `knowledge_base.py` for one structural reason: the document
modules in `app/data/knowledge_documents/` must annotate against
`KnowledgeDocument`, and `knowledge_base.py` must import those modules to
assemble the corpus. Putting the type here breaks what would otherwise be an
import cycle, and it means a reviewer opening a content file sees a two-line
import of a data class rather than an import of the whole knowledge base.

Nothing here does any work. The corpus, its accessors and the import-time
safety and vocabulary checks all live in `knowledge_base.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

#: Bumped whenever any document's text, metadata or the topic vocabulary
#: changes. The Module 21 index records the corpus version it was built from,
#: so a stale index is detectable rather than silently wrong.
KNOWLEDGE_BASE_VERSION = "1.0.0"

# --------------------------------------------------------------------------
# Topic vocabulary -- the spec's Module 22 content list, one constant each
# --------------------------------------------------------------------------

TOPIC_LAB_TEST = "laboratory_test"
TOPIC_TERMINOLOGY = "terminology"
TOPIC_REFERENCE = "reference_information"
TOPIC_CONDITION = "health_condition"
TOPIC_INTERPRETATION = "general_interpretation"
TOPIC_EDUCATION = "educational_explanation"
TOPIC_LIFESTYLE = "lifestyle_guidance"

TOPICS: Tuple[str, ...] = (
    TOPIC_LAB_TEST,
    TOPIC_TERMINOLOGY,
    TOPIC_REFERENCE,
    TOPIC_CONDITION,
    TOPIC_INTERPRETATION,
    TOPIC_EDUCATION,
    TOPIC_LIFESTYLE,
)

#: A single review date for the whole corpus. Every document carries it
#: explicitly rather than inheriting it silently, so a document copied out of
#: this file into a report still says when it was last looked at.
LAST_REVIEWED = "2026-08-30"


@dataclass(frozen=True)
class KnowledgeDocument:
    """One reviewable unit of curated medical knowledge.

    Fields exist for the reviewer as much as for the retriever:

    `doc_id`      stable identifier. Module 23 cites it; it must never be
                  reused for different content, because a citation that points
                  at replaced text is worse than no citation.
    `title`       short human-readable name, shown with a retrieved chunk.
    `topic`       one of `TOPICS`.
    `features`    canonical feature names this document explains. Checked
                  against `feature_catalog.FEATURES`.
    `conditions`  canonical condition names. Checked against
                  `conditions.CONDITIONS`.
    `summary`     one or two sentences. Used as the retrieval preview and, for
                  a short document, may be the whole of what an LLM is shown.
    `body`        the patient-education text, in paragraphs separated by blank
                  lines. Paragraph boundaries are the chunk boundaries -- see
                  `app/services/knowledge_index.py` -- so a paragraph should be
                  independently readable.
    `basis`       which guideline or reference the content reflects. REQUIRED.
                  A claim a reader cannot trace does not belong in a corpus
                  that grounds an LLM.
    `keywords`    extra retrieval surface: printed test names, abbreviations
                  and lay synonyms a query may use but the body need not.
    `last_reviewed` ISO date.
    `safety_exemptions` reviewed carve-outs from the safety scanner; see the
                  field comment below. Empty for almost every document.
    """

    doc_id: str
    title: str
    topic: str
    summary: str
    body: str
    basis: str
    features: Tuple[str, ...] = ()
    conditions: Tuple[str, ...] = ()
    keywords: Tuple[str, ...] = ()
    last_reviewed: str = LAST_REVIEWED
    #: REVIEWED exemptions from named safety patterns, as
    #: ``((pattern_name, written_justification), ...)``.
    #:
    #: Only patterns in `knowledge_safety.EXEMPTIBLE_PATTERNS` may appear, a
    #: non-empty justification is REQUIRED, and every other pattern still
    #: applies in full. An exemption is not a way to quiet the scanner: it is a
    #: reviewer's signed statement, surfaced in `knowledge_base_document()` so
    #: a clinical audit sees exactly which documents claimed one, and why.
    safety_exemptions: Tuple[Tuple[str, str], ...] = ()

    @property
    def paragraphs(self) -> List[str]:
        """`body` split on blank lines, whitespace-normalised, blanks dropped."""
        return [
            " ".join(block.split())
            for block in self.body.split("\n\n")
            if block.strip()
        ]

    def searchable_text(self) -> str:
        """Everything a retriever may match on, as one string."""
        return "\n".join(
            (
                self.title,
                " ".join(self.keywords),
                " ".join(self.features),
                " ".join(self.conditions),
                self.summary,
                self.body,
            )
        )


__all__ = [
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
]
