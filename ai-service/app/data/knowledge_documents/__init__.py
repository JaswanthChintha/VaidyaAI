from __future__ import annotations

from typing import Tuple

from app.data.knowledge_documents.health_conditions import CONDITION_DOCUMENTS
from app.data.knowledge_documents.interpretation import INTERPRETATION_DOCUMENTS
from app.data.knowledge_documents.lab_tests import LAB_TEST_DOCUMENTS
from app.data.knowledge_documents.lifestyle import LIFESTYLE_DOCUMENTS
from app.data.knowledge_documents.profile_context import PROFILE_DOCUMENTS
from app.data.knowledge_documents.reference_information import REFERENCE_DOCUMENTS
from app.data.knowledge_documents.terminology import TERMINOLOGY_DOCUMENTS
from app.data.knowledge_types import KnowledgeDocument

ALL_DOCUMENTS: Tuple[KnowledgeDocument, ...] = (
    LAB_TEST_DOCUMENTS
    + REFERENCE_DOCUMENTS
    + CONDITION_DOCUMENTS
    + TERMINOLOGY_DOCUMENTS
    + PROFILE_DOCUMENTS
    + INTERPRETATION_DOCUMENTS
    + LIFESTYLE_DOCUMENTS
)

__all__ = [
    "ALL_DOCUMENTS",
    "CONDITION_DOCUMENTS",
    "INTERPRETATION_DOCUMENTS",
    "LAB_TEST_DOCUMENTS",
    "LIFESTYLE_DOCUMENTS",
    "PROFILE_DOCUMENTS",
    "REFERENCE_DOCUMENTS",
    "TERMINOLOGY_DOCUMENTS",
]
