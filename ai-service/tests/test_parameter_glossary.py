"""Module 27's glossary for tests this platform does NOT assess.

The feature is one narrow question -- "what does this test measure?" -- asked
about a test NAME with no patient data attached. These tests hold that shape in
place, because every safety property it has comes from the narrowness:

  * no patient value ever reaches the model;
  * no number is allowed OUT of the model;
  * a refused or unrecognised answer is stated, never faked;
  * one answer per test name, cached, because the free tier is 20 calls a day.

THE NUMERIC CONTROL IS TESTED FROM BOTH SIDES ON PURPOSE. It has already failed
twice in ways nothing would have noticed: once because the shared validator's
numeric grounding is inactive for a context with no grounding (so the answer
was approved with an invented reference range in it), and once because the
word-boundary escapes were mangled into literal backspace characters, leaving a
regex that could never match. Both are silent failures of a control whose whole
job is to catch a silent failure.
"""

from __future__ import annotations

import pytest

from app.services import parameter_glossary as glossary
from app.services.parameter_glossary import describe_parameters, reset_cache


class StubClient:
    """A Module 23 text client that returns whatever it was given."""

    def __init__(self, *replies: str) -> None:
        self.replies = list(replies)
        self.prompts: list = []

    def generate_text(self, prompt, system_instruction=None, **kwargs):
        self.prompts.append(prompt)
        return self.replies[min(len(self.prompts) - 1, len(self.replies) - 1)]


CLEAN = (
    "LDL cholesterol is a form of cholesterol carried through the blood by "
    "low-density lipoproteins. It is usually measured as part of a lipid panel."
)


@pytest.fixture(autouse=True)
def _clear_cache():
    reset_cache()
    yield
    reset_cache()


# --------------------------------------------------------------------------
# The prompt must never carry the patient
# --------------------------------------------------------------------------


def test_the_prompt_contains_the_test_name_and_no_patient_data():
    """THE core property. Everything else follows from it.

    If a value reached the model, the answer could be about the person, and a
    sentence about a person's result is an interpretation -- which this feature
    exists specifically not to produce.
    """
    client = StubClient(CLEAN)
    describe_parameters(["LDL Cholesterol"], client)

    prompt = client.prompts[0]
    assert "LDL Cholesterol" in prompt

    # NO DIGIT ANYWHERE IN THE PROMPT.
    #
    # This is the assertion that actually means something. A patient value, a
    # reference bound, an age -- every one of them is a number, so a prompt
    # containing no digit at all cannot be carrying any of them. An earlier
    # version of this test hunted for words like "high" instead and failed on
    # the prompt's own instruction "do not say whether a result would be good,
    # bad, high or low", which is the opposite of a leak.
    assert not any(character.isdigit() for character in prompt), prompt

    # And the API gives a caller no way to pass one: it accepts NAMES.
    assert "value" not in prompt.lower().split("rules you must follow")[0]


def test_the_prompt_forbids_numbers_conditions_and_advice():
    client = StubClient(CLEAN)
    describe_parameters(["Potassium"], client)
    prompt = client.prompts[0].lower()
    assert "do not state any number" in prompt
    assert "do not name a condition" in prompt
    assert "do not give advice" in prompt


# --------------------------------------------------------------------------
# No number may come back
# --------------------------------------------------------------------------


def test_an_answer_containing_a_digit_is_discarded():
    """An invented reference range is the failure that matters most here.

    The shared validator cannot catch it: `_check_numeric_grounding` is only
    active when the caller supplies grounding sources or permitted numbers, and
    this caller deliberately supplies neither. So the control is local, and this
    test is the only thing standing behind it.
    """
    client = StubClient("Potassium is a mineral. A normal level is 3.5 to 5.1 mmol/L.")
    data = describe_parameters(["Potassium"], client)

    assert data.entries[0].available is False
    assert data.entries[0].description is None
    assert data.withheld_count == 1
    assert "number" in data.entries[0].notice.lower()


def test_an_answer_spelling_a_number_out_is_also_discarded():
    """Digits are the obvious evasion; words are the easy one."""
    client = StubClient(
        "Sodium is an electrolyte. A typical value is around one hundred forty."
    )
    data = describe_parameters(["Sodium"], client)
    assert data.entries[0].available is False


@pytest.mark.parametrize(
    "text",
    [
        "Vitamin D relates to bone health and how the body handles calcium.",
        "This test relates to hormone levels produced by the thyroid gland.",
        "Alkaline phosphatase is an enzyme found in the liver and in bone.",
    ],
)
def test_ordinary_words_containing_number_words_are_not_discarded(text):
    """`bone` contains `one`; `hormone` contains `one`.

    Without word boundaries the numeric control eats perfectly good
    descriptions of vitamin D, thyroid and liver tests -- the exact tests a
    reader is most likely to be looking up. This has already been broken once.
    """
    client = StubClient(text)
    data = describe_parameters(["Some Test"], client)
    assert data.entries[0].available is True, data.entries[0].notice


def test_the_number_patterns_are_alive():
    """A regex that cannot match is indistinguishable from a passing test.

    The word-boundary escapes were once written as literal backspace
    characters, so the pattern matched nothing and every check above passed for
    the wrong reason. Asserting a known-positive keeps that honest.
    """
    assert glossary._ANY_DIGIT.search("value 5")
    assert glossary._SPELLED_NUMBER.search("about forty")
    assert not glossary._SPELLED_NUMBER.search("bone and hormone")


# --------------------------------------------------------------------------
# Absence is stated, never faked
# --------------------------------------------------------------------------


def test_an_unrecognised_test_is_reported_as_unrecognised():
    client = StubClient("NOT RECOGNISED")
    data = describe_parameters(["Zorblax Index"], client)
    assert data.entries[0].available is False
    assert data.entries[0].description is None
    assert "not recognised" in data.entries[0].notice.lower()


def test_a_refused_generation_yields_no_description_rather_than_a_placeholder():
    client = StubClient("")
    data = describe_parameters(["Anything"], client)
    assert data.entries[0].available is False
    assert data.entries[0].description is None
    assert data.entries[0].notice


# --------------------------------------------------------------------------
# Quota
# --------------------------------------------------------------------------


def test_one_answer_per_test_name_is_reused():
    """The answer is about a test, not a person, so it is the same for everyone."""
    client = StubClient(CLEAN)
    describe_parameters(["LDL Cholesterol"], client)
    second = describe_parameters(["  ldl   cholesterol "], client)

    assert len(client.prompts) == 1, "the second request must not reach the model"
    assert second.cached_count == 1
    assert second.entries[0].description == CLEAN


def test_a_failure_is_never_cached():
    """One bad minute must not make a test name permanently undescribed."""
    failing = StubClient("")
    describe_parameters(["Ferritin"], failing)

    working = StubClient(CLEAN)
    data = describe_parameters(["Ferritin"], working)
    assert len(working.prompts) == 1
    assert data.entries[0].available is True


def test_a_single_report_cannot_spend_the_whole_daily_budget():
    """20 calls a day is the real ceiling; one report must not consume it."""
    client = StubClient(CLEAN)
    names = [f"Test Number {index}" for index in range(30)]
    data = describe_parameters(names, client, max_calls=3)

    assert len(client.prompts) == 3
    assert data.skipped_over_limit == 27


def test_duplicate_names_in_one_request_cost_one_call():
    client = StubClient(CLEAN)
    describe_parameters(["Urea", "urea", "UREA "], client)
    assert len(client.prompts) == 1


def test_the_ceiling_covers_a_real_report_but_still_exists():
    """RAISED FROM 8 when every test came to be described rather than only the
    ones the laboratory flagged.

    A ceiling BELOW a real report's test count is the worst of the three
    options: it describes some and not others, and the rule deciding which is
    "whatever came first in the extraction". The two real reports on this
    project carry 17 and 18 unassessed tests.

    It still exists, and it must: the free tier is twenty calls a day per
    model, so this is the one thing between a sixty-parameter report and a
    spent day.
    """
    from app.services.parameter_glossary import MAX_PER_REQUEST

    assert MAX_PER_REQUEST >= 21, "below a real report's unassessed-test count"
    assert MAX_PER_REQUEST <= 40, "no longer a meaningful ceiling"


def test_a_cache_hit_does_not_spend_the_ceiling():
    """WHAT MAKES THE HIGHER CEILING AFFORDABLE. The cache is keyed on the
    normalised test NAME and holds no patient data, so a common panel is
    described once for this process and every later report reuses it. If a hit
    consumed the budget, the ceiling would bite on reports that cost nothing.
    """
    from app.services.parameter_glossary import describe_parameters, reset_cache

    reset_cache()
    calls = []

    class Client:
        def generate_text(self, prompt, system_instruction=""):
            calls.append(prompt)
            return "This test measures something in the blood."

    names = ["PCV", "MCV", "MCH"]
    first = describe_parameters(names, Client(), max_calls=3)
    assert first.generated_count == 3
    assert len(calls) == 3

    # Same names again, plus one new, with a budget of ONE. The three cached
    # ones must not consume it.
    again = describe_parameters([*names, "ESR"], Client(), max_calls=1)
    assert again.cached_count == 3
    assert again.generated_count == 1
    assert again.skipped_over_limit == 0
    reset_cache()
