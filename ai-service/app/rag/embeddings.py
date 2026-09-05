"""Module 21, stage 2 -- EMBEDDINGS.

Spec section 12 names "Embeddings" and "Vector Index / FAISS". This module is
the embedding step. The choice of HOW to embed was made by measurement, not by
default, and the measurement is reproducible -- see
`knowledge/evaluate_embeddings.py` and the Modules 21-22 section of
`ai-service/README.md`.

--------------------------------------------------------------------------
WHAT WAS CONSIDERED
--------------------------------------------------------------------------
1. **Local sentence-transformers** (`all-MiniLM-L6-v2`). True semantic
   matching, no per-query cost, offline once the weights are local. Costs
   ~90 MB of weights plus PyTorch (~2.5 GB installed) as a runtime dependency,
   and downloads on first use.
2. **Gemini embedding API.** No local weights, strong quality. Makes indexing
   and every query network-dependent and bills per call. The service already
   holds a Gemini client for Module 4, so it is not a new dependency -- but it
   would make the RAG layer unusable offline and in tests.
3. **Deterministic lexical TF-IDF** over a two-field chunk. No model, no
   download, no network, ~200 lines. Vectors are reproducible bit-for-bit from
   the corpus.

--------------------------------------------------------------------------
WHAT WAS CHOSEN, AND WHY
--------------------------------------------------------------------------
**TF-IDF (option 3) -- and it is a TRADE-OFF, not a free win.** Both were
measured on the same 30 positive / 5 negative evaluation set over the same 243
chunks (`knowledge/evaluate_embeddings.py`):

                      Recall@1  Recall@3  Recall@5    MRR   P@3
    TF-IDF (shipped)     0.733     0.933     0.933   0.822  0.589
    all-MiniLM-L6-v2     0.967     0.967     0.967   0.971  0.678

**The neural model is better, and materially so at rank 1** (0.967 vs 0.733)
and on MRR. Any claim that they are equivalent would be false. What is true is
narrower and is what the decision rests on: at the k this platform actually
retrieves with, the gap is ONE query out of thirty (Recall@5 0.967 vs 0.933).
Module 23 is handed the top 5 chunks as grounding, so Recall@5 is the operative
metric; exact rank ordering within those five matters much less than whether
the right document is among them at all.

Why the lexical option holds up as well as it does is a property of THIS
corpus, not a general claim. Queries here are mostly not free prose -- they are
built from canonical vocabulary (`hba1c`, `"Diabetes"`) by `app/rag/query.py`,
and the corpus is tagged with those same canonical strings by construction,
enforced at import. The hardest problem neural embeddings solve, matching
different words for the same idea, is largely designed out of this pipeline
before retrieval begins.

Against a one-query difference at k=5, the costs of the neural option are
concrete: PyTorch is ~2.5 GB installed, weights download from the network on
first use, and the tests for this module are required to run with no API key
and no network. It is also not merely theoretical friction -- installing it on
this machine FAILED first time on the Windows 260-character path limit and
needed a shorter install prefix. And the index becomes a float blob whose
provenance cannot be eyeballed, where the shipped JSON can be opened and read.

--------------------------------------------------------------------------
THE KNOWN WEAKNESS -- READ THIS BEFORE RELYING ON FREE-TEXT RETRIEVAL
--------------------------------------------------------------------------
TF-IDF cannot tell "a medical question this corpus covers" from "a medical
question it does not". `DOMAIN_COVERAGE_FLOOR` catches questions that are not
medical at all; nothing here catches a question that IS medical but is about an
analyte outside the fourteen canonical features.

Measured, top score for free-text questions about analytes the corpus does NOT
hold (TSH, ferritin, white cell count, ALT, PSA, CRP):

    TF-IDF        0.141 - 0.271     covered free-text queries: 0.121 - 0.27
    all-MiniLM    0.332 - 0.453     covered free-text queries: 0.595 - 0.691

The neural model SEPARATES them cleanly -- every uncovered question scores
below every covered one, with a clear gap. TF-IDF's two ranges overlap
completely, so no threshold exists that admits the covered questions and
rejects the uncovered ones. In practice "what does my TSH result mean" retrieves
triglyceride content at 0.187, above the floor.

No similarity floor fixes this, because the failure is not that the match is
weak; it is that generic medical prose ("level", "result", "raised", "mean") is
shared between any two medical topics. This is the one place where the lexical
choice is materially worse and the difference is a SAFETY difference rather
than a quality one.

It is bounded by how the platform actually calls this module: Module 23 drives
retrieval from FINDINGS, and a finding is always a canonical feature or
condition, so the primary path cannot ask about an analyte the corpus does not
hold. The exposure is the secondary free-text path, and Module 25 should map a
term to a canonical feature before asking, rather than passing raw user text
through.

**Revisit the choice when the offline constraint can be relaxed.** The blocker
is not quality, it is that the tests for this module are required to run with
no network: query-time embedding needs the model in-process, so committing
vectors does not avoid the download. If that constraint changes, or if free-text
questions become a primary entry point, the neural backend is the better
answer and this is the evidence for it. Re-run
`knowledge/evaluate_embeddings.py` after any corpus growth in any case.

Swapping backends is deliberately cheap: `tokenize`/`vectorise`/`cosine` are the
only three functions `app/rag/index.py` calls to turn text into something
comparable, so a neural backend means replacing those and re-running the build
script -- not rewriting Module 21.

--------------------------------------------------------------------------
WHY NOT FAISS
--------------------------------------------------------------------------
The spec says "Vector Index / FAISS". FAISS earns its place by making
similarity search sublinear across millions of vectors. This corpus produces a
few hundred chunks, where an exhaustive dot product over a dense matrix is both
faster (no index-structure overhead) and EXACT -- FAISS's approximate indexes
trade recall for speed that is not needed here. Adding it would introduce a
platform-specific binary dependency to make a sub-millisecond search
marginally faster while making it slightly less accurate.

The vectors are stored as plain rows, so if the corpus ever justifies FAISS,
the change is confined to `app/rag/index.py::search`.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence, Tuple

#: Weight given to the paragraph's own text versus its document header when the
#: two field scores are combined. Chosen so that a document-level match can
#: surface a paragraph that does not name its own subject, while the paragraph's
#: own words still decide WHICH paragraph of that document wins. At 1.0 the
#: retriever finds the right paragraph but misses documents whose body omits the
#: query term; at 0.0 every chunk of a document scores identically.
BODY_WEIGHT = 0.65
HEADER_WEIGHT = 1.0 - BODY_WEIGHT

#: Tokens shorter than this are dropped unless numeric. Keeps "a", "of", "is"
#: out of the vocabulary without needing a large stopword list.
MIN_TOKEN_CHARS = 3

_TOKEN_RE = re.compile(r"[a-z0-9]+(?:\.[0-9]+)?")

#: Deliberately small. A long stopword list risks dropping a token that matters
#: in this domain, and IDF already suppresses ubiquitous terms far more safely:
#: a word appearing in every chunk gets an IDF near zero whether or not anyone
#: thought to list it.
_STOPWORDS = frozenset(
    """
    the and for that with this from are was were has have had not but its it's
    can could would should may might will shall are being been does did doing
    which who whom whose what when where why how than then them they their there
    here also more most much many some any all both each other another such
    into onto over under about above below between within without across
    because while during before after again further once only own same
    very too just now even ever never always often sometimes usually
    """.split()
)

#: Light suffix folding so "levels"/"level" and "raised"/"raise" match. This is
#: NOT a real stemmer (no Porter, no dependency): it is four conservative rules
#: that never merge clinically distinct terms. Aggressive stemming is a real
#: hazard here -- a stemmer that folds "diabetic" and "diabetes" together is
#: harmless, but one that folds "hyper-" and "hypo-" prefixed terms is not.
_SUFFIXES = ("ies", "es", "s", "ing", "ed")


def tokenize(text: str) -> List[str]:
    """Lowercase, split, drop stopwords and short tokens, fold light suffixes.

    Numbers are KEPT, including decimals: "6.5", "126" and "18.5" are among the
    most discriminating tokens in this corpus, since threshold values appear in
    exactly the documents that discuss them.
    """
    tokens: List[str] = []
    for raw in _TOKEN_RE.findall(text.lower()):
        if raw in _STOPWORDS:
            continue
        if raw[0].isdigit():
            tokens.append(raw)
            continue
        if len(raw) < MIN_TOKEN_CHARS:
            continue
        tokens.append(_fold(raw))
    return tokens


def _fold(token: str) -> str:
    if len(token) <= 4:
        return token
    for suffix in _SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) >= 4:
            return token[: -len(suffix)]
    return token


def _term_frequencies(tokens: Sequence[str]) -> Dict[str, float]:
    """Sublinear (log-scaled) term frequency.

    Raw counts let one word repeated six times in a paragraph dominate six
    distinct matching words, which is the wrong ranking for prose.
    """
    counts: Dict[str, int] = {}
    for token in tokens:
        counts[token] = counts.get(token, 0) + 1
    return {term: 1.0 + math.log(count) for term, count in counts.items()}


@dataclass(frozen=True)
class Vocabulary:
    """Term -> IDF weight, learned from the corpus at BUILD time.

    Held explicitly (rather than recomputed per query) because it is part of
    the committed index: a query vectorised against a different vocabulary than
    the one the chunks were vectorised against would produce silently
    meaningless similarities.
    """

    idf: Dict[str, float]
    document_count: int

    @classmethod
    def learn(cls, documents: Iterable[Sequence[str]]) -> "Vocabulary":
        docs = list(documents)
        seen: Dict[str, int] = {}
        for tokens in docs:
            for term in set(tokens):
                seen[term] = seen.get(term, 0) + 1
        total = len(docs)
        # Smoothed IDF, the scikit-learn convention. The +1s keep a term that
        # appears in every document at a small positive weight rather than
        # exactly zero, so it can still break a tie.
        idf = {
            term: math.log((1.0 + total) / (1.0 + df)) + 1.0
            for term, df in seen.items()
        }
        return cls(idf=idf, document_count=total)


def vectorise(tokens: Sequence[str], vocab: Vocabulary) -> Dict[str, float]:
    """A sparse, L2-normalised TF-IDF vector.

    Sparse dicts rather than dense arrays: the vocabulary runs to a few
    thousand terms while a chunk holds well under two hundred, so a dense
    representation would be ~99 % zeros. Normalising to unit length is what
    makes the dot product a COSINE, and therefore what makes the similarity
    floor in `app/rag/index.py` a fixed, interpretable number rather than
    something that drifts with document length.
    """
    weights: Dict[str, float] = {}
    for term, tf in _term_frequencies(tokens).items():
        idf = vocab.idf.get(term)
        if idf is None:
            # Unseen at build time. It cannot match any chunk, so it carries no
            # information and is dropped rather than given a guessed weight.
            continue
        weights[term] = tf * idf

    norm = math.sqrt(sum(w * w for w in weights.values()))
    if norm == 0.0:
        return {}
    return {term: w / norm for term, w in weights.items()}


def vocabulary_coverage(tokens: Sequence[str], vocab: Vocabulary) -> float:
    """Fraction of a query's content tokens that exist in the corpus at all.

    THE OFF-DOMAIN GATE. This measures something the similarity score cannot,
    and the distinction is worth stating precisely.

    Cosine similarity is computed AFTER out-of-vocabulary terms are dropped, so
    it answers "given the words I recognised, how well do they match?" -- and a
    query where only one word was recognised can score very highly, because
    after normalisation the query vector points entirely at that one word.

    Measured on the evaluation set, this is not hypothetical. "why does my
    python script raise a KeyError on line 40" scored 0.204, ABOVE eight
    genuine medical queries, on the single shared word "raise". "what is the
    weather forecast for tomorrow" scored 0.187 on "forecast", which appears in
    the corpus exactly once, in a sentence about risk estimates not being
    forecasts. Raising the similarity floor high enough to exclude those would
    have discarded most real free-text queries with it -- the floor sweep in
    `knowledge/evaluate_embeddings.py` shows Recall@3 collapsing from 0.933 to
    0.633 before the last negative is excluded.

    Coverage separates them cleanly because it looks at what was DISCARDED. An
    off-domain question is one whose vocabulary is largely absent from a
    medical corpus:

        measured negatives   0.00, 0.00, 0.00, 0.17, 0.25
        measured positives   0.67, 0.75, then 1.00 for all fourteen others

    A wide empty gap, which is what makes `DOMAIN_COVERAGE_FLOOR` a robust
    constant rather than a tuned one.

    Note this is a property of the QUERY, not of any chunk, so it is evaluated
    once per search rather than per candidate.
    """
    if not tokens:
        return 0.0
    return sum(1 for t in tokens if t in vocab.idf) / len(tokens)


def cosine(a: Dict[str, float], b: Dict[str, float]) -> float:
    """Dot product of two unit-length sparse vectors, i.e. cosine similarity.

    Iterates the SHORTER vector, which in practice is always the query.
    """
    if not a or not b:
        return 0.0
    if len(a) > len(b):
        a, b = b, a
    return sum(weight * b.get(term, 0.0) for term, weight in a.items())


def combine_field_scores(body: float, header: float) -> float:
    """Weighted blend of the two per-field cosines.

    Both inputs are in [0, 1] and the weights sum to 1, so the result is too.
    That boundedness is what lets `SIMILARITY_FLOOR` be a constant.
    """
    return BODY_WEIGHT * body + HEADER_WEIGHT * header


__all__ = [
    "BODY_WEIGHT",
    "HEADER_WEIGHT",
    "MIN_TOKEN_CHARS",
    "Vocabulary",
    "combine_field_scores",
    "cosine",
    "tokenize",
    "vectorise",
    "vocabulary_coverage",
]
