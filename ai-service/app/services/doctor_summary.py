"""Module 32 -- Doctor-Friendly Clinical Summary.

    Module 17 clinical report ─┐
    Module 28 trends           ├─> build_doctor_summary() ─> a clinician
    Module 29 comparison       │
    Modules 21/22 knowledge  ──┘

Framework-independent, exactly as `generate_report`, `analyse_trends` and
`compare_reports` are: `app/api/routes_doctor_summary.py` is a thin HTTP
wrapper and the Node backend calls this function in-process or over HTTP.

==========================================================================
THIS MODULE CALLS NO LANGUAGE MODEL AND WRITES NO PROSE
==========================================================================

`build_doctor_summary` makes ZERO model calls. Not a guarded one, not a
gated one, not an optional one. There is no import of `gemini_client`,
`gemini_text`, `app.services.explanation` or `app.safety.validator`'s
generation guard anywhere in this file, and no branch that could add one at
runtime.

Every sentence this module emits comes from `_TEMPLATES` below -- a fixed
table scanned by the Module 24 safety scanner at import time, in `_self_check`
at the bottom of this file. The only things substituted into a template are:

    * canonical condition names from `app/data/conditions.py`
    * canonical feature names from `app/data/feature_catalog.py`
    * this module's own code constants (section reason codes, basis names)

NO NUMBER AND NO UNIT IS EVER SUBSTITUTED INTO A NARRATIVE TEMPLATE. Numbers
live in structured fields. That is a deliberate second belt: the Module 24
audit's D8 defect was numeric grounding, and the `dose_quantity` safety
pattern turns on a digit next to a unit token, so a template that never
carries a digit next to a unit cannot produce either failure. It also means
the import-time scan of the literal templates is a COMPLETE scan of this
module's narrative output, rather than a scan of the parts around the holes.

WHY, AND NOT JUST HOW. The Module 24 audit (MEMORY.md §6k) rated the whole
Module 1->26 flow FAIL because free model prose reached a patient carrying a
fabricated diagnosis. Module 26 had already concluded that "recommendation
text has no free-text entry point" is the property worth keeping, and
declined to add a generator to the module most likely to drift into advice. A
clinician-facing document is a higher-stakes surface than a patient-facing
one, because a clinician may act on it. So: assemble, do not generate.

==========================================================================
WHAT DOES COME FROM OUTSIDE THIS SERVICE, AND WHAT HAPPENS TO IT
==========================================================================

Three families of string reach this document without being written here.
None of them is model-generated interpretation, and none of them is ever
spliced into a sentence -- they are carried in named `TranscribedText`
fields, scanned with the Module 24 scanner, and WITHHELD on a hit:

  report_transcription  A test name, unit or reference range exactly as
                        printed on the patient's own document, transcribed by
                        Module 4. A clinician needs these to check a row back
                        against the source page. A submitted document is an
                        untrusted input; a clinician's page is the wrong place
                        to find that out.
  knowledge_corpus      Module 22 passages. Already import-time scanned in the
                        corpus loader; re-scanned here rather than trusted at
                        a distance.
  model_artifact        A model's own `honest_read`, plus Module 8 band labels
                        and Module 20's fixed explanations. Reviewer-authored,
                        held in `app/ml/*.py` and `app/data/*.py`.

A withheld string is replaced by a state code, never by a substitute value,
and never echoed back in the refusal -- Module 24 audit D6 was exactly an
echo of injected text inside a refusal.

The SOURCE report's own text is not rewritten here at all. It is inspected:
`report_builder.report_text_violations` is run over it and the result is
published in `integrity`, field paths only.

==========================================================================
ABSENCE, ON A PAGE A CLINICIAN READS
==========================================================================

The repeated hazard of this project has a sharper edge here, because a
clinician reads a blank cell as a negative result:

  * `overall.any_assessed == False` produces `clean_bill_of_health: false`
    (enforced by a model validator, not by this function's discipline) and an
    `assessment_reading` that says an absence of findings is not a finding.
  * An unassessed condition keeps its own category and its own reading note.
    It is never merged into `normal_findings`, and `include_normal_findings:
    false` never hides it.
  * A laboratory row with no usable value is `value: null`, `position:
    not_determinable`, with a reason code. `LabRow` refuses to validate a
    not-determinable position that carries no reason.
  * Trends and comparison are absent WITH A REASON CODE when there is not
    enough history. `SectionStatus` refuses an unexplained absence.

==========================================================================
THE REFERENCE INTERVAL IS PLACED IN THE VALUE'S UNIT, ONCE
==========================================================================

`feature_engineer.py` now converts `reference_low`/`reference_high` WITH the
value, into the same canonical unit, and marks that with
`provenance.reference_converted` (fixed 2026-09-04; it previously copied the
printed bounds through unchanged, which made every converted creatinine read
as "low" in a table row).

This module calls `report_comparator.reference_interval` -- Module 29's
function, aliased for this module in that file -- which returns
already-converted bounds untouched and only applies `provenance.conversion`
itself for a carrier that does not report `reference_converted`. There is no
second conversion path here, and nothing is converted twice. When the interval
cannot be placed in the value's unit, `reference_basis` is
`not_comparable_with_value` and the bounds are OMITTED; `LabRow` refuses to
validate a row that carries them anyway.

==========================================================================
LOGGING
==========================================================================

Counts only, through `safe_meta`. No laboratory value, feature value, patient
attribute, condition name or document text is ever written to a log line.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Mapping, Optional, Tuple

from app.core.logging import get_logger, safe_meta
from app.data.conditions import CONDITIONS
from app.data.feature_catalog import CANONICAL_FEATURES, FEATURES
from app.data.recommendation_catalog import assert_safe, scan_text
from app.schemas.comparison import ReportComparisonRequest
from app.schemas.doctor_summary import (
    DOCTOR_SUMMARY_MODULE,
    LOW_DETECTION_RECALL,
    METRICS_NOT_RECORDED,
    METRICS_OPERATING_POINT_INCOMPLETE,
    POSITION_ABOVE,
    POSITION_BELOW,
    POSITION_BY_FLAG,
    POSITION_BY_INTERVAL,
    POSITION_NOT_DETERMINABLE,
    POSITION_WITHIN,
    POS_CENSORED,
    POS_NO_INTERVAL,
    POS_NO_USABLE_VALUE,
    POS_UNIT_NOT_CANONICAL,
    POS_VALUE_NOT_NUMERIC,
    REFERENCE_AS_PRINTED,
    REFERENCE_CONVERTED,
    REFERENCE_NONE_PRINTED,
    REFERENCE_NOT_COMPARABLE,
    SECTION_ANALYSIS_REFUSED,
    SECTION_SUBJECT_NOT_IN_HISTORY,
    SECTION_DISABLED,
    SECTION_NOTHING_TO_GROUND,
    SECTION_NO_HISTORY,
    SECTION_NO_MATCH,
    SECTION_RETRIEVAL_UNAVAILABLE,
    SECTION_SINGLE_REPORT,
    TRANSCRIPT_ABSENT,
    TRANSCRIPT_CLEAN,
    TRANSCRIPT_WITHHELD,
    WEAK_DISCRIMINATION_ROC_AUC,
    AssessmentBasis,
    ConditionAssessment,
    DataQualitySection,
    DoctorSummary,
    DoctorSummaryOptions,
    DoctorSummaryRequest,
    DocumentPurpose,
    EvidenceItemView,
    EvidenceSection,
    IntegrityStatement,
    KnowledgeReference,
    KnowledgeSection,
    LabProvenance,
    LabRow,
    LaboratorySection,
    MLBasisDetail,
    ModelLimitations,
    OverallStatusView,
    RuleBasisDetail,
    SectionStatus,
    SourceAttribution,
    TranscribedText,
)
from app.schemas.report import (
    ClinicalReport,
    ConditionExplanation,
    ContributionView,
    LaboratoryValue,
    MLExplanation,
    ReportedCondition,
    SourceExplanation,
)
from app.schemas.timeline import TimelineOptions, TimelineTrendsRequest
from app.services.report_builder import REPORT_VERSION, report_text_violations
from app.services.report_comparator import (
    COMPARATOR_VERSION,
    FLAG_ABNORMAL,
    compare_reports,
    outside_interval,
    reference_interval,
)
from app.services.trend_analyzer import TREND_ANALYZER_VERSION, analyse_trends

logger = get_logger(__name__)

#: Bumped when this module's own assembly behaviour changes.
DOCTOR_SUMMARY_VERSION = "1.0.0"

#: Origins for `TranscribedText`. Not free text: three fixed constants.
ORIGIN_REPORT = "report_transcription"
ORIGIN_CORPUS = "knowledge_corpus"
ORIGIN_ARTIFACT = "model_artifact"

#: Flags that place a reading on a side of its interval. The RECOGNISED set is
#: `FLAG_ABNORMAL`, Module 29's table, so there is one answer to "is this a
#: flag this service understands". This map only says which SIDE, which
#: Module 29 does not need and this module does.
_FLAG_POSITION: Dict[str, str] = {
    "normal": POSITION_WITHIN,
    "low": POSITION_BELOW,
    "high": POSITION_ABOVE,
    "critical": POSITION_ABOVE,
}


# --------------------------------------------------------------------------
# EVERY user-facing string this module can emit
# --------------------------------------------------------------------------
#
# Scanned by the Module 24 recommendation safety scanner at import time (see
# `_self_check` at the bottom). Substituted values are canonical condition
# names, canonical feature names and this module's own code constants --
# never a number, never a unit, never anything a caller supplied.

DISCLAIMER = (
    "This summary is a communication aid between a patient and a qualified "
    "health professional. It is not a diagnosis, it reaches no clinical "
    "conclusion of its own, and it is not a substitute for reviewing the "
    "original laboratory report. Every statement below is attributed to the "
    "rule, model or reference document that produced it, together with that "
    "source's stated limits."
)

DOCUMENT_TITLE = "Structured clinical summary for a healthcare professional"

DOCUMENT_PURPOSE = (
    "This document exists to improve communication between a patient and the "
    "health professional they are consulting. It gathers what an automated "
    "analysis of one laboratory report found, what it could not assess, and "
    "the evidence behind each line, in one structured place."
)

INTENDED_READER = (
    "A qualified health professional, reading alongside the patient's "
    "original laboratory report. It is generated for the patient to hand "
    "over; it is not addressed to the patient."
)

DECISION_SUPPORT_STATEMENT = (
    "This is decision support. It presents structured findings and their "
    "provenance so that a clinician can review them faster; the clinical "
    "judgement remains entirely the clinician's."
)

DOCUMENT_IS_NOT: Tuple[str, ...] = (
    "This is not a diagnosis and not a diagnostic conclusion. No line below "
    "asserts that any condition is present.",
    "It does not decide what should be done about any finding. It contains no "
    "clinical management advice of any kind.",
    "It names no pharmaceutical product and states no quantity of any "
    "substance to be given.",
    "It reaches no conclusion of its own. Every line is the output of a named "
    "rule, a named model or a named reference document, shown with that "
    "source's own limits.",
    "It is not a substitute for the original laboratory report, which remains "
    "the primary record.",
)

HOW_TO_READ: Tuple[str, ...] = (
    "An absent assessment is not a normal result. Where a topic could not be "
    "assessed it is listed separately as an open question, and the overall "
    "status section states this in its own words.",
    "A blank laboratory cell means no usable reading was available. It never "
    "means zero and never means within range.",
    "Where more than one source contributed to a topic, each is shown "
    "separately with what it actually measured. A count of risk factors and a "
    "model's estimated likelihood are different quantities and are not "
    "combined into one figure.",
    "Every model estimate is shown beside that model's recorded performance "
    "and its stated limits. A model with a low detection rate does not rule "
    "anything out when it declines to flag a topic.",
    "A reference interval is shown only where it could be placed in the same "
    "unit as the reading it sits beside.",
)

_TEMPLATES: Dict[str, str] = {
    # ---- attribution ------------------------------------------------
    "attribution_known": (
        "Assembled from one clinical report identified by the calling system, "
        "on the date shown."
    ),
    "attribution_unknown": (
        "The calling system did not identify which stored report this summary "
        "was assembled from, so no source report reference or report date can "
        "be shown. The generation timestamp below is when this summary was "
        "assembled, not when the laboratory report was produced."
    ),
    # ---- patient ----------------------------------------------------
    "patient_context": (
        "Clinical context used by the analysis. This service holds no name, "
        "date of birth or contact detail. A field marked as not supplied was "
        "not recorded; it is not a record of absence."
    ),
    # ---- laboratory -------------------------------------------------
    "laboratory_note": (
        "Every parameter the analysis received. Reference intervals are the "
        "ones printed on the source report, placed in the same unit as the "
        "reading beside them. Parameters this platform can read but the "
        "report did not carry are listed separately as not present."
    ),
    "lab_ok": "Read from the report and used by the analysis.",
    "lab_questionable": (
        "Accepted but flagged. Check this reading against the original report "
        "before relying on it."
    ),
    "lab_rejected": (
        "Read from the report and REFUSED by the validation stage, so no rule "
        "and no model used it. The reason is given beside the row. The value "
        "was present in the document; it was not missing."
    ),
    "lab_unit_assumed": (
        "No unit was printed beside this result and the canonical unit was "
        "assumed. Confirm the unit against the original report."
    ),
    "lab_converted": (
        "The reading was converted from the unit printed on the report. The "
        "printed reference interval was carried through the same conversion, "
        "so the two are comparable."
    ),
    "lab_reference_missing": (
        "The report printed no reference interval for this parameter, so no "
        "position relative to a range is stated."
    ),
    "lab_reference_not_comparable": (
        "The report printed a reference interval for this parameter, but it "
        "could not be placed in the same unit as the stored reading, so it is "
        "not shown. Read the interval from the original report."
    ),
    "lab_censored": (
        "This result was reported only as being beyond a detection limit, so "
        "the stored number is a bound on the true reading rather than the "
        "reading itself."
    ),
    "lab_extreme": (
        "This reading lies outside the range the validation stage considers "
        "physiologically plausible. Confirm it against the original report."
    ),
    "lab_derived": (
        "This value was calculated by the platform rather than read directly "
        "from the report."
    ),
    "lab_from_profile": (
        "Supplied from the patient's own profile rather than read from a "
        "laboratory report."
    ),
    # ---- overall status ---------------------------------------------
    "overall_nothing_assessed": (
        "Nothing in this report could be assessed, so no overall status is "
        "given. This is not a normal result and must not be read as one: an "
        "absence of findings here means the analysis had nothing it could "
        "use, not that nothing was found."
    ),
    "overall_incomplete": (
        "This overall status rests only on the topics that could be assessed. "
        "At least one topic could not be, and is listed as an open question "
        "below. The picture is incomplete."
    ),
    "overall_clear_complete": (
        "Every topic this platform assesses was assessed, and none was "
        "flagged against its configured thresholds. That is a statement about "
        "this platform's rules and models on this one report, and nothing "
        "wider."
    ),
    "overall_flagged": (
        "At least one topic was flagged against this platform's configured "
        "thresholds. A flag marks a topic for a clinician to consider; it "
        "asserts nothing about whether any condition is present."
    ),
    # ---- assessments ------------------------------------------------
    "condition_unassessed": (
        "{condition} could not be assessed from this report. This is an open "
        "question, not a negative result, and it is deliberately ranked above "
        "topics that were assessed and found unremarkable."
    ),
    "condition_partial": (
        "{condition} was assessed by some of the sources that normally "
        "contribute to it and not by others. The sources that did not assess "
        "it are named below."
    ),
    "condition_flagged": (
        "{condition} was flagged by at least one source against this "
        "platform's configured thresholds."
    ),
    "condition_normal": (
        "{condition} was assessed and nothing was flagged against this "
        "platform's configured thresholds."
    ),
    # ---- what each basis actually answered ---------------------------
    "basis_threshold": (
        "This source compared measured laboratory values against fixed "
        "thresholds. It answers whether a value crossed a stated cut-off."
    ),
    "basis_risk_factor": (
        "This source counted risk factors. It answers how many risk factors "
        "are present, which is not the same question as how likely a "
        "condition is, and the two must not be read as one figure."
    ),
    "basis_model": (
        "This source is a statistical model. It answers how similar this "
        "pattern of inputs is to the patterns in its training data, expressed "
        "as an estimated likelihood. It is not a measurement."
    ),
    "basis_not_assessed": (
        "This source did not assess the topic and contributed no finding. Its "
        "silence carries no information either way."
    ),
    # ---- model limitations, selected BY the recorded numbers ---------
    "model_no_metrics": (
        "No recorded performance figures accompanied this model's output, so "
        "how well it discriminates on held-out data cannot be shown here. "
        "Read the estimate below with that gap in mind."
    ),
    "model_operating_point_unknown": (
        "Performance figures accompanied this model, but they do not state how "
        "many of the true positive cases it flags at the threshold used here. "
        "How much this model MISSES therefore cannot be shown, and a result it "
        "did not flag should not be read as reassurance on the strength of the "
        "figures that are shown."
    ),
    "model_weak_discrimination": (
        "This model's recorded discrimination on held-out data is weak. Its "
        "estimate should be read as a coarse indicator, not as a "
        "quantification of this patient's likelihood."
    ),
    "model_low_detection": (
        "At the operating threshold used here, this model flags a minority of "
        "the true positive cases in its own held-out data. An unflagged "
        "result from this model therefore rules nothing out."
    ),
    "model_probability_meaning": (
        "The figure shown is the model's own estimated likelihood, produced "
        "from the inputs listed. It is not a measured quantity, and it is not "
        "a statement that the condition is present."
    ),
    "model_imputed_inputs": (
        "At least one input was not available for this patient and was filled "
        "with a value from the model's training data. The model was given a "
        "number this patient did not produce; the affected inputs are named."
    ),
    "model_skipped": (
        "This model declined to produce an estimate because required inputs "
        "were missing. A declined estimate is not a negative estimate."
    ),
    "model_thresholds": (
        "The operating thresholds shown were selected on held-out data at "
        "training time. They are properties of the model, not of this "
        "patient."
    ),
    # ---- evidence ----------------------------------------------------
    "evidence_note": (
        "The chain from input to evidence to decision, for every source that "
        "contributed. A line marked as found but not trusted means the value "
        "WAS printed on the report and the validation stage refused it, which "
        "is a different situation from the value not being there at all."
    ),
    "evidence_disabled": (
        "The evidence section was not requested by the calling system."
    ),
    "evidence_present": (
        "One line per value each source cited, with how that value reached "
        "the analysis."
    ),
    # ---- optional sections -------------------------------------------
    "trends_present": (
        "Direction of change per parameter across the reports supplied, "
        "classified against declared stability bands. Arithmetic and declared "
        "directions only; no interpretation."
    ),
    "trends_no_history": (
        "No report history was supplied, so no trend over time is shown. "
        "Nothing here should be read as an absence of change."
    ),
    "trends_subject_missing": (
        "The report this summary describes is not among the reports supplied "
        "as its history, so no trend is shown. A trend computed over a series "
        "that does not include this report would describe other reports under "
        "this report's name. This is not a finding of stability."
    ),
    "comparison_subject_missing": (
        "The report this summary describes is not among the reports supplied "
        "as its history, so no comparison is shown. Comparing two other "
        "reports would say nothing about this one, and presenting it here "
        "would imply that it did."
    ),
    "subject_not_in_history": (
        "The report history supplied with this summary did not contain the "
        "report the summary is about. The trend and comparison sections were "
        "withheld for that reason; every other section is unaffected."
    ),
    "trends_single_report": (
        "Only one report was supplied. A trend needs at least two readings, "
        "so no trend is shown. This is not a finding of stability."
    ),
    "trends_disabled": (
        "The trend section was not requested by the calling system."
    ),
    "trends_refused": (
        "The supplied report history could not be analysed, so no trend is "
        "shown. The reason is recorded in the warnings for this summary."
    ),
    "comparison_present": (
        "Parameter-by-parameter comparison between the two reports named in "
        "the pair below."
    ),
    "comparison_no_history": (
        "No report history was supplied, so no comparison with an earlier "
        "report is shown."
    ),
    "comparison_single_report": (
        "Only one report was supplied, so there is nothing to compare it "
        "with. This is not a finding that values are unchanged."
    ),
    "comparison_disabled": (
        "The comparison section was not requested by the calling system."
    ),
    "comparison_refused": (
        "The supplied report history could not be compared, so no comparison "
        "is shown. The reason is recorded in the warnings for this summary."
    ),
    "knowledge_present": (
        "Reference material from this platform's reviewed knowledge base, "
        "matched to the topics raised above. These passages are general "
        "reference; none of them is a statement about this patient."
    ),
    "knowledge_disabled": (
        "Reference material was not requested by the calling system."
    ),
    "knowledge_nothing_to_ground": (
        "No topic in this report gave a term this platform's knowledge base "
        "is indexed on, so no reference material was retrieved."
    ),
    "knowledge_no_match": (
        "A retrieval ran and nothing in the knowledge base matched the topics "
        "raised above closely enough to be shown. An empty result is a real "
        "answer, not a failure."
    ),
    "knowledge_unavailable": (
        "The knowledge base index could not be loaded, so no reference "
        "material is shown. The rest of this summary is unaffected."
    ),
    "knowledge_retrieval_limit": (
        "Retrieval here uses term-frequency matching, which was measured on "
        "this corpus and cannot reliably distinguish a topic the corpus "
        "covers from one it does not. Queries are therefore resolved to this "
        "platform's own vocabulary first, and a topic that resolves to "
        "nothing returns nothing rather than the nearest-looking passage."
    ),
    # ---- data quality -------------------------------------------------
    "quality_note": (
        "What the analysis could and could not read in the source document, "
        "and every warning raised at every stage. Read this before reading "
        "any absence above as a negative result."
    ),
    # ---- integrity ------------------------------------------------------
    "narrative_source": (
        "Every sentence in this summary comes from a fixed template table in "
        "app/services/doctor_summary.py, scanned by the Module 24 safety "
        "scanner when this service starts. No language model was called while "
        "assembling this document, and the request format has no field able "
        "to carry a language model's output."
    ),
    "scanner_name": (
        "Module 24 forbidden-pattern scanner, via "
        "app.data.recommendation_catalog.scan_text."
    ),
}


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------


def _is_number(value: object) -> bool:
    """Finite int/float that is NOT a bool.

    The bool guard matters: `hypertension` is a tri-state boolean and
    `isinstance(True, int)` is True in Python, so without it a tri-state
    would be positioned against a numeric reference interval.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value))


def _transcribe(text: object, origin: str) -> TranscribedText:
    """Carry a string this service did not author, with its scan result.

    Empty and non-string inputs are ABSENT, not withheld: nothing was
    refused. A scanner hit withholds the text and records the pattern NAMES
    only -- `scan_text` returns names, never offsets or excerpts, so the
    refusal cannot echo the input back (Module 24 audit D6).
    """
    if not isinstance(text, str) or not text.strip():
        return TranscribedText(text=None, state=TRANSCRIPT_ABSENT, origin=origin)
    hits = scan_text(text)
    if hits:
        return TranscribedText(
            text=None,
            state=TRANSCRIPT_WITHHELD,
            origin=origin,
            patterns=sorted(hits),
        )
    return TranscribedText(text=text, state=TRANSCRIPT_CLEAN, origin=origin)


def _present(reason_key: str) -> SectionStatus:
    return SectionStatus(present=True, reason=_TEMPLATES[reason_key])


def _absent(code: str, reason_key: str) -> SectionStatus:
    return SectionStatus(
        present=False, reason_code=code, reason=_TEMPLATES[reason_key]
    )


def _float_or_none(value: object) -> Optional[float]:
    return float(value) if _is_number(value) else None


def _str_or_none(value: object) -> Optional[str]:
    if value is None:
        return None
    text = str(value)
    return text or None


# --------------------------------------------------------------------------
# Laboratory rows
# --------------------------------------------------------------------------


def _lab_position(
    value: LaboratoryValue,
    low: Optional[float],
    high: Optional[float],
    interval_basis: Optional[str],
) -> Tuple[str, Optional[str], Optional[str]]:
    """`(position, position_basis, reason_code)` for one laboratory row.

    Order of preference, and why:

    1. THE INTERVAL PRINTED ON THE REPORT, once it has been placed in the
       value's unit by `reference_interval`. `outside_interval` settles it,
       including the censored cases, so this module contains no second
       censoring rule.
    2. THE MARKER PRINTED BESIDE THE RESULT, when no usable interval exists.
       `FLAG_ABNORMAL` (Module 29's table) decides whether the marker is one
       this service recognises; `_FLAG_POSITION` says which side. An
       unrecognised marker is NOT read as normal -- it falls through.
    3. Otherwise `not_determinable` with a reason code.

    The platform's own clinical thresholds in `app/data/clinical_rules.py` are
    deliberately NOT consulted. Those answer "is this concerning by this
    platform's rules", which the assessment section already answers with full
    provenance. This column answers a narrower question: did the issuing
    laboratory consider the result out of its own stated range.
    """
    if not value.usable or value.value is None:
        return POSITION_NOT_DETERMINABLE, None, POS_NO_USABLE_VALUE

    censored = getattr(value.provenance, "censored", None)
    flag = _str_or_none(value.flag)

    if not _is_number(value.value):
        # Categorical or boolean features (gender, smoking_history, the
        # tri-state comorbidities) have no position on a numeric interval.
        # A printed marker can still settle it, so the flag branch is tried.
        if flag in FLAG_ABNORMAL:
            return _FLAG_POSITION[flag], POSITION_BY_FLAG, None
        return POSITION_NOT_DETERMINABLE, None, POS_VALUE_NOT_NUMERIC

    if low is not None or high is not None:
        outside = outside_interval(float(value.value), low, high, censored)
        if outside is None:
            # Only `outside_interval`'s censored branches return None.
            return POSITION_NOT_DETERMINABLE, None, POS_CENSORED
        if not outside:
            return POSITION_WITHIN, POSITION_BY_INTERVAL, None
        # WHICH SIDE. Every branch of `outside_interval` that returns True
        # did so for one of exactly two reasons -- the value is under `low`,
        # or it is over `high` -- so re-testing those two bounds recovers the
        # side without repeating the censoring logic.
        if low is not None and float(value.value) < low:
            return POSITION_BELOW, POSITION_BY_INTERVAL, None
        return POSITION_ABOVE, POSITION_BY_INTERVAL, None

    if flag in FLAG_ABNORMAL:
        return _FLAG_POSITION[flag], POSITION_BY_FLAG, None

    if interval_basis == REFERENCE_NOT_COMPARABLE:
        return POSITION_NOT_DETERMINABLE, None, POS_NO_INTERVAL
    if not value.unit and value.provenance is not None:
        return POSITION_NOT_DETERMINABLE, None, POS_UNIT_NOT_CANONICAL
    return POSITION_NOT_DETERMINABLE, None, POS_NO_INTERVAL


def _lab_note(value: LaboratoryValue, reference_basis: str) -> str:
    """The row's caveats, assembled from whole template sentences.

    Nothing is substituted in. Each clause is a complete reviewed sentence
    selected by a boolean on the row, so the note cannot carry a number, a
    unit, or anything a caller supplied.
    """
    parts: List[str] = []
    if value.status == "rejected":
        parts.append(_TEMPLATES["lab_rejected"])
    elif value.questionable:
        parts.append(_TEMPLATES["lab_questionable"])
    else:
        parts.append(_TEMPLATES["lab_ok"])

    if value.source == "patient_profile":
        parts.append(_TEMPLATES["lab_from_profile"])
    if value.derived:
        parts.append(_TEMPLATES["lab_derived"])
    if value.unit_assumed:
        parts.append(_TEMPLATES["lab_unit_assumed"])
    if reference_basis == REFERENCE_CONVERTED:
        parts.append(_TEMPLATES["lab_converted"])
    elif reference_basis == REFERENCE_NONE_PRINTED:
        parts.append(_TEMPLATES["lab_reference_missing"])
    elif reference_basis == REFERENCE_NOT_COMPARABLE:
        parts.append(_TEMPLATES["lab_reference_not_comparable"])
    if value.censored:
        parts.append(_TEMPLATES["lab_censored"])
    if value.clinically_extreme:
        parts.append(_TEMPLATES["lab_extreme"])
    return " ".join(parts)


def _lab_row(value: LaboratoryValue) -> LabRow:
    """One `LaboratoryValue` -> one printable row, with its interval placed.

    THE UNIT HAZARD IS HANDLED HERE AND NOWHERE ELSE IN THIS MODULE.
    `reference_interval` is Module 29's function. It reads `reference_low`,
    `reference_high`, `unit_converted` and `conversion` by `getattr`, so:

      * with a `provenance`, it uses the recorded conversion arithmetic;
      * without one, the `LaboratoryValue` itself is passed, which carries
        the first three attributes and NOT `conversion`. On an unconverted
        value that is correct (interval and value are in the same printed
        unit). On a converted value the missing `conversion` sends it down the
        refusal branch, which is the conservative answer -- the interval is
        omitted rather than shown in the wrong unit.

    That fallback is a deliberate use of the function's documented duck
    typing, not an accident of it.
    """
    carrier: Any = value.provenance if value.provenance is not None else value
    low, high, basis, formula = reference_interval(carrier)

    printed_low = getattr(carrier, "reference_low", None)
    printed_high = getattr(carrier, "reference_high", None)
    had_printed_interval = _is_number(printed_low) or _is_number(printed_high)

    if basis == "reference_range":
        reference_basis = REFERENCE_AS_PRINTED
    elif basis == "reference_range_converted":
        reference_basis = REFERENCE_CONVERTED
    elif had_printed_interval:
        # An interval WAS printed and could not be carried into the value's
        # unit. Saying "none printed" here would misdescribe the document.
        reference_basis = REFERENCE_NOT_COMPARABLE
    else:
        reference_basis = REFERENCE_NONE_PRINTED

    if reference_basis in (REFERENCE_NONE_PRINTED, REFERENCE_NOT_COMPARABLE):
        low = high = None

    position, position_basis, reason_code = _lab_position(
        value, low, high, reference_basis
    )

    definition = FEATURES.get(value.feature)
    provenance = value.provenance
    return LabRow(
        feature=value.feature,
        display_name=value.display_name,
        description=definition.description if definition is not None else None,
        value=value.value,
        unit=value.unit,
        value_type=value.value_type,
        status=value.status,
        usable=value.usable,
        questionable=value.questionable,
        clinically_extreme=value.clinically_extreme,
        rejection_code=value.rejection_code,
        rejection_reason=value.rejection_reason,
        reference_low=low,
        reference_high=high,
        reference_basis=reference_basis,
        printed_flag=_str_or_none(value.flag),
        position=position,
        position_basis=position_basis,
        position_reason_code=reason_code,
        note=_lab_note(value, reference_basis),
        provenance=LabProvenance(
            source=value.source,
            original_test_name=_transcribe(value.original_test_name, ORIGIN_REPORT),
            original_unit=_transcribe(value.original_unit, ORIGIN_REPORT),
            reference_range_as_printed=_transcribe(
                value.reference_range_raw, ORIGIN_REPORT
            ),
            page_number=value.page_number,
            extraction_confidence=value.extraction_confidence,
            unit_converted=value.unit_converted,
            unit_assumed=value.unit_assumed,
            conversion=formula or None,
            derived=value.derived,
            censored=getattr(provenance, "censored", None) or value.censored,
        ),
    )


def _laboratory_section(report: ClinicalReport) -> LaboratorySection:
    rows = [_lab_row(value) for value in report.laboratory_values]
    present = {row.feature for row in rows}
    return LaboratorySection(
        rows=rows,
        total=len(rows),
        usable=sum(1 for r in rows if r.usable),
        rejected=sum(1 for r in rows if r.status == "rejected"),
        questionable=sum(1 for r in rows if r.questionable),
        outside_reference_interval=sum(
            1 for r in rows if r.position in (POSITION_BELOW, POSITION_ABOVE)
        ),
        position_not_determinable=sum(
            1 for r in rows if r.position == POSITION_NOT_DETERMINABLE
        ),
        # Catalogue order, so the list does not depend on the request.
        features_not_present=[f for f in CANONICAL_FEATURES if f not in present],
        note=_TEMPLATES["laboratory_note"],
    )


# --------------------------------------------------------------------------
# Model limitations -- read from the artifact's own recorded numbers
# --------------------------------------------------------------------------


def _model_limitations(ml: Optional[MLExplanation]) -> ModelLimitations:
    """What this model can and cannot support, in its own recorded figures.

    EVERY number here comes from the model artifact, by this route:

        app/ml/<model>.py  metadata["model_performance_reference"] and
                           metadata["thresholds"], both built from the
                           artifact's metrics JSON
          -> ClinicalDecision.metadata
          -> report_builder._explain_ml
          -> MLExplanation.performance_reference / .thresholds
          -> here

    Nothing in this function is a metric typed by hand. The two CUT-OFFS that
    select caveats (`WEAK_DISCRIMINATION_ROC_AUC`, `LOW_DETECTION_RECALL`) are
    this module's own declared constants, published on `GET /policy`; they
    decide which sentence to show, never what any number is.

    An ABSENT performance record is stated, not passed over. A clinician
    reading a probability with no performance figures beside it would
    reasonably assume the figures were unremarkable.
    """
    performance: Mapping[str, Any] = ml.performance_reference if ml else {}
    thresholds: Mapping[str, Any] = ml.thresholds if ml else {}
    if not isinstance(performance, Mapping):
        performance = {}
    if not isinstance(thresholds, Mapping):
        thresholds = {}

    roc_auc = _float_or_none(performance.get("roc_auc"))
    recall = _float_or_none(thresholds.get("indicated_recall_achieved"))
    precision = _float_or_none(thresholds.get("indicated_precision_achieved"))
    metrics_available = bool(performance)

    # A RECORD THAT IS PRESENT BUT SILENT ON THE OPERATING POINT IS NOT A
    # COMPLETE RECORD, and must not read as one. ROC-AUC describes ranking
    # across all thresholds; it says nothing about how much this model misses
    # at the one cut-off it actually applies. Reporting `metrics_available:
    # True` with recall absent is how Module 10 shipped a probability against a
    # 0.795 threshold with no statement that it catches ~70% of true positives,
    # and nothing in the document said so.
    operating_point_known = recall is not None or precision is not None
    metrics_absent_code = None
    if not metrics_available:
        metrics_absent_code = METRICS_NOT_RECORDED
    elif not operating_point_known:
        metrics_absent_code = METRICS_OPERATING_POINT_INCOMPLETE

    # `model_probability_meaning` explains a figure. A SKIPPED model shows no
    # figure, so attaching it there describes something that is not on the
    # page -- harmless-looking, and still a false statement in a clinical
    # document.
    showed_a_probability = ml is not None and not ml.skipped and ml.probability is not None
    caveats: List[str] = (
        [_TEMPLATES["model_probability_meaning"]] if showed_a_probability else []
    )
    if not metrics_available:
        caveats.append(_TEMPLATES["model_no_metrics"])
    elif not operating_point_known:
        caveats.append(_TEMPLATES["model_operating_point_unknown"])
    if roc_auc is not None and roc_auc < WEAK_DISCRIMINATION_ROC_AUC:
        caveats.append(_TEMPLATES["model_weak_discrimination"])
    if recall is not None and recall < LOW_DETECTION_RECALL:
        caveats.append(_TEMPLATES["model_low_detection"])
    if thresholds:
        caveats.append(_TEMPLATES["model_thresholds"])
    if ml is not None and ml.features_imputed:
        caveats.append(_TEMPLATES["model_imputed_inputs"])
    if ml is not None and ml.skipped:
        caveats.append(_TEMPLATES["model_skipped"])

    return ModelLimitations(
        metrics_available=metrics_available,
        metrics_absent_code=metrics_absent_code,
        roc_auc=roc_auc,
        pr_auc=_float_or_none(performance.get("pr_auc_average_precision")),
        accuracy=_float_or_none(performance.get("accuracy")),
        baseline_accuracy=_float_or_none(
            performance.get("majority_class_baseline_accuracy")
        ),
        positive_class=_str_or_none(performance.get("positive_class")),
        measured_on=_str_or_none(performance.get("measured_on")),
        artifact=_str_or_none(performance.get("artifact")),
        variant=_str_or_none(performance.get("variant")),
        operating_threshold=_float_or_none(thresholds.get("indicated")),
        precision_at_operating_threshold=precision,
        recall_at_operating_threshold=recall,
        thresholds={str(k): v for k, v in thresholds.items()},
        author_note=_transcribe(performance.get("honest_read"), ORIGIN_ARTIFACT),
        importance_scope=ml.importance_scope if ml else None,
        importance_is_per_patient=False,
        importance_caveat=ml.importance_caveat if ml else None,
        probability_semantics=ml.probability_semantics if ml else None,
        caveats=caveats,
    )


# --------------------------------------------------------------------------
# Assessments -- one block per condition, one basis per contributing source
# --------------------------------------------------------------------------

_BASIS_TEMPLATE: Dict[str, str] = {
    "threshold_comparison": "basis_threshold",
    "risk_factor_count": "basis_risk_factor",
    "model_probability": "basis_model",
    "not_assessed": "basis_not_assessed",
}


def _rule_detail(source: SourceExplanation) -> Optional[RuleBasisDetail]:
    if source.rule is None:
        return None
    return RuleBasisDetail(
        rule_ids=list(source.rule.rule_ids),
        classifications=[
            _transcribe(label, ORIGIN_ARTIFACT)
            for label in source.rule.classifications
        ],
        triggering_values=[
            {
                "feature": line.feature,
                "display_name": line.display_name,
                "value": line.value,
                "unit": line.unit,
                "comparator": line.comparator,
                "threshold": line.threshold,
                "classification": line.classification,
                "availability": line.availability,
            }
            for line in source.rule.triggering_values
        ],
        deterministic=source.rule.deterministic,
    )


def _ml_detail(source: SourceExplanation) -> Optional[MLBasisDetail]:
    if source.ml is None:
        return None
    ml = source.ml
    return MLBasisDetail(
        model_name=ml.model_name,
        model_version=ml.model_version,
        prediction=ml.prediction,
        probability=ml.probability,
        risk_band=ml.risk_band,
        band_meaning=_transcribe(ml.band_meaning, ORIGIN_ARTIFACT),
        skipped=ml.skipped,
        skip_reason=ml.skip_reason,
        skip_explanation=ml.skip_explanation,
        features_observed=list(ml.features_observed),
        features_imputed=list(ml.features_imputed),
        features_missing=list(ml.features_missing),
        limitations=_model_limitations(ml),
    )


def _assessment_basis(
    contribution: ContributionView,
    source: Optional[SourceExplanation],
) -> AssessmentBasis:
    """One contributing source, kept whole and kept separate.

    `what_this_source_answered` is chosen by Module 16's own
    `assessment_basis`, so a risk-factor tally and a model probability arrive
    at the reader already labelled as different questions. That is what
    Module 16 stamped the field for; flattening them into one "finding" is
    what it exists to prevent.
    """
    key = _BASIS_TEMPLATE.get(contribution.assessment_basis, "basis_not_assessed")
    return AssessmentBasis(
        source=contribution.source,
        source_kind=contribution.source_kind,
        status=contribution.status,
        risk=contribution.risk,
        confidence=contribution.confidence,
        assessed=contribution.assessed,
        assessment_basis=contribution.assessment_basis,
        assessment_basis_family=contribution.assessment_basis_family,
        what_this_source_answered=_TEMPLATES[key],
        decision_ids=list(contribution.decision_ids),
        rule=_rule_detail(source) if source is not None else None,
        ml=_ml_detail(source) if source is not None else None,
    )


def _reading_note(condition: ReportedCondition) -> str:
    """The sentence that stops an absence being read as a negative result."""
    if not condition.assessed:
        return _TEMPLATES["condition_unassessed"].format(condition=condition.condition)
    parts: List[str] = []
    if condition.flagged:
        parts.append(_TEMPLATES["condition_flagged"].format(condition=condition.condition))
    else:
        parts.append(_TEMPLATES["condition_normal"].format(condition=condition.condition))
    if condition.partially_assessed:
        parts.append(_TEMPLATES["condition_partial"].format(condition=condition.condition))
    return " ".join(parts)


def _assessments(
    report: ClinicalReport, options: DoctorSummaryOptions
) -> List[ConditionAssessment]:
    """One block per condition, in Module 19's priority order.

    `report.conditions` is already in that order -- flagged findings, then
    OPEN QUESTIONS, then settled normal findings -- and this module does not
    re-sort it. Re-deriving the order here would be a second prioritisation
    that could disagree with the one on the patient's own report.
    """
    explanations: Dict[str, ConditionExplanation] = {
        item.condition: item for item in report.explainability.conditions
    }

    out: List[ConditionAssessment] = []
    for condition in report.conditions:
        # An unassessed condition is NEVER hidden. `include_normal_findings`
        # hides settled findings only: "we looked and found nothing" can be
        # collapsed, "we could not look" cannot.
        if not options.include_normal_findings and condition.normal:
            continue

        explanation = explanations.get(condition.condition)
        by_source: Dict[str, SourceExplanation] = (
            {s.source: s for s in explanation.sources} if explanation else {}
        )
        out.append(
            ConditionAssessment(
                condition=condition.condition,
                status=condition.status,
                risk=condition.risk,
                priority=condition.priority,
                rank=condition.rank,
                flagged=condition.flagged,
                assessed=condition.assessed,
                critical=condition.critical,
                normal=condition.normal,
                hybrid=condition.hybrid,
                partially_assessed=condition.partially_assessed,
                unassessed_sources=list(condition.unassessed_sources),
                confidence=condition.confidence,
                confidence_basis=condition.confidence_basis,
                basis_conflict=condition.basis_conflict,
                basis_note=condition.basis_note,
                render_bases_separately=condition.render_contributions_separately,
                bases=[
                    _assessment_basis(c, by_source.get(c.source))
                    for c in condition.contributions
                ],
                reading_note=_reading_note(condition),
            )
        )
    return out


def _overall(report: ClinicalReport) -> OverallStatusView:
    """Module 18's status, with the fourth and fifth cases carried intact.

    `clean_bill_of_health` is computed here and then RE-CHECKED by
    `OverallStatusView`'s own validator. The duplication is deliberate: the
    guarantee belongs at the lowest layer (MEMORY.md §11), so the type refuses
    the dangerous combination whether or not this function got it right.
    """
    overall = report.overall
    clean = bool(
        overall.any_assessed
        and overall.complete
        and overall.abnormal_condition_count == 0
    )

    if not overall.any_assessed:
        reading = _TEMPLATES["overall_nothing_assessed"]
    elif overall.abnormal_condition_count:
        reading = _TEMPLATES["overall_flagged"]
        if not overall.complete:
            reading = f"{reading} {_TEMPLATES['overall_incomplete']}"
    elif not overall.complete:
        reading = _TEMPLATES["overall_incomplete"]
    else:
        reading = _TEMPLATES["overall_clear_complete"]

    return OverallStatusView(
        status=overall.status,
        status_label=overall.status_label,
        risk=overall.risk,
        rule_applied=overall.rule_applied,
        any_assessed=overall.any_assessed,
        complete=overall.complete,
        caveat=overall.caveat,
        clean_bill_of_health=clean,
        assessment_reading=reading,
        assessed_condition_count=overall.assessed_condition_count,
        unassessed_condition_count=overall.unassessed_condition_count,
        unassessed_conditions=list(overall.unassessed_conditions),
        partially_assessed_conditions=list(overall.partially_assessed_conditions),
        abnormal_condition_count=overall.abnormal_condition_count,
        high_risk_condition_count=overall.high_risk_condition_count,
        sources_failed=list(overall.sources_failed),
    )


# --------------------------------------------------------------------------
# Evidence
# --------------------------------------------------------------------------


def _evidence_section(
    report: ClinicalReport, options: DoctorSummaryOptions
) -> EvidenceSection:
    """Module 20's chain, source-attributed and de-duplicated.

    Lines are taken from the per-SOURCE evidence rather than the condition
    roll-up, because a clinician-facing line without an attribution is an
    unattributed claim. `(condition, source, feature)` is the identity: the
    same feature legitimately appears under two sources for one condition and
    both are kept, because they are two sources citing it.
    """
    if not options.include_evidence:
        return EvidenceSection(
            status=_absent(SECTION_DISABLED, "evidence_disabled"),
            note=_TEMPLATES["evidence_disabled"],
        )

    seen: set = set()
    lines: List[EvidenceItemView] = []
    for explanation in report.explainability.conditions:
        for source in explanation.sources:
            for line in source.evidence:
                key = (explanation.condition, source.source, line.feature)
                if key in seen:
                    continue
                seen.add(key)
                lines.append(
                    EvidenceItemView(
                        condition=explanation.condition,
                        source=source.source,
                        source_kind=source.source_kind,
                        feature=line.feature,
                        display_name=line.display_name,
                        value=line.value,
                        unit=line.unit,
                        comparator=line.comparator,
                        threshold=line.threshold,
                        classification=line.classification,
                        availability=line.availability,
                        explanation=line.explanation,
                        rejected=line.rejected,
                        rejection_code=line.rejection_code,
                        rejection_reason=line.rejection_reason,
                        questionable=line.questionable,
                        clinically_extreme=line.clinically_extreme,
                    )
                )
    return EvidenceSection(
        status=_present("evidence_present"),
        lines=lines,
        rejected_features_joined=list(
            report.explainability.rejected_features_joined
        ),
        note=_TEMPLATES["evidence_note"],
    )


# --------------------------------------------------------------------------
# Trends and historical comparison -- OPTIONAL, and absent with a reason
# --------------------------------------------------------------------------


def _subject_missing_from_history(request: DoctorSummaryRequest) -> bool:
    """Is the report this document is ABOUT absent from the series supplied?

    A trend or a comparison computed over a series that does not contain its
    own subject is a claim about OTHER reports wearing this report's name. An
    audit found two live routes to it, both in the caller rather than here:
    a subject excluded by the caller's own inclusion rule, and a subject that
    fell outside a capped history window. In the second case the caller's
    response said `excludedCount: 0` -- nothing named the subject as missing.

    So the check lives HERE, at the layer that actually renders the claim,
    where no caller's accounting bug can route around it.

    Answers False when there is no `report_ref` to check: absence of an
    identifier is not evidence of a mismatch, and the caller that omits one
    has told us nothing either way. That is a deliberate limit, not an
    oversight -- see the `report_ref` field description.
    """
    ref = request.report_ref
    if not ref:
        return False
    return all(entry.report_id != ref for entry in request.history)


def _trend_section(
    request: DoctorSummaryRequest, warnings: List[str]
) -> Tuple[SectionStatus, Optional[Any]]:
    """Module 28, or a stated reason there is no trend.

    NEVER "stable". Module 28 reserves that word for a change measured
    against a declared stability band; a single report has produced no
    measurement at all, and saying "unchanged" of it would be a fabrication
    with a clinical reading.
    """
    if not request.options.include_trends:
        return _absent(SECTION_DISABLED, "trends_disabled"), None
    if not request.history:
        return _absent(SECTION_NO_HISTORY, "trends_no_history"), None
    if len(request.history) < 2:
        return _absent(SECTION_SINGLE_REPORT, "trends_single_report"), None
    if _subject_missing_from_history(request):
        # Refuse rather than render. See `_subject_missing_from_history`.
        warnings.append(_TEMPLATES["subject_not_in_history"])
        return (
            _absent(SECTION_SUBJECT_NOT_IN_HISTORY, "trends_subject_missing"),
            None,
        )
    try:
        data = analyse_trends(
            TimelineTrendsRequest(
                patient_ref=request.patient_ref,
                reports=list(request.history),
                options=TimelineOptions(),
            )
        )
    except Exception:  # noqa: BLE001 - a refused section must not lose the document
        logger.warning(
            "doctor_summary.trends_refused %s",
            safe_meta(module=DOCTOR_SUMMARY_MODULE, reports=len(request.history)),
        )
        warnings.append(_TEMPLATES["trends_refused"])
        return _absent(SECTION_ANALYSIS_REFUSED, "trends_refused"), None
    return _present("trends_present"), data


def _comparison_section(
    request: DoctorSummaryRequest, warnings: List[str]
) -> Tuple[SectionStatus, Optional[Any]]:
    """Module 29, or a stated reason there is no comparison."""
    if not request.options.include_comparison:
        return _absent(SECTION_DISABLED, "comparison_disabled"), None
    if not request.history:
        return _absent(SECTION_NO_HISTORY, "comparison_no_history"), None
    if len(request.history) < 2:
        return _absent(SECTION_SINGLE_REPORT, "comparison_single_report"), None
    if _subject_missing_from_history(request):
        # Refuse rather than render. See `_subject_missing_from_history`.
        warnings.append(_TEMPLATES["subject_not_in_history"])
        return (
            _absent(SECTION_SUBJECT_NOT_IN_HISTORY, "comparison_subject_missing"),
            None,
        )
    try:
        data = compare_reports(
            ReportComparisonRequest(
                patient_ref=request.patient_ref,
                reports=list(request.history),
                baseline_ref=request.options.baseline_ref,
                comparison_ref=request.options.comparison_ref,
            )
        )
    except Exception:  # noqa: BLE001
        logger.warning(
            "doctor_summary.comparison_refused %s",
            safe_meta(module=DOCTOR_SUMMARY_MODULE, reports=len(request.history)),
        )
        warnings.append(_TEMPLATES["comparison_refused"])
        return _absent(SECTION_ANALYSIS_REFUSED, "comparison_refused"), None
    return _present("comparison_present"), data


# --------------------------------------------------------------------------
# Retrieved reference information (Modules 21/22)
# --------------------------------------------------------------------------


def _knowledge_section(
    report: ClinicalReport, options: DoctorSummaryOptions
) -> KnowledgeSection:
    """Reference passages for the topics this report raised.

    RETRIEVAL IS ON CANONICAL NAMES ONLY. `retrieve(conditions=..., features=
    ...)` takes exact catalogue names; no free text from the report, the
    document or the caller is passed to the retriever. That matters because
    Module 21's free-text path is the one the Module 24 audit found returning
    confidently wrong grounding (D7), and it is not used here at all.

    The passages themselves are Module 22 corpus text -- reviewed, and
    import-time scanned by the corpus loader. They are re-scanned here and
    carried as `TranscribedText`; a hit withholds the passage.
    """
    if not options.include_knowledge or options.knowledge_per_condition == 0:
        return KnowledgeSection(
            status=_absent(SECTION_DISABLED, "knowledge_disabled"),
            note=_TEMPLATES["knowledge_disabled"],
        )

    # Flagged conditions first, then unassessed ones -- an open question is
    # exactly the sort of thing a clinician may want reference material for.
    wanted: List[str] = [
        c.condition
        for c in report.conditions
        if c.flagged and c.condition in CONDITIONS
    ]
    wanted += [
        c.condition
        for c in report.conditions
        if not c.assessed and c.condition in CONDITIONS and c.condition not in wanted
    ]
    if not wanted:
        return KnowledgeSection(
            status=_absent(SECTION_NOTHING_TO_GROUND, "knowledge_nothing_to_ground"),
            note=_TEMPLATES["knowledge_nothing_to_ground"],
        )

    try:
        from app.rag.retriever import SIMILARITY_FLOOR, retrieve
    except Exception:  # noqa: BLE001 - reference material never blocks the document
        return KnowledgeSection(
            status=_absent(SECTION_RETRIEVAL_UNAVAILABLE, "knowledge_unavailable"),
            note=_TEMPLATES["knowledge_unavailable"],
        )

    references: List[KnowledgeReference] = []
    seen: set = set()
    for condition in wanted:
        features = sorted(
            {
                feature
                for c in report.conditions
                if c.condition == condition
                for feature in c.evidence_features
                if feature in FEATURES
            }
        )
        try:
            results = retrieve(
                conditions=[condition],
                features=features,
                top_k=options.knowledge_per_condition,
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "doctor_summary.retrieval_unavailable %s",
                safe_meta(module=DOCTOR_SUMMARY_MODULE),
            )
            return KnowledgeSection(
                status=_absent(SECTION_RETRIEVAL_UNAVAILABLE, "knowledge_unavailable"),
                note=_TEMPLATES["knowledge_unavailable"],
                queried_conditions=wanted,
            )
        for scored in results:
            chunk = scored.chunk
            if chunk.chunk_id in seen:
                continue
            seen.add(chunk.chunk_id)
            references.append(
                KnowledgeReference(
                    chunk_id=chunk.chunk_id,
                    doc_id=chunk.doc_id,
                    title=_transcribe(chunk.title, ORIGIN_CORPUS),
                    topic=chunk.topic,
                    text=_transcribe(chunk.text, ORIGIN_CORPUS),
                    basis=_transcribe(chunk.basis, ORIGIN_CORPUS),
                    features=list(chunk.features),
                    conditions=list(chunk.conditions),
                    last_reviewed=chunk.last_reviewed,
                    score=round(float(scored.score), 6),
                    matched_for=condition,
                    patient_specific=False,
                )
            )

    if not references:
        return KnowledgeSection(
            status=_absent(SECTION_NO_MATCH, "knowledge_no_match"),
            queried_conditions=wanted,
            similarity_floor=SIMILARITY_FLOOR,
            note=_TEMPLATES["knowledge_no_match"],
            retrieval_limitation=_TEMPLATES["knowledge_retrieval_limit"],
        )
    return KnowledgeSection(
        status=_present("knowledge_present"),
        references=references,
        queried_conditions=wanted,
        similarity_floor=SIMILARITY_FLOOR,
        note=_TEMPLATES["knowledge_present"],
        retrieval_limitation=_TEMPLATES["knowledge_retrieval_limit"],
    )


# --------------------------------------------------------------------------
# Data quality and integrity
# --------------------------------------------------------------------------


def _unmapped_count(report: ClinicalReport) -> int:
    """How many extracted parameters this tool does not assess.

    `document.unmapped_count` IS 0 ON EVERY REPORT STORED BEFORE THE
    `report_builder` FIX, and 0 here is not an absent number -- it is a claim
    that nothing on the document was set aside. `Test 2.pdf` and `Test 3.pdf`
    both say 0 and both carry seventeen.

    The feature stage's own count rides through the fusion payload untouched,
    which is why §6u's dashboard fix reads it there, and it is CORRECT in the
    two stored reports. Preferring it repairs every report already in the
    database without a re-analysis; `document` is the fallback, and it agrees
    from now on.
    """
    upstream = getattr(getattr(report, "fusion", None), "upstream_summary", None)
    counted = getattr(upstream, "unmapped_count", None)
    if isinstance(upstream, Mapping):
        counted = upstream.get("unmapped_count")
    if isinstance(counted, int) and not isinstance(counted, bool) and counted > 0:
        return counted
    return report.document.unmapped_count


def _data_quality(report: ClinicalReport) -> DataQualitySection:
    document = report.document
    return DataQualitySection(
        extraction_provided=document.extraction_provided,
        extraction_confidence=document.extraction_confidence,
        page_count=document.page_count,
        pages_unreadable=list(document.pages_unreadable),
        partial_document=document.partial_document,
        features_received=document.features_received,
        valid_count=document.valid_count,
        questionable_count=document.questionable_count,
        rejected_count=document.rejected_count,
        rejected_features=list(document.rejected_features),
        unmapped_count=_unmapped_count(report),
        sources_used=list(report.summary.sources_used),
        sources_failed=list(report.summary.sources_failed),
        warning_count=len(report.validation_warnings),
        warnings_by_stage=dict(report.warnings_by_stage),
        warnings=[w.model_dump(mode="json") for w in report.validation_warnings],
        note=_TEMPLATES["quality_note"],
    )


def _narrative_strings(summary: DoctorSummary) -> List[Tuple[str, str]]:
    """Every narrative field this module assembled, for the self-scan.

    `(where, text)` pairs. This walks THIS MODULE'S OWN output only --
    transcriptions are already scanned at the point they are carried, and the
    source report is inspected separately by `report_text_violations`.
    """
    out: List[Tuple[str, str]] = [
        ("purpose.purpose", summary.purpose.purpose),
        ("purpose.title", summary.purpose.title),
        ("purpose.intended_reader", summary.purpose.intended_reader),
        (
            "purpose.decision_support_statement",
            summary.purpose.decision_support_statement,
        ),
        ("attribution.note", summary.attribution.attribution_note),
        ("patient_note", summary.patient_note),
        ("laboratory.note", summary.laboratory.note),
        ("overall.assessment_reading", summary.overall.assessment_reading),
        ("evidence.note", summary.evidence.note),
        ("trends.reason", summary.trends.reason),
        ("comparison.reason", summary.comparison.reason),
        ("knowledge.note", summary.knowledge.note),
        ("knowledge.retrieval_limitation", summary.knowledge.retrieval_limitation),
        ("data_quality.note", summary.data_quality.note),
        ("disclaimer", summary.disclaimer),
    ]
    out += [(f"purpose.is_not[{i}]", t) for i, t in enumerate(summary.purpose.is_not)]
    out += [(f"purpose.how_to_read[{i}]", t) for i, t in enumerate(summary.purpose.how_to_read)]
    out += [(f"warnings[{i}]", t) for i, t in enumerate(summary.warnings)]
    for assessment in summary.assessments:
        out.append((f"assessments[{assessment.condition}].reading", assessment.reading_note))
        for index, basis in enumerate(assessment.bases):
            out.append(
                (
                    f"assessments[{assessment.condition}].bases[{index}].answered",
                    basis.what_this_source_answered,
                )
            )
            if basis.ml is not None:
                out += [
                    (
                        f"assessments[{assessment.condition}].bases[{index}]"
                        f".limitations.caveats[{i}]",
                        text,
                    )
                    for i, text in enumerate(basis.ml.limitations.caveats)
                ]
    for index, row in enumerate(summary.laboratory.rows):
        out.append((f"laboratory.rows[{index}].note", row.note))
    return [(where, text) for where, text in out if isinstance(text, str) and text]


def _count_withheld(summary: DoctorSummary) -> int:
    """How many outside-origin strings the scanner refused.

    Counted from the assembled document rather than from a running tally, so
    the number cannot drift away from what the document actually contains.
    """
    total = 0

    def count(item: object) -> None:
        nonlocal total
        if isinstance(item, TranscribedText) and item.state == TRANSCRIPT_WITHHELD:
            total += 1

    for row in summary.laboratory.rows:
        for item in (
            row.provenance.original_test_name,
            row.provenance.original_unit,
            row.provenance.reference_range_as_printed,
        ):
            count(item)
    for assessment in summary.assessments:
        for basis in assessment.bases:
            if basis.rule is not None:
                for label in basis.rule.classifications:
                    count(label)
            if basis.ml is not None:
                count(basis.ml.band_meaning)
                count(basis.ml.limitations.author_note)
    for reference in summary.knowledge.references:
        count(reference.title)
        count(reference.text)
        count(reference.basis)
    return total


# --------------------------------------------------------------------------
# The public entry point
# --------------------------------------------------------------------------


def build_doctor_summary(request: DoctorSummaryRequest) -> DoctorSummary:
    """Assemble the clinician-oriented summary. No model call, no free prose.

    Deterministic apart from `generated_at`: same request in, same document
    out. The only I/O is loading the committed knowledge index, and a failure
    there removes the reference section with a stated reason rather than
    failing the document.
    """
    report = request.report
    options = request.options
    warnings: List[str] = []

    trends_status, trend_data = _trend_section(request, warnings)
    comparison_status, comparison_data = _comparison_section(request, warnings)

    summary = DoctorSummary(
        summary_version=DOCTOR_SUMMARY_VERSION,
        patient_ref=request.patient_ref,
        purpose=DocumentPurpose(
            title=DOCUMENT_TITLE,
            purpose=DOCUMENT_PURPOSE,
            intended_reader=INTENDED_READER,
            is_not=list(DOCUMENT_IS_NOT),
            decision_support_statement=DECISION_SUPPORT_STATEMENT,
            how_to_read=list(HOW_TO_READ),
            contains_identity=False,
        ),
        attribution=SourceAttribution(
            report_ref=request.report_ref,
            report_date=request.report_date,
            report_generated_at=report.generated_at,
            report_version=report.report_version,
            attribution_note=(
                _TEMPLATES["attribution_known"]
                if request.report_ref is not None
                else _TEMPLATES["attribution_unknown"]
            ),
            module_versions={
                "doctor_summary": DOCTOR_SUMMARY_VERSION,
                "clinical_report": REPORT_VERSION,
                "trend_analyzer": TREND_ANALYZER_VERSION,
                "report_comparator": COMPARATOR_VERSION,
            },
        ),
        patient=report.patient.model_dump(mode="json"),
        patient_note=_TEMPLATES["patient_context"],
        laboratory=_laboratory_section(report),
        overall=_overall(report),
        abnormal_findings=list(report.abnormal_findings),
        critical_findings=list(report.critical_conditions),
        normal_findings=(
            list(report.normal_findings) if options.include_normal_findings else []
        ),
        unassessed_conditions=list(report.unassessed_conditions),
        assessments=_assessments(report, options),
        evidence=_evidence_section(report, options),
        trends=trends_status,
        trend_data=trend_data,
        comparison=comparison_status,
        comparison_data=comparison_data,
        knowledge=_knowledge_section(report, options),
        data_quality=_data_quality(report),
        warnings=warnings,
        disclaimer=DISCLAIMER,
    )

    # The integrity block is computed from the ASSEMBLED document, after the
    # fact. A claim in a docstring is not a guarantee (MEMORY.md §11); these
    # are the checks actually run, with their actual results.
    source_violations = report_text_violations(report)
    assembled = [
        (where, text)
        for where, text in _narrative_strings(summary)
        if scan_text(text)
    ]
    summary.integrity = IntegrityStatement(
        model_generated_text_included=False,
        llm_calls_made=0,
        narrative_source=_TEMPLATES["narrative_source"],
        source_report_text_violations=len(source_violations),
        source_report_violation_locations=[where for where, _text, _p in source_violations],
        transcriptions_withheld=_count_withheld(summary),
        scanner=_TEMPLATES["scanner_name"],
        assembled_text_violations=len(assembled),
    )

    logger.info(
        "doctor_summary.built %s",
        safe_meta(
            module=DOCTOR_SUMMARY_MODULE,
            version=DOCTOR_SUMMARY_VERSION,
            laboratory_rows=summary.laboratory.total,
            assessments=len(summary.assessments),
            evidence_lines=len(summary.evidence.lines),
            references=len(summary.knowledge.references),
            trends_present=summary.trends.present,
            comparison_present=summary.comparison.present,
            source_report_violations=len(source_violations),
            transcriptions_withheld=summary.integrity.transcriptions_withheld,
            assembled_violations=len(assembled),
        ),
    )
    return summary


def doctor_summary_document() -> Dict[str, object]:
    """This module's own policy, machine-readable. No patient data.

    Served by `GET /api/v1/doctor-summary/policy`, so what the document does
    and does not contain is reviewable without sending a patient's report
    through it.
    """
    return {
        "summary_version": DOCTOR_SUMMARY_VERSION,
        "module": DOCTOR_SUMMARY_MODULE,
        "title": DOCUMENT_TITLE,
        "purpose": DOCUMENT_PURPOSE,
        "intended_reader": INTENDED_READER,
        "decision_support_statement": DECISION_SUPPORT_STATEMENT,
        "does_not_contain": list(DOCUMENT_IS_NOT),
        "how_to_read": list(HOW_TO_READ),
        "sections": [
            "purpose",
            "attribution",
            "patient",
            "laboratory",
            "overall",
            "abnormal_findings",
            "critical_findings",
            "normal_findings",
            "unassessed_conditions",
            "assessments",
            "evidence",
            "trends (optional)",
            "comparison (optional)",
            "knowledge (optional)",
            "data_quality",
            "integrity",
        ],
        "generation_policy": (
            "This module calls no language model. Every sentence comes from a "
            "fixed template table scanned by the Module 24 safety scanner at "
            "import time, and no number or unit is substituted into any "
            "template. The request format has no field able to carry a "
            "language model's output."
        ),
        "absence_policy": (
            "An unassessed topic is an open question with its own category "
            "and its own note; it is never merged with normal findings, and "
            "it is never hidden. A laboratory row with no usable reading has "
            "a null value and a not-determinable position with a reason code. "
            "Trends and comparison are absent with a stated reason code when "
            "there is not enough history; neither is ever rendered as stable "
            "or unchanged."
        ),
        "reference_range_policy": (
            "A printed reference interval is shown only when it can be placed "
            "in the same unit as the reading beside it. Where the value was "
            "converted, the interval is carried through the same conversion "
            "by app.services.report_comparator.reference_interval -- Module "
            "29's function, not a second implementation. Where it cannot be "
            "carried through, the interval is omitted and the row says so."
        ),
        "provenance_policy": (
            "Every assessment carries one entry per contributing source, each "
            "with its own kind, its own status and its own provenance -- rule "
            "identifiers for a rule, model identity and recorded performance "
            "for a model. A risk-factor count and a model's estimated "
            "likelihood are never combined into one figure."
        ),
        "model_policy": (
            "Every model estimate travels with that model's recorded "
            "performance, read from the model artifact's own metadata. "
            "Caveats are selected by those figures, not hand-attached: a "
            f"recorded ROC-AUC below {WEAK_DISCRIMINATION_ROC_AUC} adds the "
            "weak-discrimination note, and a recall at the operating "
            f"threshold below {LOW_DETECTION_RECALL} adds the note that an "
            "unflagged result rules nothing out. A model whose performance "
            "was not recorded says so."
        ),
        "weak_discrimination_roc_auc": WEAK_DISCRIMINATION_ROC_AUC,
        "low_detection_recall": LOW_DETECTION_RECALL,
        "transcription_policy": (
            "Text this service did not author -- a test name or reference "
            "range transcribed from the patient's document, a reviewed corpus "
            "passage, a model artifact's own caveat -- is carried in named "
            "data fields, never substituted into a sentence, scanned with the "
            "Module 24 scanner, and withheld with a state code on a hit. The "
            "refusal never echoes the offending text back."
        ),
        "disclaimer": DISCLAIMER,
    }


# --------------------------------------------------------------------------
# Import-time enforcement
# --------------------------------------------------------------------------


def _self_check() -> None:
    """Every emittable string is scanned by the Module 24 safety scanner.

    This is a COMPLETE scan of this module's narrative output, not a partial
    one, and that is a property of the template design rather than of this
    function: the only substitutions any template takes are canonical
    condition names (`{condition}`), and those are validated against
    `app/data/conditions.py` below. No number, unit, caller string or
    document transcription is ever substituted into a template, so there is
    no runtime-composed string for the scanner to miss.
    """
    for key, template in _TEMPLATES.items():
        assert_safe(template, f"doctor summary template {key}")
    assert_safe(DISCLAIMER, "doctor summary disclaimer")
    assert_safe(DOCUMENT_TITLE, "doctor summary title")
    assert_safe(DOCUMENT_PURPOSE, "doctor summary purpose")
    assert_safe(INTENDED_READER, "doctor summary intended reader")
    assert_safe(DECISION_SUPPORT_STATEMENT, "doctor summary decision support")
    for index, text in enumerate(DOCUMENT_IS_NOT):
        assert_safe(text, f"doctor summary is_not[{index}]")
    for index, text in enumerate(HOW_TO_READ):
        assert_safe(text, f"doctor summary how_to_read[{index}]")

    # The four condition templates are the ONLY ones that take a substitution,
    # and it is always a canonical condition name. Formatting each of them
    # with every canonical name and scanning the result proves the
    # substitution cannot introduce a banned phrase -- rather than asserting
    # in a comment that it cannot.
    for key in (
        "condition_unassessed",
        "condition_partial",
        "condition_flagged",
        "condition_normal",
    ):
        for name in CONDITIONS:
            assert_safe(
                _TEMPLATES[key].format(condition=name),
                f"doctor summary {key} for {name}",
            )

    # Every `assessment_basis` Module 16 can stamp must have a sentence here.
    # A missing one would silently fall back to the not-assessed wording,
    # which would describe a real finding as an abstention.
    from app.schemas.fusion import BASIS_FAMILY

    missing = [basis for basis in BASIS_FAMILY if basis not in _BASIS_TEMPLATE]
    if missing:
        raise ValueError(
            f"assessment bases with no doctor-summary sentence: {missing}. "
            "Module 32 renders Module 16's bases; it never invents one."
        )

    # Every flag Module 29 recognises must have a side here, and no flag may
    # have a side without being recognised. A flag with a side but no entry in
    # FLAG_ABNORMAL could place a reading using a marker this service has not
    # agreed to trust.
    if set(_FLAG_POSITION) != set(FLAG_ABNORMAL):
        raise ValueError(
            "the recognised-flag table and the flag-side table have drifted; "
            "they must name exactly the same flags"
        )
    for flag, abnormal in FLAG_ABNORMAL.items():
        side = _FLAG_POSITION[flag]
        if abnormal and side == POSITION_WITHIN:
            raise ValueError(f"flag {flag!r} is abnormal but placed within range")
        if not abnormal and side != POSITION_WITHIN:
            raise ValueError(f"flag {flag!r} is normal but placed outside range")


_self_check()


__all__ = [
    "DISCLAIMER",
    "DOCTOR_SUMMARY_VERSION",
    "DOCUMENT_IS_NOT",
    "DOCUMENT_PURPOSE",
    "DOCUMENT_TITLE",
    "build_doctor_summary",
    "doctor_summary_document",
]
