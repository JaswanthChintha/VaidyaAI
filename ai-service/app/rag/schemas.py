"""Request/response contract for the Modules 21-22 endpoints.

Lives in `app/rag/` rather than `app/schemas/` so that Modules 21/22 are one
self-contained, reviewable unit -- the same reason `app/safety/` holds its own
schemas. Shapes match the rest of the service exactly: `{success, data}` on
success and `{success: false, error: {code, message}}` on failure, produced by
the app-level handlers in `app/main.py`.

Pydantic v2 throughout, and STRICT: `extra="forbid"` on every request model.
A caller that misspells `condition` for `conditions` gets a 422 rather than a
silently ignored field and an empty result -- which for a retrieval endpoint is
the worst failure mode available, because an empty result is indistinguishable
from "nothing relevant exists".
"""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.rag.index import DEFAULT_TOP_K, MAX_TOP_K, SIMILARITY_FLOOR


class RetrievalRequest(BaseModel):
    """A retrieval request: a finding, free text, or both.

    The spec's worked example is the finding form:

        {"conditions": ["Diabetes"], "features": ["hba1c", "blood_glucose"]}
    """

    model_config = ConfigDict(extra="forbid")

    conditions: List[str] = Field(
        default_factory=list,
        max_length=32,
        description=(
            "Canonical condition names from app/data/conditions.py. Matched "
            "EXACTLY, including case."
        ),
    )
    features: List[str] = Field(
        default_factory=list,
        max_length=32,
        description=(
            "Canonical feature names from app/data/feature_catalog.py. Matched "
            "EXACTLY."
        ),
    )
    text: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="Free-text question. Secondary to the finding-driven path.",
    )
    top_k: int = Field(
        default=DEFAULT_TOP_K,
        ge=1,
        le=MAX_TOP_K,
        description="Maximum chunks to return.",
    )
    floor: float = Field(
        default=SIMILARITY_FLOOR,
        ge=0.0,
        le=1.0,
        description=(
            "Similarity floor. Below it a chunk is discarded rather than "
            "returned. Overridable for evaluation; the default is the measured "
            "value and should normally be left alone."
        ),
    )

    @model_validator(mode="after")
    def _at_least_one_input(self) -> "RetrievalRequest":
        """Refuse a request that asks for nothing.

        An empty request could defensibly return the whole corpus, an arbitrary
        slice, or nothing. All three are guesses, and this service does not
        guess -- see the same policy in app/schemas/rules.py.
        """
        if not self.conditions and not self.features and not (self.text or "").strip():
            raise ValueError(
                "provide at least one of `conditions`, `features` or `text`. "
                "An empty retrieval request has no defensible answer."
            )
        return self


class RetrievedChunk(BaseModel):
    """One retrieved chunk with its FULL provenance.

    Every field here exists so a claim can be traced. Module 23 cites `doc_id`
    and `title`, shows `basis` as the source of the claim, and can show `score`
    to explain why this text was selected -- Module 20's Input -> Evidence ->
    Decision chain, applied to retrieval.
    """

    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    doc_id: str
    ordinal: int
    title: str
    topic: str
    text: str
    basis: str = Field(description="Guideline or reference the content reflects.")
    features: List[str]
    conditions: List[str]
    last_reviewed: str
    score: float = Field(description="Blended similarity, 0-1.")
    text_score: float = Field(description="Text-similarity component.")
    tag_score: float = Field(description="Exact canonical-tag overlap component.")


class RetrievalQueryEcho(BaseModel):
    """What was actually asked, echoed back."""

    model_config = ConfigDict(extra="forbid")

    conditions: List[str]
    features: List[str]
    text: Optional[str] = None
    source: str = Field(
        description="findings | text | findings_and_text | empty"
    )


class RetrievalData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: RetrievalQueryEcho
    similarity_floor: float
    returned: int
    grounding_available: bool = Field(
        description=(
            "False when nothing cleared the floor. Stated explicitly so a "
            "caller never has to infer it from an empty list."
        )
    )
    results: List[RetrievedChunk]


class RetrievalResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    success: bool = True
    data: RetrievalData


class KnowledgeDocumentSummary(BaseModel):
    """One document, without its body. For browsing the corpus."""

    model_config = ConfigDict(extra="forbid")

    doc_id: str
    title: str
    topic: str
    summary: str
    basis: str
    features: List[str]
    conditions: List[str]
    keywords: List[str]
    last_reviewed: str
    paragraphs: int


__all__ = [
    "KnowledgeDocumentSummary",
    "RetrievalData",
    "RetrievalQueryEcho",
    "RetrievalRequest",
    "RetrievalResponse",
    "RetrievedChunk",
]
