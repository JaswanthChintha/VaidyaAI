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


@pytest.fixture(autouse=True)
def _clear_cache():
    """THE CACHE IS PROCESS-WIDE, SO IT MUST NOT CROSS A TEST BOUNDARY.

    Without this, the first test to describe `C-REACTIVE PROTEIN (raised)`
    successfully answers every later one from the cache -- and the refusal
    tests, which hand the model text that must be rejected, would pass without
    the model ever being called. Autouse, because a gate test that silently
    stops exercising its gate is exactly the dead control this module has
    already lost one of.
    """
    fc.reset_cache()
    yield
    fc.reset_cache()


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
    """The ceiling still exists. The free tier is twenty calls a day."""
    over = fc.MAX_PER_REPORT + 4
    many = [
        {"test_name": f"TEST {i}", "direction": "raised"} for i in range(over)
    ]
    llm = FakeLLM(*[GOOD] * over)
    out = fc.describe_findings(many, llm=llm)
    assert len(out.entries) == fc.MAX_PER_REPORT
    assert len(llm.prompts) == fc.MAX_PER_REPORT
    assert out.skipped_over_limit == over - fc.MAX_PER_REPORT


def test_the_ceiling_clears_both_real_reports():
    """SIZED FROM MEASUREMENT, NOT GUESSED -- and the old 6 was not.

    Both real laboratory reports on this project exceeded 6: Test 3 sent seven
    findings and lost a raised C-REACTIVE PROTEIN, Test 2 sends twelve and
    would lose six. The handover recorded the ceiling as unreached because it
    counted the six entries that came back instead of the `skipped_over_limit`
    stored beside them.

    The lower bound is therefore a real report's count. The upper bound is
    there because a ceiling nothing can reach is not a ceiling: twenty calls a
    day per model is still the budget.
    """
    assert fc.MAX_PER_REPORT >= 12, "below a real report's out-of-range count"
    assert fc.MAX_PER_REPORT <= 24, "no longer a meaningful ceiling"


def test_a_cache_hit_does_not_spend_the_ceiling(guard):
    """WHAT MAKES THE RAISED CEILING AFFORDABLE.

    The key is the normalised test name and the direction, which is the entire
    prompt -- so the answer is the same for every reader and holds nothing
    patient-specific. If a hit consumed the budget, a second report of the
    same panel would truncate while costing nothing.
    """
    first = [{"test_name": f"TEST {i}", "direction": "raised"} for i in range(fc.MAX_PER_REPORT)]
    llm = FakeLLM(*[GOOD] * fc.MAX_PER_REPORT)
    fc.describe_findings(first, llm=llm)
    assert len(llm.prompts) == fc.MAX_PER_REPORT

    # The same panel again, plus four more than the ceiling would allow if the
    # hits were charged for.
    again = FakeLLM(*[GOOD] * 4)
    out = fc.describe_findings(
        first + [{"test_name": f"EXTRA {i}", "direction": "lowered"} for i in range(4)],
        llm=again,
    )
    assert out.cached_count == fc.MAX_PER_REPORT
    assert out.generated_count == 4
    assert out.skipped_over_limit == 0
    assert len(again.prompts) == 4
    assert len(out.entries) == fc.MAX_PER_REPORT + 4


def test_only_an_answer_is_cached_never_a_refusal(guard):
    """A refusal is a moment, not a fact about the test name.

    When the Gemini quota is spent every model in the chain refuses. Caching
    that would pin an empty answer to this test name for the life of the
    process, and the next report would never ask again.
    """
    fc.describe_findings(RAISED, llm=FakeLLM("Your level is over 9000."))
    llm = FakeLLM(GOOD)
    out = fc.describe_findings(RAISED, llm=llm)
    assert len(llm.prompts) == 1, "a refusal was cached"
    assert out.entries[0].available is True
    assert out.cached_count == 0


def test_a_cached_entry_carries_the_name_this_report_printed(guard):
    """The page matches the entry to the ROW it is rendering, by name.

    One laboratory prints `Lymphocytes` and another `LYMPHOCYTES`; the key
    folds them together, which is the point. Handing back the first report's
    spelling would leave the second report's row unmatched -- a paragraph
    generated, approved, and then dropped for a difference in case.
    """
    fc.describe_findings([{"test_name": "LYMPHOCYTES", "direction": "lowered"}], llm=FakeLLM(GOOD))
    out = fc.describe_findings(
        [{"test_name": "Lymphocytes", "direction": "lowered"}], llm=FakeLLM()
    )
    entry = out.entries[0]
    assert entry.cached is True
    assert entry.test_name == "Lymphocytes"
    assert entry.available is True


def test_the_laboratorys_own_spacing_does_not_buy_a_second_call(guard):
    """`RANDOM BLOOD GLUCOSE ( RBS )` is printed exactly like that.

    Whitespace is collapsed in the key as well as case folded, because a name
    spelled with a stray space is the SAME question -- and this project has
    already paid three times for a lookup defeated by a laboratory's own
    spelling. Here the cost is only a wasted call, which is precisely why it
    would never be noticed.
    """
    llm = FakeLLM(GOOD)
    fc.describe_findings(
        [{"test_name": "RANDOM BLOOD GLUCOSE ( RBS )", "direction": "raised"}], llm=llm
    )
    again = FakeLLM(GOOD)
    out = fc.describe_findings(
        [{"test_name": "Random Blood  Glucose ( RBS )  ", "direction": "raised"}],
        llm=again,
    )
    assert again.prompts == [], "a second call was spent on the same question"
    assert out.cached_count == 1


def test_the_direction_is_part_of_the_key(guard):
    """A raised result and a lowered one are different questions.

    The prompt turns on that single word, so sharing a cache entry between the
    two would answer one with the other's paragraph -- the worst available
    failure for a module whose whole input is a name and a direction.
    """
    llm = FakeLLM(GOOD, GOOD)
    fc.describe_findings(
        [
            {"test_name": "FERRITIN", "direction": "raised"},
            {"test_name": "FERRITIN", "direction": "lowered"},
        ],
        llm=llm,
    )
    assert len(llm.prompts) == 2
    assert "raised" in llm.prompts[0] and "lowered" in llm.prompts[1]


def test_the_callers_order_is_the_priority_order(guard):
    """WHAT IS DROPPED WHEN THE CEILING IS REACHED MUST BE A DECISION.

    The page sends this tool's own threshold crossings first and the results
    the laboratory merely flagged after them. That ordering is the priority,
    and it is only observable here: reordering the findings must reorder the
    entries, so a caller can rely on the tail being what is lost rather than
    on whatever came first out of the extraction.
    """
    names = [f"TEST {i}" for i in range(fc.MAX_PER_REPORT + 2)]
    llm = FakeLLM(*[GOOD] * fc.MAX_PER_REPORT)
    out = fc.describe_findings(
        [{"test_name": n, "direction": "raised"} for n in names], llm=llm
    )
    assert [e.test_name for e in out.entries] == names[: fc.MAX_PER_REPORT]
    assert out.skipped_over_limit == 2


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


def test_the_prompt_forbids_the_words_the_validator_actually_bans():
    """THE PROMPT AND THE VALIDATOR HAVE TO AGREE, and they did not.

    Module 24's `UNSAFE_TREATMENT_INSTRUCTION` is a VOCABULARY rule at
    PROHIBITED severity: it fires on `treat`, `therapy`, `medication` and the
    rest wherever they appear, including in plain description. The prompt said
    "do not give advice or recommend a test or treatment", which the model
    obeyed -- it advised nobody -- and four of six findings on a real report
    were refused anyway, for sentences like "iron deficiency, which is often
    treated with supplements".

    An instruction that forbids an INTENT cannot satisfy a validator that
    measures WORDS. This pins the two together: every word the validator bans
    outright must be named in the prompt.
    """
    from app.services.finding_context import _prompt

    prompt = _prompt("ESR", "raised").lower()
    for word in (
        "treat",
        "therapy",
        "medication",
        "medicine",
        "drug",
        "cure",
        "regimen",
        "surgery",
        "injection",
        "infusion",
        "dialysis",
        "chemotherapy",
        "prescribe",
    ):
        assert word in prompt, f"{word!r} is refused by Module 24 but not named in the prompt"


def test_the_system_instruction_bans_a_passing_mention_too():
    """"Never recommend" and "never mention" are different instructions, and
    only the second matches a vocabulary rule. The refused sentences were not
    recommendations; they mentioned a treatment in passing while describing a
    condition.
    """
    from app.services.finding_context import SYSTEM_INSTRUCTION

    lowered = SYSTEM_INSTRUCTION.lower()
    assert "not even in passing" in lowered
    assert "mention treatment" in lowered
