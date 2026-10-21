from __future__ import annotations

import dataclasses

import pytest

from app.data.conditions import CONDITIONS
from app.data.feature_catalog import FEATURES
from app.data.knowledge_base import (
    DOCUMENTS,
    KNOWLEDGE_BASE_VERSION,
    TOPICS,
    _check_document,
    coverage,
    document,
    documents_for_condition,
    documents_for_feature,
    knowledge_base_document,
    UnknownDocumentError,
)
from app.data.knowledge_safety import (
    CANARY_MIN_MATCHES,
    CANARY_SENTENCE,
    EXEMPTIBLE_PATTERNS,
    UnsafeKnowledgeError,
    normalise,
    scan_administration,
    scan_text,
)
from app.data.knowledge_types import KnowledgeDocument


def _clone(doc: KnowledgeDocument, **changes) -> KnowledgeDocument:
    return dataclasses.replace(doc, **changes)


SAMPLE = "lab_hba1c"


def test_corpus_is_not_empty_and_ids_are_unique():
    assert len(DOCUMENTS) >= 40
    assert len(set(DOCUMENTS)) == len(DOCUMENTS)


@pytest.mark.parametrize("doc_id", sorted(DOCUMENTS))
def test_every_document_is_structurally_valid(doc_id):
    _check_document(DOCUMENTS[doc_id])


@pytest.mark.parametrize("doc_id", sorted(DOCUMENTS))
def test_no_document_references_a_name_outside_the_catalogues(doc_id):
    doc = DOCUMENTS[doc_id]
    for feature in doc.features:
        assert feature in FEATURES, f"{doc_id}: {feature!r} not in feature_catalog"
    for condition in doc.conditions:
        assert condition in CONDITIONS, f"{doc_id}: {condition!r} not in conditions"


@pytest.mark.parametrize("doc_id", sorted(DOCUMENTS))
def test_every_document_carries_a_basis_and_a_review_date(doc_id):
    doc = DOCUMENTS[doc_id]
    assert doc.basis.strip()
    assert doc.last_reviewed.strip()
    assert doc.topic in TOPICS


@pytest.mark.parametrize("feature", sorted(FEATURES))
def test_every_canonical_feature_has_at_least_one_document(feature):
    assert documents_for_feature(feature), f"no knowledge document covers {feature!r}"


@pytest.mark.parametrize("condition", sorted(CONDITIONS))
def test_every_canonical_condition_has_at_least_one_document(condition):
    assert documents_for_condition(condition), f"no document covers {condition!r}"


def test_coverage_reports_no_gaps():
    gaps = coverage()
    assert gaps["uncovered_features"] == []
    assert gaps["uncovered_conditions"] == []
    assert gaps["documents"] == len(DOCUMENTS)


def test_every_topic_is_represented():
    counts = coverage()["topics"]
    for topic in TOPICS:
        assert counts[topic] > 0, f"topic {topic!r} has no documents"


def test_paragraphs_are_whitespace_normalised_and_non_empty():
    for doc in DOCUMENTS.values():
        for para in doc.paragraphs:
            assert para == " ".join(para.split())
            assert para


def test_document_lookup_and_unknown_id():
    assert document(SAMPLE).doc_id == SAMPLE
    with pytest.raises(UnknownDocumentError):
        document("no_such_document")


def test_knowledge_base_document_is_serialisable_and_complete():
    dump = knowledge_base_document()
    assert dump["version"] == KNOWLEDGE_BASE_VERSION
    assert len(dump["documents"]) == len(DOCUMENTS)
    entry = dump["documents"][SAMPLE]
    for key in ("title", "topic", "features", "conditions", "summary", "body",
                "basis", "keywords", "last_reviewed", "safety_exemptions"):
        assert key in entry


def test_the_scanner_detects_an_obviously_unsafe_sentence():
    fired = scan_text(CANARY_SENTENCE)
    assert len(fired) >= CANARY_MIN_MATCHES, fired


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Take metformin 500 mg daily.", "medication_name"),
        ("Your dose should be increased.", "dose_word"),
        ("This confirms you have diabetes.", "certainty_claim"),
        ("You have kidney disease.", "diagnostic_assertion"),
        ("There is no need to see a doctor.", "replaces_clinician"),
        ("Start taking it immediately.", "self_administration"),
        ("Consider vitamin D supplements.", "supplementation_advice"),
        ("This is a life-threatening result.", "alarmist_prose"),
        ("Treatment with atorvastatin is advised.", "medication_name"),
        ("500 milligrams is the right amount.", "dose_quantity_word"),
    ],
)
def test_scanner_catches_unsafe_text(text, expected):
    assert expected in scan_text(text), f"{text!r} -> {scan_text(text)}"


@pytest.mark.parametrize(
    "text",
    [
        "A fasting plasma glucose of 126 mg/dL is the diabetes-range cut-off.",
        "WHO describes a BMI of 30.0 kg/m2 or above as obesity.",
        "Vitamin D sufficiency begins at 30 ng/mL.",
        "Serum B12 below 200 pg/mL is reported as low.",
        "This material is educational and is not a diagnosis.",
        "Bands are expressed in milligrams per decilitre.",
        "It is used as context rather than as an established fact.",
        "Some preparations taken under medical supervision can raise it.",
    ],
)
def test_scanner_does_not_fire_on_legitimate_corpus_language(text):
    assert scan_text(text) == [], scan_text(text)


def test_scanner_is_insensitive_to_line_wrapping():
    assert scan_text("you\nhave diabetes") == scan_text("you have diabetes")
    assert scan_text("this is not a\ndiagnosis") == []
    assert normalise("a\n b\t c") == "a b c"


def test_planted_unsafe_document_is_rejected():
    planted = _clone(
        DOCUMENTS[SAMPLE],
        doc_id="planted_unsafe",
        body="Take metformin 500 mg twice a day to bring your HbA1c down.",
    )
    with pytest.raises(UnsafeKnowledgeError) as exc:
        _check_document(planted)
    assert "planted_unsafe" in str(exc.value)


@pytest.mark.parametrize(
    "field,value",
    [
        ("summary", "This confirms you have diabetes."),
        ("title", "How to treat diabetes with insulin"),
        ("basis", "Prescribe 500 mg of metformin."),
    ],
)
def test_unsafe_text_in_any_scanned_field_is_rejected(field, value):
    planted = _clone(DOCUMENTS[SAMPLE], doc_id="planted", **{field: value})
    with pytest.raises(UnsafeKnowledgeError):
        _check_document(planted)


def test_document_with_uncatalogued_feature_is_rejected():
    planted = _clone(DOCUMENTS[SAMPLE], doc_id="planted", features=("HbA1c",))
    with pytest.raises(ValueError, match="feature_catalog"):
        _check_document(planted)


def test_document_with_uncatalogued_condition_is_rejected():
    planted = _clone(DOCUMENTS[SAMPLE], doc_id="planted", conditions=("diabetes",))
    with pytest.raises(ValueError, match="conditions.CONDITIONS"):
        _check_document(planted)


def test_document_without_basis_is_rejected():
    planted = _clone(DOCUMENTS[SAMPLE], doc_id="planted", basis="   ")
    with pytest.raises(ValueError, match="basis"):
        _check_document(planted)


def test_exemptions_are_rare_and_all_justified():
    exempted = {
        d.doc_id: d.safety_exemptions for d in DOCUMENTS.values() if d.safety_exemptions
    }
    assert len(exempted) <= 3, f"too many exempted documents: {sorted(exempted)}"
    for doc_id, exemptions in exempted.items():
        for pattern, justification in exemptions:
            assert pattern in EXEMPTIBLE_PATTERNS, (doc_id, pattern)
            assert len(justification.strip()) > 40, doc_id


def test_a_non_exemptible_pattern_cannot_be_exempted():
    planted = _clone(
        DOCUMENTS[SAMPLE],
        doc_id="planted",
        safety_exemptions=(("certainty_claim", "because I said so"),),
    )
    with pytest.raises(ValueError, match="may never be exempted"):
        _check_document(planted)


def test_an_exemption_without_justification_is_rejected():
    planted = _clone(
        DOCUMENTS[SAMPLE], doc_id="planted", safety_exemptions=(("medication_name", "  "),)
    )
    with pytest.raises(ValueError, match="justification"):
        _check_document(planted)


def test_a_medication_exemption_still_forbids_administration_language():
    planted = _clone(
        DOCUMENTS[SAMPLE],
        doc_id="planted",
        body="Many people start taking insulin at this stage of the condition.",
        safety_exemptions=(("medication_name", "x" * 60),),
    )
    with pytest.raises(UnsafeKnowledgeError, match="administration"):
        _check_document(planted)


@pytest.mark.parametrize(
    "text,flagged",
    [
        ("The hormone insulin lets glucose into cells.", False),
        ("Cells respond poorly to insulin.", False),
        ("You should start taking insulin.", True),
        ("Insulin is injected before meals.", True),
        ("taking metformin", True),
    ],
)
def test_scan_administration(text, flagged):
    assert scan_administration(text) is flagged


def _validator_strings(doc):
    yield "title", doc.title
    yield "summary", doc.summary
    yield "basis", doc.basis
    for i, para in enumerate(doc.paragraphs):
        yield f"paragraph[{i}]", para
    for kw in doc.keywords:
        yield "keyword", kw


@pytest.mark.parametrize("doc_id", sorted(DOCUMENTS))
def test_every_knowledge_string_passes_the_module_24_validator(doc_id):
    from app.safety.validator import validate_text

    doc = DOCUMENTS[doc_id]
    for field, text in _validator_strings(doc):
        verdict = validate_text(text)
        assert verdict.approved, (
            f"{doc_id} [{field}] would be REJECTED by Module 24 "
            f"({list(verdict.codes)}): {text[:160]!r}. Module 23 quotes "
            "retrieved knowledge verbatim, so this string is a latent "
            "generation failure. Reword the corpus; do not loosen Module 24."
        )
