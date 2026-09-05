"""Module 21 -- Retrieval-Augmented Generation over the Module 22 corpus.

Spec section 12's pipeline, one module per stage:

    Documents            app/data/knowledge_base.py      (Module 22)
        |
        v
    Chunking             app/rag/chunking.py
        |
        v
    Embeddings           app/rag/embeddings.py
        |
        v
    Vector Index         app/rag/index.py
        |                (built by knowledge/build_index.py, committed)
        v
    Query                app/rag/query.py
        |
        v
    Similarity Search    app/rag/index.py::KnowledgeIndex.search
        |
        v
    Relevant Chunks      app/rag/retriever.py::retrieve   <- Modules 23, 25
        |
        v
    LLM Prompt           Module 23 (not built here)

This package lives at `app/rag/` rather than under `app/services/` so that the
RAG layer is one reviewable unit alongside `app/ml/` and `app/safety/`, and so
that Modules 21/22 could be built without touching files another module was
being written into.
"""

from __future__ import annotations

from app.rag.retriever import (
    build_index,
    get_index,
    reset_index_cache,
    retrieve,
    retrieve_payload,
)

__all__ = [
    "build_index",
    "get_index",
    "reset_index_cache",
    "retrieve",
    "retrieve_payload",
]
