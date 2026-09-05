"""Module 32 -- the Doctor-Friendly Clinical Summary contract, pydantic v2.

    Module 17 clinical report ─┐
    Module 28 trends           ├─> Module 32 doctor summary ─> a clinician
    Module 29 comparison       │
    Modules 21/22 knowledge  ──┘

Spec Module 32: "VaidyaAI generates a structured report that can be shared
with a healthcare professional... The purpose is not to provide a diagnosis
but to improve communication between the patient and healthcare professional."

==========================================================================
THIS MODULE ASSEMBLES. IT DOES NOT GENERATE.
==========================================================================

There is no LLM call anywhere in Module 32, and no free-text entry point into
any sentence it emits. Every narrative string comes from `_TEMPLATES` in
`app/services/doctor_summary.py`, a fixed table scanned by the Module 24
safety scanner at import time; the only things substituted into a template
are canonical feature names, canonical condition names, numbers, units, dates
and this module's own code constants.

That is the same posture Module 26 took ("serves catalogue text and calls no
model") and for a stronger reason. The Module 24 audit (MEMORY.md §6k) rated
the whole Module 1->26 flow FAIL because free model prose reached a patient
carrying a fabricated diagnosis. A clinician-facing document is a HIGHER-stakes
surface than a patient-facing one, not a lower one: a clinician may act on it.

STRUCTURALLY TRUE, NOT MERELY CLAIMED. Three properties hold it:

1. `DoctorSummaryRequest` has NO field that can carry generated prose. It
   accepts a `ClinicalReport` (Module 17, `extra="forbid"` throughout), a
   report history in Module 28's own `TimelineReportInput` shape, and options.
   `ClinicalReport` has no `explanation` field -- Module 23's output lives on
   a different object entirely and cannot be posted here.
2. Every narrative field on the response is filled from `_TEMPLATES`. The
   service module has no other string-producing path.
3. The two families of string that DO originate outside this service --
   transcriptions of the patient's own document (a printed test name, a
   printed reference range) and reviewed corpus text (Module 22 chunks,
   Module 8 band labels, artifact-authored model caveats) -- are carried in
   named data fields and are never spliced into a sentence. They are scanned
   with the Module 24 scanner and, on a hit, withheld with a code rather than
   rendered. See `TranscribedText`.

==========================================================================
ABSENCE IS NEVER A VALUE HERE EITHER
==========================================================================

The repeated hazard of this project (MEMORY.md §11) has a specific shape in a
clinician document, because a clinician reads an omission as a negative
result:

* `overall.any_assessed == False` is NOT a clean bill of health. It is
  rendered through `OverallStatusView.assessment_reading`, whose text for that
  case says so explicitly, and `clean_bill_of_health` is a literal `False` on
  the wire whenever `any_assessed` is false.
* An unassessed condition is its own category (`unassessed`), never folded in
  with `normal`. Module 17 already separates them; this module does not
  re-merge them.
* `INSUFFICIENT_DATA` carries no risk, inherited from `decisions.py` where
  that is a type-level guarantee.
* A missing laboratory value is `value: null` with a `LabPosition` of
  `not_determinable` and a reason code. Never `0`, never "within range".
* Trends and historical comparison are OPTIONAL SECTIONS. With one report
  they are ABSENT with a stated reason -- never "stable", which Module 28
  reserves for a change measured against a declared stability band.

==========================================================================
THE REFERENCE-RANGE UNIT HAZARD
==========================================================================

`feature_engineer.py` used to convert the VALUE to the canonical unit while
copying `reference_low` / `reference_high` through in the unit they were
PRINTED in: a creatinine printed in umol/L was stored as a mg/dL value beside
a umol/L interval, and rendering those two numbers in one table row made
every converted creatinine read as "low" -- a mis-rendering that would look
entirely plausible on a clinician's page.

FIXED AT THE SOURCE 2026-09-04. Module 5 now carries the interval through the
same audited conversion as the value and sets
`provenance.reference_converted`. Module 29's
`report_comparator._reference_interval` honours that flag and returns such
bounds untouched, converting only for carriers that predate it. Module 32
CALLS THAT FUNCTION. It does not contain a second conversion path, nothing is
converted twice, and `LabRow.reference_basis` states which of the four
outcomes applied so a reader can see it.

==========================================================================
PROVENANCE IS PER LINE, AND THE BASES ARE NOT FLATTENED
==========================================================================

Module 16 carries `assessment_basis` and `basis_conflict` precisely so that a
risk-factor tally and a model probability can be shown side by side rather
than averaged into one undifferentiated "finding". `ConditionAssessment.bases`
is a LIST, one entry per contributing source, each carrying its own kind, its
own provenance (rule ids, or model identity and metrics), and its own status.
Nothing in this module produces a single merged number across bases.

==========================================================================
ML PREDICTIONS CARRY THEIR OWN LIMITS
==========================================================================

Module 11 (heart) has ROC-AUC 0.697 and a recall at its operating threshold of
0.268: it flags roughly one in four true positives and almost never rules
anything out. Quoting its probability to a clinician without that is actively
misleading.

`ModelLimitations` therefore travels with EVERY machine-learning basis, and
its numbers are read from the model artifact's own metadata -- which reaches
this module through `MLExplanation.performance_reference` and
`MLExplanation.thresholds`, both populated by `report_builder._explain_ml`
from the predictor's `metadata`. No metric in this file is a number typed by
hand. When a model's performance was NOT recorded on the decision, that is
stated (`METRICS_NOT_RECORDED`) rather than passed over in silence.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.comparison import ReportComparisonData
from app.schemas.decisions import DecisionSourceKind, DecisionStatus, RiskLevel
from app.schemas.report import EVIDENCE_CHAIN, ClinicalReport
from app.schemas.timeline import TimelineReportInput, TimelineTrendsData

#: The stage identifier Module 32 stamps on its own warnings.
STAGE_DOCTOR_SUMMARY = "doctor_summary"
DOCTOR_SUMMARY_MODULE = 32


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------
# Section availability -- the vocabulary for "this section is not here"
# --------------------------------------------------------------------------
#
# Every optional section carries a `SectionStatus`. A consumer branches on
# `present`; when it is false, `reason_code` says why in a machine-readable
# way and `reason` says it in a sentence. There is deliberately no third
# state and no way to be absent without a reason.

#: No report history was supplied at all, so there is nothing to trend or
#: compare. This is the normal single-report case.
SECTION_NO_HISTORY = "NO_HISTORY_SUPPLIED"

#: Exactly one report was supplied. A trend and a comparison both need two.
SECTION_SINGLE_REPORT = "SINGLE_REPORT_ONLY"

#: The caller turned the section off.
SECTION_DISABLED = "DISABLED_BY_OPTION"

#: Nothing in the report gave a canonical condition or feature to ground a
#: retrieval on, so no knowledge was requested.
SECTION_NOTHING_TO_GROUND = "NOTHING_TO_GROUND"

#: A retrieval ran and returned nothing above the similarity floor. An empty
#: result is a real answer (see `app/rag/retriever.py`), not a failure.
SECTION_NO_MATCH = "NO_MATCHING_KNOWLEDGE"

#: The knowledge index could not be loaded. The rest of the document is still
#: assembled; a missing reference section never blocks the clinical content.
SECTION_RETRIEVAL_UNAVAILABLE = "RETRIEVAL_UNAVAILABLE"

#: Module 28 or Module 29 raised on the supplied history. The section is
#: absent rather than half-rendered.
SECTION_ANALYSIS_REFUSED = "ANALYSIS_REFUSED"
#: History was supplied, but the report this document is ABOUT is not in it.
#:
#: A trend or comparison computed over a series that excludes its own subject
#: is a claim about other reports wearing this report's name. It can happen
#: for two entirely ordinary reasons -- the subject failed the caller's own
#: inclusion rule, or the caller's history window is capped and the subject
#: fell outside it -- so the section refuses rather than the request failing.
#: An audit found both routes live, with nothing in the response naming the
#: subject as missing.
SECTION_SUBJECT_NOT_IN_HISTORY = "SUBJECT_NOT_IN_HISTORY"

SECTION_REASON_CODES: Tuple[str, ...] = (
    SECTION_NO_HISTORY,
    SECTION_SINGLE_REPORT,
    SECTION_DISABLED,
    SECTION_NOTHING_TO_GROUND,
    SECTION_NO_MATCH,
    SECTION_RETRIEVAL_UNAVAILABLE,
    SECTION_ANALYSIS_REFUSED,
    SECTION_SUBJECT_NOT_IN_HISTORY,
)


class SectionStatus(BaseModel):
    """Is this optional section present, and if not, why not.

    A section that is absent WITHOUT a reason would read as "nothing to
    report", which for trends means "stable" and for comparison means
    "unchanged". Both would be fabrications. The model therefore refuses to
    validate an absence with no reason code.
    """

    model_config = ConfigDict(extra="forbid")

    present: bool
    reason_code: Optional[str] = Field(
        default=None,
        description="Set exactly when `present` is false. See "
        "SECTION_REASON_CODES.",
    )
    reason: str = Field(
        description="Templated sentence. Always present, including when the "
        "section IS present, so a renderer can caption it either way."
    )

    @field_validator("reason_code")
    @classmethod
    def _known_code(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in SECTION_REASON_CODES:
            raise ValueError(f"reason_code must be one of {SECTION_REASON_CODES}")
        return v

    @model_validator(mode="after")
    def _absence_is_explained(self) -> "SectionStatus":
        if not self.present and self.reason_code is None:
            raise ValueError(
                "an absent section must carry a reason_code. An unexplained "
                "absence reads as a negative finding."
            )
        if self.present and self.reason_code is not None:
            raise ValueError("a present section carries no reason_code")
        return self


# --------------------------------------------------------------------------
# Text that did not originate in this service
# --------------------------------------------------------------------------

#: The scanner found nothing. The text is rendered as supplied.
TRANSCRIPT_CLEAN = "CLEAN"

#: The Module 24 scanner matched a forbidden pattern in text that came from
#: outside this service (an OCR transcription, or reviewer-authored artifact
#: text). The text is WITHHELD and this code is rendered in its place.
TRANSCRIPT_WITHHELD = "WITHHELD_BY_SAFETY_SCAN"

#: The field was absent upstream. Distinct from withheld: nothing was refused.
TRANSCRIPT_ABSENT = "NOT_PRESENT"

TRANSCRIPT_STATES: Tuple[str, ...] = (
    TRANSCRIPT_CLEAN,
    TRANSCRIPT_WITHHELD,
    TRANSCRIPT_ABSENT,
)


class TranscribedText(BaseModel):
    """A string this service did not author, carried as data with its state.

    Three sources reach this document from outside: text transcribed from the
    patient's own document by Module 4 (a printed test name, a printed
    reference range, a printed unit), reviewed corpus text from Module 22, and
    reviewer-authored caveats held in the model artifacts.

    None of them is model-generated *interpretation*, and none of them is ever
    substituted into a narrative template -- templates take canonical names
    only. They are nonetheless scanned with the Module 24 scanner before being
    rendered, because a document is an untrusted input and a clinician page is
    the wrong place to discover otherwise. A hit withholds the text and says
    so; it never silently drops it and never silently shows it.
    """

    model_config = ConfigDict(extra="forbid")

    text: Optional[str] = Field(
        default=None,
        description="The text, or null when absent or withheld. Never a "
        "substitute value.",
    )
    state: str = Field(description="See TRANSCRIPT_STATES.")
    origin: str = Field(
        description="Where it came from: report_transcription | "
        "knowledge_corpus | model_artifact."
    )
    patterns: List[str] = Field(
        default_factory=list,
        description="Safety-pattern names matched, when state is "
        f"{TRANSCRIPT_WITHHELD}. Names only -- the offending text is not "
        "echoed back (Module 24 audit D6).",
    )

    @field_validator("state")
    @classmethod
    def _known_state(cls, v: str) -> str:
        if v not in TRANSCRIPT_STATES:
            raise ValueError(f"state must be one of {TRANSCRIPT_STATES}")
        return v

    @model_validator(mode="after")
    def _state_matches_text(self) -> "TranscribedText":
        if self.state == TRANSCRIPT_CLEAN and self.text is None:
            raise ValueError("CLEAN requires text")
        if self.state != TRANSCRIPT_CLEAN and self.text is not None:
            raise ValueError(f"{self.state} must not carry text")
        return self


# --------------------------------------------------------------------------
# Request
# --------------------------------------------------------------------------


class DoctorSummaryOptions(BaseModel):
    """Options. Every one of them narrows or omits; none of them invents."""

    model_config = ConfigDict(extra="ignore")

    include_trends: bool = Field(
        default=True,
        description="Include the Module 28 trend section when two or more "
        "reports were supplied. Off means the section is absent with "
        f"reason_code {SECTION_DISABLED}, never absent silently.",
    )
    include_comparison: bool = Field(
        default=True, description="Include the Module 29 comparison section."
    )
    include_knowledge: bool = Field(
        default=True,
        description="Include retrieved reference material from the Module 22 "
        "knowledge base (Module 21 retrieval).",
    )
    include_evidence: bool = Field(
        default=True,
        description="Include Module 20's per-condition evidence lines. On by "
        "default: evidence is the point of a clinician-facing document.",
    )
    include_normal_findings: bool = Field(
        default=True,
        description="Include conditions that were assessed and not flagged. "
        "Turning this off hides SETTLED findings only; unassessed conditions "
        "are never hidden, because an open question is not a normal result.",
    )
    knowledge_per_condition: int = Field(
        default=2,
        ge=0,
        le=5,
        description="Chunks retrieved per flagged condition.",
    )
    baseline_ref: Optional[str] = Field(
        default=None,
        max_length=128,
        description="Passed straight to Module 29. Supply with "
        "comparison_ref or not at all; Module 29 rejects exactly one.",
    )
    comparison_ref: Optional[str] = Field(default=None, max_length=128)


class DoctorSummaryRequest(BaseModel):
    """Assemble a clinician-oriented summary from an ALREADY-BUILT report.

    `report` is Module 17's `ClinicalReport`, posted verbatim -- the body of
    `POST /api/v1/report/generate`'s response, relayed. This module does not
    re-run fusion, re-run the rule engine or re-derive the overall status;
    doing any of those would create a second source of truth that could
    disagree with the report the patient was already shown. It is a VIEW, in
    exactly the sense Module 17 is a view of Module 16.

    `history` is optional and is the SAME shape Modules 28 and 29 take
    (`TimelineReportInput`), so there is one way to hand this service a
    patient's report history. It drives the trends and comparison sections and
    nothing else; it never changes a single field of the clinical content
    above, which comes from `report` alone.
    """

    model_config = ConfigDict(extra="ignore")

    patient_ref: Optional[str] = Field(
        default=None,
        max_length=128,
        description="Opaque patient identifier. NEVER a name. Echoed back "
        "only, and never logged.",
    )
    report_ref: Optional[str] = Field(
        default=None,
        max_length=128,
        description="Opaque identifier of the report being summarised, so "
        "every clinical line in this document can be attributed to a source "
        "document. Absent means the attribution says it is absent.",
    )
    report_date: Optional[datetime] = Field(
        default=None,
        description="When the summarised report was produced (the backend's "
        "`Report.chronoDate`). Not inferred from anything when absent.",
    )
    report: ClinicalReport = Field(
        description="Module 17's clinical report, posted verbatim."
    )
    history: List[TimelineReportInput] = Field(
        default_factory=list,
        max_length=500,
        description="Optional report history for the trend and comparison "
        "sections. Order is irrelevant; Module 28 orders it.",
    )
    options: DoctorSummaryOptions = Field(default_factory=DoctorSummaryOptions)

    @model_validator(mode="before")
    @classmethod
    def _unwrap(cls, value: Any) -> Any:
        """Accept `{"data": {...}}` so a relayed envelope is not a 422.

        Also accepts a bare `{"success": true, "data": <ClinicalReport>}` --
        the literal response body of `/api/v1/report/generate` -- as the whole
        request, because that is the payload a caller most plausibly relays.
        The two cases are distinguished by whether the inner object carries a
        `report` key: a doctor-summary request has one, a clinical report does
        not (`ClinicalReport` forbids extras, so it never can).
        """
        if not isinstance(value, dict):
            return value
        if "report" in value:
            return value
        inner = value.get("data")
        if isinstance(inner, dict):
            if "report" in inner:
                merged = dict(inner)
                for key in (
                    "patient_ref",
                    "report_ref",
                    "report_date",
                    "history",
                    "options",
                ):
                    if key in value and key not in merged:
                        merged[key] = value[key]
                return merged
            if "report_version" in inner:
                # A relayed `/report/generate` response body.
                out = {"report": inner}
                for key in (
                    "patient_ref",
                    "report_ref",
                    "report_date",
                    "history",
                    "options",
                ):
                    if key in value:
                        out[key] = value[key]
                return out
        return value

    @model_validator(mode="after")
    def _history_ids_unique(self) -> "DoctorSummaryRequest":
        seen: Dict[str, int] = {}
        for entry in self.history:
            seen[entry.report_id] = seen.get(entry.report_id, 0) + 1
        duplicates = sorted(rid for rid, count in seen.items() if count > 1)
        if duplicates:
            raise ValueError(
                f"duplicate report_id in history: {duplicates}. Ids must be "
                "unique -- a duplicate would double-count a reading."
            )
        return self


# --------------------------------------------------------------------------
# Response -- the document's own statement of what it is
# --------------------------------------------------------------------------


class DocumentPurpose(BaseModel):
    """What this document is and, explicitly, what it is not.

    Spec Module 32 states the purpose in the negative first: "The purpose is
    not to provide a diagnosis but to improve communication between the
    patient and healthcare professional." That sentence is not decoration on
    this object; it is the first section, and every string in it is fixed,
    reviewed and import-time scanned.
    """

    model_config = ConfigDict(extra="forbid")

    title: str
    purpose: str
    intended_reader: str
    is_not: List[str] = Field(
        description="What this document does NOT do, stated item by item: no "
        "diagnosis, no treatment recommendation, no drug or dosing "
        "information, no autonomous conclusion."
    )
    decision_support_statement: str
    how_to_read: List[str] = Field(
        description="The reading rules a clinician needs in order not to "
        "misread the sections below -- chiefly that an absent assessment is "
        "not a normal result."
    )
    contains_identity: bool = Field(
        default=False,
        description="Always false. This service never receives a name, date "
        "of birth or contact detail; `backend/` attaches identity at delivery "
        "where it is authenticated and owner-scoped.",
    )


class SourceAttribution(BaseModel):
    """Which report, produced when, and by which module versions."""

    model_config = ConfigDict(extra="forbid")

    report_ref: Optional[str] = None
    report_date: Optional[datetime] = None
    report_generated_at: Optional[datetime] = Field(
        default=None, description="`ClinicalReport.generated_at`."
    )
    report_version: Optional[str] = None
    attribution_note: str = Field(
        description="States plainly when the source report was not identified "
        "by the caller, rather than leaving the reader to assume it was."
    )
    module_versions: Dict[str, str] = Field(default_factory=dict)


# --------------------------------------------------------------------------
# Response -- laboratory values
# --------------------------------------------------------------------------

#: The reading sits below the lower bound actually used.
POSITION_BELOW = "below_reference_interval"
POSITION_WITHIN = "within_reference_interval"
POSITION_ABOVE = "above_reference_interval"

#: Not determinable. NEVER rendered as `within`. `reference_basis` and
#: `position_reason_code` say which of the several reasons applied.
POSITION_NOT_DETERMINABLE = "not_determinable"

POSITION_VALUES: Tuple[str, ...] = (
    POSITION_BELOW,
    POSITION_WITHIN,
    POSITION_ABOVE,
    POSITION_NOT_DETERMINABLE,
)

#: The interval was printed on the report and the value was never converted,
#: so the two numbers are already in the same unit.
REFERENCE_AS_PRINTED = "as_printed"

#: The value was converted to its canonical unit, and the printed interval was
#: carried through the SAME conversion (Module 29's approach). `conversion`
#: names the arithmetic used.
REFERENCE_CONVERTED = "converted_with_the_value"

#: The report printed no interval for this parameter.
REFERENCE_NONE_PRINTED = "none_printed"

#: An interval was printed but could not be placed in the value's unit -- the
#: conversion detail was missing, or its factor was not usable. The interval is
#: NOT shown beside the value, because showing it would invite the exact
#: mis-reading this basis exists to prevent.
REFERENCE_NOT_COMPARABLE = "not_comparable_with_value"

REFERENCE_BASIS_VALUES: Tuple[str, ...] = (
    REFERENCE_AS_PRINTED,
    REFERENCE_CONVERTED,
    REFERENCE_NONE_PRINTED,
    REFERENCE_NOT_COMPARABLE,
)

#: Why a position could not be settled.
POS_NO_USABLE_VALUE = "NO_USABLE_VALUE"
POS_NO_INTERVAL = "NO_COMPARABLE_INTERVAL_AND_NO_FLAG"
POS_CENSORED = "CENSORED_VALUE_INCONCLUSIVE"
POS_VALUE_NOT_NUMERIC = "VALUE_NOT_NUMERIC"
POS_UNIT_NOT_CANONICAL = "UNIT_NOT_CANONICAL"

POSITION_REASON_CODES: Tuple[str, ...] = (
    POS_NO_USABLE_VALUE,
    POS_NO_INTERVAL,
    POS_CENSORED,
    POS_VALUE_NOT_NUMERIC,
    POS_UNIT_NOT_CANONICAL,
)

#: How the position was settled, when it was.
POSITION_BY_INTERVAL = "reference_interval"
POSITION_BY_FLAG = "printed_flag"
POSITION_BASIS_VALUES: Tuple[str, ...] = (
    POSITION_BY_INTERVAL,
    POSITION_BY_FLAG,
)


class LabProvenance(BaseModel):
    """Where one laboratory row came from, line by line.

    A clinician who wants to check a number against the original document
    needs the page it was printed on and the name it was printed under. Both
    are transcriptions, so both are `TranscribedText`.
    """

    model_config = ConfigDict(extra="forbid")

    source: Optional[str] = Field(
        default=None, description="lab_report | patient_profile."
    )
    original_test_name: TranscribedText
    original_unit: TranscribedText
    reference_range_as_printed: TranscribedText
    page_number: Optional[int] = None
    extraction_confidence: Optional[float] = None
    unit_converted: bool = False
    unit_assumed: bool = Field(
        default=False,
        description="No unit was printed and the canonical one was assumed. "
        "A clinician should treat such a value as needing confirmation.",
    )
    conversion: Optional[str] = Field(
        default=None,
        description="The conversion formula applied to BOTH the value and the "
        "reference interval, when one was applied.",
    )
    derived: Optional[str] = Field(
        default=None, description="How the value was derived, when not read directly."
    )
    censored: Optional[str] = Field(
        default=None,
        description="'left' for a '<x' result, 'right' for '>x'. The stored "
        "number is a BOUND on the true value, not the true value.",
    )


class LabRow(BaseModel):
    """One laboratory or profile parameter, ready to print in a table.

    `value` is `null` when there was no usable reading. Null is not zero and
    is not "within range"; `position` is `not_determinable` and
    `position_reason_code` says why.

    `reference_low` / `reference_high` are, when present, EXPRESSED IN THE
    SAME UNIT AS `value`. That is the whole point of `reference_basis`: on a
    converted value they are the printed bounds carried through the same
    arithmetic, and when they could not be carried through they are absent
    rather than shown in a unit the value is not in.
    """

    model_config = ConfigDict(extra="forbid")

    feature: str = Field(description="Canonical feature name.")
    display_name: Optional[str] = None
    description: Optional[str] = Field(
        default=None, description="The catalogue's description. Not a value."
    )
    value: Optional[Any] = None
    unit: Optional[str] = None
    value_type: Optional[str] = None

    status: str = Field(description="Module 6's status: valid | questionable | rejected.")
    usable: bool = False
    questionable: bool = False
    clinically_extreme: bool = False
    rejection_code: Optional[str] = None
    rejection_reason: Optional[str] = None

    reference_low: Optional[float] = None
    reference_high: Optional[float] = None
    reference_basis: str = Field(description="See REFERENCE_BASIS_VALUES.")
    printed_flag: Optional[str] = Field(
        default=None, description="low | normal | high | critical, as printed."
    )

    position: str = Field(description="See POSITION_VALUES.")
    position_basis: Optional[str] = Field(
        default=None,
        description="How the position was settled. Null exactly when the "
        "position is not_determinable.",
    )
    position_reason_code: Optional[str] = Field(
        default=None,
        description="Set exactly when the position is not_determinable.",
    )
    note: str = Field(description="Templated. Explains the row's caveats, if any.")

    provenance: LabProvenance

    @field_validator("reference_basis")
    @classmethod
    def _known_reference_basis(cls, v: str) -> str:
        if v not in REFERENCE_BASIS_VALUES:
            raise ValueError(f"reference_basis must be one of {REFERENCE_BASIS_VALUES}")
        return v

    @field_validator("position")
    @classmethod
    def _known_position(cls, v: str) -> str:
        if v not in POSITION_VALUES:
            raise ValueError(f"position must be one of {POSITION_VALUES}")
        return v

    @field_validator("position_basis")
    @classmethod
    def _known_position_basis(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in POSITION_BASIS_VALUES:
            raise ValueError(f"position_basis must be one of {POSITION_BASIS_VALUES}")
        return v

    @field_validator("position_reason_code")
    @classmethod
    def _known_position_reason(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in POSITION_REASON_CODES:
            raise ValueError(f"position_reason_code must be one of {POSITION_REASON_CODES}")
        return v

    @model_validator(mode="after")
    def _position_is_explained(self) -> "LabRow":
        """Structural half of "a missing position is not a normal position".

        A `not_determinable` row with no reason, or a settled row with no
        basis, is a contradiction -- caught here rather than shipped to a
        renderer that would draw an empty cell a clinician reads as normal.
        """
        determinable = self.position != POSITION_NOT_DETERMINABLE
        if determinable and self.position_reason_code is not None:
            raise ValueError("a settled position carries no reason code")
        if not determinable and self.position_reason_code is None:
            raise ValueError("not_determinable requires a position_reason_code")
        if determinable and self.position_basis is None:
            raise ValueError("a settled position must say how it was settled")
        if not determinable and self.position_basis is not None:
            raise ValueError("not_determinable carries no position_basis")
        if self.reference_basis in (
            REFERENCE_NONE_PRINTED,
            REFERENCE_NOT_COMPARABLE,
        ) and (self.reference_low is not None or self.reference_high is not None):
            raise ValueError(
                "an interval that is absent or not comparable must not be "
                "rendered beside the value"
            )
        return self


class LaboratorySection(BaseModel):
    """Every parameter the report carried, plus the ones it did not."""

    model_config = ConfigDict(extra="forbid")

    rows: List[LabRow] = Field(default_factory=list)
    total: int = 0
    usable: int = 0
    rejected: int = 0
    questionable: int = 0
    outside_reference_interval: int = 0
    position_not_determinable: int = 0
    features_not_present: List[str] = Field(
        default_factory=list,
        description="Canonical features the report did NOT carry. Named so "
        "that 'not tested' is visible rather than inferred from a gap.",
    )
    note: str = Field(default="", description="Templated section caption.")


# --------------------------------------------------------------------------
# Response -- assessments and their bases
# --------------------------------------------------------------------------


class RuleBasisDetail(BaseModel):
    """A deterministic rule fired. Which rule, on which value, against what."""

    model_config = ConfigDict(extra="forbid")

    rule_ids: List[str] = Field(default_factory=list)
    classifications: List[TranscribedText] = Field(
        default_factory=list,
        description="Module 8's band labels. Reviewed and import-time scanned "
        "in the rule table; carried here as data and re-scanned.",
    )
    triggering_values: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Feature, value, unit, comparator and threshold for each "
        "value that made the rule fire.",
    )
    deterministic: bool = True


#: A model's discrimination is weak enough that its probability should not be
#: read as a strong signal in either direction. The cut-off is this module's
#: own, declared here rather than buried, and published on GET /policy.
#: 0.75 is the conventional boundary between "acceptable" and "poor" ROC-AUC
#: in the clinical prediction literature; the point of the constant is that it
#: is ONE reviewable number, not that it is the only defensible one.
WEAK_DISCRIMINATION_ROC_AUC = 0.75

#: A model that flags fewer than half of true positives at its operating
#: threshold cannot be used to rule anything out. Module 11 sits at 0.268.
LOW_DETECTION_RECALL = 0.5

#: Performance was not recorded on the decision that reached this module.
METRICS_NOT_RECORDED = "METRICS_NOT_RECORDED"
#: A performance record exists, but the figures that say what the model MISSES
#: at its own cut-off are not in it. Distinct from METRICS_NOT_RECORDED, which
#: means nothing was carried at all: this one says "you are looking at a
#: partial record", which a reader would otherwise have no way to tell from a
#: complete one. It exists because a summary once reported
#: `metrics_available: True` with recall, precision, accuracy and baseline all
#: absent, and nothing in the document signalled the gap.
METRICS_OPERATING_POINT_INCOMPLETE = "METRICS_OPERATING_POINT_INCOMPLETE"


class ModelLimitations(BaseModel):
    """What this model can and cannot support, in its own recorded numbers.

    Every number here is read from the model artifact's metadata as it
    travelled through `MLExplanation`. Nothing in this object is a constant
    typed into this module.

    THAT CLAIM WAS ONCE FALSE, WHICH IS WHY IT IS SPELT OUT. An audit found
    four numbers -- recall, precision, accuracy and the majority-class baseline
    -- present in the metadata and simply not read, because the reader looked
    for them under one key while a model published them under another. Every
    field below is now sourced through `app/ml/operating_metrics.py`, one
    reader shared by all three predictors, so "it is in the metadata" and "it
    reaches this object" cannot drift apart per model again.

    A field that is None means the artifact does not record it. It never means
    the figure is zero, and it never means the figure is good.

    `caveats` is a list of templated sentences SELECTED BY THOSE NUMBERS --
    the weak-discrimination sentence appears because `roc_auc` is below
    `WEAK_DISCRIMINATION_ROC_AUC`, not because someone remembered to add it
    for the heart model.
    """

    model_config = ConfigDict(extra="forbid")

    metrics_available: bool = False
    metrics_absent_code: Optional[str] = Field(
        default=None,
        description=f"{METRICS_NOT_RECORDED} when the decision carried no "
        "performance reference. A probability is still shown, with the "
        "absence stated -- never quietly.",
    )
    roc_auc: Optional[float] = None
    pr_auc: Optional[float] = None
    accuracy: Optional[float] = None
    baseline_accuracy: Optional[float] = Field(
        default=None,
        description="Majority-class accuracy on the same split. Accuracy "
        "without it is not interpretable.",
    )
    positive_class: Optional[str] = None
    measured_on: Optional[str] = None
    artifact: Optional[str] = None
    variant: Optional[str] = Field(
        default=None,
        description="Which feature variant of the model actually ran. "
        "Different variants have different inputs and different numbers.",
    )

    operating_threshold: Optional[float] = None
    precision_at_operating_threshold: Optional[float] = None
    recall_at_operating_threshold: Optional[float] = Field(
        default=None,
        description="The detection rate. For Module 11 this is about 0.27, "
        "which is the single most important number on this object.",
    )
    thresholds: Dict[str, Any] = Field(
        default_factory=dict,
        description="Every threshold the artifact recorded, verbatim.",
    )

    author_note: TranscribedText = Field(
        description="The artifact's own `honest_read`, when it has one. "
        "Reviewer-authored text held in app/ml/*.py; carried as data and "
        "scanned."
    )
    importance_scope: Optional[str] = None
    importance_is_per_patient: bool = False
    importance_caveat: Optional[str] = None
    probability_semantics: Optional[str] = None

    caveats: List[str] = Field(
        default_factory=list,
        description="Templated sentences selected by the numbers above.",
    )


class MLBasisDetail(BaseModel):
    """A model produced an estimate. Which model, how good it is, and its band."""

    model_config = ConfigDict(extra="forbid")

    model_name: Optional[str] = None
    model_version: Optional[str] = None
    prediction: DecisionStatus
    probability: Optional[float] = Field(
        default=None,
        description="The model's estimate. Null means NO estimate was "
        "produced -- never 0.0, which is itself a probability.",
    )
    risk_band: Optional[str] = None
    band_meaning: TranscribedText
    skipped: bool = False
    skip_reason: Optional[str] = None
    skip_explanation: Optional[str] = None
    features_observed: List[str] = Field(default_factory=list)
    features_imputed: List[str] = Field(
        default_factory=list,
        description="Filled with a training-set median. The model saw a "
        "number the patient never produced; a clinician should know which.",
    )
    features_missing: List[str] = Field(default_factory=list)
    limitations: ModelLimitations


class AssessmentBasis(BaseModel):
    """ONE contributing source's answer, kept separate from the others.

    A rule tally and a model probability are different quantities. Module 16
    stamps `assessment_basis` and `assessment_basis_family` so they can be
    shown side by side; this object is that rendering, one per source. There
    is deliberately no merged number across bases.
    """

    model_config = ConfigDict(extra="forbid")

    source: str
    source_kind: DecisionSourceKind
    status: DecisionStatus
    risk: Optional[RiskLevel] = Field(
        default=None,
        description="Null when this source did not assess. INSUFFICIENT_DATA "
        "never carries a risk -- guaranteed at the type level in "
        "app/schemas/decisions.py.",
    )
    confidence: Optional[float] = None
    assessed: bool = True
    assessment_basis: str = Field(
        description="threshold_comparison | risk_factor_count | "
        "model_probability | not_assessed."
    )
    assessment_basis_family: str = Field(
        description="measured_value | risk_factor_burden | "
        "estimated_likelihood | none. Two sources in DIFFERENT families are "
        "answering different questions."
    )
    what_this_source_answered: str = Field(
        description="Templated sentence naming the QUESTION this basis "
        "answers, so a probability and a risk-factor tally are not read as "
        "two attempts at one number."
    )
    decision_ids: List[str] = Field(default_factory=list)
    rule: Optional[RuleBasisDetail] = None
    ml: Optional[MLBasisDetail] = None


class ConditionAssessment(BaseModel):
    """One condition, its fused position, and each basis behind it."""

    model_config = ConfigDict(extra="forbid")

    condition: str
    status: DecisionStatus
    risk: Optional[RiskLevel] = None
    priority: str
    rank: int = 0
    flagged: bool = False
    assessed: bool = True
    critical: bool = False
    normal: bool = False
    hybrid: bool = Field(
        default=False,
        description="Both a rule and a model contributed.",
    )
    partially_assessed: bool = False
    unassessed_sources: List[str] = Field(default_factory=list)
    confidence: Optional[float] = None
    confidence_basis: str = "none_produced"

    basis_conflict: bool = False
    basis_note: Optional[str] = Field(
        default=None,
        description="Module 16's fixed wording, present exactly when "
        "basis_conflict. Says the contributions answer different questions.",
    )
    render_bases_separately: bool = Field(
        default=False,
        description="Module 17's `render_contributions_separately`, carried "
        "through. True means a renderer must NOT collapse the bases below.",
    )
    bases: List[AssessmentBasis] = Field(default_factory=list)
    reading_note: str = Field(
        description="Templated. For an unassessed condition it states that "
        "this is an open question and not a negative result."
    )


class OverallStatusView(BaseModel):
    """Module 18's status, with the fourth and fifth cases carried intact."""

    model_config = ConfigDict(extra="forbid")

    status: Optional[str] = Field(
        default=None,
        description="The spec's three-value vocabulary, or null. Null is NOT "
        "healthy.",
    )
    status_label: str
    risk: Optional[RiskLevel] = None
    rule_applied: str
    any_assessed: bool = False
    complete: bool = False
    caveat: Optional[str] = None
    clean_bill_of_health: bool = Field(
        default=False,
        description="A single boolean a renderer can trust. It is true ONLY "
        "when something was assessed, the assessment was complete, and "
        "nothing was flagged. `any_assessed=false` forces it false, which is "
        "the whole reason it exists.",
    )
    assessment_reading: str = Field(
        description="Templated sentence saying what this status does and does "
        "not license the reader to conclude."
    )
    assessed_condition_count: int = 0
    unassessed_condition_count: int = 0
    unassessed_conditions: List[str] = Field(default_factory=list)
    partially_assessed_conditions: List[str] = Field(default_factory=list)
    abnormal_condition_count: int = 0
    high_risk_condition_count: int = 0
    sources_failed: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _absence_is_not_health(self) -> "OverallStatusView":
        """The single most repeated hazard on this project, enforced.

        `clean_bill_of_health` is the field a hurried renderer will reach for.
        It must be impossible for it to be true when nothing was assessed or
        when something was flagged.
        """
        if self.clean_bill_of_health and not self.any_assessed:
            raise ValueError(
                "clean_bill_of_health cannot be true when nothing was "
                "assessed. An absence of findings is not a finding."
            )
        if self.clean_bill_of_health and self.abnormal_condition_count:
            raise ValueError(
                "clean_bill_of_health cannot be true beside an abnormal finding"
            )
        if self.clean_bill_of_health and not self.complete:
            raise ValueError(
                "clean_bill_of_health cannot be true on an incomplete assessment"
            )
        return self


# --------------------------------------------------------------------------
# Response -- evidence, knowledge, quality, integrity
# --------------------------------------------------------------------------


class EvidenceItemView(BaseModel):
    """One evidence line, with its availability intact (Module 20's join)."""

    model_config = ConfigDict(extra="forbid")

    condition: str
    source: str
    source_kind: DecisionSourceKind
    feature: str
    display_name: Optional[str] = None
    value: Optional[Any] = None
    unit: Optional[str] = None
    comparator: Optional[str] = None
    threshold: Optional[Any] = None
    classification: Optional[str] = None
    availability: str = Field(
        description="observed | not_present | unreadable | "
        "found_but_not_trusted. `found_but_not_trusted` means the value WAS "
        "in the document and was refused -- a different next step from 'not "
        "ordered'."
    )
    explanation: str
    rejected: bool = False
    rejection_code: Optional[str] = None
    rejection_reason: Optional[str] = None
    questionable: bool = False
    clinically_extreme: bool = False


class EvidenceSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: SectionStatus
    chain: Tuple[str, str, str] = Field(
        default=EVIDENCE_CHAIN,
        description="Module 20's chain, imported rather than restated so the "
        "two cannot drift.",
    )
    lines: List[EvidenceItemView] = Field(default_factory=list)
    rejected_features_joined: List[str] = Field(
        default_factory=list,
        description="Features cited as evidence that Module 6 refused. Named "
        "so a clinician can see which numbers in the source document the "
        "platform did not use, and why.",
    )
    note: str = ""


class KnowledgeReference(BaseModel):
    """One retrieved passage from the Module 22 corpus, with its citation.

    This is REFERENCE MATERIAL matched to the conditions this report raised.
    It is not a statement about this patient, and `patient_specific` is a
    literal false on the wire so a renderer cannot present it as one.
    """

    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    doc_id: str
    title: TranscribedText
    topic: str
    text: TranscribedText
    basis: TranscribedText = Field(
        description="The guideline or reference the passage reflects."
    )
    features: List[str] = Field(default_factory=list)
    conditions: List[str] = Field(default_factory=list)
    last_reviewed: str = ""
    score: float = 0.0
    matched_for: str = Field(description="The condition this was retrieved for.")
    patient_specific: bool = False


class KnowledgeSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: SectionStatus
    references: List[KnowledgeReference] = Field(default_factory=list)
    queried_conditions: List[str] = Field(default_factory=list)
    similarity_floor: Optional[float] = None
    note: str = ""
    retrieval_limitation: str = Field(
        default="",
        description="Module 21 uses TF-IDF, which cannot distinguish a topic "
        "the corpus covers from one it does not. That measured limitation is "
        "stated here rather than left for the reader to discover.",
    )


class DataQualitySection(BaseModel):
    """What the platform could and could not read, in counts."""

    model_config = ConfigDict(extra="forbid")

    extraction_provided: bool = False
    extraction_confidence: Optional[float] = None
    page_count: int = 0
    pages_unreadable: List[int] = Field(default_factory=list)
    partial_document: bool = False
    features_received: int = 0
    valid_count: int = 0
    questionable_count: int = 0
    rejected_count: int = 0
    rejected_features: List[str] = Field(default_factory=list)
    unmapped_count: int = 0
    sources_used: List[str] = Field(default_factory=list)
    sources_failed: List[str] = Field(default_factory=list)
    warning_count: int = 0
    warnings_by_stage: Dict[str, int] = Field(default_factory=dict)
    warnings: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Every stage warning from the source report, stage and "
        "module intact. Dropping upstream warnings has been a real defect on "
        "this project twice.",
    )
    note: str = ""


class IntegrityStatement(BaseModel):
    """The document's own audit of how it was produced.

    This exists because a claim in a docstring is not a guarantee (MEMORY.md
    §11). These are the checks actually run, with their actual results.
    """

    model_config = ConfigDict(extra="forbid")

    model_generated_text_included: bool = Field(
        default=False,
        description="Whether any language-model-generated prose appears in "
        "this document. Always false: no code path in Module 32 calls a "
        "model, and the request schema has no field able to carry one's "
        "output.",
    )
    llm_calls_made: int = 0
    narrative_source: str = Field(
        default="",
        description="Where every sentence in this document came from.",
    )
    source_report_text_violations: int = Field(
        default=0,
        description="Result of running `report_builder.report_text_violations` "
        "over the SOURCE report. Non-zero means the report handed to this "
        "module already contained text the safety scanner objects to; the "
        "locations are listed below.",
    )
    source_report_violation_locations: List[str] = Field(
        default_factory=list,
        description="Field paths only. The offending text is NOT echoed "
        "(Module 24 audit D6: a refusal that quotes the input back is a "
        "channel).",
    )
    transcriptions_withheld: int = Field(
        default=0,
        description="Strings from outside this service that the safety "
        "scanner refused, and which are therefore absent above.",
    )
    scanner: str = Field(
        default="",
        description="Which scanner was applied to the assembled text.",
    )
    assembled_text_violations: int = Field(
        default=0,
        description="Result of scanning THIS document's own assembled "
        "narrative fields. A non-zero value here is a defect in this module's "
        "template table, not in the input.",
    )


# --------------------------------------------------------------------------
# Response -- the document
# --------------------------------------------------------------------------


class DoctorSummary(BaseModel):
    """The whole clinician-oriented document, section by section.

    Section order follows the specification's own list for Module 32: patient
    information, laboratory values, reference information, abnormal findings,
    risk classifications, ML predictions, evidence, trends, historical
    comparison, and relevant retrieved information -- with the purpose
    statement first, because the spec defines this module in the negative
    before it defines it in the positive.
    """

    model_config = ConfigDict(extra="forbid")

    summary_version: str
    generated_at: datetime = Field(default_factory=utcnow)
    patient_ref: Optional[str] = None

    purpose: DocumentPurpose
    attribution: SourceAttribution

    patient: Dict[str, Any] = Field(
        default_factory=dict,
        description="Module 17's clinical context: age, gender, BMI, "
        "tri-state comorbidity flags, and which of them were actually "
        "supplied. No identity -- see DocumentPurpose.contains_identity.",
    )
    patient_note: str = ""

    laboratory: LaboratorySection = Field(default_factory=LaboratorySection)

    overall: OverallStatusView
    abnormal_findings: List[str] = Field(default_factory=list)
    critical_findings: List[str] = Field(
        default_factory=list, description="Flagged AND High risk."
    )
    normal_findings: List[str] = Field(default_factory=list)
    unassessed_conditions: List[str] = Field(
        default_factory=list,
        description="Could NOT be assessed. Not normal, not abnormal.",
    )
    assessments: List[ConditionAssessment] = Field(
        default_factory=list,
        description="In Module 19's priority order: flagged findings first, "
        "then OPEN QUESTIONS, then settled normal findings.",
    )

    evidence: EvidenceSection
    trends: SectionStatus = Field(
        description="Status of the optional Module 28 section."
    )
    trend_data: Optional[TimelineTrendsData] = Field(
        default=None, description="Present exactly when `trends.present`."
    )
    comparison: SectionStatus
    comparison_data: Optional[ReportComparisonData] = Field(
        default=None, description="Present exactly when `comparison.present`."
    )
    knowledge: KnowledgeSection

    data_quality: DataQualitySection = Field(default_factory=DataQualitySection)
    integrity: IntegrityStatement = Field(default_factory=IntegrityStatement)
    warnings: List[str] = Field(
        default_factory=list,
        description="Warnings raised by MODULE 32 ITSELF about the request as "
        "a whole. Upstream warnings live in `data_quality.warnings`.",
    )
    disclaimer: str = ""

    @model_validator(mode="after")
    def _sections_match_their_status(self) -> "DoctorSummary":
        """A section's data and its status cannot disagree.

        Without this, a `present: false` trends status beside a populated
        `trend_data` would let a renderer draw a trend the document says is
        not there -- or, worse, the reverse.
        """
        if self.trends.present != (self.trend_data is not None):
            raise ValueError("trends.present must match the presence of trend_data")
        if self.comparison.present != (self.comparison_data is not None):
            raise ValueError(
                "comparison.present must match the presence of comparison_data"
            )
        if self.knowledge.status.present != bool(self.knowledge.references):
            raise ValueError(
                "knowledge.status.present must match the presence of references"
            )
        return self


class DoctorSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    success: bool = True
    data: DoctorSummary


__all__ = [
    "DOCTOR_SUMMARY_MODULE",
    "LOW_DETECTION_RECALL",
    "METRICS_NOT_RECORDED",
    "METRICS_OPERATING_POINT_INCOMPLETE",
    "POSITION_BASIS_VALUES",
    "POSITION_BELOW",
    "POSITION_BY_FLAG",
    "POSITION_BY_INTERVAL",
    "POSITION_NOT_DETERMINABLE",
    "POSITION_REASON_CODES",
    "POSITION_VALUES",
    "POSITION_WITHIN",
    "POSITION_ABOVE",
    "POS_CENSORED",
    "POS_NO_INTERVAL",
    "POS_NO_USABLE_VALUE",
    "POS_UNIT_NOT_CANONICAL",
    "POS_VALUE_NOT_NUMERIC",
    "REFERENCE_AS_PRINTED",
    "REFERENCE_BASIS_VALUES",
    "REFERENCE_CONVERTED",
    "REFERENCE_NONE_PRINTED",
    "REFERENCE_NOT_COMPARABLE",
    "SECTION_ANALYSIS_REFUSED",
    "SECTION_SUBJECT_NOT_IN_HISTORY",
    "SECTION_DISABLED",
    "SECTION_NOTHING_TO_GROUND",
    "SECTION_NO_HISTORY",
    "SECTION_NO_MATCH",
    "SECTION_REASON_CODES",
    "SECTION_RETRIEVAL_UNAVAILABLE",
    "SECTION_SINGLE_REPORT",
    "STAGE_DOCTOR_SUMMARY",
    "TRANSCRIPT_ABSENT",
    "TRANSCRIPT_CLEAN",
    "TRANSCRIPT_STATES",
    "TRANSCRIPT_WITHHELD",
    "WEAK_DISCRIMINATION_ROC_AUC",
    "AssessmentBasis",
    "ConditionAssessment",
    "DataQualitySection",
    "DoctorSummary",
    "DoctorSummaryOptions",
    "DoctorSummaryRequest",
    "DoctorSummaryResponse",
    "DocumentPurpose",
    "EvidenceItemView",
    "EvidenceSection",
    "IntegrityStatement",
    "KnowledgeReference",
    "KnowledgeSection",
    "LabProvenance",
    "LabRow",
    "LaboratorySection",
    "MLBasisDetail",
    "ModelLimitations",
    "OverallStatusView",
    "RuleBasisDetail",
    "SectionStatus",
    "SourceAttribution",
    "TranscribedText",
    "utcnow",
]
