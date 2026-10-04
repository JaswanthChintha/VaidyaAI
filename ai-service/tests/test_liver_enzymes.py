"""Liver enzymes -- the reviewed ALT/SGPT and AST/SGOT documents (2026-10-04).

What is pinned:

1. The printed spellings map by EXACT alias onto the right document, and a
   near-miss is still refused (the terminology module's core rule).
2. The documents pass both safety scanners and describe the test only: no
   threshold, and no feature or condition tag that would let retrieval treat
   them as evidence about an assessed result.
3. The dashboard's "what this test is" line uses the reviewed summary for
   these names WITHOUT a model call, and every other unassessed test still
   goes to the model exactly as before.
"""

from __future__ import annotations

import re

import pytest

from app.data.knowledge_base import DOCUMENTS
from app.services import parameter_glossary as glossary
from app.services.parameter_glossary import (
    ORIGIN_MODEL,
    ORIGIN_REVIEWED,
    describe_parameters,
    reset_cache,
    reviewed_entry,
)
from app.services.terminology import (
    OUTCOME_NOT_COVERED,
    OUTCOME_SERVED_FROM_KNOWLEDGE_BASE,
    explain_term,
    resolve_term,
)

ALT_NAMES = [
    "SGPT",
    "S.G.P.T.",
    "ALT",
    "SGPT (ALT)",
    "ALT/SGPT",
    "Serum SGPT",
    "Alanine Aminotransferase",
    "Alanine Aminotransferase (ALT/SGPT)",
    "Serum Glutamic Pyruvic Transaminase",
]
AST_NAMES = [
    "SGOT",
    "S.G.O.T.",
    "AST",
    "AST (SGOT)",
    "SGOT/AST",
    "Serum SGOT",
    "Aspartate Aminotransferase",
    "Aspartate Aminotransferase (AST/SGOT)",
    "Serum Glutamic Oxaloacetic Transaminase",
]


@pytest.fixture(autouse=True)
def _clear_cache():
    reset_cache()
    yield
    reset_cache()


class RefusingClient:
    """A text client that fails the test if it is ever asked anything."""

    def generate_text(self, *args, **kwargs):
        raise AssertionError("the model was asked for a reviewed description")


class StubClient:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.prompts: list = []

    def generate_text(self, prompt, system_instruction=None, **kwargs):
        self.prompts.append(prompt)
        return self.reply


# --------------------------------------------------------------------------
# 1. Exact mapping
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", ALT_NAMES)
def test_alt_spellings_resolve_to_the_alt_document(name):
    resolution = resolve_term(name)
    assert resolution.covered is True
    assert resolution.doc_ids == ("term_alt_sgpt",)
    assert resolution.canonical_feature is None


@pytest.mark.parametrize("name", AST_NAMES)
def test_ast_spellings_resolve_to_the_ast_document(name):
    resolution = resolve_term(name)
    assert resolution.covered is True
    assert resolution.doc_ids == ("term_ast_sgot",)
    assert resolution.canonical_feature is None


@pytest.mark.parametrize(
    "name", ["SGPT level", "liver enzymes", "ALTT", "GGT", "bilirubin", "ALP"]
)
def test_near_misses_and_other_liver_tests_are_still_refused(name):
    answer = explain_term(name)
    assert answer.covered is False
    assert answer.outcome == OUTCOME_NOT_COVERED
    assert answer.sources == ()


@pytest.mark.parametrize("name,doc", [("SGPT", "term_alt_sgpt"), ("SGOT", "term_ast_sgot")])
def test_the_term_explainer_serves_the_reviewed_document(name, doc):
    answer = explain_term(name)
    assert answer.outcome == OUTCOME_SERVED_FROM_KNOWLEDGE_BASE
    assert answer.explanation is not None
    assert {s.doc_id for s in answer.sources} == {doc}


# --------------------------------------------------------------------------
# 2. The documents themselves
# --------------------------------------------------------------------------


@pytest.mark.parametrize("doc_id", ["term_alt_sgpt", "term_ast_sgot"])
def test_documents_describe_the_test_and_tag_no_feature_or_condition(doc_id):
    doc = DOCUMENTS[doc_id]
    assert doc.features == ()
    assert doc.conditions == ()
    assert doc.basis.strip()
    assert doc.last_reviewed == "2026-10-04"
    # No threshold: this platform applies none to these tests.
    assert not re.search(r"\d", doc.body), "a number in the body reads as a cut-off"


@pytest.mark.parametrize("doc_id", ["term_alt_sgpt", "term_ast_sgot"])
def test_every_part_passes_the_module_24_validator(doc_id):
    from app.safety import validate_text

    doc = DOCUMENTS[doc_id]
    for text in [doc.title, doc.summary, doc.basis, *doc.paragraphs]:
        assert validate_text(text).approved, text


@pytest.mark.parametrize("doc_id", ["term_alt_sgpt", "term_ast_sgot"])
def test_the_summary_obeys_the_glossary_rules(doc_id):
    """It is shown on the dashboard in place of a model description, so it is
    held to the same rules: no number, at most two sentences."""
    summary = DOCUMENTS[doc_id].summary
    assert not glossary._ANY_DIGIT.search(summary)
    assert not glossary._SPELLED_NUMBER.search(summary)
    assert summary.count(". ") + 1 <= 2


# --------------------------------------------------------------------------
# 3. The dashboard description
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name,doc", [("SGPT", "term_alt_sgpt"), ("Serum SGOT", "term_ast_sgot")]
)
def test_reviewed_entry_uses_the_summary_word_for_word(name, doc):
    entry = reviewed_entry(name)
    assert entry is not None
    assert entry.available is True
    assert entry.origin == ORIGIN_REVIEWED
    assert entry.source_doc == doc
    assert entry.test_name == name
    assert entry.description == " ".join(DOCUMENTS[doc].summary.split())


@pytest.mark.parametrize(
    "name",
    [
        "TSH",
        "ESR",
        "LDL Cholesterol",  # an alias WITH a feature: not a reviewed description
        "fasting",  # an alias for a word, not a test, but feature-less: see below
    ],
)
def test_reviewed_entry_is_only_for_feature_less_single_document_aliases(name):
    entry = reviewed_entry(name)
    if name == "fasting":
        # Feature-less single-document aliases DO qualify; none of the
        # non-test words is a name a laboratory prints as a result row, so in
        # practice this path is the liver documents. Pinned so a widening of
        # the alias table is noticed here.
        assert entry is not None and entry.source_doc == "term_fasting_sample"
    else:
        assert entry is None


def test_describe_parameters_serves_liver_tests_without_calling_the_model():
    data = describe_parameters(["SGPT", "SGOT"], RefusingClient())
    assert data.reviewed_count == 2
    assert data.generated_count == 0
    assert [e.origin for e in data.entries] == [ORIGIN_REVIEWED, ORIGIN_REVIEWED]


def test_a_reviewed_description_costs_no_budget():
    client = StubClient(
        "TSH measures a hormone made by the pituitary gland that controls the "
        "thyroid. It is used to look at how the thyroid is working."
    )
    data = describe_parameters(["SGPT", "TSH"], client, max_calls=1)
    assert data.reviewed_count == 1
    assert data.generated_count == 1
    assert data.skipped_over_limit == 0
    assert len(client.prompts) == 1 and "TSH" in client.prompts[0]
    by_name = {e.test_name: e for e in data.entries}
    assert by_name["SGPT"].origin == ORIGIN_REVIEWED
    assert by_name["TSH"].origin == ORIGIN_MODEL
    assert by_name["TSH"].source_doc is None


def test_a_summary_that_gains_a_number_is_not_shown(monkeypatch):
    """The reviewed path is held to the glossary's no-number rule, so an edit
    that slips a cut-off into a summary falls back to the model rather than
    reaching the dashboard."""
    from dataclasses import replace

    original = DOCUMENTS["term_alt_sgpt"]
    monkeypatch.setitem(
        DOCUMENTS,
        "term_alt_sgpt",
        replace(original, summary="ALT is usually below 40 units per litre."),
    )
    assert reviewed_entry("SGPT") is None
