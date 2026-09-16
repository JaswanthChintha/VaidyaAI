"""Module 34 -- general context for an out-of-range test, and its five gates.

The property under test is never "the text is useful". It is that the text
CANNOT BECOME A STATEMENT ABOUT THE READER. Everything else this file asserts
follows from that: no patient data reaches the prompt, no number may come
back, the answer may not address the reader, and it may not assert certainty
about anyone. A refusal renders nothing at all.
"""

from __future__ import annotations

from typing import Any, List

import pytest

from app.services import finding_context as fc


class FakeLLM:
    """Returns canned text and records every prompt it was given."""

    def __init__(self, *replies: str) -> None:
        self.replies: List[str] = list(replies)
        self.prompts: List[str] = []
        self.system: List[str] = []
        self.last = ""

    def generate_text(self, prompt: str, system_instruction: str = "") -> Any:
        self.prompts.append(prompt)
        self.system.append(system_instruction)
        if not self.replies:
            return self.last
        self.last = self.replies.pop(0)
        return self.last


def approved(text: str):
    class _R:
        approved_text = text

    return _R()


@pytest.fixture
def guard(monkeypatch):
    """Safety layer that approves whatever it is handed."""
    seen = {"contexts": []}

    def fake(generate, *, context, attempts=2):
        seen["contexts"].append(context)
        return approved(generate())

    monkeypatch.setattr(fc, "guarded_generation", fake)
    return seen


GOOD = "A raised result of this kind is commonly associated with inflammation or infection somewhere in the body."

RAISED = [{"test_name": "C-REACTIVE PROTEIN", "direction": "raised"}]


# --------------------------------------------------------------------------
# GATE 0 -- no patient data ever reaches the prompt
# --------------------------------------------------------------------------


def test_the_prompt_carries_only_a_name_and_a_direction(guard):
    """THE WHOLE SAFETY ARGUMENT. The model is not in a position to interpret
    anyone, because it was never told anything about anyone."""
    llm = FakeLLM(GOOD)
    fc.describe_findings(RAISED, llm=llm)
    prompt = llm.prompts[0]
    assert "C-REACTIVE PROTEIN" in prompt
    assert "raised" in prompt
    # Nothing about the reader, in any form.
    for forbidden in ("38.9", "mg/L", "male", "20", "Diabetes", "BMI"):
        assert forbidden not in prompt, forbidden


def test_nothing_is_grounded_and_no_number_is_permitted(guard):
    fc.describe_findings(RAISED, llm=FakeLLM(GOOD))
    ctx = guard["contexts"][0]
    assert ctx.grounding_sources == ()
    assert ctx.permitted_numbers == ()
    assert ctx.purpose == "finding_context"


def test_without_a_model_nothing_is_produced_and_nothing_is_called(monkeypatch):
    monkeypatch.setattr(fc, "_resolve_llm", lambda llm, settings: None)
    out = fc.describe_findings(RAISED)
    assert out.entries == ()
    assert out.generated_count == 0


# --------------------------------------------------------------------------
# GATE 1 -- no number
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "reply",
    [
        "A raised result is commonly associated with levels above 5 mg/L.",
        "A raised result is commonly associated with a count over ten.",
    ],
)
def test_any_number_in_the_answer_throws_it_away(guard, reply):
    """An invented reference range is the most damaging hallucination here,
    and the SHARED validator cannot catch it: its numeric control is inactive
    for a context with no grounding and no permitted numbers."""
    out = fc.describe_findings(RAISED, llm=FakeLLM(reply))
    assert out.entries[0].available is False
    assert out.entries[0].text is None
    assert out.entries[0].refused_by == "number"


# --------------------------------------------------------------------------
# GATE 2 -- no second person. The gate that makes "general" mechanical.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "reply",
    [
        "Your raised result is commonly associated with inflammation.",
        "This suggests you may have an infection.",
        "A raised result means you should be concerned.",
    ],
)
def test_text_that_addresses_the_reader_is_refused(guard, reply):
    """A sentence that cannot address the reader cannot be a statement about
    the reader's health. This is checkable; "is the inference correct" is not,
    which is exactly why the gate is this one."""
    out = fc.describe_findings(RAISED, llm=FakeLLM(reply))
    assert out.entries[0].available is False
    assert out.entries[0].text is None
    assert out.entries[0].refused_by in ("second_person", "certainty")


# --------------------------------------------------------------------------
# GATE 3 -- association, not certainty
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "reply",
    [
        "A raised result indicates an active infection.",
        "A raised result confirms inflammation is present.",
        "A raised result means inflammation.",
        "A raised result is caused by bacterial infection.",
    ],
)
def test_a_statement_of_certainty_is_refused(guard, reply):
    out = fc.describe_findings(RAISED, llm=FakeLLM(reply))
    assert out.entries[0].available is False
    assert out.entries[0].refused_by == "certainty"


def test_an_association_is_allowed_through(guard):
    out = fc.describe_findings(RAISED, llm=FakeLLM(GOOD))
    assert out.entries[0].available is True
    assert "commonly associated with" in out.entries[0].text
    assert out.generated_count == 1


# --------------------------------------------------------------------------
# GATE 4 -- an unrecognised test gets nothing, never a guess
# --------------------------------------------------------------------------


def test_an_unrecognised_test_name_produces_no_text(guard):
    out = fc.describe_findings(
        [{"test_name": "ZZZ PANEL", "direction": "raised"}],
        llm=FakeLLM("NOT RECOGNISED"),
    )
    assert out.entries[0].available is False
    assert out.entries[0].refused_by == "not_recognised"


def test_a_safety_refusal_yields_no_text(monkeypatch):
    monkeypatch.setattr(
        fc, "guarded_generation", lambda g, *, context, attempts=2: approved(None)
    )
    out = fc.describe_findings(RAISED, llm=FakeLLM("ignored"))
    assert out.entries[0].available is False
    assert out.entries[0].refused_by == "safety"


# --------------------------------------------------------------------------
# The direction is never guessed at, and the quota is capped
# --------------------------------------------------------------------------


@pytest.mark.parametrize("direction", [None, "", "abnormal", "HIGH", "up"])
def test_a_direction_this_module_does_not_know_is_skipped_not_guessed(guard, direction):
    """The prompt turns on that one word. Inventing it would be inventing the
    finding, so the whole entry is dropped instead."""
    llm = FakeLLM(GOOD)
    out = fc.describe_findings(
        [{"test_name": "FERRITIN", "direction": direction}], llm=llm
    )
    assert out.entries == ()
    assert llm.prompts == []


def test_the_same_test_and_direction_is_asked_once(guard):
    llm = FakeLLM(GOOD, GOOD, GOOD)
    out = fc.describe_findings(RAISED * 3, llm=llm)
    assert len(out.entries) == 1
    assert len(llm.prompts) == 1


def test_a_report_cannot_spend_the_days_quota(guard):
    """A real report can carry a dozen out-of-range results and the free tier
    is twenty calls a day."""
    many = [
        {"test_name": f"TEST {chr(65 + i)}", "direction": "raised"} for i in range(12)
    ]
    llm = FakeLLM(*[GOOD] * 12)
    out = fc.describe_findings(many, llm=llm)
    assert len(out.entries) == fc.MAX_PER_REPORT
    assert len(llm.prompts) == fc.MAX_PER_REPORT
    assert out.skipped_over_limit == 12 - fc.MAX_PER_REPORT


def test_a_refusal_carries_no_text_at_all(guard):
    """NO PLACEHOLDER. The page renders nothing when nothing was approved, so
    the reader loses a paragraph they never saw and no absence is created."""
    out = fc.describe_findings(RAISED, llm=FakeLLM("Your level is over 9000."))
    entry = out.entries[0]
    assert entry.text is None
    assert entry.available is False
    assert out.withheld_count == 1


def test_the_policy_says_what_the_prompt_contained():
    """The published policy is the claim a reader's clinician would check."""
    policy = fc.FindingContextData().policy
    assert "NAME" in policy and "DIRECTION" in policy
    assert "never about the reader" in policy
    assert "diagnosis" in policy.lower() and "no condition is derived" in policy.lower()


# --------------------------------------------------------------------------
# THE NUMBER GATE, NARROWED FROM "ANY DIGIT" TO "A MEASUREMENT"
#
# It was `\d` and refused three quarters of everything this module produced on
# a real report: `vitamin B12`, `low T4`, `type 2 diabetes` and "one of several
# causes" are two analyte names, a condition name and a quantifier. None is a
# measurement, and the gate exists to stop MEASUREMENTS being invented.
#
# Both directions are asserted, because a gate narrowed too far is worse than
# the over-broad one it replaced.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "A lowered result is commonly associated with vitamin B12 deficiency.",
        "Commonly associated with iron deficiency, one of several causes.",
        "A raised result is commonly associated with type 2 diabetes.",
        "May be associated with thyroid conditions such as low T4.",
        "Associated with vitamin D3 deficiency and COVID-19 related inflammation.",
        "It can be a sign of infection or two distinct inflammatory processes.",
        "A raised result is commonly associated with inflammation in the body.",
    ],
)
def test_a_name_or_a_quantifier_is_not_a_measurement(text):
    from app.services.finding_context import _check

    assert _check(text) is None, text


@pytest.mark.parametrize(
    "text",
    [
        "A raised result is commonly associated with levels above 20 mm/hr.",
        "Values of 12.5 or lower are commonly associated with anaemia.",
        "Commonly associated with a level of 7 or more.",
        "Commonly associated with a range of 10-20 mm/hr.",
        # The spelled forms exist to stop the digit rule being evaded.
        "Results below twelve are commonly associated with anaemia.",
        "Commonly associated with two hundred milligrams per decilitre.",
        "Associated with readings over fifty units.",
        "Levels under ten are associated with this.",
        "Concentrations above five grams are relevant.",
    ],
)
def test_a_measurement_is_still_refused_however_it_is_written(text):
    from app.services.finding_context import _check

    assert _check(text) == "number", text


def test_the_boundaries_are_word_boundaries_and_not_backspaces():
    """THE ACCIDENT THIS FILE'S SIBLING ALREADY HAD, and it happened again here.

    `parameter_glossary.py` carries a comment recording that its spelled-number
    boundaries were once written into the source as literal BACKSPACE
    characters by a shell escaping accident, so the pattern matched nothing and
    the control was silently dead. Writing this gate reproduced it exactly:
    five `\b` became `\x08`, every spelled-number test passed for the wrong
    reason, and the only thing that caught it was a phrase that should have
    been refused coming back allowed.

    A regex cannot be trusted by inspection -- the two spellings look identical
    in a diff. This asserts on the COMPILED pattern.
    """
    from app.services.finding_context import _MEASUREMENT_DIGIT, _SPELLED_NUMBER

    for pattern in (_SPELLED_NUMBER.pattern, _MEASUREMENT_DIGIT.pattern):
        assert "\x08" not in pattern
    # And the boundary still does its job: a spelled number inside a longer
    # word is not a spelled number.
    from app.services.finding_context import _check

    assert _check("Associated with a shortening of the tendon.") is None
