from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence, Tuple

BODY_WEIGHT = 0.65
HEADER_WEIGHT = 1.0 - BODY_WEIGHT

MIN_TOKEN_CHARS = 3

_TOKEN_RE = re.compile(r"[a-z0-9]+(?:\.[0-9]+)?")

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

_SUFFIXES = ("ies", "es", "s", "ing", "ed")


def tokenize(text: str) -> List[str]:
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
    counts: Dict[str, int] = {}
    for token in tokens:
        counts[token] = counts.get(token, 0) + 1
    return {term: 1.0 + math.log(count) for term, count in counts.items()}


@dataclass(frozen=True)
class Vocabulary:

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
        idf = {
            term: math.log((1.0 + total) / (1.0 + df)) + 1.0
            for term, df in seen.items()
        }
        return cls(idf=idf, document_count=total)


def vectorise(tokens: Sequence[str], vocab: Vocabulary) -> Dict[str, float]:
    weights: Dict[str, float] = {}
    for term, tf in _term_frequencies(tokens).items():
        idf = vocab.idf.get(term)
        if idf is None:
            continue
        weights[term] = tf * idf

    norm = math.sqrt(sum(w * w for w in weights.values()))
    if norm == 0.0:
        return {}
    return {term: w / norm for term, w in weights.items()}


def vocabulary_coverage(tokens: Sequence[str], vocab: Vocabulary) -> float:
    if not tokens:
        return 0.0
    return sum(1 for t in tokens if t in vocab.idf) / len(tokens)


def cosine(a: Dict[str, float], b: Dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    if len(a) > len(b):
        a, b = b, a
    return sum(weight * b.get(term, 0.0) for term, weight in a.items())


def combine_field_scores(body: float, header: float) -> float:
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
