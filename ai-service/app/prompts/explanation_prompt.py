from __future__ import annotations

from typing import Iterable, Optional, Sequence, Tuple

PROMPT_VERSION = "m23-explain-v1"


PROHIBITIONS: Tuple[str, ...] = (
    "NEVER DIAGNOSE. Do not say or imply that the reader has, or does not "
    "have, any condition. You are describing what a measurement is, not what "
    "is wrong with a person.",
    "NEVER MENTION MEDICATION. No drug name, no drug class, no supplement "
    "recommendation, no 'medication may be considered'.",
    "NEVER GIVE A DOSAGE, an amount to take, a target to hit, or a schedule "
    "to follow.",
    "NEVER CLAIM CERTAINTY. Do not write 'definitely', 'confirms', 'proves', "
    "'clearly shows' or 'this means you have'. A single laboratory value "
    "settles nothing on its own, and saying so is part of the explanation.",
    "HEDGE EVERY INTERPRETATION. If a sentence says what a result means for "
    "the reader's body or health, it MUST also carry one of: may, might, "
    "can, could, often, usually, typically, generally, commonly, sometimes. "
    "This applies to every form of 'mean', 'indicate', 'show', 'prove', "
    "'demonstrate', 'reveal', 'signal', 'signify', 'imply', 'reflect' and "
    "'point to'. Write 'a lowered result MAY be associated with ...' or "
    "'this CAN be a sign of ...', never 'this indicates ...' or 'this shows "
    "your ... is'. 'Suggests' and 'is associated with' already carry the "
    "hedge and need no other. An unhedged interpretation is discarded in "
    "full, so the reader loses the entire explanation rather than one "
    "sentence.",
    "ALWAYS DEFER TO A QUALIFIED HEALTHCARE PROFESSIONAL. Every explanation "
    "must say, in its own words, that a qualified healthcare professional is "
    "the person to discuss this with. This system does not replace one.",
    "USE ONLY THE SUPPLIED VALUES AND THE SUPPLIED KNOWLEDGE. Every factual "
    "statement must be traceable to the knowledge extracts below, and every "
    "number you write must appear in the PERMITTED NUMBERS list. You have no "
    "other source. If the extracts do not answer something, say that it is "
    "not covered here rather than filling the gap.",
)


SYSTEM_INSTRUCTION = (
    "You are the patient-explanation layer of VaidyaAI, an educational health "
    "platform. You rewrite already-computed clinical findings into plain, "
    "calm language for the person whose report it is. You are NOT a clinician "
    "and you are NOT the analysis: the findings were produced before you were "
    "called and you may not revise, extend, contradict or second-guess them. "
    "You add no medical fact that was not handed to you. Your output is "
    "checked by an automated medical safety layer before anyone reads it, and "
    "an explanation that breaks the rules is discarded in full rather than "
    "corrected -- so restraint costs the reader nothing and overreach costs "
    "them the whole explanation."
)


def _rules_block() -> str:
    lines = [f"{n}. {rule}" for n, rule in enumerate(PROHIBITIONS, start=1)]
    return "## Absolute rules\n\n" + "\n".join(lines)


_STYLE = """\
## Style

Write 3 to 6 short sentences of continuous prose, addressing the reader as \
"you". No headings, no bullet points, no numbered lists -- a list marker \
is a number, and an unsourced number gets the explanation discarded. Do not \
open with a greeting or close with a sign-off. Plain words: prefer "average \
blood sugar over the last few months" to "glycaemic index over the preceding \
interval". Do not dramatise, do not reassure beyond what the findings say, \
and do not apologise.
"""


def _numbers_block(permitted_numbers: Sequence[float]) -> str:
    if not permitted_numbers:
        return (
            "## PERMITTED NUMBERS\n\n"
            "NONE. Write no digits at all in this explanation. Spell out any "
            "quantity in words, or leave it out."
        )
    rendered = ", ".join(_format_number(n) for n in permitted_numbers)
    return (
        "## PERMITTED NUMBERS\n\n"
        f"{rendered}\n\n"
        "These are the only digits you may write, plus any number that appears "
        "verbatim in the knowledge extracts below. Do not round them, do not "
        "convert them to other units, do not add approximations such as "
        "'about three months', and do not number your sentences. Any other "
        "number causes the whole explanation to be discarded."
    )


def _format_number(value: float) -> str:
    text = f"{float(value):.10g}"
    return text


def _findings_block(findings: Sequence[str]) -> str:
    if not findings:
        return "## Structured findings\n\nNone were supplied."
    return "## Structured findings\n\n" + "\n".join(f"- {f}" for f in findings)


def _knowledge_block(extracts: Sequence["KnowledgeExtract"]) -> str:
    if not extracts:
        return (
            "## Retrieved knowledge\n\nNONE. You have no sources, so you have "
            "nothing to explain from."
        )
    parts = ["## Retrieved knowledge", ""]
    for extract in extracts:
        parts.append(
            f"[{extract.doc_id}] {extract.title} (topic: {extract.topic}; "
            f"basis: {extract.basis})"
        )
        parts.append(extract.text)
        parts.append("")
    parts.append(
        "These extracts are the ONLY medical knowledge you have. Do not write "
        "the bracketed identifiers into your prose -- the system attaches the "
        "sources itself."
    )
    return "\n".join(parts)


class KnowledgeExtract:

    __slots__ = ("doc_id", "title", "topic", "basis", "text")

    def __init__(
        self, doc_id: str, title: str, topic: str, basis: str, text: str
    ) -> None:
        self.doc_id = doc_id
        self.title = title
        self.topic = topic
        self.basis = basis
        self.text = text


def _feedback_block(feedback: Optional[Iterable[Tuple[str, str, str]]]) -> str:
    items = list(feedback or ())
    if not items:
        return ""
    lines = [
        "## YOUR PREVIOUS ATTEMPT WAS REJECTED",
        "",
        "The automated safety layer refused your last answer. It was not shown "
        "to anyone. Write a new explanation that does not repeat these "
        "problems:",
        "",
    ]
    for code, reason, excerpt in items:
        excerpt_note = f' (the phrase "{excerpt}")' if excerpt else ""
        lines.append(f"- {code}: {reason}{excerpt_note}")
    lines.append("")
    lines.append(
        "Do not argue with the refusal and do not try to say the same thing "
        "more carefully. Drop the offending statement entirely."
    )
    return "\n".join(lines)


def build_explanation_prompt(
    *,
    subject: str,
    findings: Sequence[str],
    extracts: Sequence[KnowledgeExtract],
    permitted_numbers: Sequence[float] = (),
    feedback: Optional[Iterable[Tuple[str, str, str]]] = None,
) -> str:
    blocks = [
        f"Explain {subject} to the person whose report this is.",
        "",
        "The analysis has already been done. Your job is to put the findings "
        "below into language a person without medical training can follow, "
        "covering: what the parameter measures, why it matters, how the "
        "supplied value relates to the interpretation the analysis reached, "
        "and what the reader may want to raise with a qualified healthcare "
        "professional.",
        "",
        _findings_block(findings),
        "",
        _numbers_block(permitted_numbers),
        "",
        _knowledge_block(extracts),
        "",
        _rules_block(),
        "",
        _STYLE,
    ]
    feedback_text = _feedback_block(feedback)
    if feedback_text:
        blocks.extend(["", feedback_text])
    blocks.extend(["", "Write the explanation now. Output prose only."])
    return "\n".join(blocks)


def build_terminology_prompt(
    *,
    term: str,
    canonical_feature: Optional[str],
    extracts: Sequence[KnowledgeExtract],
    permitted_numbers: Sequence[float] = (),
    feedback: Optional[Iterable[Tuple[str, str, str]]] = None,
) -> str:
    named = f"{term}"
    if canonical_feature and canonical_feature.lower() != term.strip().lower():
        named = f"{term} (recorded by this platform as '{canonical_feature}')"
    blocks = [
        f"Explain the medical term {named} to someone reading their own "
        "laboratory report.",
        "",
        "Cover: what the test or term measures, why it is performed, what a "
        "value of it represents, and why it may matter. This is a general "
        "explanation of the term. NO ONE'S RESULT IS SUPPLIED and you must not "
        "write as though you have seen one, must not guess what a reader's "
        "value might be, and must not say whether any value would be good or "
        "bad.",
        "",
        _numbers_block(permitted_numbers),
        "",
        _knowledge_block(extracts),
        "",
        _rules_block(),
        "",
        _STYLE,
    ]
    feedback_text = _feedback_block(feedback)
    if feedback_text:
        blocks.extend(["", feedback_text])
    blocks.extend(["", "Write the explanation now. Output prose only."])
    return "\n".join(blocks)


__all__ = [
    "PROHIBITIONS",
    "PROMPT_VERSION",
    "SYSTEM_INSTRUCTION",
    "KnowledgeExtract",
    "build_explanation_prompt",
    "build_terminology_prompt",
]
