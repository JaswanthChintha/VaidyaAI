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


#: THE 19 DESCRIPTIONS ACTUALLY STORED ON `Test 2.pdf` AND `Test 3.pdf`.
#:
#: Generated from the database, not written by hand. They came back from
#: Gemini, passed Module 24 and passed the gates, and they are what the two
#: readers see today -- so any gate this project tightens has to keep letting
#: them through. Tightening a gate until it refuses live text removes a
#: paragraph from a page, which is the failure this module exists to avoid.
LIVE_APPROVED = (
    # GLYSOLATED HAEMOGLOBIN ( HBA1C) -- Test 2.pdf
    "A raised glycated hemoglobin result is commonly associated with "
    "persistently elevated blood sugar levels over time. It can be a sign of "
    "diabetes mellitus.",
    # Haemoglobin -- Test 2.pdf
    "A lowered haemoglobin result is commonly associated with anemia, which "
    "can occur due to low iron levels or blood loss. It can also be a sign of "
    "various underlying nutritional deficiencies or chronic health "
    "conditions.",
    # T.RBC -- Test 2.pdf
    "A lowered total red blood cell count is commonly associated with anemia "
    "or blood loss. It can also be a sign of nutritional deficiencies or "
    "various chronic conditions.",
    # Polymorphs -- Test 2.pdf
    "A raised level of polymorphs, a type of white blood cell, is commonly "
    "associated with the body's response to acute bacterial infections or "
    "tissue inflammation. It can also be a sign of physical stress or injury.",
    # Lymphocytes -- Test 2.pdf
    "A lowered lymphocyte count can be a sign of a recent viral infection or "
    "periods of significant physical stress. It is also commonly associated "
    "with certain long-term health conditions or issues affecting the immune "
    "system.",
    # Monocytes -- Test 2.pdf
    "A lowered monocyte count can be associated with certain conditions "
    "affecting the bone marrow or acute physical stress on the body. It can "
    "also sometimes be observed following specific types of infections or "
    "prolonged illness.",
    # PCV -- Test 2.pdf
    "A lowered packed cell volume can be a sign of anemia, where the blood "
    "has a reduced proportion of red blood cells. It is also commonly "
    "associated with recent blood loss or certain nutritional shortages.",
    # MCH -- Test 2.pdf
    "A lowered MCH result is commonly associated with iron deficiency anemia "
    "or other conditions where red blood cells contain less hemoglobin than "
    "normal. It can also be a sign of certain inherited blood disorders, such "
    "as thalassemia.",
    # MCHC -- Test 2.pdf
    "A lowered MCHC result is commonly associated with iron deficiency, where "
    "red blood cells contain less hemoglobin than usual. It can also be a "
    "sign of certain inherited blood conditions, such as thalassemia.",
    # ESR -- Test 2.pdf
    "A raised erythrocyte sedimentation rate is commonly associated with "
    "inflammation in the body. It can be a sign of various underlying issues, "
    "such as infections, autoimmune disorders, or tissue injury.",
    # CRP (C-REACTIVE PROTEIN) -- Test 2.pdf
    "A raised C-reactive protein level is commonly associated with "
    "inflammation somewhere in the body. This response can be triggered by "
    "various factors such as infections, tissue injury, or immune system "
    "activity.",
    # SGPT -- Test 2.pdf
    "A raised SGPT level is commonly associated with inflammation or stress "
    "affecting the liver. This finding can be a sign of various liver "
    "conditions, such as fatty liver or hepatitis.",
    # GLYCATED HAEMOGLOBIN (HBA1C) -- Test 3.pdf
    "A raised glycated haemoglobin (HbA1c) result is commonly associated with "
    "prediabetes or diabetes, reflecting higher average blood sugar levels "
    "over the preceding two to three months. It can also be a sign of an "
    "increased risk of developing cardiovascular complications.",
    # RANDOM BLOOD GLUCOSE ( RBS ) -- Test 3.pdf
    "A raised random blood glucose level is commonly associated with diabetes "
    "or prediabetes, which affect how the body processes sugar. It can also "
    "be a sign of recent food intake, physical stress, acute illness, or "
    "certain hormonal imbalances.",
    # HEMOGLOBIN -- Test 3.pdf
    "A lowered hemoglobin level is commonly associated with anemia, which can "
    "be a sign of iron deficiency, blood loss, or chronic kidney disease. It "
    "is also frequently associated with nutritional deficiencies, bone marrow "
    "disorders, and ongoing inflammatory conditions.",
    # NEUTROPHILS -- Test 3.pdf
    "A raised neutrophil count is commonly associated with bacterial "
    "infections, acute inflammation, or physical stress. It can also be a "
    "sign of tissue injury or various underlying medical conditions.",
    # LYMPHOCYTES -- Test 3.pdf
    "A lowered lymphocyte count can be a sign of a recent viral infection or "
    "periods of significant physical stress. It is also commonly associated "
    "with certain long-term health conditions or issues affecting the immune "
    "system.",
    # ESR -- Test 3.pdf
    "A raised erythrocyte sedimentation rate is commonly associated with "
    "inflammation in the body. It can be a sign of various underlying issues, "
    "such as infections, autoimmune disorders, or tissue injury.",
    # C-REACTIVE PROTEIN(CRP) -- Test 3.pdf
    "A raised C-reactive protein level is commonly associated with "
    "inflammation somewhere in the body. It can be a sign of infections, "
    "tissue injury, or various inflammatory conditions.",
)


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


@pytest.mark.parametrize(
    "reply",
    [
        # THE GATE WAS WRITTEN IN THE THIRD-PERSON SINGULAR AND NOTHING ELSE,
        # so every one of these passed. Only the subject is plural; the claim
        # is identical to the singular cases above and just as assertive.
        "Raised results indicate a bacterial infection.",
        "Raised results mean inflammation is present.",
        "Lowered results confirm iron deficiency.",
        "Raised results diagnose diabetes.",
        "Raised results prove an infection.",
        "Raised results demonstrate liver injury.",
        "Raised results show that the liver is inflamed.",
        "Raised results are caused by infection.",
        # Past tense and participles, swept at the same time.
        "A raised result indicated an infection.",
        "The infection was confirmed by the result.",
        "An infection has been proven by this result.",
        "These results showed that the liver is inflamed.",
        # §6as named this one and called it a wording decision. It is refused
        # now, with the rest -- but note it was never the interesting case.
        "A raised result may indicate an infection.",
    ],
)
def test_a_plural_subject_does_not_evade_the_certainty_gate(guard, reply):
    """`indicates` was listed and `indicate` was not, in EVERY verb.

    Measured before the fix: seven of seven flat assertions passed as soon as
    the subject was plural. The base form is not the hedged form -- it is the
    form the verb takes after a plural subject.
    """
    out = fc.describe_findings(RAISED, llm=FakeLLM(reply))
    assert out.entries[0].available is False
    assert out.entries[0].refused_by == "certainty"


@pytest.mark.parametrize(
    "reply",
    [
        # MCH AND MCHC ARE FINDINGS ON Test 2.pdf and their names ARE the word
        # "mean". A description that spells the acronym out must survive.
        "MCH stands for mean corpuscular haemoglobin, a measure of the average "
        "amount of haemoglobin carried in a red blood cell.",
        "MCHC refers to mean corpuscular haemoglobin concentration.",
        "Mean platelet volume describes the average size of platelets.",
        "Mean cell volume is a measure of red blood cell size.",
        "Mean arterial pressure is an average over the cardiac cycle.",
    ],
)
def test_mean_in_a_measurement_name_is_not_a_claim(guard, reply):
    """Adding `mean` bare refused four of six real laboratory phrases.

    The exception is narrow on purpose: only words that cannot begin a claim
    follow "mean" here. If it is ever incomplete the cost is a refusal, which
    renders nothing and creates no absence.
    """
    out = fc.describe_findings(
        [{"test_name": "MCH", "direction": "lowered"}], llm=FakeLLM(reply)
    )
    assert out.entries[0].available is True, out.entries[0].refused_by


@pytest.mark.parametrize(
    "reply",
    [
        # THE LEAK A FIRST DRAFT OF THE EXCEPTION LIST ALLOWED. It excused
        # `mean` before `blood` and `value` as well, which let a flat assertion
        # about a person through the exception meant to protect a test name.
        "Raised results mean blood sugar is high.",
        "Lowered results mean blood loss has occurred.",
        "Raised results mean value judgements are needed.",
    ],
)
def test_the_mean_exception_does_not_excuse_a_claim(guard, reply):
    out = fc.describe_findings(RAISED, llm=FakeLLM(reply))
    assert out.entries[0].available is False
    assert out.entries[0].refused_by == "certainty"


@pytest.mark.parametrize(
    "reply",
    [
        # WORD BOUNDARIES ARE LOAD-BEARING, and this is the glossary's
        # `bone`/`hormone` lesson in a new vocabulary (§6v). `prove` is a
        # substring of IMPROVE, which is an entirely likely word here; `mean`
        # sits inside `meaning` and `demeanour`. Without the boundaries a
        # perfectly general sentence is thrown away.
        "Levels often improve once the underlying cause is addressed.",
        "An improved result is commonly seen after the cause resolves.",
        "The meaning of this test is often misunderstood.",
    ],
)
def test_a_listed_word_inside_a_longer_word_is_not_a_claim(guard, reply):
    out = fc.describe_findings(RAISED, llm=FakeLLM(reply))
    assert out.entries[0].available is True, out.entries[0].refused_by


def test_the_certainty_pattern_carries_no_backspace():
    """The backspace accident, twice in this codebase (§6as).

    `\\b` written through a shell heredoc arrives as `\\x08` and the pattern
    matches nothing, silently. A regex cannot be reviewed by eye -- the two are
    indistinguishable in a diff -- so the COMPILED pattern is asserted instead.
    """
    assert "\x08" not in fc._CERTAINTY.pattern


def test_the_prompt_names_the_certainty_words_the_gate_measures():
    """§6as's lesson, applied to this gate instead of the treatment one.

    The gate refuses base forms now. A prompt that forbade only "indicates"
    while the gate refused "indicate" would refuse the model for obeying it --
    which is exactly how four of six findings were lost on a real report.
    """
    prompt = fc._prompt("FERRITIN", "raised")
    for word in ("mean", "indicate", "confirm", "diagnose", "prove",
                 "demonstrate", "shows that", "is caused by"):
        assert word in prompt, word
    assert "plural" in prompt.lower(), "the prompt does not mention the form that evaded the gate"


def test_an_association_is_allowed_through(guard):
    out = fc.describe_findings(RAISED, llm=FakeLLM(GOOD))
    assert out.entries[0].available is True
    assert "commonly associated with" in out.entries[0].text
    assert out.generated_count == 1


def test_every_live_approved_description_still_passes_the_gate(guard):
    """REGRESSION, from the 19 descriptions actually stored on the two real
    reports. A tightened gate that refuses text a reader is seeing today has
    removed a paragraph, and that is the failure this module exists to avoid.

    These are the real approved texts, not paraphrases -- the ones that came
    back from Gemini, passed Module 24 and are in Mongo now.
    """
    for text in LIVE_APPROVED:
        assert fc._check(text) is None, text


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


class RaisingLLM:
    """A model that never answers -- Gemini's `ServerError`, as measured."""

    def __init__(self, *replies: Any) -> None:
        # Each reply is text to return, or an exception to raise.
        self.replies = list(replies)
        self.calls = 0

    def generate_text(self, prompt: str, system_instruction: str = "") -> Any:
        self.calls += 1
        reply = self.replies.pop(0) if self.replies else RuntimeError("ServerError")
        if isinstance(reply, BaseException):
            raise reply
        return reply


def test_an_outage_is_not_recorded_as_a_safety_refusal():
    """⚠ MEASURED 2026-09-24 on `Test 3.pdf`: NEUTROPHILS, ESR and CRP raised
    `ServerError` on both attempts, and were stored as `refused_by: "safety"`
    -- which the backend caches as a verdict. The REAL `guarded_generation`
    is used here, because the conflation lived in it."""
    llm = RaisingLLM(RuntimeError("ServerError"), RuntimeError("ServerError"))
    out = fc.describe_findings(RAISED, llm=llm)
    assert llm.calls == 2  # both attempts were made
    entry = out.entries[0]
    assert entry.available is False
    assert entry.text is None
    assert entry.refused_by == fc.REFUSED_MODEL_UNAVAILABLE == "model_unavailable"
    assert out.withheld_count == 1


def test_a_real_refusal_after_one_outage_is_still_a_safety_refusal():
    """One attempt raised, the other produced text Module 24 refused. The
    validator DID judge something, so this is not an outage."""
    unsafe = "Raised levels are commonly associated with infection, which is often treated with medication."
    llm = RaisingLLM(RuntimeError("ServerError"), unsafe)
    out = fc.describe_findings(RAISED, llm=llm)
    assert llm.calls == 2
    assert out.entries[0].available is False
    assert out.entries[0].refused_by == "safety"


def test_a_real_refusal_on_both_attempts_is_a_safety_refusal():
    unsafe = "Raised levels are commonly associated with infection, which is often treated with medication."
    out = fc.describe_findings(RAISED, llm=RaisingLLM(unsafe, unsafe))
    assert out.entries[0].refused_by == "safety"


def test_an_outage_then_an_answer_is_approved():
    llm = RaisingLLM(RuntimeError("ServerError"), GOOD)
    out = fc.describe_findings(RAISED, llm=llm)
    assert out.entries[0].available is True
    assert out.entries[0].text == GOOD
    assert out.entries[0].refused_by is None


def test_an_outage_is_not_cached_so_the_next_request_asks_again():
    first = fc.describe_findings(RAISED, llm=RaisingLLM())
    assert first.entries[0].refused_by == "model_unavailable"
    second = fc.describe_findings(RAISED, llm=RaisingLLM(GOOD))
    assert second.entries[0].available is True
    assert second.entries[0].cached is False


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

# --------------------------------------------------------------------------
# THE NUMBER GATE AND THE TEST NAME WE SUPPLIED OURSELVES
#
# Found 2026-09-20 on `03-renal-anaemia-deficiency.pdf`: of four findings,
# vitamin D was the ONLY one refused, and the whole finding then vanished
# from the patient's summary. The cause was not the model inventing a
# number -- it was the model NAMING THE TEST IT WAS ASKED ABOUT.
# --------------------------------------------------------------------------


def test_echoing_a_test_name_that_contains_digits_is_not_a_number():
    """`Vitamin D, 25-Hydroxy` leads with digits, and nothing protected it.

    `_MEASUREMENT_DIGIT` excludes a digit that follows a letter, which is why
    `B12` and `T3` were always safe. `25-Hydroxy` puts its digits FIRST, so a
    correct, careful sentence was refused for repeating the name supplied in
    the prompt.
    """
    from app.services.finding_context import _check

    sentence = (
        "A lowered 25-hydroxy vitamin D level is commonly associated with "
        "insufficient sunlight exposure or low dietary intake."
    )
    assert _check(sentence, "Vitamin D, 25-Hydroxy") is None
    # The same sentence without the echo always passed -- that asymmetry is
    # what made this look like a model failure rather than a gate failure.
    assert _check(sentence.replace("25-hydroxy ", ""), "Vitamin D, 25-Hydroxy") is None


def test_a_number_the_model_invented_is_still_refused():
    """⚠ THE HALF THAT MUST NOT COLLAPSE.

    Only WHOLE TOKENS of the test name are removed. A bare `25` is not the
    token `25-hydroxy`, so a threshold the model produced is still caught even
    when its digits happen to appear in the name.
    """
    from app.services.finding_context import _check

    name = "Vitamin D, 25-Hydroxy"
    assert _check("A lowered result below 25 ng/mL is commonly associated with low intake.", name) == "number"
    assert _check("A lowered 25-hydroxy vitamin D level below 30 is commonly associated with low intake.", name) == "number"
    # And with no test name at all the gate is exactly as strict as before.
    assert _check("A raised level above 1.3 mg/dL is commonly associated with kidney disease.") == "number"


def test_the_other_gates_are_untouched_by_the_name_strip():
    """Stripping digits must not open the second-person or certainty gates."""
    from app.services.finding_context import _check

    name = "Vitamin D, 25-Hydroxy"
    assert _check("Your 25-hydroxy vitamin D level is low.", name) == "second_person"
    assert _check("A lowered 25-hydroxy vitamin D level indicates deficiency.", name) == "certainty"


# --------------------------------------------------------------------------
# THE DEADLINE, AND WORK THAT OUTLIVES THE REQUEST (2026-09-24)
# --------------------------------------------------------------------------
#
# During a Gemini outage seven findings took ~5 minutes; the backend gave up
# at 180 s and the page showed NOTHING, although every description was later
# written. The request now waits at most `finding_context_deadline_seconds`,
# returns what is finished, and leaves the rest running.


class BlockingLLM:
    """A model that answers only when the test lets it, and counts calls."""

    def __init__(self, reply: str = GOOD) -> None:
        import threading

        self.reply = reply
        self.release = threading.Event()
        self.calls = 0
        self.active = 0
        self.peak = 0
        self._lock = threading.Lock()

    def generate_text(self, prompt: str, system_instruction: str = "") -> str:
        with self._lock:
            self.calls += 1
            self.active += 1
            self.peak = max(self.peak, self.active)
        try:
            assert self.release.wait(timeout=10), "test never released the model"
            return self.reply
        finally:
            with self._lock:
                self.active -= 1


def _settings(deadline: float = 0.2, concurrency: int = 2):
    from app.config import Settings

    return Settings(
        _env_file=None,
        finding_context_deadline_seconds=deadline,
        finding_context_concurrency=concurrency,
    )


def _drain(timeout: float = 5.0) -> None:
    import time

    end = time.monotonic() + timeout
    while fc._INFLIGHT and time.monotonic() < end:
        time.sleep(0.01)
    assert not fc._INFLIGHT, "a finding-context job never finished"


def test_a_slow_finding_is_in_progress_not_refused_and_the_request_does_not_wait(guard):
    import time

    llm = BlockingLLM()
    try:
        started = time.monotonic()
        out = fc.describe_findings(RAISED, llm=llm, settings=_settings(deadline=0.2))
        assert time.monotonic() - started < 2.0
        entry = out.entries[0]
        assert entry.available is False
        assert entry.text is None
        assert entry.refused_by == fc.REFUSED_IN_PROGRESS == "in_progress"
        assert out.in_progress_count == 1
        assert out.withheld_count == 0  # not a refusal
    finally:
        llm.release.set()
        _drain()


def test_the_unfinished_job_keeps_running_and_the_next_request_gets_it_free(guard):
    llm = BlockingLLM()
    try:
        first = fc.describe_findings(RAISED, llm=llm, settings=_settings(deadline=0.1))
        assert first.entries[0].refused_by == "in_progress"
    finally:
        llm.release.set()
        _drain()

    second = fc.describe_findings(RAISED, llm=llm, settings=_settings())
    assert second.entries[0].available is True
    assert second.entries[0].text == GOOD
    assert second.entries[0].cached is True
    assert llm.calls == 1  # the answer was paid for once


def test_a_finding_already_in_flight_is_joined_not_written_twice(guard):
    llm = BlockingLLM()
    try:
        fc.describe_findings(RAISED, llm=llm, settings=_settings(deadline=0.1))
        again = fc.describe_findings(RAISED, llm=llm, settings=_settings(deadline=0.1))
        assert again.entries[0].refused_by == "in_progress"
        assert llm.calls == 1
    finally:
        llm.release.set()
        _drain()
    assert llm.calls == 1


def test_a_request_that_waits_long_enough_gets_the_joined_answer(guard):
    import threading

    llm = BlockingLLM()
    try:
        fc.describe_findings(RAISED, llm=llm, settings=_settings(deadline=0.1))
        threading.Timer(0.2, llm.release.set).start()
        joined = fc.describe_findings(RAISED, llm=llm, settings=_settings(deadline=5.0))
    finally:
        llm.release.set()
        _drain()
    assert joined.entries[0].available is True
    # This request spent nothing: the job was started by the first one.
    assert joined.entries[0].cached is True
    assert joined.generated_count == 0 and joined.cached_count == 1
    assert llm.calls == 1


@pytest.mark.parametrize("concurrency, peak", [(1, 1), (2, 2)])
def test_findings_are_described_at_most_n_at_a_time(guard, concurrency, peak):
    llm = BlockingLLM()
    many = [{"test_name": f"TEST {i}", "direction": "raised"} for i in range(4)]
    try:
        out = fc.describe_findings(many, llm=llm, settings=_settings(deadline=0.3, concurrency=concurrency))
        assert out.in_progress_count == 4
    finally:
        llm.release.set()
        _drain()
    assert llm.peak == peak
    assert llm.calls == 4
