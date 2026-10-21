from __future__ import annotations

import re
import threading
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from app.core.logging import get_logger, safe_meta
from app.rag.index import (
    DEFAULT_INDEX_PATH,
    DEFAULT_TOP_K,
    SIMILARITY_FLOOR,
    KnowledgeIndex,
    ScoredChunk,
    load_index,
    save_index,
)
from app.rag.query import Query, UnknownVocabularyError, build_query

logger = get_logger(__name__)

_INDEX: Optional[KnowledgeIndex] = None
_LOCK = threading.Lock()


def get_index(path: Path = DEFAULT_INDEX_PATH, *, refresh: bool = False) -> KnowledgeIndex:
    global _INDEX
    if _INDEX is not None and not refresh:
        return _INDEX
    with _LOCK:
        if _INDEX is None or refresh:
            _INDEX = load_index(path)
            logger.info(
                "knowledge_index_loaded %s",
                safe_meta(
                    chunks=len(_INDEX.chunks),
                    corpus_version=_INDEX.corpus_version,
                ),
            )
    return _INDEX


def reset_index_cache() -> None:
    global _INDEX
    with _LOCK:
        _INDEX = None


def build_index(save: bool = False, path: Path = DEFAULT_INDEX_PATH) -> KnowledgeIndex:
    index = KnowledgeIndex.build()
    if save:
        written = save_index(index, path)
        logger.info(
            "knowledge_index_built %s",
            safe_meta(chunks=len(index.chunks), path=str(written)),
        )
    return index


def _anchor_free_text(text: str) -> "tuple[tuple[str, ...], tuple[str, ...]]":
    from app.data.conditions import CONDITIONS
    from app.data.feature_catalog import lookup_test_name

    words = [w for w in re.split(r"[^A-Za-z0-9()/+-]+", text or "") if w]
    candidates = list(words) + [
        f"{a} {b}" for a, b in zip(words, words[1:])
    ]

    features: Dict[str, None] = {}
    conditions: Dict[str, None] = {}
    lowered_conditions = {name.lower(): name for name in CONDITIONS}

    for candidate in candidates:
        match, _ = lookup_test_name(candidate)
        if match is not None and getattr(match, "exact", False):
            features.setdefault(match.feature, None)
        canonical = lowered_conditions.get(candidate.lower())
        if canonical is not None:
            conditions.setdefault(canonical, None)

    return tuple(features), tuple(conditions)


def _anchored_query(
    conditions: Sequence[str],
    features: Sequence[str],
    text: Optional[str],
):
    anchored_features, anchored_conditions = (), ()
    if text and not (features or conditions):
        anchored_features, anchored_conditions = _anchor_free_text(text)
        if not (anchored_features or anchored_conditions):
            return None

    query = build_query(
        conditions=tuple(conditions) + tuple(anchored_conditions),
        features=tuple(features) + tuple(anchored_features),
        text=text,
    )
    return None if query.is_empty else query


def retrieve(
    *,
    conditions: Sequence[str] = (),
    features: Sequence[str] = (),
    text: Optional[str] = None,
    top_k: int = DEFAULT_TOP_K,
    floor: float = SIMILARITY_FLOOR,
    index: Optional[KnowledgeIndex] = None,
) -> List[ScoredChunk]:
    query = _anchored_query(conditions, features, text)
    if query is None:
        return []
    return (index or get_index()).search(query, top_k=top_k, floor=floor)


def retrieve_payload(
    *,
    conditions: Sequence[str] = (),
    features: Sequence[str] = (),
    text: Optional[str] = None,
    top_k: int = DEFAULT_TOP_K,
    floor: float = SIMILARITY_FLOOR,
    index: Optional[KnowledgeIndex] = None,
) -> Dict[str, object]:
    query = _anchored_query(conditions, features, text)
    results = (
        []
        if query is None
        else (index or get_index()).search(query, top_k=top_k, floor=floor)
    )
    echo = (
        {"conditions": [], "features": [], "text": text, "source": "unanchored"}
        if query is None
        else {
            "conditions": list(query.conditions),
            "features": list(query.features),
            "text": query.raw_text,
            "source": query.source,
        }
    )
    return {
        "query": echo,
        "similarity_floor": floor,
        "returned": len(results),
        "results": [r.to_dict() for r in results],
        "grounding_available": bool(results),
    }


__all__ = [
    "UnknownVocabularyError",
    "build_index",
    "get_index",
    "reset_index_cache",
    "retrieve",
    "retrieve_payload",
]
