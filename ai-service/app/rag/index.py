from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from app.data.knowledge_base import DOCUMENTS, KNOWLEDGE_BASE_VERSION
from app.rag.chunking import Chunk, chunk_corpus
from app.rag.embeddings import (
    Vocabulary,
    combine_field_scores,
    cosine,
    tokenize,
    vectorise,
    vocabulary_coverage,
)
from app.rag.query import Query

INDEX_FORMAT_VERSION = "1"

DEFAULT_INDEX_PATH = (
    Path(__file__).resolve().parents[2] / "knowledge" / "artifacts"
    / "knowledge_index_v1.json"
)

SIMILARITY_FLOOR = 0.12

TAG_WEIGHT = 0.35
TEXT_WEIGHT = 1.0 - TAG_WEIGHT

DOMAIN_COVERAGE_FLOOR = 0.40

DEFAULT_TOP_K = 5
MAX_TOP_K = 25

MAX_CHUNKS_PER_DOCUMENT = 2


class IndexError_(RuntimeError):
    pass


class StaleIndexError(IndexError_):
    pass


class MissingIndexError(IndexError_):
    pass


@dataclass(frozen=True)
class ScoredChunk:

    chunk: Chunk
    score: float
    text_score: float
    tag_score: float

    def to_dict(self) -> Dict[str, object]:
        return {
            "chunk_id": self.chunk.chunk_id,
            "doc_id": self.chunk.doc_id,
            "ordinal": self.chunk.ordinal,
            "title": self.chunk.title,
            "topic": self.chunk.topic,
            "text": self.chunk.text,
            "basis": self.chunk.basis,
            "features": list(self.chunk.features),
            "conditions": list(self.chunk.conditions),
            "last_reviewed": self.chunk.last_reviewed,
            "score": round(self.score, 6),
            "text_score": round(self.text_score, 6),
            "tag_score": round(self.tag_score, 6),
        }


def corpus_fingerprint() -> str:
    digest = hashlib.sha256()
    for doc_id, doc in DOCUMENTS.items():
        digest.update(doc_id.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(doc.title.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(doc.summary.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(doc.body.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(doc.basis.encode("utf-8"))
        digest.update(b"\x00")
        digest.update("|".join(doc.features).encode("utf-8"))
        digest.update(b"\x00")
        digest.update("|".join(doc.conditions).encode("utf-8"))
        digest.update(b"\x00")
        digest.update("|".join(doc.keywords).encode("utf-8"))
        digest.update(b"\xff")
    return digest.hexdigest()


@dataclass
class KnowledgeIndex:

    chunks: List[Chunk]
    body_vectors: List[Dict[str, float]]
    header_vectors: List[Dict[str, float]]
    vocabulary: Vocabulary
    corpus_version: str
    fingerprint: str


    @classmethod
    def build(cls) -> "KnowledgeIndex":
        chunks = chunk_corpus()

        body_tokens = [tokenize(c.text) for c in chunks]
        header_tokens = [tokenize(c.retrieval_text) for c in chunks]

        vocabulary = Vocabulary.learn(body_tokens + header_tokens)

        return cls(
            chunks=chunks,
            body_vectors=[vectorise(t, vocabulary) for t in body_tokens],
            header_vectors=[vectorise(t, vocabulary) for t in header_tokens],
            vocabulary=vocabulary,
            corpus_version=KNOWLEDGE_BASE_VERSION,
            fingerprint=corpus_fingerprint(),
        )


    def search(
        self,
        query: Query,
        *,
        top_k: int = DEFAULT_TOP_K,
        floor: float = SIMILARITY_FLOOR,
        domain_floor: float = DOMAIN_COVERAGE_FLOOR,
        per_document: Optional[int] = MAX_CHUNKS_PER_DOCUMENT,
    ) -> List[ScoredChunk]:
        if query.is_empty:
            return []

        top_k = max(0, min(int(top_k), MAX_TOP_K))
        if top_k == 0:
            return []

        query_tokens = tokenize(query.text)

        if not query.tag_count:
            if vocabulary_coverage(query_tokens, self.vocabulary) < domain_floor:
                return []

        query_vector = vectorise(query_tokens, self.vocabulary)
        wanted_features = frozenset(query.features)
        wanted_conditions = frozenset(query.conditions)
        tag_total = len(wanted_features) + len(wanted_conditions)

        scored: List[ScoredChunk] = []
        for index, chunk in enumerate(self.chunks):
            text_score = combine_field_scores(
                cosine(query_vector, self.body_vectors[index]),
                cosine(query_vector, self.header_vectors[index]),
            )

            if tag_total:
                matched = len(wanted_features.intersection(chunk.features)) + len(
                    wanted_conditions.intersection(chunk.conditions)
                )
                tag_score = matched / tag_total
                blended = TEXT_WEIGHT * text_score + TAG_WEIGHT * tag_score
            else:
                tag_score = 0.0
                blended = text_score

            if blended >= floor:
                scored.append(
                    ScoredChunk(
                        chunk=chunk,
                        score=blended,
                        text_score=text_score,
                        tag_score=tag_score,
                    )
                )

        scored.sort(key=lambda s: (-s.score, s.chunk.chunk_id))

        if per_document is not None and per_document > 0:
            kept: List[ScoredChunk] = []
            used: Dict[str, int] = {}
            for candidate in scored:
                if used.get(candidate.chunk.doc_id, 0) >= per_document:
                    continue
                used[candidate.chunk.doc_id] = used.get(candidate.chunk.doc_id, 0) + 1
                kept.append(candidate)
                if len(kept) >= top_k:
                    break
            return kept

        return scored[:top_k]


    def to_dict(self) -> Dict[str, object]:
        return {
            "index_format_version": INDEX_FORMAT_VERSION,
            "corpus_version": self.corpus_version,
            "fingerprint": self.fingerprint,
            "chunk_count": len(self.chunks),
            "vocabulary_size": len(self.vocabulary.idf),
            "document_count": self.vocabulary.document_count,
            "idf": {t: round(w, 8) for t, w in sorted(self.vocabulary.idf.items())},
            "chunks": [
                {
                    "chunk_id": c.chunk_id,
                    "doc_id": c.doc_id,
                    "ordinal": c.ordinal,
                    "text": c.text,
                    "retrieval_text": c.retrieval_text,
                    "title": c.title,
                    "topic": c.topic,
                    "basis": c.basis,
                    "features": list(c.features),
                    "conditions": list(c.conditions),
                    "last_reviewed": c.last_reviewed,
                    "body_vector": {
                        t: round(w, 8) for t, w in sorted(self.body_vectors[i].items())
                    },
                    "header_vector": {
                        t: round(w, 8)
                        for t, w in sorted(self.header_vectors[i].items())
                    },
                }
                for i, c in enumerate(self.chunks)
            ],
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, object], *, verify: bool = True) -> "KnowledgeIndex":
        found_format = str(payload.get("index_format_version", ""))
        if found_format != INDEX_FORMAT_VERSION:
            raise StaleIndexError(
                f"index format version {found_format!r} but this code writes "
                f"{INDEX_FORMAT_VERSION!r}. Rebuild with "
                "`python knowledge/build_index.py`."
            )

        if verify:
            live = corpus_fingerprint()
            stored = str(payload.get("fingerprint", ""))
            if stored != live:
                raise StaleIndexError(
                    "the committed index was built from a DIFFERENT corpus than "
                    f"the one now loaded (index {stored[:12]}..., corpus "
                    f"{live[:12]}...). Retrieval would serve stale text under "
                    "provenance pointing at the current document. Rebuild with "
                    "`python knowledge/build_index.py`."
                )

        raw_chunks = payload["chunks"]
        chunks: List[Chunk] = []
        body_vectors: List[Dict[str, float]] = []
        header_vectors: List[Dict[str, float]] = []
        for row in raw_chunks:
            chunks.append(
                Chunk(
                    chunk_id=row["chunk_id"],
                    doc_id=row["doc_id"],
                    ordinal=int(row["ordinal"]),
                    text=row["text"],
                    retrieval_text=row["retrieval_text"],
                    title=row["title"],
                    topic=row["topic"],
                    basis=row["basis"],
                    features=tuple(row["features"]),
                    conditions=tuple(row["conditions"]),
                    last_reviewed=row["last_reviewed"],
                )
            )
            body_vectors.append({t: float(w) for t, w in row["body_vector"].items()})
            header_vectors.append(
                {t: float(w) for t, w in row["header_vector"].items()}
            )

        return cls(
            chunks=chunks,
            body_vectors=body_vectors,
            header_vectors=header_vectors,
            vocabulary=Vocabulary(
                idf={t: float(w) for t, w in payload["idf"].items()},
                document_count=int(payload["document_count"]),
            ),
            corpus_version=str(payload.get("corpus_version", "")),
            fingerprint=str(payload.get("fingerprint", "")),
        )

    def stats(self) -> Dict[str, object]:
        by_topic: Dict[str, int] = {}
        for chunk in self.chunks:
            by_topic[chunk.topic] = by_topic.get(chunk.topic, 0) + 1
        lengths = [len(c.text) for c in self.chunks]
        return {
            "index_format_version": INDEX_FORMAT_VERSION,
            "corpus_version": self.corpus_version,
            "fingerprint": self.fingerprint,
            "documents": len({c.doc_id for c in self.chunks}),
            "chunks": len(self.chunks),
            "chunks_by_topic": by_topic,
            "vocabulary_size": len(self.vocabulary.idf),
            "chunk_chars_min": min(lengths) if lengths else 0,
            "chunk_chars_max": max(lengths) if lengths else 0,
            "chunk_chars_mean": round(sum(lengths) / len(lengths), 1) if lengths else 0,
            "similarity_floor": SIMILARITY_FLOOR,
            "domain_coverage_floor": DOMAIN_COVERAGE_FLOOR,
            "tag_weight": TAG_WEIGHT,
            "default_top_k": DEFAULT_TOP_K,
            "max_chunks_per_document": MAX_CHUNKS_PER_DOCUMENT,
        }


def save_index(index: KnowledgeIndex, path: Path = DEFAULT_INDEX_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(index.to_dict(), indent=1, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def load_index(
    path: Path = DEFAULT_INDEX_PATH, *, verify: bool = True
) -> KnowledgeIndex:
    if not path.exists():
        raise MissingIndexError(
            f"no knowledge index at {path}. Build it with "
            "`python knowledge/build_index.py`. The index is a committed "
            "artifact and is never built at import or request time."
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    return KnowledgeIndex.from_dict(payload, verify=verify)


__all__ = [
    "DEFAULT_INDEX_PATH",
    "DOMAIN_COVERAGE_FLOOR",
    "DEFAULT_TOP_K",
    "INDEX_FORMAT_VERSION",
    "MAX_CHUNKS_PER_DOCUMENT",
    "MAX_TOP_K",
    "SIMILARITY_FLOOR",
    "TAG_WEIGHT",
    "TEXT_WEIGHT",
    "KnowledgeIndex",
    "MissingIndexError",
    "ScoredChunk",
    "StaleIndexError",
    "corpus_fingerprint",
    "load_index",
    "save_index",
]
