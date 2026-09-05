"""Module 21, stage 1 -- CHUNKING.

Spec section 12: ``Documents -> Chunking -> Embeddings -> Vector Index``.

WHY PARAGRAPHS ARE THE CHUNK UNIT
--------------------------------------------------------------------------
The obvious alternative is a fixed-width sliding window (e.g. 512 characters,
50-character overlap). It is the wrong choice HERE, and the reason is specific
to this corpus rather than general.

The Module 22 documents were authored with one idea per paragraph and an
explicit instruction that each must stand alone (see the reviewer notes in
`app/data/knowledge_documents/lab_tests.py`). That is a semantic boundary a
human put there deliberately. A fixed window ignores it and produces chunks
that begin mid-sentence and straddle two ideas -- which is exactly the chunk
that, retrieved and handed to an LLM, produces a confident sentence built from
half of one claim and half of another.

Fixed windows earn their place on scraped or unstructured text, where no
authored boundary exists to respect. This corpus is neither.

THE TWO-FIELD CHUNK
--------------------------------------------------------------------------
Each chunk carries two texts, and keeping them apart is load-bearing:

    `text`            the paragraph alone. This is what a reader sees and what
                      an LLM is grounded on.
    `retrieval_text`  the paragraph PLUS its document's title, keywords and
                      canonical tags.

A paragraph in the middle of a document often does not repeat what the document
is about -- a paragraph of `ref_hba1c_bands` may say "from 5.7 % up to 6.4 %"
without containing the word "HbA1c" anywhere. Searching the bare paragraph
would never find it for a query about HbA1c. Searching the enriched text finds
it, while the reader still sees only the paragraph.

The two fields are scored SEPARATELY and combined with weights
(`app/rag/embeddings.py`), rather than concatenated into one bag of words. If
they were concatenated, every chunk of a document would inherit an identical
header and score nearly identically, and the retriever would be able to pick the
right document but not the right paragraph within it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

from app.data.knowledge_base import DOCUMENTS
from app.data.knowledge_types import KnowledgeDocument

#: Paragraphs shorter than this are merged into the preceding chunk. A 40-word
#: fragment retrieved on its own rarely carries enough context to ground
#: anything, and it dilutes the index with near-duplicate headers.
MIN_CHUNK_CHARS = 240

#: Hard cap. Above this a chunk is split on sentence boundaries. The corpus is
#: authored well within it; the cap exists so that a future long paragraph
#: degrades predictably rather than producing one enormous chunk that matches
#: every query weakly.
MAX_CHUNK_CHARS = 1400

#: Sentence terminators used when a paragraph must be split.
_SENTENCE_END = (". ", "? ", "! ")


@dataclass(frozen=True)
class Chunk:
    """One retrievable unit, carrying its full provenance.

    Provenance is copied onto the chunk rather than looked up from `doc_id` at
    read time. Module 23 cites a chunk and Module 20's explainability principle
    applies: whatever justified a claim must travel WITH the claim. A retrieved
    chunk that needs a second lookup to say where it came from is one refactor
    away from being cited with no source at all.
    """

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
    """The document-level retrieval surface shared by all of its chunks."""
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
    """Split an over-long paragraph on sentence boundaries, never mid-sentence."""
    if len(paragraph) <= MAX_CHUNK_CHARS:
        return [paragraph]

    pieces: List[str] = []
    remaining = paragraph
    while len(remaining) > MAX_CHUNK_CHARS:
        window = remaining[:MAX_CHUNK_CHARS]
        cut = max((window.rfind(end) for end in _SENTENCE_END), default=-1)
        if cut <= 0:
            # No sentence boundary in range. Splitting mid-sentence would
            # produce exactly the fragment this module exists to avoid, so the
            # oversized piece is kept whole and the cap is treated as advisory.
            break
        pieces.append(remaining[: cut + 1].strip())
        remaining = remaining[cut + 2 :].strip()
    if remaining:
        pieces.append(remaining)
    return pieces


def _merge_short(paragraphs: List[str]) -> List[str]:
    """Fold sub-threshold paragraphs into the preceding one."""
    merged: List[str] = []
    for para in paragraphs:
        if merged and len(para) < MIN_CHUNK_CHARS:
            merged[-1] = f"{merged[-1]} {para}"
        else:
            merged.append(para)
    # A document whose FIRST paragraph is short has nothing to merge backwards
    # into; fold it forwards instead so it is never emitted alone.
    if len(merged) > 1 and len(merged[0]) < MIN_CHUNK_CHARS:
        merged[1] = f"{merged[0]} {merged[1]}"
        merged.pop(0)
    return merged


def chunk_document(doc: KnowledgeDocument) -> List[Chunk]:
    """Split one document into chunks, in document order.

    Deterministic: the same document always yields the same chunks with the
    same ids. `build_index` depends on this -- see `app/rag/index.py`.
    """
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
    """Every chunk of the whole Module 22 corpus, in `DOCUMENT_ORDER`.

    The order is stable because `DOCUMENTS` preserves the declared order of
    `knowledge_documents.ALL_DOCUMENTS`, which that module's docstring pins as
    part of the contract.
    """
    chunks: List[Chunk] = []
    for doc in DOCUMENTS.values():
        chunks.extend(chunk_document(doc))
    return chunks


#: Exposed so the header can be recomputed identically at query time when a
#: caller wants to know what surface a chunk was matched on.
document_header = _header

__all__ = [
    "MAX_CHUNK_CHARS",
    "MIN_CHUNK_CHARS",
    "Chunk",
    "chunk_corpus",
    "chunk_document",
    "document_header",
]
