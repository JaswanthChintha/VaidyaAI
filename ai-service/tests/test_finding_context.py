from __future__ import annotations

from typing import Any, List

import pytest

from app.services import finding_context as fc


class FakeLLM:

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
    fc.reset_cache()
    yield
    fc.reset_cache()


@pytest.fixture
def guard(monkeypatch):
    seen = {"contexts": []}

    def fake(generate, *, context, attempts=2):
        seen["contexts"].append(context)
        return approved(generate())

    monkeypatch.setattr(fc, "guarded_generation", fake)
    return seen


GOOD = "A raised result of this kind is commonly associated with inflammation or infection somewhere in the body."

RAISED = [{"test_name": "C-REACTIVE PROTEIN", "direction": "raised"}]


LIVE_APPROVED = (
    "A raised glycated hemoglobin result is commonly associated with "
    "persistently elevated blood sugar levels over time. It can be a sign of "
    "diabetes mellitus.",
    "A lowered haemoglobin result is commonly associated with anemia, which "
    "can occur due to low iron levels or blood loss. It can also be a sign of "
    "various underlying nutritional deficiencies or chronic health "
    "conditions.",
    "A lowered total red blood cell count is commonly associated with anemia "
    "or blood loss. It can also be a sign of nutritional deficiencies or "
    "various chronic conditions.",
    "A raised level of polymorphs, a type of white blood cell, is commonly "
    "associated with the body's response to acute bacterial infections or "
    "tissue inflammation. It can also be a sign of physical stress or injury.",
    "A lowered lymphocyte count can be a sign of a recent viral infection or "
    "periods of significant physical stress. It is also commonly associated "
    "with certain long-term health conditions or issues affecting the immune "
    "system.",
    "A lowered monocyte count can be associated with certain conditions "
    "affecting the bone marrow or acute physical stress on the body. It can "
    "also sometimes be observed following specific types of infections or "
    "prolonged illness.",
    "A lowered packed cell volume can be a sign of anemia, where the blood "
    "has a reduced proportion of red blood cells. It is also commonly "
    "associated with recent blood loss or certain nutritional shortages.",
    "A lowered MCH result is commonly associated with iron deficiency anemia "
    "or other conditions where red blood cells contain less hemoglobin than "
    "normal. It can also be a sign of certain inherited blood disorders, such "
    "as thalassemia.",
    "A lowered MCHC result is commonly associated with iron deficiency, where "
    "red blood cells contain less hemoglobin than usual. It can also be a "
    "sign of certain inherited blood conditions, such as thalassemia.",
    "A raised erythrocyte sedimentation rate is commonly associated with "
    "inflammation in the body. It can be a sign of various underlying issues, "
    "such as infections, autoimmune disorders, or tissue injury.",
    "A raised C-reactive protein level is commonly associated with "
    "inflammation somewhere in the body. This response can be triggered by "
    "various factors such as infections, tissue injury, or immune system "
    "activity.",
    "A raised SGPT level is commonly associated with inflammation or stress "
    "affecting the liver. This finding can be a sign of various liver "
    "conditions, such as fatty liver or hepatitis.",
    "A raised glycated haemoglobin (HbA1c) result is commonly associated with "
    "prediabetes or diabetes, reflecting higher average blood sugar levels "
    "over the preceding two to three months. It can also be a sign of an "
    "increased risk of developing cardiovascular complications.",
    "A raised random blood glucose level is commonly associated with diabetes "
    "or prediabetes, which affect how the body processes sugar. It can also "
    "be a sign of recent food intake, physical stress, acute illness, or "
    "certain hormonal imbalances.",
    "A lowered hemoglobin level is commonly associated with anemia, which can "
    "be a sign of iron deficiency, blood loss, or chronic kidney disease. It "
    "is also frequently associated with nutritional deficiencies, bone marrow "
    "disorders, and ongoing inflammatory conditions.",
    "A raised neutrophil count is commonly associated with bacterial "
    "infections, acute inflammation, or physical stress. It can also be a "
    "sign of tissue injury or various underlying medical conditions.",
    "A lowered lymphocyte count can be a sign of a recent viral infection or "
    "periods of significant physical stress. It is also commonly associated "
    "with certain long-term health conditions or issues affecting the immune "
    "system.",
    "A raised erythrocyte sedimentation rate is commonly associated with "
    "inflammation in the body. It can be a sign of various underlying issues, "
    "such as infections, autoimmune disorders, or tissue injury.",
    "A raised C-reactive protein level is commonly associated with "
    "inflammation somewhere in the body. It can be a sign of infections, "
    "tissue injury, or various inflammatory conditions.",
)


def test_the_prompt_carries_only_a_name_and_a_direction(guard):
    llm = FakeLLM(GOOD)
    fc.describe_findings(RAISED, llm=llm)
    prompt = llm.prompts[0]
    assert "C-REACTIVE PROTEIN" in prompt
    assert "raised" in prompt
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


@pytest.mark.parametrize(
    "reply",
    [
        "A raised result is commonly associated with levels above 5 mg/L.",
        "A raised result is commonly associated with a count over ten.",
    ],
)
def test_any_number_in_the_answer_throws_it_away(guard, reply):
    out = fc.describe_findings(RAISED, llm=FakeLLM(reply))
    assert out.entries[0].available is False
    assert out.entries[0].text is None
    assert out.entries[0].refused_by == "number"


@pytest.mark.parametrize(
    "reply",
    [
        "Your raised result is commonly associated with inflammation.",
        "This suggests you may have an infection.",
        "A raised result means you should be concerned.",
    ],
)
def test_text_that_addresses_the_reader_is_refused(guard, reply):
    out = fc.describe_findings(RAISED, llm=FakeLLM(reply))
    assert out.entries[0].available is False
    assert out.entries[0].text is None
    assert out.entries[0].refused_by in ("second_person", "certainty")


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
        "Raised results indicate a bacterial infection.",
        "Raised results mean inflammation is present.",
        "Lowered results confirm iron deficiency.",
        "Raised results diagnose diabetes.",
        "Raised results prove an infection.",
        "Raised results demonstrate liver injury.",
        "Raised results show that the liver is inflamed.",
        "Raised results are caused by infection.",
        "A raised result indicated an infection.",
        "The infection was confirmed by the result.",
        "An infection has been proven by this result.",
        "These results showed that the liver is inflamed.",
        "A raised result may indicate an infection.",
    ],
)
def test_a_plural_subject_does_not_evade_the_certainty_gate(guard, reply):
    out = fc.describe_findings(RAISED, llm=FakeLLM(reply))
    assert out.entries[0].available is False
    assert out.entries[0].refused_by == "certainty"


@pytest.mark.parametrize(
    "reply",
    [
        "MCH stands for mean corpuscular haemoglobin, a measure of the average "
        "amount of haemoglobin carried in a red blood cell.",
        "MCHC refers to mean corpuscular haemoglobin concentration.",
        "Mean platelet volume describes the average size of platelets.",
        "Mean cell volume is a measure of red blood cell size.",
        "Mean arterial pressure is an average over the cardiac cycle.",
    ],
)
def test_mean_in_a_measurement_name_is_not_a_claim(guard, reply):
    out = fc.describe_findings(
        [{"test_name": "MCH", "direction": "lowered"}], llm=FakeLLM(reply)
    )
    assert out.entries[0].available is True, out.entries[0].refused_by


@pytest.mark.parametrize(
    "reply",
    [
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
        "Levels often improve once the underlying cause is addressed.",
        "An improved result is commonly seen after the cause resolves.",
        "The meaning of this test is often misunderstood.",
    ],
)
def test_a_listed_word_inside_a_longer_word_is_not_a_claim(guard, reply):
    out = fc.describe_findings(RAISED, llm=FakeLLM(reply))
    assert out.entries[0].available is True, out.entries[0].refused_by


def test_the_certainty_pattern_carries_no_backspace():
    assert "\x08" not in fc._CERTAINTY.pattern


def test_the_prompt_names_the_certainty_words_the_gate_measures():
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
    for text in LIVE_APPROVED:
        assert fc._check(text) is None, text


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

    def __init__(self, *replies: Any) -> None:
        self.replies = list(replies)
        self.calls = 0

    def generate_text(self, prompt: str, system_instruction: str = "") -> Any:
        self.calls += 1
        reply = self.replies.pop(0) if self.replies else RuntimeError("ServerError")
        if isinstance(reply, BaseException):
            raise reply
        return reply


def test_an_outage_is_not_recorded_as_a_safety_refusal():
    llm = RaisingLLM(RuntimeError("ServerError"), RuntimeError("ServerError"))
    out = fc.describe_findings(RAISED, llm=llm)
    assert llm.calls == 2
    entry = out.entries[0]
    assert entry.available is False
    assert entry.text is None
    assert entry.refused_by == fc.REFUSED_MODEL_UNAVAILABLE == "model_unavailable"
    assert out.withheld_count == 1


def test_a_real_refusal_after_one_outage_is_still_a_safety_refusal():
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


@pytest.mark.parametrize("direction", [None, "", "abnormal", "HIGH", "up"])
def test_a_direction_this_module_does_not_know_is_skipped_not_guessed(guard, direction):
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
    assert fc.MAX_PER_REPORT >= 12, "below a real report's out-of-range count"
    assert fc.MAX_PER_REPORT <= 24, "no longer a meaningful ceiling"


def test_a_cache_hit_does_not_spend_the_ceiling(guard):
    first = [{"test_name": f"TEST {i}", "direction": "raised"} for i in range(fc.MAX_PER_REPORT)]
    llm = FakeLLM(*[GOOD] * fc.MAX_PER_REPORT)
    fc.describe_findings(first, llm=llm)
    assert len(llm.prompts) == fc.MAX_PER_REPORT

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
    fc.describe_findings(RAISED, llm=FakeLLM("Your level is over 9000."))
    llm = FakeLLM(GOOD)
    out = fc.describe_findings(RAISED, llm=llm)
    assert len(llm.prompts) == 1, "a refusal was cached"
    assert out.entries[0].available is True
    assert out.cached_count == 0


def test_a_cached_entry_carries_the_name_this_report_printed(guard):
    fc.describe_findings([{"test_name": "LYMPHOCYTES", "direction": "lowered"}], llm=FakeLLM(GOOD))
    out = fc.describe_findings(
        [{"test_name": "Lymphocytes", "direction": "lowered"}], llm=FakeLLM()
    )
    entry = out.entries[0]
    assert entry.cached is True
    assert entry.test_name == "Lymphocytes"
    assert entry.available is True


def test_the_laboratorys_own_spacing_does_not_buy_a_second_call(guard):
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
    names = [f"TEST {i}" for i in range(fc.MAX_PER_REPORT + 2)]
    llm = FakeLLM(*[GOOD] * fc.MAX_PER_REPORT)
    out = fc.describe_findings(
        [{"test_name": n, "direction": "raised"} for n in names], llm=llm
    )
    assert [e.test_name for e in out.entries] == names[: fc.MAX_PER_REPORT]
    assert out.skipped_over_limit == 2


def test_a_refusal_carries_no_text_at_all(guard):
    out = fc.describe_findings(RAISED, llm=FakeLLM("Your level is over 9000."))
    entry = out.entries[0]
    assert entry.text is None
    assert entry.available is False
    assert out.withheld_count == 1


def test_the_policy_says_what_the_prompt_contained():
    policy = fc.FindingContextData().policy
    assert "NAME" in policy and "DIRECTION" in policy
    assert "never about the reader" in policy
    assert "diagnosis" in policy.lower() and "no condition is derived" in policy.lower()


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
    from app.services.finding_context import _MEASUREMENT_DIGIT, _SPELLED_NUMBER

    for pattern in (_SPELLED_NUMBER.pattern, _MEASUREMENT_DIGIT.pattern):
        assert "\x08" not in pattern
    from app.services.finding_context import _check

    assert _check("Associated with a shortening of the tendon.") is None


def test_the_prompt_forbids_the_words_the_validator_actually_bans():
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
    from app.services.finding_context import SYSTEM_INSTRUCTION

    lowered = SYSTEM_INSTRUCTION.lower()
    assert "not even in passing" in lowered
    assert "mention treatment" in lowered


def test_echoing_a_test_name_that_contains_digits_is_not_a_number():
    from app.services.finding_context import _check

    sentence = (
        "A lowered 25-hydroxy vitamin D level is commonly associated with "
        "insufficient sunlight exposure or low dietary intake."
    )
    assert _check(sentence, "Vitamin D, 25-Hydroxy") is None
    assert _check(sentence.replace("25-hydroxy ", ""), "Vitamin D, 25-Hydroxy") is None


def test_a_number_the_model_invented_is_still_refused():
    from app.services.finding_context import _check

    name = "Vitamin D, 25-Hydroxy"
    assert _check("A lowered result below 25 ng/mL is commonly associated with low intake.", name) == "number"
    assert _check("A lowered 25-hydroxy vitamin D level below 30 is commonly associated with low intake.", name) == "number"
    assert _check("A raised level above 1.3 mg/dL is commonly associated with kidney disease.") == "number"


def test_the_other_gates_are_untouched_by_the_name_strip():
    from app.services.finding_context import _check

    name = "Vitamin D, 25-Hydroxy"
    assert _check("Your 25-hydroxy vitamin D level is low.", name) == "second_person"
    assert _check("A lowered 25-hydroxy vitamin D level indicates deficiency.", name) == "certainty"


class BlockingLLM:

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
        assert out.withheld_count == 0
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
    assert llm.calls == 1


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
