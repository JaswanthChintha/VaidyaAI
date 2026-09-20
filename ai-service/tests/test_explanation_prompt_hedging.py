"""The prompt must name what the SAFETY LAYER measures, not something near it.

WHY THIS FILE EXISTS
====================

`Test 3.pdf` lost its entire lymphocytes explanation on 2026-09-20:

    outcome: withheld_by_safety
    violation_codes: ["UNHEDGED_INTERPRETIVE_CLAIM"]
    attempts: 2

The model was refused twice, the second time with its own violation quoted
back to it. The prompt's certainty rule forbids a VOCABULARY -- 'definitely',
'confirms', 'proves', 'clearly shows', 'this means you have' -- while
`positive.required_hedging` measures a STRUCTURE: an interpretive verb beside
a clinical subject with no hedge in the sentence. A sentence can contain none
of the forbidden words and still be refused.

This is §6at's lesson, which this platform has already paid for once: Module
24's treatment rule is a vocabulary rule, "do not advise" did not stop four
refusals in six on a real report, and NAMING THE WORDS fixed it.

⚠ THE CRUELLEST FAILURE IS A PROMPT THAT RECOMMENDS A HEDGE THE VALIDATOR
DOES NOT ACCEPT -- the model obeys and is refused anyway. So these tests
couple the prompt to the validator's own lists rather than to a copy of them.
"""

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
    """It must live in `PROHIBITIONS`, which is interpolated into the prompt
    and published by `GET /api/v1/explain/policy` -- not written inline, where
    the reviewable list and the prompt would drift apart."""
    assert _hedging_rule()


def test_every_hedge_the_prompt_offers_is_one_the_VALIDATOR_ACCEPTS():
    """⚠ THE POINT OF THE WHOLE FILE.

    If the prompt recommends a word `HEDGE_MARKERS` does not contain, a model
    that follows the instruction exactly is still refused, and the reader
    still loses the explanation. Every hedge named must be honoured.
    """
    rule = _hedging_rule()
    # The words offered in the "MUST also carry one of: ..." clause.
    offered = re.search(r"carry one of:\s*([^.]+)\.", rule)
    assert offered, "the rule no longer lists the acceptable hedges"
    words = [w.strip().lower() for w in offered.group(1).split(",") if w.strip()]
    assert len(words) >= 5, words
    for word in words:
        assert word in HEDGE_MARKERS, f"prompt offers {word!r}, validator does not accept it"


def test_every_verb_the_prompt_names_is_one_the_validator_refuses():
    """The other direction: naming a verb the validator does not measure would
    make the rule read as arbitrary, and a rule that looks arbitrary is one a
    model weighs against the others."""
    rule = _hedging_rule()
    # SCOPED TO THE CLAUSE THAT LISTS THEM. A bare `'([a-z ]+)'` over the
    # whole rule also matches the ` or ` BETWEEN the two quoted example
    # sentences further down -- which is how this test first failed, on its
    # own extraction rather than on the prompt.
    clause = re.search(r"This applies to every form of ([^.]+)\.", rule)
    assert clause, "the rule no longer lists the verbs it applies to"
    named = {m.lower() for m in re.findall(r"'([a-z ]+)'", clause.group(1))}
    assert len(named) >= 8, named
    # COMPARED ON A SHORT PREFIX, NOT A STEM. The prompt names the base form
    # a writer would use ('signify', 'imply') and the validator holds the
    # inflection it must match ('signifies', 'implies'). A naive `rstrip("s")`
    # gets -ies -> -ie and fails on exactly those two, which is how this test
    # failed the first time -- on its own stemmer, not on the prompt. Four
    # characters is enough to catch a verb the validator has never heard of,
    # which is the only thing this assertion is for.
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


# --------------------------------------------------------------------------
# The two sentences, put through the REAL validator
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sentence",
    [
        # The shape that cost the reader the explanation. No forbidden
        # certainty word appears in either.
        "A low lymphocyte count indicates your immune system is under strain.",
        "This shows your body is fighting an infection.",
    ],
)
def test_the_unhedged_shape_really_is_refused(sentence):
    """A probe's output is a claim about the probe until something agrees --
    so the bad example is run through the validator itself rather than
    asserted from the rule's wording."""
    verdict = validate_text(sentence)
    codes = {str(c) for c in verdict.codes}
    assert any("UNHEDGED_INTERPRETIVE_CLAIM" in c for c in codes), codes


@pytest.mark.parametrize(
    "sentence",
    [
        # The shape the prompt now asks for, using the hedges it offers.
        "A low lymphocyte count may indicate that your immune system is under strain.",
        "This can be a sign that your body is fighting an infection.",
        "A lowered result is commonly associated with a recent viral infection.",
    ],
)
def test_the_hedged_shape_the_prompt_asks_for_is_NOT_refused(sentence):
    """⚠ WITHOUT THIS, THE RULE COULD BE UNSATISFIABLE and nobody would know.
    A prompt that demands a form the validator also refuses would turn one
    refusal into a guaranteed one."""
    verdict = validate_text(sentence)
    codes = {str(c) for c in verdict.codes}
    assert not any("UNHEDGED_INTERPRETIVE_CLAIM" in c for c in codes), codes
