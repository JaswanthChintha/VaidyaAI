"""Module 22 corpus -- the content files, assembled.

One module per topic area, so a clinical reviewer opens a file about a subject
rather than scrolling one enormous list. The split is by TOPIC, not by size:

    lab_tests.py              what each laboratory test measures
    reference_information.py  the published bands and cut-offs
    health_conditions.py      one document per canonical condition
    terminology.py            what the words mean (Module 25 reads these)
    profile_context.py        the six patient-profile features
    interpretation.py         how to read a result at all
    lifestyle.py              pre-approved educational guidance (Module 26)

`ALL_DOCUMENTS` is the concatenation, in the order below. THE ORDER IS PART OF
THE CONTRACT: `knowledge_base.DOCUMENT_ORDER` follows it, the Module 21 index
assigns chunk ids in it, and the committed index is therefore reproducible only
if it is stable. Append within a topic; do not reorder to tidy.

Nothing is validated here. Every structural, vocabulary and safety check runs in
`app/data/knowledge_base.py::_self_check()`, at import, over the assembled
corpus -- one place, so a document added to any file below cannot bypass it.
"""

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
