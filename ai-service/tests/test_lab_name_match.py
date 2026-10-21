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


def test_the_prompt_carries_the_names_and_no_patient_anything():
    client = RecordingClient(groups(["Zorblex Factor", "Frimbulin"]))
    match_names(["Zorblex Factor", "Frimbulin"], client)

    assert len(client.prompts) == 1
    prompt = client.prompts[0]
    assert "Zorblex Factor" in prompt
    assert "Frimbulin" in prompt

    for forbidden in ("12.1", "38.9", "mg/L", "2026-"):
        assert forbidden not in prompt
    assert re.search(r"\d", prompt) is None


def test_one_call_for_the_whole_set_not_one_per_name():
    client = RecordingClient(groups())
    match_names(["Alpha", "Beta", "Gamma", "Delta"], client)
    assert len(client.prompts) == 1


def test_a_name_the_model_invented_is_dropped_with_its_group():
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
    client = RecordingClient(
        groups(["Zorblex Factor", "Frimbulin"], ["Frimbulin", "Quixotor"])
    )
    out = match_names(["Zorblex Factor", "Frimbulin", "Quixotor"], client)

    assert out.groups == []
    assert out.refused_overlapping == 2


def test_the_names_are_matched_case_and_punctuation_insensitively():
    client = RecordingClient(groups(["zorblex  factor", "FRIMBULIN"]))
    out = match_names(["Zorblex Factor", "Frimbulin"], client)

    assert len(out.groups) == 1
    assert sorted(out.groups[0].names) == ["Frimbulin", "Zorblex Factor"]


def test_the_display_name_is_the_longest_of_the_group():
    client = RecordingClient(groups(["ZBX", "Zorblex Factor (ZBX)"]))
    out = match_names(["ZBX", "Zorblex Factor (ZBX)"], client)

    assert out.groups[0].display_name == "Zorblex Factor (ZBX)"


def test_free_and_total_are_refused_even_though_the_model_said_join():
    client = RecordingClient(groups(["Free Frimbulin", "Total Frimbulin"]))
    out = match_names(["Free Frimbulin", "Total Frimbulin"], client)

    assert out.groups == []
    assert out.refused_contrast == 1


def test_free_and_a_BARE_name_are_refused_too():
    client = RecordingClient(groups(["Free Frimbulin", "Frimbulin"]))
    out = match_names(["Free Frimbulin", "Frimbulin"], client)

    assert out.groups == []
    assert out.refused_contrast == 1


def test_total_against_a_bare_name_still_joins():
    client = RecordingClient(groups(["Total Frimbulin", "Frimbulin"]))
    out = match_names(["Total Frimbulin", "Frimbulin"], client)

    assert len(out.groups) == 1
    assert out.refused_contrast == 0


def test_the_same_qualifier_on_both_sides_joins():
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

    assert out.skipped_over_limit == 5


def test_the_answer_is_cached_against_the_name_set():
    client = RecordingClient(groups(["Zorblex Factor", "Frimbulin"]))
    first = match_names(["Zorblex Factor", "Frimbulin"], client)
    second = match_names(["Frimbulin", "Zorblex Factor"], client)

    assert len(client.prompts) == 1
    assert [g.names for g in first.groups] == [g.names for g in second.groups]


def test_a_cached_answer_cannot_be_mutated_by_its_caller():
    client = RecordingClient(groups(["Zorblex Factor", "Frimbulin"]))
    first = match_names(["Zorblex Factor", "Frimbulin"], client)
    first.groups.clear()

    second = match_names(["Zorblex Factor", "Frimbulin"], client)
    assert len(second.groups) == 1
