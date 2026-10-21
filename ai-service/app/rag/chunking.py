from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

from app.data.knowledge_base import DOCUMENTS
from app.data.knowledge_types import KnowledgeDocument

MIN_CHUNK_CHARS = 240

MAX_CHUNK_CHARS = 1400

_SENTENCE_END = (". ", "? ", "! ")


@dataclass(frozen=True)
class Chunk:

    chunk_id: str
    doc_id: str
    ordinal: int
    text: str
    retrieval_text: str
    title: str
    topic: str
    basis: str
    features: Tuple[str, ...]
    conditions: Tuple[str, ...]
    last_reviewed: str


def _header(doc: KnowledgeDocument) -> str:
    return " ".join(
        (
            doc.title,
            " ".join(doc.keywords),
            " ".join(doc.features),
            " ".join(doc.conditions),
            doc.topic.replace("_", " "),
            doc.summary,
        )
    )


def _split_long(paragraph: str) -> List[str]:
    if len(paragraph) <= MAX_CHUNK_CHARS:
        return [paragraph]

    pieces: List[str] = []
    remaining = paragraph
    while len(remaining) > MAX_CHUNK_CHARS:
        window = remaining[:MAX_CHUNK_CHARS]
        cut = max((window.rfind(end) for end in _SENTENCE_END), default=-1)
        if cut <= 0:
            break
        pieces.append(remaining[: cut + 1].strip())
        remaining = remaining[cut + 2 :].strip()
    if remaining:
        pieces.append(remaining)
    return pieces


def _merge_short(paragraphs: List[str]) -> List[str]:
    merged: List[str] = []
    for para in paragraphs:
        if merged and len(para) < MIN_CHUNK_CHARS:
            merged[-1] = f"{merged[-1]} {para}"
        else:
            merged.append(para)
    if len(merged) > 1 and len(merged[0]) < MIN_CHUNK_CHARS:
        merged[1] = f"{merged[0]} {merged[1]}"
        merged.pop(0)
    return merged


def chunk_document(doc: KnowledgeDocument) -> List[Chunk]:
    header = _header(doc)

    paragraphs: List[str] = []
    for para in _merge_short(doc.paragraphs):
        paragraphs.extend(_split_long(para))

    return [
        Chunk(
            chunk_id=f"{doc.doc_id}#{ordinal}",
            doc_id=doc.doc_id,
            ordinal=ordinal,
            text=text,
            retrieval_text=f"{header} {text}",
            title=doc.title,
            topic=doc.topic,
            basis=doc.basis,
            features=doc.features,
            conditions=doc.conditions,
            last_reviewed=doc.last_reviewed,
        )
        for ordinal, text in enumerate(paragraphs)
    ]


def chunk_corpus() -> List[Chunk]:
    chunks: List[Chunk] = []
    for doc in DOCUMENTS.values():
        chunks.extend(chunk_document(doc))
    return chunks


document_header = _header

__all__ = [
    "MAX_CHUNK_CHARS",
    "MIN_CHUNK_CHARS",
    "Chunk",
    "chunk_corpus",
    "chunk_document",
    "document_header",
]
