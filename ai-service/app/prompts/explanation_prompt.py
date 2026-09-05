"""The Gemini prompts for Modules 23 and 25.

Kept in its own module -- like `extraction_prompt.py` -- so the exact words put
in front of the model can be reviewed, diffed and versioned independently of
the service code. Bump `PROMPT_VERSION` on any wording change.

==========================================================================
WHAT THIS PROMPT IS AND IS NOT
==========================================================================

It is NOT a safety mechanism. Module 24 is the safety mechanism, and it runs
over every generation afterwards regardless of what the model was asked. A
prompt is a request; a validator is a control. This file exists to make the
request as narrow as possible so that the control is rarely the thing standing
between a patient and an unsafe sentence.

That distinction matters for how the file is read: nothing here may be cited as
evidence that the system cannot produce unsafe text. It can. `app/safety/`
is why it does not reach a patient.

==========================================================================
THE SIX PROHIBITIONS
==========================================================================

`PROHIBITIONS` below is the reviewable list, and it is interpolated into the
prompt rather than restated, so the list and the prompt cannot drift apart.
Spec section 14 names each of these as something the safety layer must catch:

    no diagnosis, no medication, no dosage, no claim of certainty,
    always defer to a qualified healthcare professional,
    use only the values and knowledge supplied.

==========================================================================
WHY THE SUPPLIED-VALUES RULE IS STATED SO INSISTENTLY
==========================================================================

Module 24 enforces NUMERIC GROUNDING: every number in the output must appear
either in the retrieved knowledge or among the patient's validated values. A
model that invents "the normal range is 70 to 99" when 99 was never supplied
gets its whole explanation rejected -- so a fabricated number does not cost the
patient a wrong fact, it costs them the entire explanation.

The prompt therefore lists the permitted numbers explicitly and forbids
numbered lists, percentages, dates and "about 3 months" style approximations,
because each of those is a number the validator will not find in the sources.
"""

from __future__ import annotations

from typing import Iterable, Optional, Sequence, Tuple

PROMPT_VERSION = "m23-explain-v1"


#: The reviewable prohibition list. Tested for, interpolated below, and
#: published by `GET /api/v1/explain/policy`.
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


#: Appended to every prompt. Separated so the rules are visibly the same for
#: the explanation path and the terminology path.
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
    """One retrieved chunk, in the shape the prompt renders.

    A tiny local structure rather than an import of `app.rag.schemas`, so this
    file stays a pure prompt module with no dependency on the retriever's
    representation. `app/services/explanation.py` does the conversion.
    """

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
    """Render the previous rejection so a retry is not the same request.

    `feedback` is `(code, reason, excerpt)` triples taken from the previous
    `SafetyVerdict`. Retrying with an unchanged prompt would be asking the same
    question and hoping for a different answer, which is why
    `app/services/explanation.py` refuses to retry when there is nothing to
    say back.
    """
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
    """Module 23's prompt: structured findings + retrieved knowledge -> prose.

    `subject` is what is being explained ("the HbA1c result"). `findings` are
    Module 16/17's already-computed statements, rendered as flat lines. Nothing
    the patient typed reaches this prompt; nothing outside `extracts` and
    `permitted_numbers` is available to the model.
    """
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
    """Module 25's optional plain-language rewrite of a curated term entry.

    Reached ONLY after the term has been mapped to something the curated corpus
    actually covers -- see `app/services/terminology.py`. The model is never
    asked "what is X"; it is asked to simplify text the platform already holds.
    """
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
