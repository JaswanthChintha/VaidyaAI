from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, Field

from app.config import Settings, get_settings
from app.core.logging import get_logger, safe_meta
from app.data.clinical_rules import COMPARATORS
from app.data.feature_catalog import NOT_MEASURED_SOURCES
from app.safety import (
    SafetyContext,
    guarded_generation,
)
from app.safety.policy import SAFETY_LAYER_VERSION

logger = get_logger(__name__)

NARRATIVE_VERSION = "1.0.0"


def _code_fingerprint() -> str:
    services = Path(__file__).resolve().parent
    files = [services / "clinician_narrative.py", services / "doctor_summary.py"]
    files += sorted((services.parent / "safety").glob("*.py"))
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.name.encode("utf-8"))
        try:
            digest.update(path.read_bytes().replace(b"\r\n", b"\n"))
        except OSError:
            digest.update(b"<unreadable>")
    return digest.hexdigest()[:16]


NARRATIVE_CODE_FINGERPRINT = _code_fingerprint()

OUTCOME_GENERATED = "generated"
OUTCOME_NO_MODEL = "model_unavailable"
OUTCOME_WITHHELD_BY_SAFETY = "withheld_by_safety"
OUTCOME_FACTS_MISSING = "facts_missing"

OUTCOME_VALUES = (
    OUTCOME_GENERATED,
    OUTCOME_NO_MODEL,
    OUTCOME_WITHHELD_BY_SAFETY,
    OUTCOME_FACTS_MISSING,
)

NOTICE = (
    "A written summary could not be prepared for this report, so the "
    "structured summary is shown instead. Nothing about the findings changes."
)

CLOSING_LINE = (
    "Not a diagnosis and not a clinical conclusion. The original laboratory "
    "report remains the primary record."
)


class NarrativeSafety(BaseModel):

    model_config = ConfigDict(frozen=True, extra="forbid")

    validated: bool
    verdict: Optional[str] = None
    version: str = SAFETY_LAYER_VERSION
    violation_codes: Tuple[str, ...] = ()
    attempts: int = 0


class ClinicianNarrative(BaseModel):

    model_config = ConfigDict(frozen=True, extra="forbid")

    module: int = 32
    version: str = NARRATIVE_VERSION
    outcome: str = Field(description="See OUTCOME_VALUES.")
    text: Optional[str] = None
    notice: Optional[str] = None
    missing_facts: Tuple[str, ...] = ()
    llm_calls_made: int = 0
    safety: NarrativeSafety


def _field(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _value_strings(summary: Any) -> List[str]:
    rows = _field(_field(summary, "laboratory"), "rows") or []
    out: List[str] = []
    for row in rows:
        value = _field(row, "value")
        if value is None:
            continue
        if _field(row, "usable") is False:
            continue

        provenance = _field(row, "provenance")
        if _field(provenance, "source") in NOT_MEASURED_SOURCES:
            continue

        printed = _field(_field(provenance, "original_test_name"), "text")
        if _field(provenance, "source") == "lab_report" and printed:
            name = str(printed)
        else:
            name = str(_field(row, "display_name") or _field(row, "feature") or "")

        unit = _field(row, "unit")
        rendered = f"{value} {unit}".strip() if unit else str(value)
        out.append(f"{name} {rendered}".strip())
    return out


def _unmapped_count(summary: Any) -> int:
    quality = _field(summary, "data_quality")
    counted = _field(quality, "unmapped_count")
    if isinstance(counted, int) and not isinstance(counted, bool) and counted > 0:
        return counted
    return 0


def _triggering(summary: Any) -> Dict[str, Tuple[str, ...]]:
    printed_by_key: Dict[str, str] = {}
    for row in _field(_field(summary, "laboratory"), "rows") or []:
        provenance = _field(row, "provenance")
        if _field(provenance, "source") != "lab_report":
            continue
        text = _field(_field(provenance, "original_test_name"), "text")
        if not text:
            continue
        for key in (_field(row, "feature"), _field(row, "display_name")):
            if key:
                printed_by_key.setdefault(str(key), str(text))

    named_by_key: Dict[str, str] = {}
    for row in _field(_field(summary, "laboratory"), "rows") or []:
        feature = _field(row, "feature")
        display = _field(row, "display_name")
        if feature and display:
            named_by_key.setdefault(str(feature), str(display))

    out: Dict[str, List[str]] = {}
    required: List[str] = []
    flagged = set(_field(summary, "abnormal_findings") or [])
    for assessment in _field(summary, "assessments") or []:
        condition = _field(assessment, "condition")
        if condition not in flagged:
            continue
        entries: List[Tuple[str, Optional[str], Optional[str]]] = []
        for basis in _field(assessment, "bases") or []:
            rule = _field(basis, "rule")
            for line in _field(rule, "triggering_values") or []:
                display = _field(line, "display_name")
                feature = _field(line, "feature")
                name = (
                    printed_by_key.get(str(feature))
                    or printed_by_key.get(str(display))
                    or display
                    or named_by_key.get(str(feature))
                    or feature
                )
                value = _field(line, "value")
                if not name or value is None:
                    continue
                unit = _field(line, "unit")
                classification = _field(line, "classification")
                comparator = _field(line, "comparator")
                threshold = _field(line, "threshold")
                compare = COMPARATORS.get(str(comparator)) if comparator is not None else None
                if compare is not None and threshold is not None:
                    try:
                        if not compare(float(value), float(threshold)):
                            continue
                    except (TypeError, ValueError):
                        pass
                base = f"{name} {value} {unit}".strip() if unit else f"{name} {value}"
                cut = (
                    f"{comparator} {threshold}"
                    if comparator is not None and threshold is not None
                    else None
                )
                entry = (base, cut, classification or None)
                if entry not in entries:
                    entries.append(entry)
                    required.append(str(value))

        def _render(base: str, cut: Optional[str], cls: Optional[str]) -> str:
            if cut and cls:
                return f"{base} ({cut}, {cls})"
            if cut:
                return f"{base} ({cut})"
            if cls:
                return f"{base} ({cls})"
            return base

        classes = {cls for _, _, cls in entries}
        shared = next(iter(classes)) if len(entries) > 1 and len(classes) == 1 else None
        if shared:
            rows = [_render(base, cut, None) for base, cut, _ in entries]
            rows.append(f"together, {shared}")
        else:
            rows = [_render(base, cut, cls) for base, cut, cls in entries]
        if rows:
            out[str(condition)] = tuple(rows)
    return {k: tuple(v) for k, v in out.items()}, tuple(dict.fromkeys(required))


def _qualified(summary: Any) -> Dict[str, str]:
    flagged = set(_field(summary, "abnormal_findings") or [])
    out: Dict[str, str] = {}
    for assessment in _field(summary, "assessments") or []:
        condition = _field(assessment, "condition")
        if condition not in flagged:
            continue
        status = _field(assessment, "status")
        if status and str(status).strip() and str(status).strip() != "Indicated":
            out[str(condition)] = str(status).strip()
    return out


def _out_of_range(summary: Any) -> Tuple[str, ...]:
    out: List[str] = []
    required: List[str] = []
    for row in _field(_field(summary, "laboratory"), "rows") or []:
        provenance = _field(row, "provenance")
        if _field(provenance, "source") in NOT_MEASURED_SOURCES:
            continue
        if _field(row, "usable") is False:
            continue
        value = _field(row, "value")
        if value is None:
            continue
        position = str(_field(row, "position") or "")
        flag = str(_field(row, "printed_flag") or "").strip().lower()
        abnormal = position in ("below_reference_interval", "above_reference_interval") or (
            flag not in ("", "none", "null", "normal")
        )
        if not abnormal:
            continue
        printed = _field(_field(provenance, "original_test_name"), "text")
        name = str(printed) if printed else str(
            _field(row, "display_name") or _field(row, "feature") or ""
        )
        unit = _field(row, "unit")
        rendered = f"{name} {value} {unit}".strip() if unit else f"{name} {value}"
        direction = (
            "below the printed reference interval"
            if position == "below_reference_interval"
            else "above the printed reference interval"
            if position == "above_reference_interval"
            else f"marked {flag} by the laboratory"
        )
        entry = f"{rendered} ({direction})"
        if entry not in out:
            out.append(entry)
            required.append(str(value))
    return tuple(out), tuple(dict.fromkeys(required))


def _flag_groups(summary: Any) -> Dict[str, Tuple[str, ...]]:
    flagged = set(_field(summary, "abnormal_findings") or [])
    both: List[str] = []
    rule_only: List[str] = []
    model_only: List[str] = []
    for assessment in _field(summary, "assessments") or []:
        name = _field(assessment, "condition")
        if name not in flagged:
            continue
        kinds = set()
        for basis in _field(assessment, "bases") or []:
            if _field(basis, "status") in (None, "Not Indicated"):
                continue
            if _field(basis, "assessed") is False:
                continue
            kind = _field(basis, "source_kind") or ""
            if kind == "machine_learning":
                kinds.add("model")
            elif kind:
                kinds.add("rule")
        if "rule" in kinds and "model" in kinds:
            both.append(str(name))
        elif "model" in kinds:
            model_only.append(str(name))
        elif "rule" in kinds:
            rule_only.append(str(name))
    return {
        "both": tuple(both),
        "rule_only": tuple(rule_only),
        "model_only": tuple(model_only),
    }


_NUMBER_TOKEN = re.compile(r"(?<![\d.])-?\d+(?:\.\d+)?")


def _numbers_in(values: Sequence[str]) -> Tuple[float, ...]:
    found: List[float] = []
    for item in values:
        for token in _NUMBER_TOKEN.findall(str(item)):
            try:
                found.append(float(token))
            except ValueError:
                continue
    return tuple(found)


def _round(value: Any, places: int = 2) -> Optional[str]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return f"{round(float(value), places):.{places}f}"


def _model_notes(summary: Any) -> List[str]:
    notes: List[str] = []
    seen: set = set()
    flagged = set(_field(summary, "abnormal_findings") or [])
    for assessment in _field(summary, "assessments") or []:
        condition = _field(assessment, "condition")
        if condition not in flagged:
            continue
        for basis in _field(assessment, "bases") or []:
            if _field(basis, "status") == "Not Indicated":
                continue
            if _field(basis, "assessed") is False:
                continue
            ml = _field(basis, "ml")
            if ml is None:
                continue
            limits = _field(ml, "limitations")
            if limits is None:
                continue
            key = str(condition)
            if key in seen:
                continue
            seen.add(key)

            model = _field(ml, "model_name") or "statistical model"
            if _field(limits, "metrics_available") is False:
                notes.append(
                    f"{condition}: flagged by a {model}. No validation metrics "
                    "are recorded for this model, so its performance cannot be "
                    "stated. Not a measurement and not diagnostic."
                )
                continue

            bits: List[str] = []
            auc = _round(_field(limits, "roc_auc"), 3)
            if auc:
                bits.append(f"ROC-AUC {auc}")
            precision = _round(_field(limits, "precision_at_operating_threshold"))
            recall = _round(_field(limits, "recall_at_operating_threshold"))
            if precision and recall:
                bits.append(f"precision {precision} / recall {recall}")
            threshold = _round(_field(limits, "operating_threshold"))
            if threshold:
                bits.append(f"at an operating threshold of {threshold}")
            measured = _field(limits, "measured_on")
            if measured:
                measured = re.sub(
                    r",\s*(?:see|refer to)\b[^,]*\bartifacts?\b\.?$",
                    "",
                    str(measured).strip(),
                    flags=re.IGNORECASE,
                ).rstrip(" .,")
                if measured:
                    bits.append(f"measured on {measured}")
            variant = _field(limits, "variant")
            if variant and str(variant) != "neither":
                bits.append(f"variant: {str(variant).replace('_', ' ')}")

            notes.append(
                f"{condition}: flagged by a {model} -- "
                + ", ".join(bits)
                + ". An estimated probability from comparable records, not a "
                "measurement of this patient and not a diagnosis."
            )
    return notes


_COMORBIDITY_KEYS = ("hypertension", "heart_disease", "smoking_history")


def _not_supplied(patient: Any) -> Tuple[str, ...]:
    return tuple(
        key for key in _COMORBIDITY_KEYS if _field(patient, key, None) is None
    )


class _Facts(BaseModel):

    model_config = ConfigDict(frozen=True, extra="forbid")

    subject: str
    values: Tuple[str, ...]
    flagged: Tuple[str, ...]
    normal: Tuple[str, ...]
    unassessed: Tuple[str, ...]
    not_supplied: Tuple[str, ...]
    model_notes: Tuple[str, ...]
    no_intervals: bool
    triggering: Dict[str, Tuple[str, ...]] = Field(default_factory=dict)
    qualified: Dict[str, str] = Field(default_factory=dict)
    out_of_range: Tuple[str, ...] = ()
    required_values: Tuple[str, ...] = ()
    unmapped_count: int = 0
    flagged_both: Tuple[str, ...] = ()
    flagged_rule_only: Tuple[str, ...] = ()
    flagged_model_only: Tuple[str, ...] = ()


def collect_facts(summary: Any) -> _Facts:
    patient = _field(summary, "patient") or {}
    age = _field(patient, "age")
    gender = _field(patient, "gender")
    subject = " ".join(
        part
        for part in (
            f"{age}-year-old" if age is not None else "",
            str(gender) if gender else "",
        )
        if part
    ).strip() or "This patient"

    rows = _field(_field(summary, "laboratory"), "rows") or []
    no_intervals = bool(rows) and all(
        _field(row, "reference_low") is None and _field(row, "reference_high") is None
        for row in rows
    )

    groups = _flag_groups(summary)
    triggering, trigger_values = _triggering(summary)
    out_of_range, range_values = _out_of_range(summary)
    return _Facts(
        flagged_both=groups["both"],
        flagged_rule_only=groups["rule_only"],
        flagged_model_only=groups["model_only"],
        subject=subject,
        values=tuple(_value_strings(summary)),
        flagged=tuple(_field(summary, "abnormal_findings") or []),
        normal=tuple(_field(summary, "normal_findings") or []),
        unassessed=tuple(_field(summary, "unassessed_conditions") or []),
        not_supplied=_not_supplied(patient),
        model_notes=tuple(_model_notes(summary)),
        no_intervals=no_intervals,
        triggering=triggering,
        qualified=_qualified(summary),
        out_of_range=out_of_range,
        required_values=trigger_values,
        unmapped_count=_unmapped_count(summary),
    )


def _missing(text: str, facts: _Facts) -> Tuple[str, ...]:
    gaps: List[str] = []
    body = text
    lowered = body.lower()

    for name in facts.flagged:
        if str(name).lower() not in lowered:
            gaps.append(f"flagged:{name}")

    for value in facts.required_values:
        if value not in body:
            gaps.append(f"value:{value}")

    if facts.flagged_model_only and not re.search(
        r"(model|pattern)[^.]{0,140}\b(alone|only|by itself)\b"
        r"|\b(alone|only|by itself)\b[^.]{0,80}(model|pattern)"
        r"|no measured value[^.]{0,80}(cross|cut-off|cutoff|threshold)"
        r"|(did not|without)[^.]{0,40}cross",
        lowered,
    ):
        gaps.append("model_only_distinction")

    for condition, status in facts.qualified.items():
        word = str(status).split()[0].lower()
        name = re.escape(str(condition).lower())
        near = rf"{name}[^.]{{0,100}}\b{re.escape(word)}\b|\b{re.escape(word)}\b[^.]{{0,100}}{name}"
        if not re.search(near, lowered):
            gaps.append(f"status:{condition}")

    return tuple(dict.fromkeys(gaps))

_INSTRUCTIONS = """You are writing a short handover note for a clinician who has
been handed a patient's phone. Use the facts below and NOTHING else.

WHAT THIS NOTE CONTAINS, AND IT CONTAINS NOTHING ELSE:
  1. what was flagged, and the measured value and threshold behind each one.

Do NOT list the parameters that are outside their printed reference interval.
The page composes that list itself, from the rows, and prints it directly
below this note.

Say nothing about what was assessed, what was not assessed, what could not be
assessed, or what was not supplied. Do not mention this tool's coverage, its
scope, or anything it did not look at. A reader wants the findings.

Rules:
- Plain professional English. No headings, no bullet points, no markdown.
- Begin every sentence with a capital letter, including one that starts with a
  name copied from the facts below. Those are given in lower case and a
  sentence opening ". hypertension, heart disease..." has reached a real
  document on this project before.
- Do not name or describe the software, its components, its models by type, or
  any statistical measure such as an AUC, a precision or a recall. Write about
  the patient.
- Do not state or imply that the patient has any condition. Findings are
  things this tool flagged, not diagnoses.
- DO NOT INTERPRET ANY VALUE. Never write what a result means, suggests,
  indicates, reflects, is consistent with, points to, or is in keeping with.
  Report what was measured and what was flagged, and stop there.
- Attribute every finding: "this tool flagged X", never "X is present",
  "X is likely" or "the results show X".
- A HEADING THAT IS NOT "FLAGGED" IS THE STATUS, AND YOU MUST CARRY IT.
  "BORDERLINE -- Obesity" is not a flag: write that the tool recorded Obesity
  as borderline, in the same sentence as the name, not that it flagged
  Obesity. Do not upgrade a borderline finding to a flagged one, and never
  drop the word.
- Give the REASON with the finding: the parameter, its value and the threshold
  it crossed, exactly as the facts give them.
- Do not describe any value as high, low, raised, elevated, poor, good or
  well-controlled beyond what the facts themselves say. If a value crossed a
  cut-off, say that it crossed one.
- Use only the numbers given. Never introduce a number that is not below.
- Name every laboratory value WITH ITS TEST NAME, exactly as given.
- Every flagged topic must appear, and every value given as its reason.
- For each topic under FLAGGED BY THE STATISTICAL MODEL, write this sentence
  with the topic's name in it: "<topic> was flagged by the statistical model
  alone, and no measured value crossed a cut-off for it."
- Do not write any closing disclaimer. That sentence is added after you.
- Do not state the patient's age or sex. The page states them above this note.
- Topics that share a reason go in ONE sentence as a list. Do not repeat the
  same sentence with a different name in it; four copies of "this tool flagged
  X because a measured value crossed a cut-off" is the fault this document was
  rewritten to remove.
- THE READER IS A CLINICIAN. Write for one: concise, technical, no lay glosses.
  Do not explain what a laboratory test is or what a threshold means, and do
  not reassure or advise. Use the clinical name of a parameter where the report
  gives one. Prefer the shortest sentence that carries the fact. This is a
  handover note, not patient education.
- Two or three short paragraphs, SEPARATED BY A BLANK LINE. The reader's page
  splits paragraphs on blank lines; groups divided by spaces arrive as one
  dense block.
"""


def _facts_block(facts: _Facts) -> str:
    lines: List[str] = []

    for condition in facts.flagged:
        reasons = facts.triggering.get(condition)
        if reasons:
            status = facts.qualified.get(condition)
            head = f"{status.upper()} -- {condition}" if status else f"FLAGGED -- {condition}"
            lines.append(f"{head}: " + "; ".join(reasons))
    unexplained = [c for c in facts.flagged if not facts.triggering.get(c)]
    if unexplained:
        model_only = [c for c in unexplained if c in facts.flagged_model_only]
        other = [c for c in unexplained if c not in facts.flagged_model_only]
        if model_only:
            lines.append(
                "FLAGGED BY THE STATISTICAL MODEL, no measured value crossed a "
                "cut-off: " + ", ".join(model_only)
            )
        if other:
            lines.append(
                "ALSO FLAGGED: "
                + ", ".join(
                    f"{c} ({facts.qualified[c].lower()})" if c in facts.qualified else c
                    for c in other
                )
            )

    if not lines:
        lines.append("NOTHING FLAGGED: this tool flagged no topic on this report.")


    return "\n".join(lines)


def build_prompt(facts: _Facts, feedback: Any = None, missing: Sequence[str] = ()) -> str:
    prompt = f"{_INSTRUCTIONS}\n{_facts_block(facts)}\n"
    if missing:
        prompt += (
            "\nYour previous answer LEFT OUT the following, and every one of "
            "them must appear: "
            + "; ".join(str(item).split(":", 1)[-1].replace("_", " ") for item in missing)
            + ". Write it again with all of them included.\n"
        )
    if feedback is not None:
        codes = ", ".join(sorted(set(getattr(feedback, "codes", ()) or ())))
        if codes:
            prompt += (
                "\nYour previous answer was refused by a safety check for: "
                f"{codes}. Rewrite it without that content. Do not restate any "
                "condition as present, and do not give treatment advice.\n"
            )
    return prompt


def _resolve_llm(llm: Any, settings: Optional[Settings]) -> Optional[Any]:
    if llm is not None:
        return llm
    resolved = settings or get_settings()
    if not resolved.has_api_key:
        return None
    from app.services.gemini_text import build_text_client

    return build_text_client(resolved)


def _refusal(outcome: str, safety: NarrativeSafety, *, missing=(), calls=0):
    return ClinicianNarrative(
        outcome=outcome,
        text=None,
        notice=NOTICE,
        missing_facts=tuple(missing),
        llm_calls_made=calls,
        safety=safety,
    )


def write_clinician_summary(
    summary: Any,
    *,
    llm: Any = None,
    settings: Optional[Settings] = None,
) -> ClinicianNarrative:
    facts = collect_facts(summary)
    client = _resolve_llm(llm, settings)
    if client is None:
        return _refusal(
            OUTCOME_NO_MODEL,
            NarrativeSafety(validated=False),
        )

    permitted = (
        _numbers_in(facts.values)
        + _numbers_in(tuple(facts.model_notes))
        + _numbers_in(
            tuple(value for values in facts.triggering.values() for value in values)
        )
        + _numbers_in(facts.required_values)
    )

    context = SafetyContext(
        grounding_sources=tuple(facts.model_notes) or (_facts_block(facts),),
        permitted_numbers=permitted,
        require_referral=False,
        purpose="clinician_narrative",
    )

    gaps: Tuple[str, ...] = ()
    result = None
    calls = 0
    for round_missing in ((), None):
        if round_missing is None:
            if not gaps:
                break
            round_missing = gaps

        def generate(feedback: Any = None, _missing_now=round_missing) -> Any:
            return client.generate_text(build_prompt(facts, feedback, _missing_now))

        result = guarded_generation(generate, context=context, attempts=2)
        calls += result.attempts
        if not result.approved_text:
            break
        gaps = _missing(result.approved_text, facts)
        if not gaps:
            break

    safety = NarrativeSafety(
        validated=True,
        verdict="approved" if result and result.approved_text else "rejected",
        violation_codes=tuple(sorted(set(result.verdict.codes)))
        if result and result.verdict
        else (),
        attempts=calls,
    )

    if not result or not result.approved_text:
        logger.warning(
            "clinician_narrative %s",
            safe_meta(outcome=OUTCOME_WITHHELD_BY_SAFETY, module=32),
        )
        return _refusal(OUTCOME_WITHHELD_BY_SAFETY, safety, calls=calls)
    if gaps:
        logger.warning(
            "clinician_narrative %s",
            safe_meta(outcome=OUTCOME_FACTS_MISSING, missing=len(gaps), module=32),
        )
        return _refusal(OUTCOME_FACTS_MISSING, safety, missing=gaps, calls=calls)

    logger.info(
        "clinician_narrative %s",
        safe_meta(outcome=OUTCOME_GENERATED, attempts=result.attempts, module=32),
    )
    parts = [result.approved_text.strip()]
    parts.append(CLOSING_LINE)

    return ClinicianNarrative(
        outcome=OUTCOME_GENERATED,
        text="\n\n".join(parts),
        notice=None,
        llm_calls_made=calls,
        safety=safety,
    )


__all__ = [
    "CLOSING_LINE",
    "ClinicianNarrative",
    "NOTICE",
    "OUTCOME_FACTS_MISSING",
    "OUTCOME_GENERATED",
    "OUTCOME_NO_MODEL",
    "OUTCOME_VALUES",
    "OUTCOME_WITHHELD_BY_SAFETY",
    "collect_facts",
    "write_clinician_summary",
]
