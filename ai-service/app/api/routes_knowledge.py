from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query as QueryParam

from app.core.auth import require_service_key
from app.core.errors import ServiceError
from app.core.logging import get_logger, safe_meta
from app.data.knowledge_base import (
    DOCUMENTS,
    KNOWLEDGE_BASE_VERSION,
    TOPICS,
    coverage,
    document,
    UnknownDocumentError,
)
from app.rag.index import (
    DOMAIN_COVERAGE_FLOOR,
    SIMILARITY_FLOOR,
    TAG_WEIGHT,
    MissingIndexError,
    StaleIndexError,
)
from app.rag.query import UnknownVocabularyError
from app.rag.retriever import get_index, retrieve_payload
from app.rag.schemas import RetrievalRequest, RetrievalResponse

logger = get_logger(__name__)

router = APIRouter(
    prefix="/api/v1/knowledge",
    tags=["knowledge-rag"],
    dependencies=[Depends(require_service_key)],
)


class KnowledgeVocabularyError(ServiceError):

    status_code = 422
    code = "UNKNOWN_VOCABULARY"


class KnowledgeIndexUnavailableError(ServiceError):

    status_code = 503
    code = "KNOWLEDGE_INDEX_UNAVAILABLE"


@router.post(
    "/retrieve",
    response_model=RetrievalResponse,
    summary="Retrieve grounding knowledge for a finding or a question",
)
async def retrieve_knowledge(payload: RetrievalRequest) -> RetrievalResponse:
    try:
        data = retrieve_payload(
            conditions=payload.conditions,
            features=payload.features,
            text=payload.text,
            top_k=payload.top_k,
            floor=payload.floor,
        )
    except UnknownVocabularyError as exc:
        raise KnowledgeVocabularyError(str(exc)) from exc
    except (MissingIndexError, StaleIndexError) as exc:
        logger.error("knowledge_index_unavailable %s", safe_meta(reason=type(exc).__name__))
        raise KnowledgeIndexUnavailableError(str(exc)) from exc

    logger.info(
        "knowledge_retrieved %s",
        safe_meta(returned=data["returned"], source=data["query"]["source"]),
    )
    return RetrievalResponse(success=True, data=data)


@router.get("/index", summary="Index statistics and the retrieval policy")
async def index_stats() -> Dict[str, Any]:
    try:
        stats = get_index().stats()
    except (MissingIndexError, StaleIndexError) as exc:
        raise KnowledgeIndexUnavailableError(str(exc)) from exc

    return {
        "success": True,
        "data": {
            "module": 21,
            "index": stats,
            "policy": {
                "chunking": "one chunk per authored paragraph; short paragraphs "
                "merged, over-long ones split on sentence boundaries",
                "embedding": "deterministic TF-IDF over a two-field chunk "
                "(paragraph body + document header), L2-normalised, cosine",
                "scoring": (
                    f"{1 - TAG_WEIGHT:.2f} x text similarity + {TAG_WEIGHT:.2f} "
                    "x exact canonical-tag overlap"
                ),
                "similarity_floor": SIMILARITY_FLOOR,
                "domain_coverage_floor": DOMAIN_COVERAGE_FLOOR,
                "empty_rather_than_irrelevant": (
                    "a chunk below the similarity floor, and any query below "
                    "the domain-coverage floor, return nothing: grounding an "
                    "LLM on a poorly-matched chunk is worse than grounding it "
                    "on none"
                ),
                "built_by": "knowledge/build_index.py (committed artifact; "
                "never built at import or request time)",
            },
        },
    }


@router.get("/coverage", summary="Which vocabulary the knowledge base covers")
async def knowledge_coverage() -> Dict[str, Any]:
    return {
        "success": True,
        "data": {
            "module": 22,
            "version": KNOWLEDGE_BASE_VERSION,
            "topics": list(TOPICS),
            "coverage": coverage(),
        },
    }


@router.get("/documents", summary="List the knowledge base documents")
async def list_documents(
    topic: Optional[str] = QueryParam(default=None, description="Filter by topic."),
    condition: Optional[str] = QueryParam(default=None),
    feature: Optional[str] = QueryParam(default=None),
) -> Dict[str, Any]:
    docs = list(DOCUMENTS.values())
    if topic:
        docs = [d for d in docs if d.topic == topic]
    if condition:
        docs = [d for d in docs if condition in d.conditions]
    if feature:
        docs = [d for d in docs if feature in d.features]

    return {
        "success": True,
        "data": {
            "total": len(DOCUMENTS),
            "returned": len(docs),
            "filters": {"topic": topic, "condition": condition, "feature": feature},
            "documents": [
                {
                    "doc_id": d.doc_id,
                    "title": d.title,
                    "topic": d.topic,
                    "summary": d.summary,
                    "basis": d.basis,
                    "features": list(d.features),
                    "conditions": list(d.conditions),
                    "keywords": list(d.keywords),
                    "last_reviewed": d.last_reviewed,
                    "paragraphs": len(d.paragraphs),
                }
                for d in docs
            ],
        },
    }


class UnknownKnowledgeDocumentError(ServiceError):
    status_code = 404
    code = "UNKNOWN_DOCUMENT"


@router.get("/documents/{doc_id}", summary="One knowledge document in full")
async def get_document(doc_id: str) -> Dict[str, Any]:
    try:
        doc = document(doc_id)
    except UnknownDocumentError as exc:
        raise UnknownKnowledgeDocumentError(
            f"no knowledge document with id {doc_id!r}"
        ) from exc

    return {
        "success": True,
        "data": {
            "doc_id": doc.doc_id,
            "title": doc.title,
            "topic": doc.topic,
            "summary": doc.summary,
            "body": doc.body,
            "paragraphs": doc.paragraphs,
            "basis": doc.basis,
            "features": list(doc.features),
            "conditions": list(doc.conditions),
            "keywords": list(doc.keywords),
            "last_reviewed": doc.last_reviewed,
            "safety_exemptions": [
                {"pattern": n, "justification": j} for n, j in doc.safety_exemptions
            ],
        },
    }
