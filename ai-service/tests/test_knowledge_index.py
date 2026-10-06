"""Module 21 -- chunking, indexing, similarity search and retrieval.

Runs with NO network, NO API key and NO model download. The index is either
built in-process from the committed corpus (deterministic, pure Python) or
loaded from the committed artifact. Nothing here reaches outside the repo,
which is the property that made the lexical embedding choice possible -- see
`app/rag/embeddings.py`.
"""

from __future__ import annotations

import json

import pytest

from app.data.conditions import DIABETES, ANEMIA, KIDNEY_DISEASE
from app.data.knowledge_base import DOCUMENTS
from app.rag.chunking import (
    MAX_CHUNK_CHARS,
    MIN_CHUNK_CHARS,
    chunk_corpus,
    chunk_document,
)
from app.rag.embeddings import (
    Vocabulary,
    cosine,
    tokenize,
    vectorise,
    vocabulary_coverage,
)
from app.rag.index import (
    DEFAULT_INDEX_PATH,
    DOMAIN_COVERAGE_FLOOR,
    MAX_CHUNKS_PER_DOCUMENT,
    SIMILARITY_FLOOR,
    KnowledgeIndex,
    MissingIndexError,
    StaleIndexError,
    corpus_fingerprint,
    load_index,
)
from app.rag.query import UnknownVocabularyError, build_query
from app.rag.retriever import build_index, retrieve, retrieve_payload


@pytest.fixture(scope="module")
def index() -> KnowledgeIndex:
    """Built in-process from the live corpus. No I/O, no network."""
    return KnowledgeIndex.build()


def _doc_ids(results):
    out = []
    for r in results:
        if r.chunk.doc_id not in out:
            out.append(r.chunk.doc_id)
    return out


# --------------------------------------------------------------------------
# Chunking
# --------------------------------------------------------------------------


def test_chunking_produces_chunks_for_every_document():
    chunks = chunk_corpus()
    assert len({c.doc_id for c in chunks}) == len(DOCUMENTS)
    assert len(chunks) > len(DOCUMENTS), "documents should split into paragraphs"


def test_chunk_ids_are_unique_and_stable():
    first = [c.chunk_id for c in chunk_corpus()]
    second = [c.chunk_id for c in chunk_corpus()]
    assert first == second, "chunking must be deterministic"
    assert len(set(first)) == len(first)


def test_chunk_ids_encode_document_and_ordinal():
    for chunk in chunk_corpus():
        assert chunk.chunk_id == f"{chunk.doc_id}#{chunk.ordinal}"


def test_no_chunk_is_below_the_minimum_except_a_lone_one():
    """Short paragraphs are merged, so a tiny chunk means the merge broke."""
    for doc in DOCUMENTS.values():
        chunks = chunk_document(doc)
        if len(chunks) > 1:
            for chunk in chunks:
                assert len(chunk.text) >= MIN_CHUNK_CHARS, chunk.chunk_id


def test_chunks_respect_the_maximum_where_sentence_boundaries_allow():
    for chunk in chunk_corpus():
        # The cap is advisory when no sentence boundary exists in range; the
        # corpus should never actually rely on that escape hatch.
        assert len(chunk.text) <= MAX_CHUNK_CHARS * 1.5, chunk.chunk_id


def test_retrieval_text_carries_the_document_header_but_text_does_not():
    """The reader sees the paragraph; the retriever sees paragraph + header."""
    doc = DOCUMENTS["ref_hba1c_bands"]
    for chunk in chunk_document(doc):
        assert chunk.text in chunk.retrieval_text
        assert doc.title in chunk.retrieval_text
        assert doc.title not in chunk.text or chunk.ordinal == 0


def test_every_chunk_carries_full_provenance():
    """Provenance travels WITH the chunk -- Module 20's principle."""
    for chunk in chunk_corpus():
        doc = DOCUMENTS[chunk.doc_id]
        assert chunk.title == doc.title
        assert chunk.topic == doc.topic
        assert chunk.basis == doc.basis
        assert chunk.features == doc.features
        assert chunk.conditions == doc.conditions
        assert chunk.last_reviewed == doc.last_reviewed


# --------------------------------------------------------------------------
# Embeddings
# --------------------------------------------------------------------------


def test_tokenize_keeps_numbers_and_drops_stopwords():
    tokens = tokenize("The HbA1c was 6.5 % and the glucose was 126 mg/dL")
    assert "6.5" in tokens and "126" in tokens
    assert "the" not in tokens and "and" not in tokens


def test_vectors_are_unit_length():
    vocab = Vocabulary.learn([tokenize("alpha beta gamma"), tokenize("beta delta")])
    vector = vectorise(tokenize("alpha beta"), vocab)
    assert pytest.approx(sum(w * w for w in vector.values()), abs=1e-9) == 1.0


def test_cosine_of_identical_text_is_one():
    vocab = Vocabulary.learn([tokenize("alpha beta gamma"), tokenize("delta epsilon")])
    v = vectorise(tokenize("alpha beta gamma"), vocab)
    assert pytest.approx(cosine(v, v), abs=1e-9) == 1.0


def test_cosine_of_disjoint_text_is_zero():
    vocab = Vocabulary.learn([tokenize("alpha beta"), tokenize("gamma delta")])
    a = vectorise(tokenize("alpha beta"), vocab)
    b = vectorise(tokenize("gamma delta"), vocab)
    assert cosine(a, b) == 0.0


def test_out_of_vocabulary_terms_are_dropped_not_guessed():
    vocab = Vocabulary.learn([tokenize("alpha beta")])
    assert vectorise(tokenize("zzzz yyyy"), vocab) == {}


def test_vocabulary_coverage_separates_on_domain_from_off_domain(index):
    on = vocabulary_coverage(tokenize("what does my hba1c and glucose mean"),
                             index.vocabulary)
    off = vocabulary_coverage(tokenize("how do I fix a puncture on my bicycle tyre"),
                              index.vocabulary)
    assert on >= DOMAIN_COVERAGE_FLOOR
    assert off < DOMAIN_COVERAGE_FLOOR


# --------------------------------------------------------------------------
# Index build determinism and staleness
# --------------------------------------------------------------------------


def test_index_build_is_deterministic():
    a, b = KnowledgeIndex.build(), KnowledgeIndex.build()
    assert a.fingerprint == b.fingerprint
    assert [c.chunk_id for c in a.chunks] == [c.chunk_id for c in b.chunks]
    assert a.to_dict() == b.to_dict()


def test_serialised_index_round_trips(index):
    restored = KnowledgeIndex.from_dict(json.loads(json.dumps(index.to_dict())))
    assert [c.chunk_id for c in restored.chunks] == [c.chunk_id for c in index.chunks]
    assert restored.fingerprint == index.fingerprint


def test_committed_artifact_exists_and_matches_the_live_corpus():
    """The shipped index must be the index the shipped corpus produces.

    If this fails, run `python knowledge/build_index.py`.
    """
    assert DEFAULT_INDEX_PATH.exists(), (
        f"no committed index at {DEFAULT_INDEX_PATH}; "
        "run `python knowledge/build_index.py`"
    )
    loaded = load_index()
    assert loaded.fingerprint == corpus_fingerprint()


def test_committed_artifact_is_byte_identical_to_a_fresh_build():
    fresh = json.dumps(
        KnowledgeIndex.build().to_dict(), indent=1, sort_keys=True, ensure_ascii=False
    )
    assert DEFAULT_INDEX_PATH.read_text(encoding="utf-8") == fresh, (
        "the committed index is out of date; run `python knowledge/build_index.py`"
    )


def test_a_stale_index_is_refused_rather_than_silently_used(index):
    """Serving old text under current provenance is the failure this prevents."""
    payload = index.to_dict()
    payload["fingerprint"] = "0" * 64
    with pytest.raises(StaleIndexError):
        KnowledgeIndex.from_dict(payload)


def test_a_wrong_format_version_is_refused(index):
    payload = index.to_dict()
    payload["index_format_version"] = "999"
    with pytest.raises(StaleIndexError):
        KnowledgeIndex.from_dict(payload)


def test_missing_artifact_raises(tmp_path):
    with pytest.raises(MissingIndexError):
        load_index(tmp_path / "nope.json")


def test_fingerprint_changes_when_a_document_changes(monkeypatch):
    import dataclasses
    before = corpus_fingerprint()
    doc = DOCUMENTS["lab_hba1c"]
    patched = dict(DOCUMENTS)
    patched["lab_hba1c"] = dataclasses.replace(doc, summary=doc.summary + " edited")
    monkeypatch.setattr("app.rag.index.DOCUMENTS", patched)
    assert corpus_fingerprint() != before


# --------------------------------------------------------------------------
# Query construction
# --------------------------------------------------------------------------


def test_query_expands_a_finding_into_catalogue_vocabulary():
    q = build_query(conditions=[DIABETES], features=["hba1c"])
    assert q.source == "findings"
    assert "hba1c" in q.text.lower()
    # Expanded with the printed synonyms Module 5 uses to read real reports.
    assert "glycated" in q.text.lower() or "a1c" in q.text.lower()


def test_query_rejects_a_non_canonical_condition():
    with pytest.raises(UnknownVocabularyError, match="conditions"):
        build_query(conditions=["diabetes"])


def test_query_rejects_a_non_canonical_feature():
    with pytest.raises(UnknownVocabularyError, match="features"):
        build_query(features=["HbA1c"])


def test_query_refuses_rather_than_answering_the_valid_half():
    """Answering the rest would hide the caller's bug behind plausible output."""
    with pytest.raises(UnknownVocabularyError):
        build_query(conditions=[DIABETES, "Diabetes Mellitus"], features=["hba1c"])


def test_empty_query_is_empty():
    assert build_query().is_empty
    assert build_query(text="   ").is_empty


def test_query_deduplicates_while_preserving_order():
    q = build_query(features=["hba1c", "bmi", "hba1c"])
    assert q.features == ("hba1c", "bmi")


# --------------------------------------------------------------------------
# Similarity search -- the spec's worked example
# --------------------------------------------------------------------------


def test_spec_example_retrieves_diabetes_knowledge(index):
    """Condition: Diabetes + HbA1c/Blood Glucose -> relevant clinical knowledge."""
    results = retrieve(
        conditions=[DIABETES], features=["hba1c", "blood_glucose"], index=index
    )
    assert results
    ids = _doc_ids(results)
    assert any(d.startswith("cond_diabetes") or "hba1c" in d or "glucose" in d
               for d in ids), ids


@pytest.mark.parametrize(
    "conditions,features,expected_any",
    [
        ([ANEMIA], ["hemoglobin"], {"cond_anemia", "lab_hemoglobin",
                                    "ref_hemoglobin_bands"}),
        ([KIDNEY_DISEASE], ["creatinine"], {"cond_kidney_disease", "lab_creatinine",
                                            "ref_creatinine_bands", "term_egfr"}),
        ([], ["vitamin_d"], {"lab_vitamin_d", "ref_vitamin_d_bands",
                             "cond_vitamin_d_deficiency", "life_vitamin_d_sources"}),
        ([], ["bmi"], {"ref_bmi_bands", "term_bmi_word", "cond_obesity",
                       "profile_bmi_derived", "cond_underweight"}),
    ],
)
def test_finding_driven_retrieval_returns_the_right_documents(
    index, conditions, features, expected_any
):
    results = retrieve(conditions=conditions, features=features, index=index)
    assert results, (conditions, features)
    assert set(_doc_ids(results)) & expected_any, _doc_ids(results)


def test_results_are_ranked_by_descending_score(index):
    results = retrieve(conditions=[DIABETES], features=["hba1c"], top_k=10, index=index)
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)


def test_search_is_deterministic(index):
    a = retrieve(conditions=[DIABETES], features=["hba1c"], index=index)
    b = retrieve(conditions=[DIABETES], features=["hba1c"], index=index)
    assert [r.chunk.chunk_id for r in a] == [r.chunk.chunk_id for r in b]


def test_top_k_is_respected(index):
    for k in (1, 3, 5):
        assert len(retrieve(conditions=[DIABETES], top_k=k, index=index)) <= k


def test_no_single_document_monopolises_the_results(index):
    """Grounding diversity -- see MAX_CHUNKS_PER_DOCUMENT."""
    results = retrieve(
        conditions=[DIABETES], features=["hba1c", "blood_glucose"], top_k=5, index=index
    )
    counts = {}
    for r in results:
        counts[r.chunk.doc_id] = counts.get(r.chunk.doc_id, 0) + 1
    assert max(counts.values()) <= MAX_CHUNKS_PER_DOCUMENT, counts


# --------------------------------------------------------------------------
# The floors -- return NOTHING rather than something irrelevant
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "how do I fix a puncture on my bicycle tyre",
        "asdfghjkl qwertyuiop",
        "why does my python script raise a KeyError on line 40",
        "what is the weather forecast for tomorrow afternoon",
    ],
)
def test_off_domain_queries_return_nothing(index, text):
    """Grounding an LLM on a bad chunk is worse than grounding it on none."""
    assert retrieve(text=text, index=index) == []


@pytest.mark.parametrize("text", ["", "   ", "\n\t "])
def test_empty_queries_return_nothing(index, text):
    assert retrieve(text=text, index=index) == []


def test_no_query_at_all_returns_nothing(index):
    assert retrieve(index=index) == []


def test_every_returned_chunk_clears_the_floor(index):
    results = retrieve(conditions=[DIABETES], top_k=25, index=index)
    assert all(r.score >= SIMILARITY_FLOOR for r in results)


def test_raising_the_floor_to_one_returns_nothing(index):
    assert retrieve(conditions=[DIABETES], floor=1.0, index=index) == []


def test_lowering_the_floor_admits_more(index):
    strict = retrieve(conditions=[DIABETES], top_k=25, floor=0.5, index=index)
    loose = retrieve(conditions=[DIABETES], top_k=25, floor=0.05, index=index)
    assert len(loose) >= len(strict)


def test_scores_are_bounded(index):
    for r in retrieve(conditions=[DIABETES], features=["hba1c"], top_k=25, index=index):
        assert 0.0 <= r.score <= 1.0
        assert 0.0 <= r.text_score <= 1.0
        assert 0.0 <= r.tag_score <= 1.0


# --------------------------------------------------------------------------
# Provenance completeness
# --------------------------------------------------------------------------


def test_every_result_carries_complete_provenance(index):
    """Module 23 cites this; Module 20 requires it to be traceable."""
    results = retrieve(
        conditions=[DIABETES], features=["hba1c"], top_k=10, index=index
    )
    assert results
    for r in results:
        payload = r.to_dict()
        for key in ("chunk_id", "doc_id", "title", "topic", "text", "basis",
                    "features", "conditions", "last_reviewed", "score",
                    "text_score", "tag_score"):
            assert key in payload, key
        assert payload["basis"].strip(), "a retrieved chunk must cite its basis"
        assert payload["doc_id"] in DOCUMENTS
        assert payload["text"].strip()


def test_retrieve_payload_echoes_the_query_and_states_availability(index):
    payload = retrieve_payload(
        conditions=[DIABETES], features=["hba1c"], index=index
    )
    assert payload["query"]["conditions"] == [DIABETES]
    assert payload["query"]["features"] == ["hba1c"]
    assert payload["query"]["source"] == "findings"
    assert payload["grounding_available"] is True
    assert payload["returned"] == len(payload["results"])


def test_retrieve_payload_reports_no_grounding_for_off_domain(index):
    payload = retrieve_payload(text="how do I fix my bicycle", index=index)
    assert payload["results"] == []
    assert payload["grounding_available"] is False


# --------------------------------------------------------------------------
# build_index() -- the in-process half of the build script
# --------------------------------------------------------------------------


def test_build_index_matches_the_class_build():
    assert build_index().fingerprint == KnowledgeIndex.build().fingerprint


def test_build_index_can_write_an_artifact(tmp_path):
    path = tmp_path / "idx.json"
    built = build_index(save=True, path=path)
    assert path.exists()
    assert load_index(path).fingerprint == built.fingerprint


def test_index_stats_report_shape_only(index):
    stats = index.stats()
    assert stats["chunks"] == len(index.chunks)
    assert stats["documents"] == len(DOCUMENTS)
    assert stats["similarity_floor"] == SIMILARITY_FLOOR
    # Counts and thresholds only -- no corpus prose leaks into the stats
    # payload, so it is safe to log and to expose for introspection.
    serialised = json.dumps(stats)
    for chunk in index.chunks[:20]:
        assert chunk.text not in serialised


# --------------------------------------------------------------------------
# The anchoring reaches the PUBLIC path too (section 6k D7 / section 6r D1)
# --------------------------------------------------------------------------
#
# The anchoring control existed, was tested, and was documented -- on
# `retrieve()`. `retrieve_payload()` built its query directly and skipped it,
# and `retrieve_payload` is what `POST /api/v1/knowledge/retrieve` calls. So
# the one path a stranger can reach was the one without the control, and two
# audits recorded the defect as open because a fix applied to one of two
# duplicated paths looks complete from either end.
#
# These are D7's own examples. `test_retrieve_payload_reports_no_grounding_for
# _off_domain` above passed throughout, because "how do I fix my bicycle" is
# so far off-domain that the similarity floor caught it. The dangerous queries
# are the MEDICAL ones this corpus does not cover: measured, they score
# 0.141-0.271 while covered terms score 0.121-0.27, so the ranges overlap
# completely and no floor can separate them.


@pytest.mark.parametrize(
    "question",
    [
        # Was "my ALT and AST liver enzymes are high" until 2026-10-04, when
        # ALT and AST became features with their own documents. ALP and GGT
        # are the liver tests the corpus still does not cover.
        "my ALP and GGT liver enzymes are high",
        "C reactive protein CRP",
        "what should I take for my thyroid",
        "is my liver enzyme high",
        "chest pain",
    ],
)
def test_an_uncovered_medical_question_grounds_on_nothing(index, question):
    """Both entry points, because only one of them used to refuse."""
    assert retrieve(text=question, index=index) == []
    payload = retrieve_payload(text=question, index=index)
    assert payload["returned"] == 0
    assert payload["grounding_available"] is False
    assert payload["results"] == []


@pytest.mark.parametrize(
    "question,expected_feature",
    [
        ("what does a raised HbA1c mean", "hba1c"),
        ("blood glucose", "blood_glucose"),
    ],
)
def test_a_covered_question_still_retrieves_and_says_what_it_anchored_to(
    index, question, expected_feature
):
    """The refusal must not have been bought by refusing everything.

    D7's worst example was this one: a query naming a feature the corpus DOES
    cover, which still retrieved a different analyte as its top chunk. It must
    now resolve to the canonical name and retrieve on that.
    """
    payload = retrieve_payload(text=question, index=index)
    assert payload["returned"] > 0
    assert payload["grounding_available"] is True
    assert expected_feature in payload["query"]["features"]


def test_the_findings_path_is_untouched_by_anchoring(index):
    """Canonical names are already exact and must not be re-resolved."""
    payload = retrieve_payload(
        conditions=[DIABETES], features=["hba1c"], index=index
    )
    assert payload["returned"] > 0
    assert payload["query"]["conditions"] == [DIABETES]
    assert payload["query"]["features"] == ["hba1c"]


def test_a_refused_query_echoes_that_it_anchored_to_nothing(index):
    """The echo must not imply a question was asked that never was."""
    payload = retrieve_payload(text="what should I take for my thyroid", index=index)
    assert payload["query"]["features"] == []
    assert payload["query"]["conditions"] == []
    assert payload["query"]["text"] == "what should I take for my thyroid"
