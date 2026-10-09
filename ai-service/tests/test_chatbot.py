"""The VaidyaAI chatbot (owner, 2026-10-09).

Pinned here:
  * the fixed replies (emergency, diagnosis, medicines) never call a model,
    and Module 24 itself approves every one of them;
  * an answer is grounded -- in the app's help notes, the reviewed knowledge
    base, or the one report the backend sent -- and passes Module 24;
  * an unsafe or unsourced answer is replaced by a fixed reply, never shown;
  * OFF_TOPIC questions get the redirect;
  * no OpenRouter key -> "unavailable", and Gemini is never used for chat.
"""

from __future__ import annotations

from typing import List

import pytest

from app.data.app_help import HELP_NOTES, match_help
from app.safety.validator import SafetyContext, validate_text
from app.services import chatbot as cb


class FakeLLM:
    """Returns the scripted answers in order; records every prompt."""

    def __init__(self, answers: List[str]):
        self.answers = list(answers)
        self.prompts: List[str] = []

    def generate_text(self, prompt, *, system_instruction, temperature, max_output_tokens):
        self.prompts.append(prompt)
        assert system_instruction == cb.SYSTEM_INSTRUCTION
        if not self.answers:
            raise AssertionError("the model was called more times than scripted")
        return self.answers.pop(0)


REPORT = cb.ReportContext(
    results=[cb.ReportResult(name="HbA1c", value="5.6", unit="%", reference="4.0 - 5.6")],
    topics=[cb.ReportTopic(condition="Diabetes", status="Not indicated")],
)


# --------------------------------------------------------------------------
# Fixed replies
# --------------------------------------------------------------------------


@pytest.mark.parametrize("kind", sorted(cb.FIXED_REPLIES))
@pytest.mark.parametrize("referral", [True, False])
def test_every_fixed_reply_is_approved_by_module_24(kind, referral):
    verdict = validate_text(
        cb.FIXED_REPLIES[kind], SafetyContext(require_referral=referral, purpose="chat_answer")
    )
    assert verdict.approved, (kind, verdict.codes)


@pytest.mark.parametrize(
    "question, kind",
    [
        ("I have chest pain and feel dizzy", "emergency"),
        ("I can't breathe properly", "emergency"),
        ("Do I have diabetes?", "diagnosis"),
        ("am i anaemic based on this", "diagnosis"),
        ("Which tablet should I take for sugar?", "medication"),
        ("what dose of metformin is right", "medication"),
        ("should I stop my medicine", "medication"),
    ],
)
def test_risky_questions_get_a_fixed_reply_and_no_model_call(question, kind):
    llm = FakeLLM([])
    out = cb.answer_question(question, llm=llm)
    assert cb.classify(question) == kind
    assert out.outcome == cb.OUTCOME_REFUSED
    assert out.answer == cb.FIXED_REPLIES[kind]
    assert llm.prompts == []
    assert out.model_used is False


@pytest.mark.parametrize(
    "question",
    ["What is HbA1c?", "How do I upload a report?", "What is the Timeline page?", "how to sleep better"],
)
def test_ordinary_questions_are_not_refused(question):
    assert cb.classify(question) is None


# --------------------------------------------------------------------------
# Answers
# --------------------------------------------------------------------------


def test_no_model_configured_means_unavailable():
    out = cb.answer_question("What is HbA1c?", llm=None)
    assert out.outcome == cb.OUTCOME_UNAVAILABLE


def test_an_app_question_is_grounded_in_the_help_notes_and_gets_no_referral_tacked_on():
    llm = FakeLLM(["Open the Reports page, choose a PDF or a clear photo up to 10 MB, press Upload, then press Analyse."])
    out = cb.answer_question("How do I upload a report?", llm=llm)
    assert out.outcome == cb.OUTCOME_ANSWERED
    assert [s.title for s in out.sources] == ["Uploading a report"]
    assert "HOW THE APP WORKS" in llm.prompts[0]
    assert "healthcare professional" not in out.answer  # app help, not health


def test_a_report_question_sees_only_that_report_and_may_quote_its_numbers():
    llm = FakeLLM(["Your HbA1c on this report is 5.6 %, and the usual range printed on it is 4.0 - 5.6, so it is at the top of that range. Please discuss it with your doctor."])
    out = cb.answer_question("Is my HbA1c close to the limit?", report=REPORT, llm=llm)
    assert out.outcome == cb.OUTCOME_ANSWERED
    assert out.sources[0].title == "This report's results"
    assert "Result: HbA1c = 5.6 %" in llm.prompts[0]


def test_a_number_that_is_not_in_the_report_is_refused():
    llm = FakeLLM(["Your HbA1c is 7.9 %, which may be worth discussing with a doctor."] * 2)
    out = cb.answer_question("What is my HbA1c?", report=REPORT, llm=llm)
    assert out.outcome == cb.OUTCOME_WITHHELD
    assert "7.9" not in out.answer


def test_with_no_grounding_at_all_an_answer_may_not_contain_a_number():
    llm = FakeLLM(["Many adults drink about 8 glasses of water a day."] * 2)
    out = cb.answer_question("How much water is good to drink?", llm=llm)
    assert out.outcome == cb.OUTCOME_WITHHELD
    assert "8" not in out.answer


def test_a_retry_is_told_why_and_can_succeed():
    llm = FakeLLM([
        "Many adults drink about 8 glasses of water a day.",
        "Drinking water regularly through the day can help many people. Please ask a doctor what suits you.",
    ])
    out = cb.answer_question("How much water is good to drink?", llm=llm)
    assert out.outcome == cb.OUTCOME_ANSWERED
    assert "NOT ALLOWED" in llm.prompts[1]


def test_a_diagnosis_in_the_answer_is_never_shown():
    llm = FakeLLM(["You have diabetes."] * 2)
    out = cb.answer_question("What does HbA1c measure?", llm=llm)
    assert out.outcome == cb.OUTCOME_WITHHELD
    assert "You have diabetes" not in out.answer


def test_off_topic_gets_the_redirect():
    llm = FakeLLM(["OFF_TOPIC", "OFF_TOPIC"])
    out = cb.answer_question("Write me a poem about cricket", llm=llm)
    assert out.outcome == cb.OUTCOME_OFF_TOPIC
    assert out.answer == cb.REPLY_OFF_TOPIC


def test_an_empty_question_calls_nothing():
    llm = FakeLLM([])
    assert cb.answer_question("   ", llm=llm).outcome == cb.OUTCOME_OFF_TOPIC


def test_a_failing_model_becomes_a_fixed_reply_not_an_error():
    class Broken:
        def generate_text(self, *a, **k):
            raise RuntimeError("provider down")

    out = cb.answer_question("What is HbA1c?", llm=Broken())
    assert out.outcome in (cb.OUTCOME_WITHHELD, cb.OUTCOME_OFF_TOPIC)
    assert out.answer in cb.FIXED_REPLIES.values()


# --------------------------------------------------------------------------
# Help notes
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "question, note_id",
    [
        ("how do I upload a pdf", "upload"),
        ("what is the timeline", "timeline"),
        ("what does population context mean", "population"),
        ("my analysis is slow", "analyse"),
        ("how to delete my account", "account"),
        ("what does not assessed mean", "not_assessed"),
    ],
)
def test_app_questions_find_the_right_note(question, note_id):
    assert match_help(question)[0].note_id == note_id


@pytest.mark.parametrize("note", HELP_NOTES, ids=lambda n: n.note_id)
def test_every_help_note_passes_module_24_as_it_stands(note):
    verdict = validate_text(note.text, SafetyContext(require_referral=False, purpose="chat_help_note"))
    assert verdict.approved, (note.note_id, verdict.codes)


# --------------------------------------------------------------------------
# The route
# --------------------------------------------------------------------------


def test_the_route_needs_the_service_key(authed_client):
    res = authed_client.post("/api/v1/chat", json={"question": "What is HbA1c?"})
    assert res.status_code == 401


def test_the_route_answers_through_the_service(client):
    from app.api.routes_chat import get_chat_llm
    from app.main import app

    app.dependency_overrides[get_chat_llm] = lambda: FakeLLM(
        ["Open the Reports page, press Upload, then press Analyse."]
    )
    res = client.post("/api/v1/chat", json={"question": "How do I upload a report?"})
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["data"]["outcome"] == "answered"
    assert body["data"]["sources"][0]["kind"] == "app_help"


def test_the_route_refuses_an_overlong_question(client):
    res = client.post("/api/v1/chat", json={"question": "x" * 301})
    assert res.status_code == 422


def test_chat_never_uses_gemini():
    """With a Gemini key and NO OpenRouter key, chat is unavailable."""
    from app.api.routes_chat import get_chat_llm
    from app.config import Settings

    settings = Settings(_env_file=None, gemini_api_key="g" * 40, openrouter_api_key="")
    assert get_chat_llm(settings) is None
