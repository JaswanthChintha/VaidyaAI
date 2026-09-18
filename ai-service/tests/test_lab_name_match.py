"""Module 36 -- which printed test names are the same test.

EVERY FIXTURE NAME HERE IS INVENTED, for the reason `test_lab_polarity.py`
states: there is no list of known tests in the module and there must be none in
its tests either, or the suite would pass by recognising the fixtures instead of
the rule working. The one exception is the CONTRAST tests, which use real words
(`free`, `total`, `direct`) because those words ARE the rule under test.

The three things this file is really about:

  1. THE PROMPT CARRIES NAMES AND NOTHING ELSE. Asserted against the prompt the
     module actually built, not against the code that builds it.
  2. THE MODEL PROPOSES AND THIS MODULE DISPOSES. Every gate is exercised with
     an answer that tries to get past it.
  3. A WRONG JOIN IS THE WORST THING THIS CAN DO, so the guard that stops
     `Free X` joining `X` has its own tests -- including the case the first
     version of that guard let through.
"""

from __future__ import annotations

import json
import re
from typing import Any, List, Optional

import pytest

from app.services.lab_name_match import (
    MAX_NAMES,
    contrasts,
    match_names,
    reset_cache,
)


class RecordingClient:
    """A Module 23 text client that records every prompt it is given."""

    def __init__(self, payload: Any, *, raw: Optional[str] = None) -> None:
        self.payload = payload
        self.raw = raw
        self.prompts: List[str] = []

    def generate_text(self, prompt: str, system_instruction: str | None = None) -> str:
        self.prompts.append(prompt)
        if self.raw is not None:
            return self.raw
        return json.dumps(self.payload)


def groups(*sets: List[str]) -> dict:
    return {"groups": [list(s) for s in sets]}


@pytest.fixture(autouse=True)
def _clean_cache():
    reset_cache()
    yield
    reset_cache()


# --------------------------------------------------------------------------
# 1. the prompt
# --------------------------------------------------------------------------


def test_the_prompt_carries_the_names_and_no_patient_anything():
    client = RecordingClient(groups(["Zorblex Factor", "Frimbulin"]))
    match_names(["Zorblex Factor", "Frimbulin"], client)

    assert len(client.prompts) == 1
    prompt = client.prompts[0]
    assert "Zorblex Factor" in prompt
    assert "Frimbulin" in prompt

    # WHAT MUST NOT BE IN THE PROMPT IS PATIENT DATA, NOT THE WORD "PATIENT".
    #
    # TWO WRONG VERSIONS OF THIS TEST CAME FIRST, and both are worth recording
    # because they are the same mistake in two costumes. The first compared
    # substrings and "low" matched inside "Rules you must follow". The second
    # forbade the whole words "patient" and "range" -- which appear in the
    # prompt's own instruction NOT to mention a patient or a range, so the
    # test was failing ON THE SAFETY RULE IT WAS MEANT TO PROTECT.
    #
    # A vocabulary test cannot tell a leak from a prohibition. The leak vectors
    # are figures, units and dates, so those are what is asserted -- none of
    # them can hide inside an English word.
    for forbidden in ("12.1", "38.9", "mg/L", "2026-"):
        assert forbidden not in prompt
    # NO DIGIT ANYWHERE. The names sent here carry none and the prompt's own
    # example JSON carries none, so any digit at all would be this prompt
    # acquiring a figure from somewhere -- which is the whole hazard, stated
    # as one assertion that cannot be argued with.
    assert re.search(r"\d", prompt) is None


def test_one_call_for_the_whole_set_not_one_per_name():
    # "Are these the same test" is a question about the SET. Asked name by
    # name it has no answer, and it would also cost one call per row.
    client = RecordingClient(groups())
    match_names(["Alpha", "Beta", "Gamma", "Delta"], client)
    assert len(client.prompts) == 1


# --------------------------------------------------------------------------
# 2. the gates
# --------------------------------------------------------------------------


def test_a_name_the_model_invented_is_dropped_with_its_group():
    # ECHO VALIDATION. A name that was not sent cannot be matched back to a
    # reading, and a group half made of real names is not half right.
    client = RecordingClient(groups(["Zorblex Factor", "Invented Marker"]))
    out = match_names(["Zorblex Factor", "Frimbulin"], client)

    assert out.groups == []
    assert out.proposed == 1
    assert out.refused_unknown_name == 1


def test_a_group_of_one_is_dropped():
    client = RecordingClient(groups(["Zorblex Factor"]))
    out = match_names(["Zorblex Factor", "Frimbulin"], client)

    assert out.groups == []
    assert out.refused_too_small == 1


def test_a_name_in_two_groups_invalidates_BOTH():
    # Not just the second one. There is no basis for preferring whichever the
    # model emitted first, and putting one test's readings on another test's
    # chart is the worst outcome available here.
    client = RecordingClient(
        groups(["Zorblex Factor", "Frimbulin"], ["Frimbulin", "Quixotor"])
    )
    out = match_names(["Zorblex Factor", "Frimbulin", "Quixotor"], client)

    assert out.groups == []
    assert out.refused_overlapping == 2


def test_the_names_are_matched_case_and_punctuation_insensitively():
    # The model is told to echo exactly and does not always. Folding is for
    # COMPARISON; the name kept is the one the report printed.
    client = RecordingClient(groups(["zorblex  factor", "FRIMBULIN"]))
    out = match_names(["Zorblex Factor", "Frimbulin"], client)

    assert len(out.groups) == 1
    assert sorted(out.groups[0].names) == ["Frimbulin", "Zorblex Factor"]


def test_the_display_name_is_the_longest_of_the_group():
    client = RecordingClient(groups(["ZBX", "Zorblex Factor (ZBX)"]))
    out = match_names(["ZBX", "Zorblex Factor (ZBX)"], client)

    assert out.groups[0].display_name == "Zorblex Factor (ZBX)"


# --------------------------------------------------------------------------
# 3. the contrast guard -- a wrong join is the worst outcome
# --------------------------------------------------------------------------


def test_free_and_total_are_refused_even_though_the_model_said_join():
    client = RecordingClient(groups(["Free Frimbulin", "Total Frimbulin"]))
    out = match_names(["Free Frimbulin", "Total Frimbulin"], client)

    assert out.groups == []
    assert out.refused_contrast == 1


def test_free_and_a_BARE_name_are_refused_too():
    """The case the first version of this guard let straight through.

    It was a set of contrast pairs refused only when BOTH names carried a
    different member, so `Free Frimbulin` against `Total Frimbulin` was caught
    and `Free Frimbulin` against `Frimbulin` was not -- the bare name carries
    no member at all. Free and total are different tests, and 6au names that
    exact pair as the reason not to subset-match. The rule is now equality of
    the qualifiers present on each side.
    """
    client = RecordingClient(groups(["Free Frimbulin", "Frimbulin"]))
    out = match_names(["Free Frimbulin", "Frimbulin"], client)

    assert out.groups == []
    assert out.refused_contrast == 1


def test_total_against_a_bare_name_still_joins():
    """`total` is a clarifier, not a qualifier, and this is the whole point.

    TOTAL WBC COUNT and WBC Count are one test, as are Total Cholesterol and
    Cholesterol. A guard that refused any modifier would block the join this
    module exists for.
    """
    client = RecordingClient(groups(["Total Frimbulin", "Frimbulin"]))
    out = match_names(["Total Frimbulin", "Frimbulin"], client)

    assert len(out.groups) == 1
    assert out.refused_contrast == 0


def test_the_same_qualifier_on_both_sides_joins():
    # An abbreviation and its expansion, both of the FREE form.
    client = RecordingClient(groups(["Free Frimbulin", "Free Frimbulinogen"]))
    out = match_names(["Free Frimbulin", "Free Frimbulinogen"], client)

    assert len(out.groups) == 1


@pytest.mark.parametrize(
    "first,second",
    [
        ("Direct Frimbulin", "Indirect Frimbulin"),
        ("Fasting Zorblex", "Random Zorblex"),
        ("Zorblex", "Fasting Zorblex"),
        ("Pre Zorblex", "Post Zorblex"),
    ],
)
def test_other_qualifiers_that_change_the_measurement(first, second):
    assert contrasts(first, second) is True


@pytest.mark.parametrize(
    "first,second",
    [
        ("TOTAL ZORBLEX COUNT", "Zorblex Count"),
        ("ZBX", "ZBX (Zorblex Factor)"),
        ("Zorblex Factor", "Frimbulin"),
    ],
)
def test_names_that_do_not_contrast(first, second):
    assert contrasts(first, second) is False


# --------------------------------------------------------------------------
# 4. degradation -- every failure means "nothing joined"
# --------------------------------------------------------------------------


def test_an_unparsable_answer_joins_nothing_and_does_not_raise():
    client = RecordingClient(None, raw="I am afraid I cannot help with that.")
    out = match_names(["Zorblex Factor", "Frimbulin"], client)

    assert out.groups == []
    assert out.requested == 2


def test_an_empty_group_list_is_a_valid_answer():
    client = RecordingClient(groups())
    out = match_names(["Zorblex Factor", "Frimbulin"], client)

    assert out.groups == []
    assert out.proposed == 0


def test_fewer_than_two_names_asks_nothing():
    client = RecordingClient(groups())
    out = match_names(["Zorblex Factor"], client)

    assert out.groups == []
    assert client.prompts == []


def test_nothing_to_do_answers_with_an_empty_set_rather_than_throwing():
    client = RecordingClient(groups())
    out = match_names([], client)

    assert out.groups == []
    assert out.requested == 0
    assert client.prompts == []


def test_duplicate_names_do_not_consume_two_slots():
    client = RecordingClient(groups())
    out = match_names(["Zorblex Factor", "zorblex factor", "Frimbulin"], client)

    assert out.requested == 2


def test_the_ceiling_is_reported_not_silent():
    names = [f"Marker {n}" for n in range(MAX_NAMES + 5)]
    client = RecordingClient(groups())
    out = match_names(names, client)

    # NOT AN ABSENCE. The count that answers "did this truncate" is the one the
    # producer keeps about what it did NOT do -- §6at, and Module 35 the same.
    assert out.skipped_over_limit == 5


def test_the_answer_is_cached_against_the_name_set():
    client = RecordingClient(groups(["Zorblex Factor", "Frimbulin"]))
    first = match_names(["Zorblex Factor", "Frimbulin"], client)
    second = match_names(["Frimbulin", "Zorblex Factor"], client)

    # ONE call for two requests, in either order: the key is the sorted folded
    # set, so a second report carrying the same vocabulary costs nothing.
    assert len(client.prompts) == 1
    assert [g.names for g in first.groups] == [g.names for g in second.groups]


def test_a_cached_answer_cannot_be_mutated_by_its_caller():
    # `model_copy(deep=True)` on the way in and out. A caller that sorted the
    # returned list in place would otherwise edit every later reader's copy.
    client = RecordingClient(groups(["Zorblex Factor", "Frimbulin"]))
    first = match_names(["Zorblex Factor", "Frimbulin"], client)
    first.groups.clear()

    second = match_names(["Zorblex Factor", "Frimbulin"], client)
    assert len(second.groups) == 1
