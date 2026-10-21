from __future__ import annotations

from typing import Any, List, Optional

import pytest

from app.services import summary_prose as sp


SENTENCES = [
    "This tool checked 8 conditions against a fixed set of thresholds.",
    "3 need a closer look: Kidney Disease, Anemia, Obesity.",
    "Your laboratory marked 11 further results outside its own range.",
]

NAMES = ("Kidney Disease", "Anemia", "Obesity")


class FakeLLM:

    def __init__(self, *replies: str) -> None:
        self.replies: List[str] = list(replies)
        self.prompts: List[str] = []
        self.last: str = ""

    def generate_text(self, prompt: str) -> Any:
        self.prompts.append(prompt)
        if not self.replies:
            return self.last
        self.last = self.replies.pop(0)
        return self.last


def approved(text: str):

    class _V:
        codes = ()

    class _R:
        approved_text = text
        verdict = _V()
        attempts = 1

    return _R()


def refused(*codes: str):
    class _V:
        pass

    _V.codes = codes

    class _R:
        approved_text = None
        verdict = _V()
        attempts = 2

    return _R()


@pytest.fixture
def guard(monkeypatch):

    seen = {"contexts": []}

    def fake(generate, *, context, attempts=2):
        seen["contexts"].append(context)
        return approved(generate())

    monkeypatch.setattr(sp, "guarded_generation", fake)
    return seen


def test_without_a_model_it_refuses_and_never_calls_out(monkeypatch):
    monkeypatch.setattr(sp, "_resolve_llm", lambda llm, settings: None)
    out = sp.rewrite_summary(SENTENCES, names=NAMES)
    assert out.outcome == sp.OUTCOME_NO_MODEL
    assert out.text is None
    assert out.llm_calls_made == 0
    assert out.safety.validated is False


def test_no_sentences_is_not_an_error_and_never_reaches_a_model():
    calls = FakeLLM("anything at all")
    out = sp.rewrite_summary([], llm=calls)
    assert out.outcome == sp.OUTCOME_NOTHING_TO_WRITE
    assert out.text is None
    assert calls.prompts == []


def test_blank_sentences_do_not_count_as_something_to_write():
    out = sp.rewrite_summary(["", "   ", None], llm=FakeLLM("x"))
    assert out.outcome == sp.OUTCOME_NOTHING_TO_WRITE


def test_a_safety_refusal_yields_no_text(monkeypatch):
    monkeypatch.setattr(
        sp, "guarded_generation", lambda g, *, context, attempts=2: refused("X_CODE")
    )
    out = sp.rewrite_summary(SENTENCES, names=NAMES, llm=FakeLLM("ignored"))
    assert out.outcome == sp.OUTCOME_WITHHELD_BY_SAFETY
    assert out.text is None
    assert out.safety.violation_codes == ("X_CODE",)


def test_the_composed_sentences_are_the_only_grounding(guard):
    sp.rewrite_summary(SENTENCES, names=NAMES, llm=FakeLLM(" ".join(SENTENCES)))
    context = guard["contexts"][0]
    assert context.grounding_sources == tuple(SENTENCES)
    assert context.purpose == "patient_summary_prose"


def test_a_dropped_number_throws_the_rewrite_away(guard):
    out = sp.rewrite_summary(
        SENTENCES,
        names=NAMES,
        llm=FakeLLM(
            "We checked several conditions. 3 need a closer look: Kidney "
            "Disease, Anemia, Obesity. Your laboratory marked 11 further "
            "results outside its own range."
        ),
    )
    assert out.outcome == sp.OUTCOME_FACTS_MISSING
    assert out.text is None
    assert "number:8" in out.missing_facts


def test_a_dropped_condition_name_throws_the_rewrite_away(guard):
    out = sp.rewrite_summary(
        SENTENCES,
        names=NAMES,
        llm=FakeLLM(
            "This tool checked 8 conditions against a fixed set of "
            "thresholds. 3 need a closer look: Kidney Disease and Anemia. "
            "Your laboratory marked 11 further results outside its own range."
        ),
    )
    assert out.outcome == sp.OUTCOME_FACTS_MISSING
    assert "name:Obesity" in out.missing_facts


def test_a_whole_dropped_sentence_is_caught_by_its_figures(guard):
    out = sp.rewrite_summary(
        SENTENCES,
        names=NAMES,
        llm=FakeLLM(
            "This tool checked 8 conditions against a fixed set of "
            "thresholds. 3 need a closer look: Kidney Disease, Anemia, "
            "Obesity."
        ),
    )
    assert out.outcome == sp.OUTCOME_FACTS_MISSING
    assert "number:11" in out.missing_facts


def test_an_invented_number_throws_the_rewrite_away(guard):
    out = sp.rewrite_summary(
        SENTENCES,
        names=NAMES,
        llm=FakeLLM(
            "This tool checked 8 conditions against a fixed set of "
            "thresholds, covering 42 measurements. 3 need a closer look: "
            "Kidney Disease, Anemia, Obesity. Your laboratory marked 11 "
            "further results outside its own range."
        ),
    )
    assert out.outcome == sp.OUTCOME_FACTS_INVENTED
    assert out.text is None
    assert "number:42" in out.invented_facts


def test_an_invented_reassurance_throws_the_rewrite_away(guard):
    out = sp.rewrite_summary(
        SENTENCES,
        names=NAMES,
        llm=FakeLLM(
            "This tool checked 8 conditions against a fixed set of "
            "thresholds and the picture is broadly reassuring. 3 need a "
            "closer look: Kidney Disease, Anemia, Obesity. Your laboratory "
            "marked 11 further results outside its own range."
        ),
    )
    assert out.outcome == sp.OUTCOME_FACTS_INVENTED
    assert out.text is None
    assert "verdict:reassuring" in out.invented_facts


@pytest.mark.parametrize(
    "word", ["normal", "healthy", "fine", "mild", "severe", "unremarkable"]
)
def test_every_verdict_word_is_refused_when_it_was_not_in_the_input(guard, word):
    out = sp.rewrite_summary(
        SENTENCES,
        names=NAMES,
        llm=FakeLLM(
            f"This tool checked 8 conditions and they look {word}. 3 need a "
            "closer look: Kidney Disease, Anemia, Obesity. Your laboratory "
            "marked 11 further results outside its own range."
        ),
    )
    assert out.outcome == sp.OUTCOME_FACTS_INVENTED
    assert f"verdict:{word}" in out.invented_facts


def test_a_verdict_word_ALREADY_in_the_input_is_allowed_through(guard):
    sentences = ["Your haemoglobin is low at 10.6 g/dl."]
    out = sp.rewrite_summary(
        sentences, llm=FakeLLM("Your haemoglobin is low, at 10.6 g/dl.")
    )
    assert out.outcome == sp.OUTCOME_GENERATED
    assert "low" in out.text


@pytest.mark.parametrize(
    "outcome", [o for o in sp.OUTCOME_VALUES if o != sp.OUTCOME_GENERATED]
)
def test_text_is_none_on_every_refusal(outcome):
    out = sp.SummaryProse(outcome=outcome, safety=sp.ProseSafety(validated=False))
    assert out.text is None


def test_a_clean_rewrite_is_returned_and_says_so(guard):
    out = sp.rewrite_summary(
        SENTENCES,
        names=NAMES,
        llm=FakeLLM(
            "This tool checked 8 conditions against a fixed set of "
            "thresholds, and 3 need a closer look: Kidney Disease, Anemia "
            "and Obesity. Your laboratory marked 11 further results outside "
            "its own range."
        ),
    )
    assert out.outcome == sp.OUTCOME_GENERATED
    assert out.text.startswith("This tool checked 8 conditions")
    assert out.missing_facts == ()
    assert out.invented_facts == ()


def test_a_dropped_fact_is_named_back_to_the_model_on_the_retry(guard):
    llm = FakeLLM(
        "This tool checked 8 conditions. 3 need a closer look: Kidney "
        "Disease, Anemia. Your laboratory marked 11 further results outside "
        "its own range.",
        "This tool checked 8 conditions. 3 need a closer look: Kidney "
        "Disease, Anemia, Obesity. Your laboratory marked 11 further results "
        "outside its own range.",
    )
    out = sp.rewrite_summary(SENTENCES, names=NAMES, llm=llm)
    assert out.outcome == sp.OUTCOME_GENERATED
    assert "Obesity" in llm.prompts[1]
    assert "DROPPED" in llm.prompts[1]


def test_the_retry_is_capped(guard):
    llm = FakeLLM("nothing useful", "still nothing useful")
    out = sp.rewrite_summary(SENTENCES, names=NAMES, llm=llm)
    assert out.outcome == sp.OUTCOME_FACTS_MISSING
    assert len(llm.prompts) == 2


def test_the_prompt_forbids_an_opinion_in_as_many_words():
    prompt = sp.build_prompt(SENTENCES)
    assert "Add nothing." in prompt
    assert "Do not add an opinion" in prompt
    for sentence in SENTENCES:
        assert sentence in prompt


def test_numbers_are_compared_as_written_not_as_floats():
    assert sp.numbers_in("a 5.0 b 11 c -2.5") == ("5.0", "11", "-2.5")
    assert sp._invented("we found 5 things", ["we found 5.0 things"]) == (
        "number:5",
    )
