"""The VaidyaAI chatbot (owner, 2026-10-09).

Answers three kinds of question, in plain words:

  * how to use the app        -- grounded in `app/data/app_help.py`
  * general lab-test / health -- grounded in the reviewed knowledge base when
                                 the question names a test or topic it covers
  * the user's own report     -- grounded in that report's results, sent by the
                                 backend only from the report's own dashboard

THE MODEL IS OPENROUTER'S, NOT GEMINI'S. Gemini's daily quota is what reads
reports and writes the dashboard explanations; a chat must never spend it. If
no OpenRouter key is configured the chat says it is unavailable -- it does not
fall back to Gemini.

THE SAFETY ORDER, and why each step is where it is:

  1. Fixed replies BEFORE any model call, for an emergency, a request for a
     diagnosis, and a request about medicines or doses. These are the answers
     that must never vary and never depend on a model behaving.
  2. The model is told to answer only from the material given, never to
     diagnose or name a medicine, and to reply OFF_TOPIC to anything outside
     health, lab tests and this app.
  3. Every answer goes through Module 24 (`guarded_generation`) with the
     material as its grounding -- so a number in the answer must come from the
     report or the notes -- and with a professional referral required for any
     health answer. Two failed attempts -> a fixed, safe reply.
  4. With NO grounding at all (a general health question the knowledge base
     does not cover), an answer may not contain a number: Module 24's numeric
     check only runs when there is grounding to check against, so this file
     closes that gap itself rather than let an unsourced figure through.

Nothing here logs the question, the report or the answer -- outcomes and
counts only, through `safe_meta`.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field

from app.core.logging import get_logger, safe_meta
from app.data.app_help import match_help
from app.safety.fallback import guarded_generation
from app.safety.validator import SafetyContext

logger = get_logger(__name__)

MAX_QUESTION_CHARS = 300
MAX_ANSWER_TOKENS = 600
CHAT_TEMPERATURE = 0.2

OUTCOME_ANSWERED = "answered"
OUTCOME_REFUSED = "refused"
OUTCOME_OFF_TOPIC = "off_topic"
OUTCOME_WITHHELD = "withheld"
OUTCOME_UNAVAILABLE = "unavailable"

# --------------------------------------------------------------------------
# Fixed replies -- reviewed wording, never composed at runtime
# --------------------------------------------------------------------------

REPLY_EMERGENCY = (
    "This could need urgent care. Please call 112 (India's emergency number) or "
    "your local emergency number now, or go to the nearest hospital. A qualified "
    "healthcare professional should see you as soon as possible."
)
# Worded so Module 24 itself approves them (tests/test_chatbot.py checks):
# the first drafts named "diagnosis" and "medicines, doses or treatment" and
# were REJECTED by the very checker every other answer has to pass.
REPLY_DIAGNOSIS = (
    "I can only explain what lab results mean in general. Whether a result "
    "points to a health condition is for a qualified healthcare professional "
    "to decide. Please discuss your report with your doctor."
)
REPLY_MEDICATION = (
    "Questions about what to take, or how much, need a qualified healthcare "
    "professional who knows your full history. Please ask your doctor or "
    "pharmacist."
)
REPLY_OFF_TOPIC = (
    "I can help with questions about lab tests, general health, your reports, "
    "and how to use VaidyaAI. Please ask me something about those."
)
REPLY_WITHHELD = (
    "I couldn't give a safe answer to that. Please rephrase it, or discuss it "
    "with a qualified healthcare professional."
)
REPLY_UNAVAILABLE = "Chat isn't available right now. Please try again later."

FIXED_REPLIES = {
    "emergency": REPLY_EMERGENCY,
    "diagnosis": REPLY_DIAGNOSIS,
    "medication": REPLY_MEDICATION,
    "off_topic": REPLY_OFF_TOPIC,
    "withheld": REPLY_WITHHELD,
    "unavailable": REPLY_UNAVAILABLE,
}

# Patterns are on lower-cased text. Kept to clear requests; anything subtler is
# Module 24's job on the answer, not a guess about the question.
_EMERGENCY = re.compile(
    r"\b(chest pain|can'?t breathe|cannot breathe|difficulty breathing|"
    r"unconscious|fainted|stroke|heart attack|suicid\w*|kill myself|"
    r"overdose|severe bleeding|seizure)\b"
)
_DIAGNOSIS = re.compile(
    r"\b(do i have|have i got|am i (?:diabetic|anaemic|anemic|sick|ill)|"
    r"diagnose|diagnosis of me|is it cancer|do i suffer)\b"
)
_MEDICATION = re.compile(
    r"\b(medicines?|medications?|tablets?|pills?|drugs?|dose|dosage|"
    r"prescri\w*|antibiotic\w*|insulin|metformin|statins?|"
    r"should i (?:take|stop|start)|how much .* (?:take|mg))\b"
)

OFF_TOPIC_TOKEN = "OFF_TOPIC"
_DIGIT = re.compile(r"\d")


def classify(question: str) -> Optional[str]:
    """A fixed-reply category, or None to answer with the model."""
    q = (question or "").lower()
    if _EMERGENCY.search(q):
        return "emergency"
    if _DIAGNOSIS.search(q):
        return "diagnosis"
    if _MEDICATION.search(q):
        return "medication"
    return None


# --------------------------------------------------------------------------
# Data shapes
# --------------------------------------------------------------------------


class ReportResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(max_length=120)
    value: Optional[str] = Field(default=None, max_length=60)
    unit: Optional[str] = Field(default=None, max_length=30)
    reference: Optional[str] = Field(default=None, max_length=80)
    flag: Optional[str] = Field(default=None, max_length=30)


class ReportTopic(BaseModel):
    model_config = ConfigDict(extra="forbid")
    condition: str = Field(max_length=80)
    status: str = Field(max_length=40)


class ReportContext(BaseModel):
    """What the backend sends from ONE report's stored analysis."""

    model_config = ConfigDict(extra="forbid")
    results: List[ReportResult] = Field(default_factory=list, max_length=80)
    topics: List[ReportTopic] = Field(default_factory=list, max_length=30)
    overall: Optional[str] = Field(default=None, max_length=80)


class ChatSource(BaseModel):
    kind: str  # "report" | "app_help" | "knowledge"
    title: str


class ChatAnswer(BaseModel):
    outcome: str
    answer: str
    sources: List[ChatSource] = Field(default_factory=list)
    model_used: bool = False


# --------------------------------------------------------------------------
# Grounding
# --------------------------------------------------------------------------


def _report_lines(report: ReportContext) -> List[str]:
    lines: List[str] = []
    if report.overall:
        lines.append(f"Overall: {report.overall}")
    for r in report.results:
        parts = [r.name]
        if r.value is not None:
            parts.append(f"= {r.value}{(' ' + r.unit) if r.unit else ''}")
        if r.reference:
            parts.append(f"(usual range on the report: {r.reference})")
        if r.flag:
            parts.append(f"[{r.flag}]")
        lines.append("Result: " + " ".join(parts))
    for t in report.topics:
        lines.append(f"Topic checked: {t.condition} -- {t.status}")
    return lines


def _knowledge(question: str) -> List[Dict[str, Any]]:
    """Reviewed knowledge chunks for a question, anchored to the catalogue."""
    try:
        from app.rag.retriever import retrieve

        return [s.to_dict() for s in retrieve(text=question, top_k=3)]
    except Exception:  # noqa: BLE001 -- no grounding is a valid answer
        return []


SYSTEM_INSTRUCTION = (
    "You are VaidyaAI's help assistant. You answer three kinds of question: how "
    "to use the VaidyaAI app; general questions about laboratory tests and "
    "general healthy habits; and questions about the user's own report when its "
    "results are given to you.\n"
    "Rules:\n"
    "- Use plain, simple English. Two to six short sentences.\n"
    "- Use ONLY the material given below for facts about the app and the "
    "report. If the material does not answer an app question, say you are not "
    "sure and suggest the Reports or Your details page.\n"
    "- Never say the person has, or does not have, a disease. Never name a "
    "medicine, a dose or a treatment.\n"
    "- Do not state any number unless it appears in the material given.\n"
    "- Use careful wording such as 'can', 'may', 'is often used to'. Never "
    "write that a result 'shows', 'proves' or 'means' something about the "
    "person.\n"
    "- For anything about their health, suggest discussing it with a doctor.\n"
    f"- If the question is not about health, lab tests or this app, reply with "
    f"exactly {OFF_TOPIC_TOKEN} and nothing else."
)


def _prompt(question: str, help_notes, chunks, report_lines) -> str:
    blocks: List[str] = []
    if help_notes:
        blocks.append(
            "HOW THE APP WORKS:\n" + "\n".join(f"- {n.title}: {n.text}" for n in help_notes)
        )
    if chunks:
        blocks.append(
            "REVIEWED HEALTH INFORMATION:\n"
            + "\n".join(f"- {c['title']}: {c['text']}" for c in chunks)
        )
    if report_lines:
        blocks.append("THE USER'S REPORT:\n" + "\n".join(report_lines))
    material = "\n\n".join(blocks) if blocks else "(no reference material for this question)"
    return f"{material}\n\nQUESTION: {question}"


# --------------------------------------------------------------------------
# The entry point
# --------------------------------------------------------------------------


def _fixed(kind: str, outcome: str) -> ChatAnswer:
    logger.info("chat_answer %s", safe_meta(outcome=outcome, kind=kind, model=False))
    return ChatAnswer(outcome=outcome, answer=FIXED_REPLIES[kind])


def answer_question(
    question: str,
    *,
    report: Optional[ReportContext] = None,
    llm: Any = None,
) -> ChatAnswer:
    """Answer one question. Never raises; every failure is a fixed reply."""
    q = (question or "").strip()[:MAX_QUESTION_CHARS]
    if not q:
        return _fixed("off_topic", OUTCOME_OFF_TOPIC)

    kind = classify(q)
    if kind is not None:
        return _fixed(kind, OUTCOME_REFUSED)

    if llm is None:
        return _fixed("unavailable", OUTCOME_UNAVAILABLE)

    help_notes = match_help(q)
    chunks = _knowledge(q)
    report_lines = _report_lines(report) if report else []
    grounding: Sequence[str] = tuple(
        [n.text for n in help_notes] + [c["text"] for c in chunks] + report_lines
    )
    health_question = bool(chunks or report_lines) or not help_notes

    context = SafetyContext(
        grounding_sources=tuple(grounding),
        # An app-only answer ("press Upload") needs no referral appended; any
        # answer touching health does.
        require_referral=health_question,
        purpose="chat_answer",
    )
    prompt = _prompt(q, help_notes, chunks, report_lines)
    off_topic = {"seen": False}

    def generate(feedback=None):
        # A retry is told, in general terms, why the last answer was refused --
        # never the refused text itself.
        retry_note = (
            "\n\nYOUR PREVIOUS ANSWER WAS NOT ALLOWED. Answer again more "
            "carefully: hedged wording ('can', 'may'), no numbers that are not "
            "in the material, no diagnosis, no medicine names."
            if feedback is not None
            else ""
        )
        text = llm.generate_text(
            prompt + retry_note,
            system_instruction=SYSTEM_INSTRUCTION,
            temperature=CHAT_TEMPERATURE,
            max_output_tokens=MAX_ANSWER_TOKENS,
        )
        if isinstance(text, str) and text.strip().strip(".").upper() == OFF_TOPIC_TOKEN:
            off_topic["seen"] = True
            raise ValueError("off topic")  # ends this attempt; handled below
        # No grounding -> no numbers: Module 24 cannot check them (header, 4).
        if not grounding and isinstance(text, str) and _DIGIT.search(text):
            raise ValueError("ungrounded number")
        return text

    result = guarded_generation(generate, context=context, attempts=2)

    if off_topic["seen"] and result.approved_text is None:
        return _fixed("off_topic", OUTCOME_OFF_TOPIC)
    if result.approved_text is None:
        return _fixed("withheld", OUTCOME_WITHHELD)

    sources: List[ChatSource] = []
    if report_lines:
        sources.append(ChatSource(kind="report", title="This report's results"))
    sources += [ChatSource(kind="app_help", title=n.title) for n in help_notes]
    seen_docs = set()
    for c in chunks:
        if c["doc_id"] not in seen_docs:
            seen_docs.add(c["doc_id"])
            sources.append(ChatSource(kind="knowledge", title=c["title"]))

    logger.info(
        "chat_answer %s",
        safe_meta(outcome=OUTCOME_ANSWERED, model=True, sources=len(sources),
                  attempts=result.attempts),
    )
    return ChatAnswer(
        outcome=OUTCOME_ANSWERED,
        answer=result.approved_text,
        sources=sources,
        model_used=True,
    )


__all__ = [
    "ChatAnswer",
    "ChatSource",
    "FIXED_REPLIES",
    "MAX_QUESTION_CHARS",
    "ReportContext",
    "ReportResult",
    "ReportTopic",
    "SYSTEM_INSTRUCTION",
    "answer_question",
    "classify",
]
