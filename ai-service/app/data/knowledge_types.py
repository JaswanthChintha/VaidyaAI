from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

KNOWLEDGE_BASE_VERSION = "1.0.0"


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

LAST_REVIEWED = "2026-08-30"


@dataclass(frozen=True)
class KnowledgeDocument:

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
    safety_exemptions: Tuple[Tuple[str, str], ...] = ()

    @property
    def paragraphs(self) -> List[str]:
        return [
            " ".join(block.split())
            for block in self.body.split("\n\n")
            if block.strip()
        ]

    def searchable_text(self) -> str:
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
