from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field

from app.core.logging import get_logger, safe_meta
from app.data.app_help import SITE_MAP, match_help
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


REPLY_EMERGENCY = (
    "This could need urgent care. Please call 112 (India's emergency number) or "
    "your local emergency number now, or go to the nearest hospital. A qualified "
    "healthcare professional should see you as soon as possible."
)
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

_HEALTH_WORDS = re.compile(
    r"\b(health\w*|blood|tests?|testing|lab|labs|laborator\w*|results?|reports?|"
    r"range|levels?|values?|normal|high|low|sugar|glucose|hba1c|a1c|cholesterol|"
    r"lipids?|ldl|hdl|triglycerides?|kidneys?|renal|liver|heart|thyroid|tsh|"
    r"vitamins?|iron|ferritin|haemoglobin|hemoglobin|anaemi\w*|anemi\w*|"
    r"diabet\w*|pressure|bmi|weight|diet\w*|foods?|eat\w*|exercis\w*|sleep\w*|"
    r"water|hydrat\w*|doctors?|symptoms?|urine|creatinine|egfr|sgpt|sgot|alt|"
    r"ast|bilirubin|platelets?|wbc|rbc|cbc|proteins?|fats?|salt|smok\w*|"
    r"alcohol|stress|fasting|medical|body|diseases?|conditions?|infections?|"
    r"immun\w*|nutrition\w*|calori\w*|fitness|lifestyle|wellness|vaidyaai)\b"
)


def classify(question: str) -> Optional[str]:
    q = (question or "").lower()
    if _EMERGENCY.search(q):
        return "emergency"
    if _DIAGNOSIS.search(q):
        return "diagnosis"
    if _MEDICATION.search(q):
        return "medication"
    return None


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

    model_config = ConfigDict(extra="forbid")
    results: List[ReportResult] = Field(default_factory=list, max_length=80)
    topics: List[ReportTopic] = Field(default_factory=list, max_length=30)
    overall: Optional[str] = Field(default=None, max_length=80)


class ChatSource(BaseModel):
    kind: str
    title: str


class ChatAnswer(BaseModel):
    outcome: str
    answer: str
    sources: List[ChatSource] = Field(default_factory=list)
    model_used: bool = False


def _report_lines(report: ReportContext) -> List[str]:
    lines: List[str] = []
    if report.overall:
        lines.append(f"Overall: {report.overall}")
    for r in report.results:
        parts = [r.name]
        if r.value is not None:
            parts.append(f"= {r.value}{(' ' + r.unit) if r.unit else ''}")
        if r.reference:
            reference = r.reference
            if r.unit and not re.search(r"[A-Za-z%]", reference):
                reference = f"{reference} {r.unit}"
            parts.append(f"(usual range on the report: {reference})")
        if r.flag:
            parts.append(f"[{r.flag}]")
        lines.append("Result: " + " ".join(parts))
    for t in report.topics:
        lines.append(f"Topic checked: {t.condition} -- {t.status}")
    return lines


def _knowledge(question: str) -> List[Dict[str, Any]]:
    try:
        from app.rag.retriever import retrieve

        return [s.to_dict() for s in retrieve(text=question, top_k=3)]
    except Exception:
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
    "- Never describe a button, icon, page or feature of the app that is not "
    "in the material. If the material does not have it, say VaidyaAI does not "
    "have it. (Live 2026-10-09: a 'share icon' and email sharing were invented.)\n"
    "- For a question about the app, answer exactly what was asked: say where "
    "to click, using the exact names of the menu items, pages, sections and "
    "buttons in the material (for example: click Timeline in the menu on the "
    "left).\n"
    "- Never say the person has, or does not have, a disease. Never name a "
    "medicine, a dose or a treatment.\n"
    "- Do not state any number unless it appears in the material given. Copy "
    "each value's unit exactly as the report gives it.\n"
    "- Use careful wording such as 'can', 'may', 'is often used to'. Do not "
    "use the words 'shows', 'show', 'means', 'mean', 'indicates', 'proves' or "
    "'confirms' at all -- not even about the app. Say 'has', 'lists', "
    "'compares', 'is used for' or 'can suggest' instead. (Live 2026-10-09: "
    "'the Timeline shows...' was refused by the safety check.)\n"
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


def _fixed(kind: str, outcome: str) -> ChatAnswer:
    logger.info("chat_answer %s", safe_meta(outcome=outcome, kind=kind, model=False))
    return ChatAnswer(outcome=outcome, answer=FIXED_REPLIES[kind])


def answer_question(
    question: str,
    *,
    report: Optional[ReportContext] = None,
    llm: Any = None,
) -> ChatAnswer:
    q = (question or "").strip()[:MAX_QUESTION_CHARS]
    if not q:
        return _fixed("off_topic", OUTCOME_OFF_TOPIC)

    kind = classify(q)
    if kind is not None:
        return _fixed(kind, OUTCOME_REFUSED)

    help_notes = match_help(q)
    chunks = _knowledge(q)
    app_question = bool(help_notes) and not chunks

    if not help_notes and not chunks and not _HEALTH_WORDS.search(q.lower()):
        return _fixed("off_topic", OUTCOME_OFF_TOPIC)

    def note_answer() -> ChatAnswer:
        note = help_notes[0]
        logger.info("chat_answer %s", safe_meta(outcome=OUTCOME_ANSWERED, kind="app_help", model=False))
        return ChatAnswer(
            outcome=OUTCOME_ANSWERED,
            answer=note.text,
            sources=[ChatSource(kind="app_help", title=note.title)],
        )

    if llm is None:
        return note_answer() if app_question else _fixed("unavailable", OUTCOME_UNAVAILABLE)

    if app_question and SITE_MAP not in help_notes:
        help_notes = help_notes + [SITE_MAP]

    report_lines = _report_lines(report) if (report and not app_question) else []
    grounding: Sequence[str] = tuple(
        [n.text for n in help_notes] + [c["text"] for c in chunks] + report_lines
    )
    health_question = not app_question

    context = SafetyContext(
        grounding_sources=tuple(grounding),
        require_referral=health_question,
        purpose="chat_answer",
    )
    prompt = _prompt(q, help_notes, chunks, report_lines)
    off_topic = {"seen": False}

    def generate(feedback=None):
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
            raise ValueError("off topic")
        if not grounding and isinstance(text, str) and _DIGIT.search(text):
            raise ValueError("ungrounded number")
        return text

    result = guarded_generation(generate, context=context, attempts=2)

    if result.approved_text is None and app_question:
        return note_answer()
    if off_topic["seen"] and result.approved_text is None:
        return _fixed("off_topic", OUTCOME_OFF_TOPIC)
    if result.approved_text is None:
        return _fixed("withheld", OUTCOME_WITHHELD)

    sources: List[ChatSource] = []
    if report_lines:
        sources.append(ChatSource(kind="report", title="This report's results"))
    cited = [n for n in help_notes if n is not SITE_MAP] or help_notes
    sources += [ChatSource(kind="app_help", title=n.title) for n in cited]
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
