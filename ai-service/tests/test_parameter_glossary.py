from __future__ import annotations

import pytest

from app.services import parameter_glossary as glossary
from app.services.parameter_glossary import describe_parameters, reset_cache


class StubClient:

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


def test_the_prompt_contains_the_test_name_and_no_patient_data():
    client = StubClient(CLEAN)
    describe_parameters(["LDL Cholesterol"], client)

    prompt = client.prompts[0]
    assert "LDL Cholesterol" in prompt

    assert not any(character.isdigit() for character in prompt), prompt

    assert "value" not in prompt.lower().split("rules you must follow")[0]


def test_the_prompt_forbids_numbers_conditions_and_advice():
    client = StubClient(CLEAN)
    describe_parameters(["Potassium"], client)
    prompt = client.prompts[0].lower()
    assert "do not state any number" in prompt
    assert "do not name a condition" in prompt
    assert "do not give advice" in prompt


def test_an_answer_containing_a_digit_is_discarded():
    client = StubClient("Potassium is a mineral. A normal level is 3.5 to 5.1 mmol/L.")
    data = describe_parameters(["Potassium"], client)

    assert data.entries[0].available is False
    assert data.entries[0].description is None
    assert data.withheld_count == 1
    assert "number" in data.entries[0].notice.lower()


def test_an_answer_spelling_a_number_out_is_also_discarded():
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
    client = StubClient(text)
    data = describe_parameters(["Some Test"], client)
    assert data.entries[0].available is True, data.entries[0].notice


def test_the_number_patterns_are_alive():
    assert glossary._ANY_DIGIT.search("value 5")
    assert glossary._SPELLED_NUMBER.search("about forty")
    assert not glossary._SPELLED_NUMBER.search("bone and hormone")


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


def test_one_answer_per_test_name_is_reused():
    client = StubClient(CLEAN)
    describe_parameters(["LDL Cholesterol"], client)
    second = describe_parameters(["  ldl   cholesterol "], client)

    assert len(client.prompts) == 1, "the second request must not reach the model"
    assert second.cached_count == 1
    assert second.entries[0].description == CLEAN


def test_a_failure_is_never_cached():
    failing = StubClient("")
    describe_parameters(["Ferritin"], failing)

    working = StubClient(CLEAN)
    data = describe_parameters(["Ferritin"], working)
    assert len(working.prompts) == 1
    assert data.entries[0].available is True


def test_a_single_report_cannot_spend_the_whole_daily_budget():
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
    from app.services.parameter_glossary import MAX_PER_REQUEST

    assert MAX_PER_REQUEST >= 21, "below a real report's unassessed-test count"
    assert MAX_PER_REQUEST <= 40, "no longer a meaningful ceiling"


def test_a_cache_hit_does_not_spend_the_ceiling():
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

    again = describe_parameters([*names, "ESR"], Client(), max_calls=1)
    assert again.cached_count == 3
    assert again.generated_count == 1
    assert again.skipped_over_limit == 0
    reset_cache()
