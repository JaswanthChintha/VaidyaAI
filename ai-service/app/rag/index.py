"""Module 21, stages 3 and 5 -- VECTOR INDEX and SIMILARITY SEARCH.

Spec section 12: ``Embeddings -> Vector Index / FAISS -> Query -> Similarity
Search -> Relevant Medical Chunks``.

--------------------------------------------------------------------------
THE INDEX IS BUILT BY A SCRIPT, NEVER AT IMPORT OR REQUEST TIME
--------------------------------------------------------------------------
This follows the `ml/` pattern exactly, for the same reasons `app/ml/` gives:
building at import makes startup time depend on corpus size and makes every
process do identical work; building per request is worse again. More
importantly, a committed artifact is REVIEWABLE and REPRODUCIBLE -- the index
that ships is the index that was checked, and `knowledge/build_index.py` can
regenerate it byte-for-byte.

    knowledge/build_index.py   ->  knowledge/artifacts/knowledge_index_v1.json

The artifact is JSON rather than a pickle or a binary blob. It is a data file
describing a curated medical corpus, and a reviewer should be able to open it.
It also means no version-sensitive deserialisation: unlike the scikit-learn
artifacts in `ml/artifacts/`, this one cannot be invalidated by a library
upgrade.

--------------------------------------------------------------------------
STALENESS IS DETECTED, NOT ASSUMED AWAY
--------------------------------------------------------------------------
The artifact records the corpus version AND a content fingerprint of every
document it was built from. Loading an index whose fingerprint disagrees with
the live corpus raises. The failure it prevents is specific and nasty: someone
edits a document, does not rebuild, and retrieval silently serves the OLD text
with provenance pointing at the NEW document -- a citation that does not say
what the cited document says.

--------------------------------------------------------------------------
THE SIMILARITY FLOOR
--------------------------------------------------------------------------
`SIMILARITY_FLOOR` is the module's most consequential constant. Below it,
results are DISCARDED and the retriever returns nothing.

Returning nothing is the correct behaviour and is better than returning the
best of a bad set. A weakly-matched chunk handed to an LLM as grounding does
not degrade gracefully: the model treats retrieved text as authoritative, so an
irrelevant chunk produces a confident, well-written answer about the wrong
thing. That is worse than "I don't have information about that", which is what
Module 23 can say when it is handed nothing.

The value is justified by measurement in the README, not by taste.
"""

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

#: Bumped when the index FORMAT changes (not when the corpus changes -- that is
#: `KNOWLEDGE_BASE_VERSION`). An artifact with an older format version is
#: refused rather than parsed on a guess.
INDEX_FORMAT_VERSION = "1"

#: Where `knowledge/build_index.py` writes and `load_index` reads.
DEFAULT_INDEX_PATH = (
    Path(__file__).resolve().parents[2] / "knowledge" / "artifacts"
    / "knowledge_index_v1.json"
)

#: Minimum blended score for a chunk to be returned at all. See the module
#: docstring and the measured justification in the README.
#:
#: Measured behaviour at 0.12 on the evaluation set: every on-topic
#: finding-driven query keeps its relevant chunks (the weakest true positive
#: scores well above it), while off-topic and nonsense queries
#: ("how do I fix my bicycle", "asdfghjkl") return EMPTY rather than a
#: plausible-looking wrong answer. Lowering it to 0.05 admits junk; raising it
#: to 0.20 starts discarding genuine matches for single-feature queries, whose
#: scores are structurally lower because the query is short.
SIMILARITY_FLOOR = 0.12

#: Weight of exact TAG overlap versus text similarity in the blended score.
#: Both components are in [0, 1] and the weights sum to 1, so the blend is too
#: -- which is what keeps `SIMILARITY_FLOOR` a fixed, interpretable number.
#:
#: 0.35 was chosen so that tag agreement is decisive between two chunks of
#: similar text relevance, without letting a tag match alone clear the floor:
#: a chunk with a perfect tag match but near-zero text similarity scores ~0.35
#: and survives, which is correct (it IS about the right condition), while a
#: chunk with neither scores 0 and does not.
TAG_WEIGHT = 0.35
TEXT_WEIGHT = 1.0 - TAG_WEIGHT

#: Minimum fraction of a query's content tokens that must appear in the corpus
#: vocabulary for the query to be answered AT ALL. Below it the query is judged
#: off-domain and search returns nothing without scoring anything.
#:
#: This is a SECOND, independent gate, and it exists because the similarity
#: floor provably cannot do this job -- see `embeddings.vocabulary_coverage`
#: for the measurements. Briefly: a nonsense query that shares one incidental
#: word with the corpus out-scores real medical queries, because the query
#: vector normalises to point entirely at that one word.
#:
#: 0.40 sits in the middle of a wide measured gap (negatives topped out at
#: 0.25; the weakest genuine query scored 0.67), so it is not finely tuned and
#: does not need to be.
DOMAIN_COVERAGE_FLOOR = 0.40

#: Default number of chunks returned. Small on purpose: an LLM prompt grounded
#: on five well-matched paragraphs produces better output than one grounded on
#: twenty, where the relevant material is diluted.
DEFAULT_TOP_K = 5
MAX_TOP_K = 25

#: At most this many chunks from any ONE document may appear in a result set.
#:
#: Without it, a single well-matched document monopolises the whole result:
#: measured on the spec's own example (Diabetes + hba1c + blood_glucose), three
#: of the top five chunks came from `cond_diabetes` and the two documents
#: holding the actual threshold numbers did not appear at all. Handing an LLM
#: five paragraphs that are largely restatements of each other wastes most of
#: the grounding budget.
#:
#: Measured over the 30 positive evaluation queries, mean per query:
#:
#:     cap    distinct docs in top-5    RELEVANT docs in top-5
#:     1              3.90                      2.10
#:     2              2.93                      1.87
#:     3              2.73                      1.77
#:     none           2.67                      1.70
#:
#: A cap of 1 maximises both, and is the right setting if breadth is all that
#: matters. The default is 2 because chunks are paragraphs and a document's
#: paragraphs are complementary rather than repetitive -- one says what a test
#: is, another gives its bands -- so allowing a genuinely best-matching
#: document a second paragraph buys context that a second marginal document
#: does not. It keeps most of the diversity gain (2.67 -> 2.93 distinct,
#: 1.70 -> 1.87 relevant) while retaining that. Set to 1 to prefer breadth.
MAX_CHUNKS_PER_DOCUMENT = 2


class IndexError_(RuntimeError):
    """Base class for index build/load failures."""


class StaleIndexError(IndexError_):
    """The committed index does not match the live corpus."""


class MissingIndexError(IndexError_):
    """No index artifact was found where one was expected."""


@dataclass(frozen=True)
class ScoredChunk:
    """One retrieval result, carrying full provenance.

    Every field a citation needs travels with the result. Module 23 can render
    a reference, and Module 20's principle holds: a reader can see WHY this
    text was put in front of them -- which document, on what basis, matched how
    well, and by which signal.
    """

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
    """SHA-256 over every document's identity and content, in corpus order.

    Any edit to any document, and any reordering, changes this. That is what
    makes `StaleIndexError` possible.
    """
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
    """The searchable index: chunks, their two field vectors, and the vocabulary."""

    chunks: List[Chunk]
    body_vectors: List[Dict[str, float]]
    header_vectors: List[Dict[str, float]]
    vocabulary: Vocabulary
    corpus_version: str
    fingerprint: str

    # ------------------------------------------------------------------ build

    @classmethod
    def build(cls) -> "KnowledgeIndex":
        """Build from the live corpus. Deterministic.

        Called by `knowledge/build_index.py` and by tests. NOT called at import
        or per request -- see the module docstring.
        """
        chunks = chunk_corpus()

        body_tokens = [tokenize(c.text) for c in chunks]
        header_tokens = [tokenize(c.retrieval_text) for c in chunks]

        # One shared vocabulary across both fields. Two separate vocabularies
        # would give the same term different IDF weights depending on which
        # field it appeared in, making the two field scores incomparable and
        # the weighted blend meaningless.
        vocabulary = Vocabulary.learn(body_tokens + header_tokens)

        return cls(
            chunks=chunks,
            body_vectors=[vectorise(t, vocabulary) for t in body_tokens],
            header_vectors=[vectorise(t, vocabulary) for t in header_tokens],
            vocabulary=vocabulary,
            corpus_version=KNOWLEDGE_BASE_VERSION,
            fingerprint=corpus_fingerprint(),
        )

    # ----------------------------------------------------------------- search

    def search(
        self,
        query: Query,
        *,
        top_k: int = DEFAULT_TOP_K,
        floor: float = SIMILARITY_FLOOR,
        domain_floor: float = DOMAIN_COVERAGE_FLOOR,
        per_document: Optional[int] = MAX_CHUNKS_PER_DOCUMENT,
    ) -> List[ScoredChunk]:
        """Rank chunks against `query`, discarding anything below `floor`.

        TWO independent gates decide that nothing is returned, and they catch
        different failures:

          * `domain_floor` -- the question is not about this corpus.
          * `floor`        -- the question is on-topic but nothing matches well.

        Returns [] for an empty query and in both gated cases. All three are
        deliberate: grounding an LLM on a poorly-matched chunk is worse than
        grounding it on nothing. See the module docstring.
        """
        if query.is_empty:
            return []

        top_k = max(0, min(int(top_k), MAX_TOP_K))
        if top_k == 0:
            return []

        query_tokens = tokenize(query.text)

        # Gate 1: is this question about this corpus at all? Checked before any
        # scoring, because a query that fails it has no meaningful similarity to
        # anything here -- see DOMAIN_COVERAGE_FLOOR.
        #
        # Finding-driven queries are exempt by construction rather than by
        # special case: `build_query` expands them from the canonical
        # catalogues, so their coverage is ~1.0 and they always pass. The
        # explicit skip below avoids penalising a finding query whose free-text
        # half happens to be off-domain, where the caller HAS named a real
        # condition and is entitled to knowledge about it.
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
                # A free-text query has no tags to agree with. Re-weighting to
                # pure text keeps the score on the SAME [0, 1] scale, so one
                # floor governs both query kinds. Multiplying by TEXT_WEIGHT
                # instead would silently make the floor 1/0.65 stricter here.
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

        # Ties broken by chunk_id so the ranking is fully deterministic; two
        # equally-scored chunks must not swap places between runs.
        scored.sort(key=lambda s: (-s.score, s.chunk.chunk_id))

        # Diversify: no single document may fill the result set. Applied AFTER
        # ranking, so the best chunk of a document is always the one kept.
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

    # ------------------------------------------------------------ persistence

    def to_dict(self) -> Dict[str, object]:
        return {
            "index_format_version": INDEX_FORMAT_VERSION,
            "corpus_version": self.corpus_version,
            "fingerprint": self.fingerprint,
            "chunk_count": len(self.chunks),
            "vocabulary_size": len(self.vocabulary.idf),
            "document_count": self.vocabulary.document_count,
            # Sorted so the serialised artifact is byte-identical across runs
            # regardless of dict iteration order.
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

        raw_chunks = payload["chunks"]  # type: ignore[index]
        chunks: List[Chunk] = []
        body_vectors: List[Dict[str, float]] = []
        header_vectors: List[Dict[str, float]] = []
        for row in raw_chunks:  # type: ignore[union-attr]
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
                idf={t: float(w) for t, w in payload["idf"].items()},  # type: ignore[union-attr]
                document_count=int(payload["document_count"]),  # type: ignore[arg-type]
            ),
            corpus_version=str(payload.get("corpus_version", "")),
            fingerprint=str(payload.get("fingerprint", "")),
        )

    def stats(self) -> Dict[str, object]:
        """Introspection payload. Shape and counts only -- no PHI, ever."""
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
    """Write the artifact. `sort_keys` so the file is reproducible."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(index.to_dict(), indent=1, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def load_index(
    path: Path = DEFAULT_INDEX_PATH, *, verify: bool = True
) -> KnowledgeIndex:
    """Load the committed artifact.

    Raises `MissingIndexError` if absent and `StaleIndexError` if it does not
    match the live corpus. Neither is downgraded to a warning: a service that
    quietly serves stale knowledge is worse than one that refuses to start.
    """
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
