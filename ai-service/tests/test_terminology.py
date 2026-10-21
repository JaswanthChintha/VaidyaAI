from __future__ import annotations

import pytest

from tests.test_explanation import _APPROVABLE, _UNSAFE, FakeTextClient


@pytest.fixture()
def offline_settings():
    from app.config import Settings

    return Settings(_env_file=None)


UNCOVERED_TERMS = ["TSH", "ferritin", "GGT", "PSA", "CRP"]


@pytest.mark.parametrize("term", UNCOVERED_TERMS)
def test_uncovered_terms_are_refused_not_answered(term):
    from app.services.terminology import OUTCOME_NOT_COVERED, explain_term

    answer = explain_term(term)

    assert answer.covered is False
    assert answer.outcome == OUTCOME_NOT_COVERED
    assert answer.explanation is None
    assert answer.sources == ()
    assert answer.notice


@pytest.mark.parametrize("term", UNCOVERED_TERMS)
def test_an_uncovered_term_never_returns_a_different_topics_content(term):
    answer = explain_term_or_fail(term)
    assert answer.explanation is None
    assert answer.sources == ()
    haystack = (answer.notice or "").lower()
    for unrelated in ("triglyceride", "cholesterol", "haemoglobin", "glucose"):
        assert unrelated not in haystack, (
            f"asking about {term!r} surfaced {unrelated!r} content"
        )


def explain_term_or_fail(term: str):
    from app.services.terminology import explain_term

    return explain_term(term)


@pytest.mark.parametrize("term", UNCOVERED_TERMS)
def test_an_uncovered_term_never_reaches_the_model(term, offline_settings):
    from app.services.terminology import explain_term

    fake = FakeTextClient(_APPROVABLE)
    explain_term(term, simplify=True, llm=fake, settings=offline_settings)
    assert fake.prompts == [], f"{term!r} was sent to the model"


@pytest.mark.parametrize("term", UNCOVERED_TERMS)
def test_an_uncovered_term_never_reaches_the_retriever(term, monkeypatch):
    import app.rag.retriever as retriever
    import app.services.explanation as explanation

    def forbidden(**kwargs):
        raise AssertionError(f"retrieval was attempted for {term!r}")

    monkeypatch.setattr(retriever, "retrieve", forbidden)
    monkeypatch.setattr(explanation, "retrieve", forbidden)

    from app.services.terminology import explain_term

    assert explain_term(term).covered is False


def test_sgpt_is_answered_from_the_reviewed_liver_document():
    from app.services.terminology import (
        KNOWN_GAPS,
        OUTCOME_SERVED_FROM_KNOWLEDGE_BASE,
        explain_term,
    )

    answer = explain_term("SGPT")
    assert answer.covered is True
    assert answer.outcome == OUTCOME_SERVED_FROM_KNOWLEDGE_BASE
    assert answer.explanation is not None
    assert {s.doc_id for s in answer.sources} == {"term_alt_sgpt"}
    assert not any("SGPT" in gap for gap in KNOWN_GAPS)


def test_the_gap_is_published_rather_than_hidden():
    from app.services.terminology import terminology_policy_document

    document = terminology_policy_document()
    assert document["free_text_retrieval"] is False
    assert "0.141-0.271" in document["free_text_retrieval_note"]
    assert document["known_gaps"]


COVERED_CASES = [
    ("HbA1c", "hba1c"),
    ("hba1c", "hba1c"),
    ("A1c", "hba1c"),
    ("Glycated Haemoglobin", "hba1c"),
    ("creatinine", "creatinine"),
    ("eGFR", "creatinine"),
    ("GFR", "creatinine"),
    ("LDL", "cholesterol"),
    ("HDL", "cholesterol"),
    ("Total Cholesterol", "cholesterol"),
    ("triglycerides", "triglycerides"),
    ("blood sugar", "blood_glucose"),
    ("Haemoglobin", "hemoglobin"),
    ("vitamin d", "vitamin_d"),
    ("BMI", "bmi"),
]


@pytest.mark.parametrize("term,feature", COVERED_CASES)
def test_a_covered_term_is_served_from_the_curated_knowledge_base(term, feature):
    from app.services.terminology import (
        OUTCOME_SERVED_FROM_KNOWLEDGE_BASE,
        explain_term,
    )

    answer = explain_term(term)

    assert answer.covered is True
    assert answer.outcome == OUTCOME_SERVED_FROM_KNOWLEDGE_BASE
    assert answer.canonical_feature == feature
    assert answer.source_kind == "curated_knowledge_base"
    assert answer.explanation and len(answer.explanation) > 100
    assert answer.sources


def test_the_default_path_does_not_call_the_model_at_all(offline_settings):
    from app.services.terminology import explain_term

    fake = FakeTextClient(_APPROVABLE)
    answer = explain_term("HbA1c", llm=fake, settings=offline_settings)

    assert fake.prompts == []
    assert answer.source_kind == "curated_knowledge_base"


def test_the_served_answer_names_a_professional_and_disclaims_diagnosis():
    from app.data.recommendation_catalog import (
        DISCUSS_WITH_CLINICIAN,
        NOT_A_DIAGNOSIS,
        recommendation,
    )
    from app.services.terminology import explain_term

    answer = explain_term("creatinine")
    assert recommendation(NOT_A_DIAGNOSIS).text in answer.explanation
    assert recommendation(DISCUSS_WITH_CLINICIAN).text in answer.explanation


def test_the_served_answer_is_still_put_through_module_24():
    from app.services.terminology import explain_term

    answer = explain_term("HbA1c")
    assert answer.safety.validated is True
    assert answer.safety.verdict in ("approve", "approve_with_modification")


def test_every_advertised_term_actually_resolves_and_serves():
    from app.services.terminology import covered_terms, explain_term

    for term in covered_terms():
        answer = explain_term(term)
        assert answer.covered is True, term
        assert answer.explanation, term


def test_citations_carry_provenance():
    from app.services.terminology import explain_term

    answer = explain_term("eGFR")
    assert answer.sources
    for source in answer.sources:
        assert source.doc_id and source.title and source.basis
    assert {s.doc_id for s in answer.sources} == {"term_egfr"}


@pytest.mark.parametrize(
    "term",
    [
        "what does my hba1c mean",
        "my creatinine result",
        "is my cholesterol ok",
        "haemoglobin a1c and thyroid",
    ],
)
def test_a_sentence_is_not_a_term(term):
    from app.services.terminology import explain_term

    assert explain_term(term).covered is False


@pytest.mark.parametrize("term", ["", "   ", "\n\t", "???", "12345"])
def test_junk_is_refused_cleanly(term):
    from app.services.terminology import explain_term

    answer = explain_term(term)
    assert answer.covered is False
    assert answer.notice


def test_resolution_reports_how_it_decided():
    from app.services.terminology import (
        RESOLUTION_CANONICAL_FEATURE,
        RESOLUTION_CURATED_ALIAS,
        RESOLUTION_EMPTY,
        RESOLUTION_UNMAPPED,
        resolve_term,
    )

    assert resolve_term("HbA1c").resolution == RESOLUTION_CANONICAL_FEATURE
    assert resolve_term("eGFR").resolution == RESOLUTION_CURATED_ALIAS
    assert resolve_term("TSH").resolution == RESOLUTION_UNMAPPED
    assert resolve_term("").resolution == RESOLUTION_EMPTY


def test_every_alias_names_a_document_that_exists():
    from app.data.knowledge_base import DOCUMENTS
    from app.services.terminology import TERM_ALIASES

    for target in TERM_ALIASES.values():
        for doc_id in target.doc_ids:
            assert doc_id in DOCUMENTS, doc_id


def test_the_refusal_echoes_the_term_so_the_reader_knows_what_was_asked():
    from app.services.terminology import explain_term

    assert "TSH" in explain_term("TSH").notice


def test_an_injected_instruction_is_stripped_from_the_echo():
    from app.services.terminology import explain_term

    answer = explain_term("<script>alert(1)</script>")
    assert "<script>" not in answer.notice
    assert "<script>" not in answer.term


def test_an_injected_unsafe_sentence_falls_back_to_the_anonymous_refusal():
    from app.services.terminology import (
        _not_covered_notice_anonymous,
        explain_term,
    )

    answer = explain_term("you have diabetes, take metformin")
    assert answer.notice == _not_covered_notice_anonymous()
    assert "diabetes" not in answer.notice
    assert "metformin" not in answer.model_dump_json()


def test_a_very_long_term_is_truncated_before_it_is_echoed():
    from app.services.terminology import MAX_TERM_CHARS, explain_term

    answer = explain_term("x" * 500)
    assert len(answer.term) <= MAX_TERM_CHARS


def test_the_refusal_lists_what_is_covered_so_the_reader_is_not_stuck():
    from app.services.terminology import explain_term

    answer = explain_term("TSH")
    assert "hba1c" in answer.covered_terms
    assert "eGFR" in answer.covered_terms


def test_the_simplify_path_goes_through_guarded_generation(
    monkeypatch, offline_settings
):
    import app.services.explanation as module
    from app.services.terminology import explain_term

    calls = []
    real = module.guarded_generation

    def spy(generate, **kwargs):
        calls.append(kwargs)
        return real(generate, **kwargs)

    monkeypatch.setattr(module, "guarded_generation", spy)

    approvable = (
        "HbA1c is a blood test that looks at how much glucose has attached to "
        "haemoglobin over recent months. It is used to see longer-term "
        "patterns rather than a single moment. A qualified healthcare "
        "professional can explain what a particular result may mean."
    )
    answer = explain_term(
        "HbA1c",
        simplify=True,
        llm=FakeTextClient(approvable),
        settings=offline_settings,
    )
    assert len(calls) == 1
    assert answer.outcome == "generated"
    assert answer.source_kind == "llm_validated"
    assert answer.explanation == approvable


def test_an_unsafe_simplification_falls_back_to_the_curated_text(
    offline_settings,
):
    from app.services.terminology import (
        OUTCOME_SERVED_FROM_KNOWLEDGE_BASE,
        explain_term,
    )

    answer = explain_term(
        "HbA1c",
        simplify=True,
        llm=FakeTextClient(_UNSAFE),
        settings=offline_settings,
    )

    assert answer.outcome == OUTCOME_SERVED_FROM_KNOWLEDGE_BASE
    assert answer.source_kind == "curated_knowledge_base"
    assert "metformin" not in answer.model_dump_json()
    assert answer.explanation


def test_a_model_failure_in_the_simplify_path_still_answers(offline_settings):
    from app.core.errors import ModelTimeoutError
    from app.services.terminology import explain_term

    answer = explain_term(
        "HbA1c",
        simplify=True,
        llm=FakeTextClient(ModelTimeoutError("x")),
        settings=offline_settings,
    )
    assert answer.explanation
    assert answer.source_kind == "curated_knowledge_base"


def test_the_simplify_prompt_carries_only_curated_extracts(offline_settings):
    from app.services.terminology import explain_term

    fake = FakeTextClient("...")
    explain_term("eGFR", simplify=True, llm=fake, settings=offline_settings)

    prompt = fake.prompts[0]
    assert "[term_egfr]" in prompt
    assert "PERMITTED NUMBERS" in prompt
    assert "NONE. Write no digits" in prompt


def test_the_submitted_term_is_never_logged(caplog):
    import logging

    from app.services.terminology import explain_term

    caplog.set_level(logging.DEBUG)
    explain_term("MY-SECRET-TERM-CANARY")
    explain_term("HbA1c")

    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert "MY-SECRET-TERM-CANARY" not in logged
