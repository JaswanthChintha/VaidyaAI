from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from app.data.conditions import CONDITIONS
from app.data.feature_catalog import FEATURES, FEATURE_SYNONYMS

MAX_SYNONYMS_PER_FEATURE = 6


class UnknownVocabularyError(ValueError):
    pass


@dataclass(frozen=True)
class Query:

    text: str
    features: Tuple[str, ...] = ()
    conditions: Tuple[str, ...] = ()
    source: str = "findings"
    raw_text: Optional[str] = None

    @property
    def is_empty(self) -> bool:
        return not self.text.strip()

    @property
    def tag_count(self) -> int:
        return len(self.features) + len(self.conditions)


def _feature_terms(name: str) -> List[str]:
    definition = FEATURES[name]
    terms = [name, name.replace("_", " "), definition.description]
    synonyms = FEATURE_SYNONYMS.get(name, ())
    for synonym in synonyms[:MAX_SYNONYMS_PER_FEATURE]:
        terms.append(getattr(synonym, "term", str(synonym)))
    if definition.canonical_unit:
        terms.append(definition.canonical_unit)
    return terms


def build_query(
    *,
    conditions: Sequence[str] = (),
    features: Sequence[str] = (),
    text: Optional[str] = None,
) -> Query:
    unknown_features = [f for f in features if f not in FEATURES]
    unknown_conditions = [c for c in conditions if c not in CONDITIONS]
    if unknown_features or unknown_conditions:
        parts = []
        if unknown_features:
            parts.append(
                f"features {unknown_features!r} are not in feature_catalog.FEATURES"
            )
        if unknown_conditions:
            parts.append(
                f"conditions {unknown_conditions!r} are not in conditions.CONDITIONS"
            )
        raise UnknownVocabularyError(
            "; ".join(parts)
            + ". Names are matched exactly, including case: 'Diabetes' is "
            "canonical and 'diabetes' is not. Retrieval refuses rather than "
            "quietly returning results for the remainder of the query."
        )

    ordered_features = tuple(dict.fromkeys(features))
    ordered_conditions = tuple(dict.fromkeys(conditions))

    terms: List[str] = []
    for condition in ordered_conditions:
        terms.append(condition)
        terms.append(CONDITIONS[condition].description)
    for feature in ordered_features:
        terms.extend(_feature_terms(feature))

    free_text = (text or "").strip()
    if free_text:
        terms.append(free_text)

    if ordered_conditions or ordered_features:
        source = "findings_and_text" if free_text else "findings"
    else:
        source = "text" if free_text else "empty"

    return Query(
        text=" ".join(t for t in terms if t).strip(),
        features=ordered_features,
        conditions=ordered_conditions,
        source=source,
        raw_text=free_text or None,
    )


__all__ = [
    "MAX_SYNONYMS_PER_FEATURE",
    "Query",
    "UnknownVocabularyError",
    "build_query",
]
