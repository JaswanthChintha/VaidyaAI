"""Module 21, stage 4 -- QUERY CONSTRUCTION.

Spec Module 21's worked example is not a text search:

    Condition: Diabetes
    Patient Features: HbA1c = ..., Blood Glucose = ...
            -> RAG Retrieval -> Relevant Clinical Knowledge

So the primary input to retrieval is a FINDING -- a canonical condition and/or
a set of canonical features -- not a sentence. Free text is supported as a
secondary path (Module 25 will ask "what does eGFR mean"), but it is not the
main one, and building the module around it would have been building it around
the wrong caller.

--------------------------------------------------------------------------
WHY A FINDING IS EXPANDED RATHER THAN USED RAW
--------------------------------------------------------------------------
A raw query of `"Diabetes hba1c"` is two tokens. Against TF-IDF that is a thin,
high-variance signal: one unlucky term weight and the ranking is arbitrary.

So a finding is expanded into a richer query using vocabulary the platform
already maintains and already keeps aligned:

* the canonical names themselves (which the corpus is tagged with, enforced at
  import by `knowledge_base._check_document`),
* each feature's human description from `feature_catalog.FEATURES`,
* each feature's PRINTED SYNONYMS from `feature_catalog.FEATURE_SYNONYMS` --
  the same table Module 5 uses to read a lab report, so the query speaks the
  vocabulary that appears on real reports,
* each condition's description from `conditions.CONDITIONS`.

This is deliberately reusing the platform's existing vocabulary rather than
introducing a second, private synonym list that would drift out of step with
the one Module 5 depends on.

--------------------------------------------------------------------------
TAG MATCHING IS SEPARATE FROM TEXT SIMILARITY
--------------------------------------------------------------------------
The expansion above feeds the TEXT score. Alongside it, `Query` carries the
canonical names as a structured set, and `app/rag/index.py` scores tag overlap
independently before blending the two.

Keeping them separate matters. Tag overlap is an EXACT, structural fact -- this
document is tagged `Diabetes`, that one is not -- and folding it into a bag of
words would let a document that merely mentions the word "diabetes" a lot
outrank one actually tagged with it. Blending two bounded scores keeps both
signals legible and keeps the result in [0, 1].
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from app.data.conditions import CONDITIONS
from app.data.feature_catalog import FEATURES, FEATURE_SYNONYMS

#: Cap on synonyms pulled in per feature. The synonym table holds many spellings
#: of the same printed name ("HbA1c", "Hb A1c", "Glycosylated Haemoglobin"...).
#: All of them would swamp the query with near-duplicate tokens and let one
#: heavily-aliased feature dominate a multi-feature query.
MAX_SYNONYMS_PER_FEATURE = 6


class UnknownVocabularyError(ValueError):
    """Raised when a query names a feature or condition outside the catalogues.

    Deliberately an error and never a silent drop. A caller asking about
    `"HbA1c"` (wrong case) or `"diabetes"` (wrong case) has a bug, and
    answering it with results for the REST of its query would hide that bug
    behind plausible-looking output -- the same failure mode
    `app/data/conditions.py` exists to prevent for fusion.
    """


@dataclass(frozen=True)
class Query:
    """A retrieval request, expanded and ready to vectorise.

    `text` is what gets vectorised. `features` and `conditions` are the
    structured tags, scored separately. `source` records how the query was
    built, which is echoed in the response so a caller can see whether it was
    served a finding-driven or a free-text retrieval.
    """

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
    """Canonical name, description and printed synonyms for one feature."""
    definition = FEATURES[name]
    terms = [name, name.replace("_", " "), definition.description]
    synonyms = FEATURE_SYNONYMS.get(name, ())
    for synonym in synonyms[:MAX_SYNONYMS_PER_FEATURE]:
        # `Synonym.term` is the printed test name. Tolerate a bare string too,
        # so this does not break if that table is ever simplified.
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
    """Build a `Query` from a finding, free text, or both.

    At least one of the three must be non-empty; an entirely empty request is
    an empty `Query`, which `retrieve` answers with no results rather than with
    an arbitrary slice of the corpus.

    Raises `UnknownVocabularyError` if any name is outside the catalogues.
    """
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

    # De-duplicate while preserving caller order, so the same request always
    # produces the same query string and therefore the same ranking.
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
