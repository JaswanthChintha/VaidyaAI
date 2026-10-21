from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.comparison import ReportComparisonData
from app.schemas.decisions import DecisionSourceKind, DecisionStatus, RiskLevel
from app.schemas.report import EVIDENCE_CHAIN, ClinicalReport
from app.schemas.timeline import TimelineReportInput, TimelineTrendsData

STAGE_DOCTOR_SUMMARY = "doctor_summary"
DOCTOR_SUMMARY_MODULE = 32


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


SECTION_NO_HISTORY = "NO_HISTORY_SUPPLIED"

SECTION_SINGLE_REPORT = "SINGLE_REPORT_ONLY"

SECTION_DISABLED = "DISABLED_BY_OPTION"

SECTION_NOTHING_TO_GROUND = "NOTHING_TO_GROUND"

SECTION_NO_MATCH = "NO_MATCHING_KNOWLEDGE"

SECTION_RETRIEVAL_UNAVAILABLE = "RETRIEVAL_UNAVAILABLE"

SECTION_ANALYSIS_REFUSED = "ANALYSIS_REFUSED"
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


TRANSCRIPT_CLEAN = "CLEAN"

TRANSCRIPT_WITHHELD = "WITHHELD_BY_SAFETY_SCAN"

TRANSCRIPT_ABSENT = "NOT_PRESENT"

TRANSCRIPT_STATES: Tuple[str, ...] = (
    TRANSCRIPT_CLEAN,
    TRANSCRIPT_WITHHELD,
    TRANSCRIPT_ABSENT,
)


class TranscribedText(BaseModel):

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


class DoctorSummaryOptions(BaseModel):

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


class DocumentPurpose(BaseModel):

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


POSITION_BELOW = "below_reference_interval"
POSITION_WITHIN = "within_reference_interval"
POSITION_ABOVE = "above_reference_interval"

POSITION_NOT_DETERMINABLE = "not_determinable"

POSITION_VALUES: Tuple[str, ...] = (
    POSITION_BELOW,
    POSITION_WITHIN,
    POSITION_ABOVE,
    POSITION_NOT_DETERMINABLE,
)

REFERENCE_AS_PRINTED = "as_printed"

REFERENCE_CONVERTED = "converted_with_the_value"

REFERENCE_NONE_PRINTED = "none_printed"

REFERENCE_NOT_COMPARABLE = "not_comparable_with_value"

REFERENCE_BASIS_VALUES: Tuple[str, ...] = (
    REFERENCE_AS_PRINTED,
    REFERENCE_CONVERTED,
    REFERENCE_NONE_PRINTED,
    REFERENCE_NOT_COMPARABLE,
)

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

POSITION_BY_INTERVAL = "reference_interval"
POSITION_BY_FLAG = "printed_flag"
POSITION_BASIS_VALUES: Tuple[str, ...] = (
    POSITION_BY_INTERVAL,
    POSITION_BY_FLAG,
)


class LabProvenance(BaseModel):

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


class RuleBasisDetail(BaseModel):

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


WEAK_DISCRIMINATION_ROC_AUC = 0.75

LOW_DETECTION_RECALL = 0.5

METRICS_NOT_RECORDED = "METRICS_NOT_RECORDED"
METRICS_OPERATING_POINT_INCOMPLETE = "METRICS_OPERATING_POINT_INCOMPLETE"


class ModelLimitations(BaseModel):

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


class EvidenceItemView(BaseModel):

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


class DoctorSummary(BaseModel):

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
