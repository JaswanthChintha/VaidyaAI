from __future__ import annotations

import json

import pytest

from app.data.knowledge_base import ALL_DOCUMENTS
from app.data.recommendation_catalog import RECOMMENDATIONS
from app.safety.policy import ViolationCode
from app.safety.validator import validate_text


def _rejects(text: str) -> bool:
    return str(validate_text(text).verdict) == "reject"


def _codes(text: str) -> set:
    return {v.code for v in validate_text(text).violations}


@pytest.mark.parametrize(
    "text",
    [
        "Your kidneys are failing.",
        "Your results are completely fine and nothing is wrong.",
        "You do not have diabetes.",
        "Your liver is damaged.",
        "Your heart is deteriorating.",
        "Your blood sugar is out of control.",
        "Nothing is wrong.",
        "There is no cause for concern.",
        "You are perfectly healthy.",
        "Everything is normal.",
        "Your report is completely clear.",
    ],
)
def test_a_bare_clinical_assertion_about_the_reader_is_rejected(text: str) -> None:
    assert _rejects(text), f"bare clinical assertion approved: {text!r}"


def test_false_reassurance_is_treated_as_seriously_as_false_alarm() -> None:
    assert ViolationCode.UNHEDGED_INTERPRETIVE_CLAIM in _codes(
        "Your results are completely fine and nothing is wrong."
    )


def test_education_about_a_value_is_still_permitted() -> None:
    for allowed in (
        "A normal HbA1c is below 5.7 percent.",
        "Your HbA1c is 6.8 percent.",
        "This value sits above the reference range printed on the report.",
    ):
        assert not _rejects(allowed), f"legitimate text rejected: {allowed!r}"


@pytest.mark.parametrize(
    "label,text",
    [
        ("newline", "you\nhave diabetes"),
        ("CRLF", "you\r\nhave diabetes"),
        ("tab", "you\thave diabetes"),
        ("double space", "you  have diabetes"),
        ("comma", "You, have diabetes."),
        ("parenthetical", "You (have) diabetes."),
        ("quoted emphasis", 'You "have" diabetes.'),
        ("several at once", "Your,  kidneys   are\tfailing."),
    ],
)
def test_a_split_phrase_is_still_caught(label: str, text: str) -> None:
    assert _rejects(text), f"{label}: banned phrase escaped as {text!r}"


@pytest.mark.parametrize(
    "text",
    [
        "This is not a diagnosis.",
        "This is never a diagnosis.",
        "This is not any kind of diagnosis.",
        "No diagnosis is offered here.",
        "This is not  a diagnosis.",
        "This does not diagnose any condition.",
        "Nothing here is a diagnosis.",
    ],
)
def test_a_correct_disclaimer_is_not_refused(text: str) -> None:
    assert not _rejects(text), f"platform disclaimer refused: {text!r}"


@pytest.mark.parametrize(
    "text",
    [
        "Your diagnosis is diabetes.",
        "The diagnosis is chronic kidney disease.",
        "I diagnose you with anemia.",
        "You have diabetes.",
    ],
)
def test_widening_the_diagnosis_rule_did_not_weaken_it(text: str) -> None:
    assert _rejects(text), f"diagnostic assertion approved: {text!r}"


def test_only_the_word_diagnosis_is_eligible_for_the_carve_out() -> None:
    assert _rejects("You do not have diabetes.")


@pytest.mark.parametrize(
    "label,char",
    [
        ("zero-width space", "​"),
        ("zero-width non-joiner", "‌"),
        ("soft hyphen", "­"),
        ("word joiner", "⁠"),
        ("BOM", "﻿"),
        ("left-to-right mark", "‎"),
        ("pop directional isolate", "⁩"),
    ],
)
def test_an_invisible_character_between_words_does_not_hide_a_phrase(
    label: str, char: str
) -> None:
    assert _rejects(f"you{char}have diabetes"), f"{label} hid the phrase"


@pytest.mark.parametrize("char", ["​", "­", "﻿"])
def test_an_invisible_character_inside_a_word_does_not_hide_it_either(
    char: str,
) -> None:
    verdict = validate_text(f"Your doctor may start met{char}formin.")
    assert ViolationCode.MEDICATION_REFERENCE in {v.code for v in verdict.violations}


def test_every_catalogue_recommendation_still_passes() -> None:
    offenders = [
        (code, rec.text)
        for code, rec in RECOMMENDATIONS.items()
        if _rejects(rec.text)
    ]
    assert not offenders, f"catalogue text refused by its own validator: {offenders}"


def test_every_knowledge_base_paragraph_still_passes() -> None:
    offenders = []
    for document in ALL_DOCUMENTS:
        for paragraph in getattr(document, "paragraphs", ()) or ():
            if _rejects(paragraph):
                offenders.append((getattr(document, "doc_id", "?"), paragraph[:80]))
    assert not offenders, f"KB paragraphs refused: {offenders[:5]}"


@pytest.mark.parametrize(
    "injected",
    [
        "there is no  need to see a doctor",
        "you do not need to see a doctor",
        "this report replaces a clinical consultation",
        "take metformin 500 mg twice a day",
        "you have diabetes",
    ],
)
def test_an_injected_term_is_never_echoed_back(injected: str) -> None:
    from app.services.terminology import explain_term

    body = json.dumps(explain_term(injected).model_dump(), default=str).lower()
    tail = " ".join(injected.lower().split()[-3:])
    assert tail not in body, f"injected phrase echoed back: {injected!r}"


def test_a_legitimate_term_is_still_echoed_and_served() -> None:
    from app.services.terminology import explain_term

    assert explain_term("HbA1c").outcome == "served_from_knowledge_base"
    refused = explain_term("TSH")
    assert refused.outcome == "term_not_covered"
    assert refused.term == "TSH", "a safe term should still be named back"


@pytest.mark.parametrize(
    "query",
    [
        "my ALP and GGT liver enzymes are high",
        "C reactive protein CRP",
        "what is my TSH level",
        "how do I bake a chocolate cake",
        "why does my python script raise a KeyError",
    ],
)
def test_free_text_outside_the_catalogue_retrieves_nothing(query: str) -> None:
    from app.rag.retriever import retrieve

    assert retrieve(text=query) == [], f"off-catalogue query retrieved: {query!r}"


def test_free_text_naming_a_real_feature_retrieves_that_feature() -> None:
    from app.rag.retriever import retrieve

    chunks = retrieve(text="what does a raised HbA1c mean")
    assert chunks, "a covered question should still retrieve"
    assert chunks[0].chunk.doc_id == "lab_hba1c"


def _grounded_ctx():
    from app.safety.schemas import SafetyContext

    return SafetyContext(
        grounding_sources=("HbA1c of 6.8 percent.",),
        permitted_numbers=(6.8,),
        check_numeric_grounding=True,
        purpose="test",
    )


@pytest.mark.parametrize(
    "text,ungrounded",
    [
        ("Your HbA1c is 6.8 percent.", False),
        ("Your HbA1c is six point eight percent.", False),
        ("Your HbA1c is nine point nine percent.", True),
        ("Your HbA1c is 9.9 percent.", True),
        ("This is .5 points above.", True),
        ("One hundred and twenty six is the threshold.", True),
        ("HDL is one of the two main types of cholesterol.", False),
        ("This explains this one and why it is the value used.", False),
        ("The range is one unit either side of the reference.", False),
    ],
)
def test_spelled_out_numbers_are_grounded_like_digits(
    text: str, ungrounded: bool
) -> None:
    codes = {v.code for v in validate_text(text, _grounded_ctx()).violations}
    hit = ViolationCode.UNGROUNDED_NUMERIC_CLAIM in codes
    assert hit == ungrounded, f"{text!r}: flagged={hit}, expected={ungrounded}"
