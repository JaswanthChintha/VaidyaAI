"""Module 32's handover note, written as prose by the model.

==========================================================================
WHY THIS EXISTS, AND WHAT IT IS NOT ALLOWED TO COST
==========================================================================

The clinician summary has always been COMPOSED: every sentence assembled from
a decision some stage already made, with `integrity.llm_calls_made: 0` and
`model_generated_text_included: false` published about the document itself.
That was the right default and MEMORY.md 6w argues it at length -- "summarise
these results for a doctor" is the worst possible use of a model, because a
clinical narrative with no rule, no threshold and no evidence chain reads more
authoritative than the findings it is made of.

The user asked for it to be written by the model anyway, because the composed
version kept reaching for this system's own vocabulary. That is a legitimate
call: prose written for a reader is better prose. **It is implemented so that
the worst case is exactly the composed passage**, and so that the two claims
above stop being false the moment a model is involved.

FOUR GATES, AND THE TEXT IS DISCARDED AT ANY OF THEM:

1. NO MODEL, NO GENERATION. Without a key the caller renders what it renders
   today. This is also what makes the suite run offline.
2. MODULE 24. The same `guarded_generation` every other model text goes
   through. A refused generation is discarded inside the safety layer and
   never reaches this module.
3. THE FACT CHECK, which is this file's own contribution. A model asked to
   rewrite may drop a sentence, and the sentences it is most likely to drop
   are the qualifying ones. Every value, every flagged name, every unassessed
   name, every unsupplied profile answer, the no-intervals fact and the
   model-only distinction must be present in the output or the whole thing is
   thrown away. See `_missing`.
4. NO SILENT SUBSTITUTION. `text` is None on every refusal and `outcome` says
   which gate stopped it, so a caller cannot render a partial narrative and
   cannot mistake a refusal for an empty document.

Each refusal gets ONE retry that says what went wrong -- the safety layer
quotes its codes back, and a fact check failure names what was dropped. "Try
again" is not feedback, and without the second kind a model that omits one of
three unsupplied answers fails permanently for that report.

==========================================================================
THE MODEL NEVER HANDLES THE SAFETY-CRITICAL SENTENCES
==========================================================================

The model limitation note and the closing line are APPENDED after approval,
verbatim, and the model is told not to write them. The first version asked it
to copy them and had `_missing` verify the copy, which was wrong twice over:

* it was unsatisfiable. The kidney model's own note is judged
  UNHEDGED_INTERPRETIVE_CLAIM by this module's safety context -- it passes
  Module 32's transcription check, which applies different controls -- so a
  narrative REQUIRED to contain it could never be approved. Every live attempt
  was refused, and the refusing paragraph was the safety note itself;
* even if it had passed, a sentence the model retypes is a sentence the model
  can mistype. Appending it is not a weaker guarantee than checking it, it is
  the difference between verifying a copy and not making one.

==========================================================================
THE ONE PROPERTY THIS FILE MUST HAVE
==========================================================================

Model-written text enters `ClinicianNarrative.text` from exactly one place --
`GuardedGenerationResult.approved_text`, and only after `_missing` returns
empty. The limitation notes and the closing line are then appended from our own
constants. A refused generation is never stored on the object at all.

==========================================================================
WHY `require_referral` IS OFF HERE, AND WHAT REPLACES IT
==========================================================================

Module 24's default demands the "consult a qualified healthcare professional"
framing, which is incoherent in a document ADDRESSED to that professional.

MEASURED, NOT ASSUMED, because the first version of this comment claimed more
than was true. Running the validator both ways over the same approved text:

    require_referral=False -> approved, no codes
    require_referral=True  -> approved, codes ['MISSING_PROFESSIONAL_REFERRAL']

So it is **not a blocking control** -- it records a code and approves anyway,
which is 6r's finding about MISSING_PROFESSIONAL_REFERRAL, named in 6k D1 and
never actually fixed. Leaving it on would therefore stamp a violation code on
every narrative this module ever produces while refusing nothing. It is off
for that reason and no other, and a mutation flipping it is EQUIVALENT -- the
behaviour does not change either way.

What actually enforces the framing is the closing line, and it is APPENDED
rather than checked: the model never writes it, so it cannot be dropped at all.
Every other control -- diagnostic assertions, treatment advice, numeric
grounding -- is untouched and does block.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, Field

from app.config import Settings, get_settings
from app.core.logging import get_logger, safe_meta
from app.safety import (
    SafetyContext,
    guarded_generation,
)
from app.safety.policy import SAFETY_LAYER_VERSION

logger = get_logger(__name__)

NARRATIVE_VERSION = "1.0.0"

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

#: Shown by the caller when there is no approved narrative. It says which of
#: the four cases happened in words, because "the composed version is what you
#: are reading" is a fact the reader is entitled to.
NOTICE = (
    "A written summary could not be prepared for this report, so the "
    "structured summary is shown instead. Nothing about the findings changes."
)

#: The line the document closes on. APPENDED after approval, never written by
#: the model -- which is what allows `require_referral` to be off without
#: losing the framing (see the module docstring).
CLOSING_LINE = (
    "Not a diagnosis and not a clinical conclusion. The original laboratory "
    "report remains the primary record."
)


class NarrativeSafety(BaseModel):
    """What the safety layer did. Codes and counts only -- never the text."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    validated: bool
    verdict: Optional[str] = None
    version: str = SAFETY_LAYER_VERSION
    violation_codes: Tuple[str, ...] = ()
    attempts: int = 0


class ClinicianNarrative(BaseModel):
    """The written handover note, or the stated reason there is not one."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    module: int = 32
    version: str = NARRATIVE_VERSION
    outcome: str = Field(description="See OUTCOME_VALUES.")
    #: The ONLY string a caller may render. None on every refusal.
    text: Optional[str] = None
    notice: Optional[str] = None
    #: Which required facts were absent from the model's output. Populated
    #: only for OUTCOME_FACTS_MISSING, and it names the FACT, never the text.
    missing_facts: Tuple[str, ...] = ()
    llm_calls_made: int = 0
    safety: NarrativeSafety


# --------------------------------------------------------------------------
# The facts the narrative is made of, and must still contain
# --------------------------------------------------------------------------


def _field(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _value_strings(summary: Any) -> List[str]:
    """Every reported value, NAMED, exactly as the document prints it.

    WITH THE TEST NAME. The first version passed bare numbers, and the model
    duly wrote "the reported values are 8.4 %, 186 mg/dl, 14.8 g/dl..." -- a
    list of quantities of nothing, which is worse than the composed passage it
    was meant to improve on.

    LABORATORY ROWS ONLY. `laboratory.rows` also carries the age, sex and BMI
    the assessment used, and listing "58 years" and "male" under "reported
    values" says the laboratory measured them.
    """
    rows = _field(_field(summary, "laboratory"), "rows") or []
    out: List[str] = []
    for row in rows:
        value = _field(row, "value")
        if value is None:
            continue
        if _field(row, "usable") is False:
            continue

        # `provenance.source`, NOT a top-level `source`. The first version
        # looked for the latter, found nothing on any row, and let the profile
        # answers through -- the live narrative opened "a patient with Age in
        # whole years recorded as 58 years and Self-described gender as stored
        # by Module 2 as male", which is the catalog's INTERNAL note for
        # `gender` (MEMORY.md 6y, still open at source) printed in a clinical
        # document. This is the same predicate the composed passage uses and
        # has been right on real data for three sessions.
        provenance = _field(row, "provenance")
        if _field(provenance, "source") == "patient_profile":
            continue

        # The laboratory's own printed name when there is one; otherwise the
        # catalog's. Never `display_name` for a profile row -- see above.
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
    """Parameters the laboratory reported that this platform does not assess.

    `_value_strings` above returns the ASSESSED subset and nothing else -- four
    rows on `Test 2.pdf`, out of twenty-one the laboratory printed. Handed that
    list under the heading "REPORTED VALUES", the model wrote, faithfully:

        "The reported values are GLYSOLATED HAEMOGLOBIN ( HBA1C) 5.9 %, Random
         Blood Sugar 134.7 mg/dl, Haemoglobin 10.6 g/dl, and SERUM CREATININE
         0.99 mg/dl."

    Seventeen were missing from that sentence, among them a CRP of 12.1 mg/L,
    an SGPT of 101.9 U/L and an ESR of 35 mm/hr. A clinician reading it would
    reasonably take it for the panel.

    THE MODEL WAS OBEYING THE LABEL. The fix is not a stronger instruction: it
    is to stop calling the assessed subset "the reported values", and to give
    the document the number it needs to say what it has not covered.
    """
    quality = _field(summary, "data_quality")
    counted = _field(quality, "unmapped_count")
    if isinstance(counted, int) and not isinstance(counted, bool) and counted > 0:
        return counted
    return 0


def _triggering(summary: Any) -> Dict[str, Tuple[str, ...]]:
    """For every FLAGGED condition, the values that crossed and what they crossed.

    THE READER'S SPEC, AND IT IS A BETTER DOCUMENT THAN THE ONE IT REPLACES:
    "what diseases are flagged and why, that's it".

    The "why" is not prose -- it is on the payload already, as the rule's own
    triggering values: the parameter, its value, the comparator, the threshold
    and the classification the rule assigned. "Glycated haemoglobin 7 % at or
    above the ADA diabetes-range threshold of 6.5 %" is the reason, stated in
    the producer's own words.

    WHY NOT `position` FOR THIS. On `Test 3.pdf` only ONE row is
    `above_reference_interval`, because the laboratory printed no interval for
    HbA1c or haemoglobin -- yet those two are exactly what flagged Diabetes and
    Anemia. A document that listed "out of range" by printed interval alone
    would omit the values its own findings rest on.
    """
    # THE LABORATORY'S OWN PRINTED NAME, wherever there is one -- the same
    # rule `_value_strings` follows and for the same reason: a clinician
    # matches the row against the paper in front of them. The triggering
    # values carry the catalog's display name, so they are joined back to the
    # laboratory rows on the feature key.
    # KEYED ON BOTH, because a triggering value and a laboratory row do not
    # always agree on which identifier they carry: the rule lines lead with
    # `display_name` and the rows with `feature`. Matching on either is what
    # makes the join land on real payloads and on fixtures alike.
    printed_by_key: Dict[str, str] = {}
    for row in _field(_field(summary, "laboratory"), "rows") or []:
        provenance = _field(row, "provenance")
        # ONLY A LABORATORY ROW HAS A PRINTED NAME WORTH PREFERRING. A profile
        # row carries a transcribed `original_test_name` too -- the BMI row's
        # is the string "bmi" (§6w's open `origin: report_transcription`) --
        # and trusting it put the internal feature key into the document as
        # "bmi 25.25 kg/m2", which is what §6an-i swept off every
        # reader-facing screen. Same predicate `_value_strings` uses.
        if _field(provenance, "source") != "lab_report":
            continue
        text = _field(_field(provenance, "original_test_name"), "text")
        if not text:
            continue
        for key in (_field(row, "feature"), _field(row, "display_name")):
            if key:
                printed_by_key.setdefault(str(key), str(text))

    # AND A FALLBACK TO THE CATALOG NAME, so a rule line that carries only a
    # feature key never puts one on the page. Obesity's trigger is the BMI,
    # whose row is a profile answer with no printed laboratory name -- without
    # this the document said "bmi 25.25 kg/m2", which is the internal key
    # §6an-i swept off every reader-facing screen.
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
        rows: List[str] = []
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
                rendered = f"{name} {value} {unit}".strip() if unit else f"{name} {value}"
                classification = _field(line, "classification")
                comparator = _field(line, "comparator")
                threshold = _field(line, "threshold")
                if comparator is not None and threshold is not None:
                    rendered += f" ({comparator} {threshold}"
                    rendered += f", {classification})" if classification else ")"
                elif classification:
                    rendered += f" ({classification})"
                if rendered not in rows:
                    rows.append(rendered)
                    required.append(str(value))
        if rows:
            out[str(condition)] = tuple(rows)
    return {k: tuple(v) for k, v in out.items()}, tuple(dict.fromkeys(required))


def _qualified(summary: Any) -> Dict[str, str]:
    """Flagged conditions whose status is NOT a plain `Indicated`.

    ==========================================================================
    WHY THIS EXISTS: "flagged Obesity" FOR A BMI OF 25.25
    ==========================================================================

    Read off the real clinician page on 2026-09-18:

        This tool flagged Obesity because Body mass index was 25.25 kg/m2
        (>= 25, inside the WHO overweight band of 25.0-29.9).

    **The sentence contradicts its own parenthetical.** 25.25 is overweight;
    obesity begins at 30.0. Module 8 had it right -- `RULE_OBESITY_BMI` puts
    that value in a BORDERLINE band at LOW risk and labels it the overweight
    band -- and the composed document renders it right too, as
    `Obesity (borderline)`. Only the WRITTEN narrative lost it, and it lost it
    because `_facts_block` handed the model the word FLAGGED for every
    condition in `abnormal_findings` regardless of status. **The model was
    told it was flagged, so it wrote that it was flagged.**

    The same collapse hits Diabetes, which holds two separate decisions here --
    `Indicated` on HbA1c 7 % and `Borderline` on a random glucose of 168 --
    and was narrated as one flat "flagged ... because A and B".

    THE STATUS IS THE RULE ENGINE'S OWN WORD, carried through rather than
    re-derived. This function does not decide what is borderline; it reports
    what Module 8 already decided.
    """
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
    """Laboratory rows outside the interval the laboratory itself printed.

    Separate from `_triggering` and both are wanted: a parameter can be marked
    high by the laboratory without crossing any cut-off this tool holds, and
    that is still a parameter out of range.
    """
    out: List[str] = []
    required: List[str] = []
    for row in _field(_field(summary, "laboratory"), "rows") or []:
        provenance = _field(row, "provenance")
        if _field(provenance, "source") == "patient_profile":
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
    """Which KIND of check flagged what -- MEMORY.md 6w's first kept thing.

    A clinician told "kidney disease flagged", with no mention that no measured
    value crossed anything, is being told something the analysis did not find.
    The composed passage says it; the narrative has to as well, and `_missing`
    verifies the model-only group survived.
    """
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


#: A HYPHEN BETWEEN TWO DIGITS IS A RANGE, NOT A MINUS SIGN.
#:
#: The classification text carries "the WHO overweight band of 25.0-29.9", and
#: the old pattern read that as 25.0 and MINUS 29.9. The permitted set then
#: held -29.9 while the model, quite reasonably, wrote 29.9 -- and the whole
#: document was refused as an UNGROUNDED_NUMERIC_CLAIM. Two live generations
#: were lost to it before the permitted set was printed and read.
#:
#: The lookbehind refuses to treat "-" as a sign when a digit or a decimal
#: point precedes it, which is exactly when it is a range.
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
    """A metric as a clinician would read it, or nothing."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return f"{round(float(value), places):.{places}f}"


def _model_notes(summary: Any) -> List[str]:
    """The performance of every model that FLAGGED, in one line each.

    THE RULE IS UNCHANGED FROM 6w AND IS NOT NEGOTIABLE: a model-derived flag
    may not appear without its limitation. That defect -- "every model
    probability shown with no ROC-AUC, no recall and no caveat" -- recurred
    three times and is what this function exists to prevent.

    WHAT CHANGED IS THE REGISTER, on the reader's objection. This returned
    `limitations.author_note.text`, a curated note written in plain language
    for a lay reader:

        "This came from a pattern model, not from a measurement. It was
         developed on one small dataset in which the two groups separated
         unusually cleanly, so its accuracy there flatters it ..."

    In a document headed "Summary for a healthcare professional" that is a
    paragraph of methodology narrative where a clinician wants the numbers.
    The same structure already carries them -- `roc_auc`, precision and recall
    AT THE OPERATING THRESHOLD, the threshold itself, the validation split and
    the model variant -- so the note is now built from those.

    IT ALSO COVERS MORE THAN THE PROSE DID. `author_note` is `NOT_PRESENT` for
    the diabetes model, so on a report flagging Diabetes and Kidney Disease
    only ONE caveat ever appeared. Diabetes carries recall 0.70 at its
    operating threshold -- close to a third of true cases not flagged -- which
    is precisely the figure a clinician needs and the old note omitted.

    A model with no metrics still gets a line saying so: `metrics_available`
    false is a fact about the model, and silence would read as "no limitation".
    """
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
            # THREE PLACES FOR THE AUC. The kidney model's 0.9987 rounds to
            # "1.00" at two, which reads as a perfect classifier -- the one
            # impression this note exists to prevent.
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
                # "held-out test split, see the metrics artifact" -- the
                # trailing clause points at `ml/artifacts/*.metrics.json` and
                # is for whoever maintains the model, not for the clinician
                # reading this line. WHICH SPLIT the metrics came from is
                # clinical information and stays; only the pointer goes, and
                # only when it is recognisably a pointer.
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


#: The three tri-state comorbidity answers. `null` means the patient never
#: supplied one -- NOT that they answered no.
_COMORBIDITY_KEYS = ("hypertension", "heart_disease", "smoking_history")


def _not_supplied(patient: Any) -> Tuple[str, ...]:
    """Which profile answers the analysis did not have.

    DERIVED THE WAY THE PRODUCER EXPOSES IT, which is as `null` values on the
    three tri-state keys -- there is no `not_supplied` list on the payload. The
    first version read one, got an empty tuple on every real report, and the
    absence check it fed could therefore never fire: the live narrative dropped
    "hypertension, heart disease and smoking history were not supplied" and the
    gate reported nothing missing.

    Second time in this module that a guessed field name produced a check that
    silently protected nothing. Read the response, not the variable name.
    """
    return tuple(
        key for key in _COMORBIDITY_KEYS if _field(patient, key, None) is None
    )


class _Facts(BaseModel):
    """What the narrative is built from AND checked against."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    subject: str
    values: Tuple[str, ...]
    flagged: Tuple[str, ...]
    normal: Tuple[str, ...]
    unassessed: Tuple[str, ...]
    not_supplied: Tuple[str, ...]
    model_notes: Tuple[str, ...]
    no_intervals: bool
    #: Per flagged condition, the values that crossed and what they crossed.
    #: This IS the "why" the document is now made of.
    triggering: Dict[str, Tuple[str, ...]] = Field(default_factory=dict)
    #: Flagged conditions whose status is not a plain `Indicated`, as
    #: {condition: status}. See `_qualified`: the narrative called a
    #: BORDERLINE overweight finding "flagged Obesity".
    qualified: Dict[str, str] = Field(default_factory=dict)
    #: Rows outside the laboratory's own printed interval.
    out_of_range: Tuple[str, ...] = ()
    #: THE BARE VALUES behind the two above, taken from the producer rather
    #: than re-parsed out of the rendered strings. Re-parsing picked the 1 out
    #: of "HbA1c" as the number to check for, which is present in almost any
    #: text -- so the check passed on a narrative that had dropped the value.
    required_values: Tuple[str, ...] = ()
    #: Still collected; no longer stated. The page lists the parameters.
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
        required_values=trigger_values + range_values,
        unmapped_count=_unmapped_count(summary),
    )


def _missing(text: str, facts: _Facts) -> Tuple[str, ...]:
    """Which required facts are NOT in the model's output.

    THE REQUIRED SET IS NOW EXACTLY WHAT THE DOCUMENT IS FOR: every flagged
    condition, and every number behind it. A rewrite that drops a finding or a
    value still throws the whole narrative away.

    The absence checks -- unsupplied profile answers, topics that could not be
    assessed, the no-intervals note -- are gone with the sentences they
    guarded. See `_facts_block`.
    """
    gaps: List[str] = []
    body = text
    lowered = body.lower()

    for name in facts.flagged:
        if str(name).lower() not in lowered:
            gaps.append(f"flagged:{name}")

    # THE NUMBER HAS TO SURVIVE. The unit may legitimately be written
    # differently and the test name reworded, but the figure is the thing a
    # clinician reads this document for. Taken from the whole string rather
    # than its first token: these strings lead with the TEST NAME.
    for value in facts.required_values:
        if value not in body:
            gaps.append(f"value:{value}")

    # WHICH KIND OF CHECK FLAGGED WHAT, for the model-only group -- the one a
    # compressed rewrite drops and the one a clinician is misled by losing.
    #
    # THE SUBSTANCE, NOT ONE PHRASING OF IT. An earlier version looked for
    # "model ... alone/only" and refused a live narrative that had said the
    # same thing another way. A gate that always refuses is a feature that
    # never ships.
    if facts.flagged_model_only and not re.search(
        r"(model|pattern)[^.]{0,140}\b(alone|only|by itself)\b"
        r"|\b(alone|only|by itself)\b[^.]{0,80}(model|pattern)"
        r"|no measured value[^.]{0,80}(cross|cut-off|cutoff|threshold)"
        r"|(did not|without)[^.]{0,40}cross",
        lowered,
    ):
        gaps.append("model_only_distinction")

    # A STATUS THAT IS NOT `Indicated` HAS TO SURVIVE THE REWRITE.
    #
    # A CONTROL IN A PROMPT IS NOT A CONTROL -- this project's own repeated
    # lesson. `_facts_block` now hands the model `BORDERLINE -- Obesity`
    # instead of `FLAGGED -- Obesity`, and THIS is what makes that stick: a
    # narrative that still calls it flagged is regenerated with the gap fed
    # back, and a second failure refuses the narrative altogether. The page
    # then renders the composed document, which has always said
    # `Obesity (borderline)` correctly. **The fallback is already right**,
    # which is what makes refusing safe here.
    #
    # THE SUBSTANCE, NOT ONE PHRASING, and in the same sentence as the
    # condition -- the word loose anywhere in the document would be satisfied
    # by a borderline remark about something else. Tested against "Obesity is
    # borderline", "borderline Obesity" and "Obesity (borderline)".
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
  1. what was flagged, and the measured value and threshold behind each one;
  2. the parameters that are out of range.

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
    """WHAT WAS FLAGGED, WHY, AND WHICH PARAMETERS ARE OUT OF RANGE.

    Nothing else. The reader's instruction, and it is the right shape for a
    handover note: a clinician wants the findings and the numbers behind them.

    GONE, DELIBERATELY, AND EACH WAS A §6w REQUIREMENT:
      * "assessed and not flagged" -- the topics that were checked and clear;
      * "could not be assessed" -- the topics with no input;
      * "not supplied" -- the profile answers the patient never gave;
      * the no-reference-intervals note.

    Those exist because a compressed rewrite dropping them was a logged defect.
    The owner has asked three times for a document that says what was flagged
    and why and nothing else, which is their call to make; this records what
    the document no longer states so nobody later mistakes it for an oversight.
    The full assessed/unassessed picture is still on the PAGE around this note.
    """
    lines: List[str] = [f"SUBJECT: {facts.subject}"]

    # THE FINDINGS, EACH WITH THE VALUE THAT PRODUCED IT.
    for condition in facts.flagged:
        reasons = facts.triggering.get(condition)
        if reasons:
            # THE STATUS REPLACES THE WORD "FLAGGED", it does not decorate it.
            # `FLAGGED -- Obesity` and `BORDERLINE -- Obesity` are different
            # claims, and handing the model the first while the evidence beside
            # it says "overweight band" is what produced a sentence that
            # contradicted its own parenthetical. See `_qualified`.
            status = facts.qualified.get(condition)
            head = f"{status.upper()} -- {condition}" if status else f"FLAGGED -- {condition}"
            lines.append(f"{head}: " + "; ".join(reasons))
    # A flagged condition with no triggering value still has to be named, or
    # `_missing` requires a name the model was never given and every narrative
    # is refused forever. That fallback fired for real once already.
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
            # Carries the status here too, or a borderline condition with no
            # triggering value would arrive as a flat "ALSO FLAGGED".
            lines.append(
                "ALSO FLAGGED: "
                + ", ".join(
                    f"{c} ({facts.qualified[c].lower()})" if c in facts.qualified else c
                    for c in other
                )
            )

    if facts.out_of_range:
        lines.append("OUT OF RANGE: " + "; ".join(facts.out_of_range))

    return "\n".join(lines)


def build_prompt(facts: _Facts, feedback: Any = None, missing: Sequence[str] = ()) -> str:
    prompt = f"{_INSTRUCTIONS}\n{_facts_block(facts)}\n"
    if missing:
        # SECOND ROUND, AFTER A FACT CHECK FAILURE. The safety layer retries
        # its own refusals; this is the other kind, and without it a model that
        # drops one of three unsupplied answers -- which is what happened on
        # the first live run that got this far -- fails permanently for that
        # report. What was dropped is named, because "try again" is not
        # feedback.
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


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------


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
    """Write the handover note, or say why there is not one.

    Deterministic in one respect that matters: with no model configured this
    returns `model_unavailable` without touching the network, which is what
    makes the caller's fallback the normal path rather than an error path.
    """
    facts = collect_facts(summary)
    client = _resolve_llm(llm, settings)
    if client is None:
        return _refusal(
            OUTCOME_NO_MODEL,
            NarrativeSafety(validated=False),
        )

    # EVERY NUMBER THE PROMPT SUPPLIES IS PERMITTED, AND ONLY THOSE.
    #
    # The thresholds belong here now. The note is REQUIRED to state why each
    # finding was flagged, and the why is "HbA1c 8.4 % at or above 6.5 %" --
    # so 6.5 reaches the model in the facts. Without it in this tuple the
    # validator's numeric grounding would read 6.5 as invented and refuse the
    # document for obeying its own prompt. That is §6as's defect and it has
    # now been one edit away three times in this file: whenever the prompt
    # starts supplying a figure, this line is the other half of the change.
    permitted = (
        _numbers_in(facts.values)
        + _numbers_in(tuple(facts.model_notes) + (facts.subject,))
        + _numbers_in(facts.out_of_range)
        + _numbers_in(
            tuple(value for values in facts.triggering.values() for value in values)
        )
        + _numbers_in(facts.required_values)
    )

    context = SafetyContext(
        grounding_sources=tuple(facts.model_notes) or (_facts_block(facts),),
        permitted_numbers=permitted,
        # See the module docstring: the reader IS the professional, and the
        # closing line is appended by construction instead.
        require_referral=False,
        purpose="clinician_narrative",
    )

    # TWO ROUNDS, FOR TWO DIFFERENT REFUSALS. `guarded_generation` retries its
    # own -- a safety rejection, with the codes quoted back. A FACT CHECK
    # failure is the other kind and it owns no loop, so without this round a
    # model that drops one of three unsupplied answers fails permanently for
    # that report. Both rounds are capped; nothing here retries forever.
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
    # THE SAFETY SENTENCES ARE OURS, ADDED AFTER APPROVAL.
    #
    # The model never sees them and never retypes them, so they cannot be
    # paraphrased, truncated or dropped -- and the narrative is not required to
    # survive a check that the notes themselves do not pass (which is what made
    # every live attempt unapprovable).
    # THE MODEL NOTES ARE NO LONGER APPENDED TO THIS DOCUMENT.
    #
    # THE READER'S INSTRUCTION, GIVEN THREE TIMES: this page is a clinical
    # summary and must not carry "roc, model and all". They are right about
    # what it is -- a clinician reading a handover note is not reading a model
    # card, and two paragraphs of ROC-AUC and operating thresholds in the
    # middle of it are noise at best.
    #
    # §6w's requirement is NOT discarded, it is MOVED: the metrics render on
    # the page itself, beside the data-quality furniture, from
    # `assessments[].bases[].ml.limitations` which the payload already carries.
    # A model-derived flag still cannot reach a reader with no indication of
    # what produced it -- it simply no longer interrupts the prose.
    #
    # `facts.model_notes` is still collected: it is the narrative's grounding
    # source and its permitted numbers, both of which are safety controls on
    # what the model may write, not text for the page.
    parts = [result.approved_text.strip()]
    parts.append(CLOSING_LINE)

    return ClinicianNarrative(
        outcome=OUTCOME_GENERATED,
        # THE ONLY ASSIGNMENT of model-written text. See the module docstring.
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
