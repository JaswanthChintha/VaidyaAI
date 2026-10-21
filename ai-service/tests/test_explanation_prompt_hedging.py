import re

import pytest

from app.prompts.explanation_prompt import PROHIBITIONS, build_explanation_prompt
from app.safety.policy import HEDGE_MARKERS, INTERPRETIVE_VERBS
from app.safety.validator import validate_text


def _hedging_rule() -> str:
    for rule in PROHIBITIONS:
        if "HEDGE EVERY INTERPRETATION" in rule:
            return rule
    raise AssertionError("the hedging prohibition is not in PROHIBITIONS")


def test_the_hedging_rule_is_in_the_reviewable_list():
    assert _hedging_rule()


def test_every_hedge_the_prompt_offers_is_one_the_VALIDATOR_ACCEPTS():
    rule = _hedging_rule()
    offered = re.search(r"carry one of:\s*([^.]+)\.", rule)
    assert offered, "the rule no longer lists the acceptable hedges"
    words = [w.strip().lower() for w in offered.group(1).split(",") if w.strip()]
    assert len(words) >= 5, words
    for word in words:
        assert word in HEDGE_MARKERS, f"prompt offers {word!r}, validator does not accept it"


def test_every_verb_the_prompt_names_is_one_the_validator_refuses():
    rule = _hedging_rule()
    clause = re.search(r"This applies to every form of ([^.]+)\.", rule)
    assert clause, "the rule no longer lists the verbs it applies to"
    named = {m.lower() for m in re.findall(r"'([a-z ]+)'", clause.group(1))}
    assert len(named) >= 8, named
    prefixes = {v.lower()[:4] for v in INTERPRETIVE_VERBS}
    for verb in named:
        assert verb[:4] in prefixes, (
            f"prompt names {verb!r}, which matches nothing in INTERPRETIVE_VERBS"
        )


def test_the_rule_reaches_the_built_prompt():
    prompt = build_explanation_prompt(
        subject="the lymphocytes result",
        findings=["Lymphocytes 14 % is below the printed interval 20-40."],
        extracts=[],
    )
    assert "HEDGE EVERY INTERPRETATION" in prompt


@pytest.mark.parametrize(
    "sentence",
    [
        "A low lymphocyte count indicates your immune system is under strain.",
        "This shows your body is fighting an infection.",
    ],
)
def test_the_unhedged_shape_really_is_refused(sentence):
    verdict = validate_text(sentence)
    codes = {str(c) for c in verdict.codes}
    assert any("UNHEDGED_INTERPRETIVE_CLAIM" in c for c in codes), codes


@pytest.mark.parametrize(
    "sentence",
    [
        "A low lymphocyte count may indicate that your immune system is under strain.",
        "This can be a sign that your body is fighting an infection.",
        "A lowered result is commonly associated with a recent viral infection.",
    ],
)
def test_the_hedged_shape_the_prompt_asks_for_is_NOT_refused(sentence):
    verdict = validate_text(sentence)
    codes = {str(c) for c in verdict.codes}
    assert not any("UNHEDGED_INTERPRETIVE_CLAIM" in c for c in codes), codes
