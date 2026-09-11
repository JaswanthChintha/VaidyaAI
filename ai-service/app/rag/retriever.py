"""Module 21 -- the public, framework-independent entry points.

`retrieve(...)` and `build_index(...)` are what Modules 23 and 25 call
IN-PROCESS, exactly as `evaluate_rules`, `predict_all` and `fuse_decisions` are
called today. Nothing here imports FastAPI. `app/api/routes_knowledge.py` is a
thin HTTP wrapper over these functions and holds no logic of its own, so the
HTTP layer can never drift from the in-process one.

--------------------------------------------------------------------------
THE PROCESS-LOCAL CACHE
--------------------------------------------------------------------------
`get_index()` loads the committed artifact once per process and memoises it.
This is a LOAD, not a build: the vectors were computed by
`knowledge/build_index.py` and committed. Loading is reading JSON.

The cache is deliberately not a lazy build. If the artifact is missing or
stale, the caller gets `MissingIndexError` / `StaleIndexError` rather than a
silent rebuild -- a silent rebuild would make "the index is a reviewed,
committed artifact" false in exactly the situation where it matters.
"""

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
    """The process-wide index, loaded once. Thread-safe."""
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
    """Drop the memoised index. For tests and for a deliberate reload."""
    global _INDEX
    with _LOCK:
        _INDEX = None


def build_index(save: bool = False, path: Path = DEFAULT_INDEX_PATH) -> KnowledgeIndex:
    """Build the index from the live corpus, optionally writing the artifact.

    The in-process half of `knowledge/build_index.py`. Exposed so tests and
    Module 23 can build without shelling out, and so the build path and the
    committed path are provably the same code.
    """
    index = KnowledgeIndex.build()
    if save:
        written = save_index(index, path)
        logger.info(
            "knowledge_index_built %s",
            safe_meta(chunks=len(index.chunks), path=str(written)),
        )
    return index


def _anchor_free_text(text: str) -> "tuple[tuple[str, ...], tuple[str, ...]]":
    """Resolve free text to canonical features and conditions, or to nothing.

    Deliberately EXACT, in the same way Module 25 is exact: each word (and each
    adjacent word pair, so "kidney disease" and "blood glucose" resolve) is put
    through the same synonym index Module 5 uses, and through the condition
    vocabulary. Nothing fuzzy, no nearest match, no similarity.

    A phrase that anchors to nothing returns empty, and the caller then returns
    no chunks at all. That is the point: it is better to tell someone their
    question is not covered than to explain a different analyte to them.
    """
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
    """Build the query BOTH entry points retrieve with, anchoring included.

    THIS EXISTS BECAUSE THE ANCHORING WAS ONLY ON ONE OF THEM. `retrieve` did
    it; `retrieve_payload` -- which is what the public
    `POST /api/v1/knowledge/retrieve` endpoint calls -- built its query
    directly and skipped it. So the safety control existed, was tested, was
    documented, and was bypassed by the one path a stranger can reach:

        "what should I take for my thyroid"  -> 5 chunks about triglycerides
        "is my liver enzyme high"            -> 5 chunks about LDL/HDL
        "chest pain"                         -> a chunk about seeking advice

    That is section 6k's D7 defect, which section 6r found still live, and it
    stayed live because a fix applied to one of two duplicated code paths
    looks complete from either end. Both paths now build their query here, so
    the next control added cannot be half-applied the same way.

    Returns `None` when free text anchors to nothing at all -- the caller
    returns no chunks, which is the whole point: better to say a question is
    not covered than to explain a different analyte.
    """
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
    """Retrieve grounding chunks for a finding, free text, or both.

    The spec's worked example is a finding:

        retrieve(conditions=["Diabetes"], features=["hba1c", "blood_glucose"])

    Returns [] when nothing clears `floor`. That is a real answer, not a
    failure: grounding an LLM on a poorly-matched chunk is worse than grounding
    it on nothing, because the model will use whatever it is given.

    Raises `UnknownVocabularyError` if a name is outside the catalogues, rather
    than silently answering the rest of the query.
    """
    # FREE TEXT IS ANCHORED TO THE CATALOGUE BEFORE IT IS TRUSTED.
    #
    # TF-IDF cannot tell a medical question this corpus covers from one it does
    # not. That is measured, not suspected: uncovered terms (TSH, ferritin,
    # WBC, ALT, PSA, CRP) score 0.141-0.271 while covered ones score
    # 0.121-0.27 -- the ranges OVERLAP COMPLETELY, so no similarity floor can
    # separate them. The consequence was confidently wrong grounding:
    #
    #     "my ALT and AST liver enzymes are high"  -> term_ldl_hdl
    #     "C reactive protein CRP"                 -> lab_hemoglobin
    #     "what does a raised HbA1c mean"          -> cond_elevated_hemoglobin
    #
    # The last one is the worst of the three: the query names a feature this
    # corpus DOES cover, and it still retrieved a different analyte as its top
    # chunk. Handing any of these to an LLM as grounding is worse than handing
    # it nothing, because the model will faithfully explain whatever it is given.
    #
    # The findings path does not have this problem -- it retrieves on canonical
    # names, which are exact. So free text is resolved to canonical
    # features/conditions FIRST and then retrieved the reliable way, which is
    # the same principle Module 25 uses for terminology (map exactly, or refuse).
    # A query that anchors to nothing in the catalogue returns NOTHING, rather
    # than the nearest-looking chunk.
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
    """`retrieve`, plus the query echo Module 23 needs to cite what it asked.

    The echo matters for explainability: a reader shown retrieved knowledge
    should be able to see what question produced it, not just the answer.
    """
    query = _anchored_query(conditions, features, text)
    results = (
        []
        if query is None
        else (index or get_index()).search(query, top_k=top_k, floor=floor)
    )
    # The echo describes what was ACTUALLY retrieved on, anchored terms
    # included, so a reader can see that "my thyroid" resolved to nothing and
    # a covered question resolved to the canonical names it was answered
    # with. An echo of the raw text alone would hide the step that matters.
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
        # Stated explicitly so a caller never has to infer "no results" from an
        # empty list, and so the reason is unambiguous in a log or a prompt.
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
