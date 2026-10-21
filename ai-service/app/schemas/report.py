from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.decisions import (
    DecisionSourceKind,
    DecisionStatus,
    RiskLevel,
)
from app.schemas.features import (
    FeatureProvenance,
    StageWarning,
    UpstreamExtraction,
)
from app.schemas.fusion import (
    DecisionFusionData,
    DecisionFusionRequest,
    STATUS_HEALTHY,
    STATUS_NEEDS_MEDICAL_ATTENTION,
    STATUS_NEEDS_MONITORING,
)

STAGE_REPORT = "report"
REPORT_MODULE = 17


STATUS_NOT_ASSESSED = "Not Assessed"

STATUS_HEALTHY_PARTIAL = "Healthy (partial assessment)"

OVERALL_STATUS_LABELS: Tuple[str, ...] = (
    STATUS_HEALTHY,
    STATUS_HEALTHY_PARTIAL,
    STATUS_NEEDS_MONITORING,
    STATUS_NEEDS_MEDICAL_ATTENTION,
    STATUS_NOT_ASSESSED,
)

RULE_NOTHING_ASSESSED = "nothing_assessed"
RULE_NO_ABNORMAL_FINDINGS = "no_abnormal_findings"
RULE_ABNORMAL_WITHOUT_HIGH_RISK = "abnormal_without_high_risk"
RULE_ABNORMAL_WITH_HIGH_RISK = "abnormal_with_high_risk"
RULE_NO_LAB_RESULT_ASSESSED = "no_lab_result_assessed"

OVERALL_STATUS_RULES: Tuple[str, ...] = (
    RULE_NOTHING_ASSESSED,
    RULE_NO_LAB_RESULT_ASSESSED,
    RULE_NO_ABNORMAL_FINDINGS,
    RULE_ABNORMAL_WITHOUT_HIGH_RISK,
    RULE_ABNORMAL_WITH_HIGH_RISK,
)

CAVEAT_NOTHING_ASSESSED = (
    "Nothing in this report could be assessed, so no overall health status is "
    "given. An absence of findings here is not a finding of good health: it "
    "means the analysis had nothing it could use."
)

CAVEAT_NO_LAB_RESULT_ASSESSED = (
    "No test result on this report is one this tool assesses, so no overall "
    "health status is given. Any topic shown was judged only from the details "
    "entered, such as age, height and weight, and that is not a check of the "
    "report."
)

CAVEAT_ASSESSMENT_INCOMPLETE = (
    "This overall status rests only on the topics that could be assessed. At "
    "least one topic could not be, so this picture is incomplete and a "
    "qualified healthcare professional should read it alongside the original "
    "report."
)

OVERALL_STATUS_POLICY = (
    "The spec's three outcomes are applied unchanged to the topics that were "
    "actually assessed: no abnormal finding gives Healthy, an abnormal finding "
    "without a High risk gives Needs Monitoring, and an abnormal finding with a "
    "High risk gives Needs Medical Attention. When NOTHING was assessed the "
    "status is Not Assessed and never Healthy, because 'no abnormal findings' "
    "is vacuously true of a report that could not be read. When only some "
    "topics were assessed the status is kept but marked incomplete rather than "
    "downgraded, because inventing a worse status would report a finding "
    "nobody made; a partial clean result is labelled 'Healthy (partial "
    "assessment)' so the label alone cannot be mistaken for a complete one."
)


class OverallHealthStatus(BaseModel):

    model_config = ConfigDict(extra="forbid")

    status: Optional[str] = Field(
        default=None,
        description=(
            "One of the spec's THREE outcomes, or None when nothing was "
            "assessed. Mirrors Module 16's `summary.overall_status` exactly, so "
            "the two layers cannot disagree."
        ),
    )
    status_label: str = Field(
        default=STATUS_NOT_ASSESSED,
        description=(
            "Always renderable: the spec's three, 'Not Assessed' when nothing "
            "was assessed, or 'Healthy (partial assessment)' when nothing "
            "abnormal was found but not every topic could be looked at. A "
            "renderer shows THIS, never a default it invents for a null "
            "`status`, and the label alone never presents a partial clean "
            "result as a complete one."
        ),
    )
    risk: Optional[RiskLevel] = Field(
        default=None,
        description="Highest risk across assessed conditions. None when nothing "
        "was assessed -- never defaulted to Low.",
    )
    rule_applied: str = Field(
        default=RULE_NOTHING_ASSESSED,
        description="Which branch of the Module 18 rule produced this.",
    )
    any_assessed: bool = False
    complete: bool = Field(
        default=False,
        description=(
            "Every topic this analysis attempted was assessed and no source "
            "failed. False means the status below rests on partial "
            "information; `caveat` is then non-null."
        ),
    )
    caveat: Optional[str] = Field(
        default=None,
        description="Fixed wording. Non-null EXACTLY when `complete` is False.",
    )
    assessed_condition_count: int = 0
    unassessed_condition_count: int = 0
    unassessed_conditions: List[str] = Field(
        default_factory=list,
        description="Named, so the gap is specific rather than a vague hedge.",
    )
    partially_assessed_conditions: List[str] = Field(
        default_factory=list,
        description="Assessed by some sources but not all -- the finding stands "
        "but rests on fewer analyses than usual.",
    )
    sources_failed: List[str] = Field(default_factory=list)
    abnormal_condition_count: int = 0
    high_risk_condition_count: int = 0
    policy: str = OVERALL_STATUS_POLICY


PRIORITY_HIGH = "High"
PRIORITY_MEDIUM = "Medium"
PRIORITY_LOW = "Low"
PRIORITY_NOT_ASSESSED = "Not Assessed"

PRIORITY_BANDS: Tuple[str, ...] = (
    PRIORITY_HIGH,
    PRIORITY_MEDIUM,
    PRIORITY_LOW,
    PRIORITY_NOT_ASSESSED,
)

TIER_FLAGGED = 0
TIER_UNASSESSED = 1
TIER_NORMAL = 2

PRIORITIZATION_POLICY = (
    "Findings are prioritised BY CONDITION, never by how many decisions "
    "mentioned a condition: the rule engine emits one decision per RULE, so "
    "counting decisions would rank a condition higher purely because two "
    "relevant tests were ordered. Flagged findings come first, ordered High "
    "then Medium then Low. Conditions that could NOT be assessed come next, in "
    "their own band, because they carry no risk level and burying an open "
    "question under settled ones is the failure this ordering exists to "
    "prevent. Conditions that were assessed with nothing flagged come last."
)


class PrioritizedFinding(BaseModel):

    model_config = ConfigDict(extra="forbid")

    rank: int = Field(description="1-based position in the ordered list.")
    condition: str
    priority: str = Field(
        description="High | Medium | Low | Not Assessed. 'Not Assessed' is a "
        "BAND, not a risk level: the condition has no risk level at all."
    )
    tier: int = Field(
        description="0 flagged, 1 unassessed, 2 normal. The primary sort key."
    )
    status: DecisionStatus
    risk: Optional[RiskLevel] = None
    flagged: bool = False
    assessed: bool = True
    critical: bool = Field(
        default=False, description="Flagged AND High risk (spec Module 17)."
    )
    hybrid: bool = False
    sources: List[str] = Field(default_factory=list)
    confidence: Optional[float] = None
    partially_assessed: bool = False
    basis_conflict: bool = False
    contributing_decision_count: int = Field(
        default=0,
        description=(
            "How many RAW decisions fused into this condition. DISPLAY ONLY. "
            "It is deliberately NOT part of the ordering -- see the module "
            "docstring."
        ),
    )


EVIDENCE_CHAIN: Tuple[str, str, str] = ("Input", "Evidence", "Decision")

AVAILABILITY_OBSERVED = "observed"
AVAILABILITY_NOT_PRESENT = "not_present_in_report"
AVAILABILITY_UNREADABLE = "unreadable_document"
AVAILABILITY_FOUND_BUT_NOT_TRUSTED = "found_but_not_trusted"

AVAILABILITY_VALUES: Tuple[str, ...] = (
    AVAILABILITY_OBSERVED,
    AVAILABILITY_NOT_PRESENT,
    AVAILABILITY_UNREADABLE,
    AVAILABILITY_FOUND_BUT_NOT_TRUSTED,
)

EXPLANATION_OBSERVED = (
    "This value was read from the submitted report and used in the analysis."
)
EXPLANATION_NOT_PRESENT = (
    "This value was not found in the submitted report, so it could not be used."
)
EXPLANATION_UNREADABLE = (
    "Part of the submitted document could not be read, so this value may be "
    "missing from the analysis rather than absent from the report."
)
EXPLANATION_FOUND_BUT_NOT_TRUSTED = (
    "This value was printed in the submitted report and was read, but it did "
    "not pass the checks that decide whether a reading can be relied on, so "
    "nothing in this analysis was based on it. It was kept here, with the "
    "reason, rather than reported as missing."
)

AVAILABILITY_EXPLANATION: Dict[str, str] = {
    AVAILABILITY_OBSERVED: EXPLANATION_OBSERVED,
    AVAILABILITY_NOT_PRESENT: EXPLANATION_NOT_PRESENT,
    AVAILABILITY_UNREADABLE: EXPLANATION_UNREADABLE,
    AVAILABILITY_FOUND_BUT_NOT_TRUSTED: EXPLANATION_FOUND_BUT_NOT_TRUSTED,
}

ML_IMPORTANCE_CAVEAT = (
    "Feature importance here is measured across the whole training set. It "
    "ranks inputs for the model as a whole, and it is why the evidence below "
    "is ordered as it is. It is not a per-patient explanation and it does not "
    "say why this particular result came out as it did."
)

ML_PROBABILITY_SEMANTICS = (
    "An estimated probability produced by a statistical model from records "
    "resembling this one. It is not a measurement of this person and it is not "
    "a diagnosis."
)

EXPLAINABILITY_POLICY = (
    "Every automated finding is shown as Input, then Evidence, then Decision. "
    "A rule names the value that triggered it, the threshold it was compared "
    "against and the band that resulted. A model names itself, its estimated "
    "probability, the inputs it received and whether each was observed or "
    "filled in. A value the report contained but that could not be relied on "
    "is shown as found and not trusted, with the reason, and never as missing."
)


class EvidenceLine(BaseModel):

    model_config = ConfigDict(extra="forbid")

    feature: str = Field(description="Canonical feature name, e.g. 'creatinine'.")
    display_name: Optional[str] = Field(
        default=None, description="The catalogue's description of the feature."
    )
    value: Any = None
    unit: Optional[str] = None
    threshold: Optional[Any] = Field(
        default=None, description="Rule decisions only. None for ML."
    )
    comparator: Optional[str] = None
    classification: Optional[str] = Field(
        default=None,
        description="The producer's OWN band wording for this finding, "
        "verbatim. Spec Module 20: rule decisions record the classification.",
    )
    reference_low: Optional[float] = Field(
        default=None,
        description="Lower reference bound printed on the report, IN THE SAME "
        "CANONICAL UNIT as `value` and `unit` -- Module 5 converts the interval "
        "with the value. Safe to render as `value unit (ref low-high)`. Absent "
        "when nothing was printed or when the bound could not be converted.",
    )
    reference_high: Optional[float] = Field(
        default=None,
        description="Upper reference bound, in the same canonical unit as "
        "`value`. Same conversion and same refusal rule as `reference_low`.",
    )
    note: Optional[str] = Field(
        default=None, description="The producer's own note, carried unchanged."
    )
    source_stage: Optional[str] = None

    availability: str = Field(
        default=AVAILABILITY_OBSERVED,
        description="observed | not_present_in_report | unreadable_document | "
        "found_but_not_trusted. See the module docstring.",
    )
    explanation: str = Field(
        default=EXPLANATION_OBSERVED,
        description="Fixed wording for `availability`. Never composed.",
    )
    rejected: bool = Field(
        default=False,
        description="Module 6 refused this value. `availability` is then "
        "found_but_not_trusted and the reason fields are populated.",
    )
    rejection_code: Optional[str] = Field(
        default=None, description="Module 6's machine-readable RejectionCode."
    )
    rejection_reason: Optional[str] = Field(
        default=None, description="Module 6's own human-readable explanation."
    )
    rejected_value: Optional[Any] = Field(
        default=None,
        description="What was actually printed, preserved untouched. This is "
        "the fact that makes 'not present' a lie.",
    )
    rejected_unit: Optional[str] = None
    questionable: bool = Field(
        default=False, description="Used, but Module 6 marked it less reliable."
    )
    clinically_extreme: bool = False
    related_warnings: List[StageWarning] = Field(
        default_factory=list,
        description="Upstream warnings that name this feature, with their "
        "origin stage intact. The other half of the join.",
    )


class RuleExplanation(BaseModel):

    model_config = ConfigDict(extra="forbid")

    rule_ids: List[str] = Field(
        default_factory=list, description="Every rule that fired, by id."
    )
    classifications: List[str] = Field(
        default_factory=list,
        description="The rules' OWN band wording, verbatim. Never re-derived "
        "from the status -- a band label says more than a status enum does.",
    )
    triggering_values: List[EvidenceLine] = Field(
        default_factory=list,
        description="The laboratory values that triggered the rules, each with "
        "the threshold it was compared against.",
    )
    deterministic: bool = True


class MLExplanation(BaseModel):

    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    model_name: Optional[str] = None
    model_version: Optional[str] = None
    prediction: DecisionStatus
    risk_band: Optional[str] = None
    band_meaning: Optional[str] = None
    probability: Optional[float] = Field(
        default=None, description="None when the model abstained."
    )
    probability_semantics: str = ML_PROBABILITY_SEMANTICS
    thresholds: Dict[str, Any] = Field(default_factory=dict)
    input_evidence: List[EvidenceLine] = Field(default_factory=list)
    features_observed: List[str] = Field(default_factory=list)
    features_imputed: List[str] = Field(
        default_factory=list,
        description="Filled in by the model's own pipeline. NOT measured.",
    )
    features_missing: List[str] = Field(default_factory=list)
    global_feature_importance: Dict[str, float] = Field(
        default_factory=dict,
        description="Model-level, mean impurity decrease over the TRAINING "
        "SET. Orders the evidence; explains the model, not the patient.",
    )
    importance_scope: str = Field(
        default="global_model_level",
        description="Never 'per_patient'. The artifacts do not support that.",
    )
    importance_is_per_patient: bool = Field(
        default=False,
        description="Literal False on the wire so a renderer cannot label a "
        "global ranking as the reason for this individual result.",
    )
    importance_caveat: str = ML_IMPORTANCE_CAVEAT
    performance_reference: Dict[str, Any] = Field(
        default_factory=dict,
        description="Where the model's published metrics come from, so a "
        "reader can check what its numbers actually mean.",
    )
    skipped: bool = False
    skip_reason: Optional[str] = Field(
        default=None,
        description="Why the model declined to predict (spec Module 12's "
        "information-sufficiency skip), as the MACHINE-READABLE code the "
        "producer stamped in `skipped_reason`. Recorded, never hidden.",
    )
    skip_explanation: Optional[str] = Field(
        default=None,
        description=(
            "The same reason in a sentence, naming the inputs that were not "
            "available. Composed from fixed wording plus canonical feature "
            "names, never from free text. Non-null whenever `skipped` is true "
            "and the producer named the inputs it needed, so a reader can tell "
            "'the model declined because creatinine was missing' from 'the "
            "model broke'."
        ),
    )


class SourceExplanation(BaseModel):

    model_config = ConfigDict(extra="forbid")

    source: str
    source_kind: DecisionSourceKind
    status: DecisionStatus
    risk: Optional[RiskLevel] = None
    confidence: Optional[float] = None
    assessed: bool = True
    assessment_basis: str
    assessment_basis_family: str = Field(
        description="Which QUESTION this source answered: measured_value, "
        "risk_factor_burden, estimated_likelihood or none."
    )
    band_labels: List[str] = Field(default_factory=list)
    decision_ids: List[str] = Field(default_factory=list)
    rule: Optional[RuleExplanation] = None
    ml: Optional[MLExplanation] = None
    evidence: List[EvidenceLine] = Field(default_factory=list)


class ConditionExplanation(BaseModel):

    model_config = ConfigDict(extra="forbid")

    condition: str
    status: DecisionStatus
    risk: Optional[RiskLevel] = None
    confidence: Optional[float] = None
    chain: Tuple[str, str, str] = EVIDENCE_CHAIN
    sources: List[SourceExplanation] = Field(
        default_factory=list,
        description="ONE PER CONTRIBUTING SOURCE, side by side. When "
        "`basis_conflict` is set these must be rendered separately and never "
        "merged into a single sentence.",
    )
    evidence: List[EvidenceLine] = Field(
        default_factory=list,
        description="The union across sources, de-duplicated, in a stable order.",
    )
    basis_conflict: bool = False
    basis_note: Optional[str] = None
    hybrid: bool = False
    fusion_explanation: Optional[str] = Field(
        default=None,
        description="Spec section 13's 'Fusion Explainability': which sources "
        "combined into this decision.",
    )


class ExplainabilitySection(BaseModel):

    model_config = ConfigDict(extra="forbid")

    chain: Tuple[str, str, str] = EVIDENCE_CHAIN
    policy: str = EXPLAINABILITY_POLICY
    conditions: List[ConditionExplanation] = Field(default_factory=list)
    rejected_features_joined: List[str] = Field(
        default_factory=list,
        description="Features whose evidence was corrected from 'not available' "
        "to 'found but not trusted'. Listed so the join is auditable.",
    )
    ml_importance_scope: str = "global_model_level"
    ml_importance_caveat: str = ML_IMPORTANCE_CAVEAT


class PatientInformation(BaseModel):

    model_config = ConfigDict(extra="forbid")

    age: Optional[int] = None
    gender: Optional[str] = None
    bmi: Optional[float] = None
    hypertension: Optional[bool] = Field(
        default=None, description="TRI-STATE. None means UNKNOWN, never false."
    )
    heart_disease: Optional[bool] = Field(
        default=None, description="TRI-STATE. None means UNKNOWN, never false."
    )
    smoking_history: Optional[str] = None
    provided_fields: List[str] = Field(
        default_factory=list,
        description="Which of the above were actually supplied. Distinguishes "
        "'not recorded' from 'recorded as absent'.",
    )
    contains_identity: bool = Field(
        default=False,
        description="Always False. Present so a consumer can assert it.",
    )


class LaboratoryValue(BaseModel):

    model_config = ConfigDict(extra="forbid")

    feature: str
    display_name: Optional[str] = None
    value: Any = None
    unit: Optional[str] = None
    value_type: Optional[str] = None
    status: str = Field(description="valid | questionable | rejected.")
    usable: bool = Field(
        description="True for valid and questionable, False for rejected. The "
        "single field a card should gate on."
    )
    questionable: bool = False
    clinically_extreme: bool = False
    extreme_direction: Optional[str] = None
    reference_low: Optional[float] = Field(
        default=None,
        description="Lower reference bound, IN THE SAME UNIT AS `value` and "
        "`unit` (canonical whenever the value is). Module 5 converts the "
        "interval alongside the value and drops a bound it cannot convert, so "
        "a card may print `value unit (ref low-high)` directly. "
        "`reference_range_raw` keeps the text exactly as printed.",
    )
    reference_high: Optional[float] = Field(
        default=None,
        description="Upper reference bound, in the same unit as "
        "`reference_low` and `value`.",
    )
    reference_range_raw: Optional[str] = Field(
        default=None,
        description="The reference range EXACTLY as printed on the report, "
        "never converted. Display-only: do not compare it with `value`.",
    )
    flag: Optional[str] = Field(
        default=None, description="The laboratory's OWN flag, if it printed one."
    )
    original_test_name: Optional[str] = Field(
        default=None, description="Exactly as printed on the report."
    )
    original_unit: Optional[str] = None
    unit_converted: bool = False
    unit_assumed: bool = False
    derived: Optional[str] = None
    censored: Optional[str] = None
    page_number: Optional[int] = None
    extraction_confidence: Optional[float] = None
    source: Optional[str] = None
    rejection_code: Optional[str] = None
    rejection_reason: Optional[str] = None
    provenance: Optional[FeatureProvenance] = None


class ContributionView(BaseModel):

    model_config = ConfigDict(extra="forbid")

    source: str
    source_kind: DecisionSourceKind
    status: DecisionStatus
    risk: Optional[RiskLevel] = None
    confidence: Optional[float] = None
    assessed: bool = True
    assessment_basis: str
    assessment_basis_family: str
    band_labels: List[str] = Field(default_factory=list)
    traces: List[str] = Field(default_factory=list)
    evidence_features: List[str] = Field(default_factory=list)
    recommendation_codes: List[str] = Field(default_factory=list)
    decision_ids: List[str] = Field(default_factory=list)


class ReportedCondition(BaseModel):

    model_config = ConfigDict(extra="forbid")

    condition: str
    status: DecisionStatus
    risk: Optional[RiskLevel] = None
    confidence: Optional[float] = None
    confidence_basis: str = "none_produced"
    priority: str = PRIORITY_NOT_ASSESSED
    rank: int = 0
    flagged: bool = False
    assessed: bool = True
    critical: bool = False
    normal: bool = False
    hybrid: bool = False
    sources: List[str] = Field(default_factory=list)
    source_kinds: List[DecisionSourceKind] = Field(default_factory=list)
    contributions: List[ContributionView] = Field(
        default_factory=list, description="Side by side. Never blended."
    )
    basis_conflict: bool = False
    basis_note: Optional[str] = None
    render_contributions_separately: bool = Field(
        default=False,
        description="Mirror of `basis_conflict`, named for the renderer so the "
        "obligation is unmissable.",
    )
    partially_assessed: bool = False
    unassessed_sources: List[str] = Field(default_factory=list)
    evidence_features: List[str] = Field(default_factory=list)
    recommendation_codes: List[str] = Field(default_factory=list)
    decision_ids: List[str] = Field(default_factory=list)
    contributing_decision_count: int = 0


class ReportRecommendation(BaseModel):

    model_config = ConfigDict(extra="forbid")

    code: str
    text: str
    category: Optional[str] = None
    conditions: List[str] = Field(
        default_factory=list,
        description="Which conditions raised it. De-duplication keeps ONE "
        "entry and records every condition behind it.",
    )
    occurrences: int = Field(
        default=1, description="How many decisions carried this code."
    )


class DocumentQuality(BaseModel):

    model_config = ConfigDict(extra="forbid")

    extraction_provided: bool = False
    extraction_confidence: Optional[float] = None
    page_count: int = 0
    pages_unreadable: List[int] = Field(default_factory=list)
    pages_unreadable_count: int = 0
    partial_document: bool = Field(
        default=False, description="True when any page was unreadable."
    )
    features_received: int = 0
    valid_count: int = 0
    questionable_count: int = 0
    rejected_count: int = 0
    rejected_features: List[str] = Field(default_factory=list)
    missing_features: List[str] = Field(default_factory=list)
    unmapped_count: int = 0
    upstream: UpstreamExtraction = Field(
        default_factory=UpstreamExtraction,
        description="Module 4's own context, carried verbatim.",
    )


class ReportSummary(BaseModel):

    model_config = ConfigDict(extra="forbid")

    condition_count: int = 0
    abnormal_count: int = 0
    critical_count: int = 0
    normal_count: int = 0
    unassessed_count: int = 0
    hybrid_count: int = 0
    laboratory_value_count: int = 0
    usable_laboratory_value_count: int = 0
    rejected_laboratory_value_count: int = 0
    recommendation_count: int = 0
    warning_count: int = 0
    evidence_line_count: int = 0
    sources_used: List[str] = Field(default_factory=list)
    sources_failed: List[str] = Field(default_factory=list)
    basis_conflict_conditions: List[str] = Field(default_factory=list)
    input_kind: str = "none"


class ClinicalReport(BaseModel):

    model_config = ConfigDict(extra="forbid")

    report_version: str
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    patient: PatientInformation = Field(default_factory=PatientInformation)
    laboratory_values: List[LaboratoryValue] = Field(default_factory=list)
    conditions: List[ReportedCondition] = Field(
        default_factory=list,
        description="The clinical decisions, ONE PER CONDITION, in Module 19's "
        "priority order.",
    )
    overall: OverallHealthStatus = Field(default_factory=OverallHealthStatus)
    overall_risk: Optional[RiskLevel] = Field(
        default=None,
        description="Mirror of `overall.risk`. None when nothing was assessed.",
    )
    critical_conditions: List[str] = Field(
        default_factory=list, description="Flagged AND High risk."
    )
    abnormal_findings: List[str] = Field(default_factory=list)
    normal_findings: List[str] = Field(
        default_factory=list, description="Assessed, nothing flagged."
    )
    unassessed_conditions: List[str] = Field(
        default_factory=list,
        description="Could NOT be assessed. Not normal, not abnormal.",
    )
    prioritized: List[PrioritizedFinding] = Field(
        default_factory=list, description="Module 19."
    )
    explainability: ExplainabilitySection = Field(
        default_factory=ExplainabilitySection, description="Module 20."
    )
    recommendations: List[ReportRecommendation] = Field(default_factory=list)
    document: DocumentQuality = Field(default_factory=DocumentQuality)
    validation_warnings: List[StageWarning] = Field(
        default_factory=list,
        description=(
            "EVERY warning from EVERY stage -- extraction, feature "
            "engineering, validation, rules, ml, fusion and report -- with its "
            "origin `stage` and `module` intact. Dropping upstream warnings "
            "has been a real defect on this project twice; this is the last "
            "hop and it does not drop them."
        ),
    )
    warnings_by_stage: Dict[str, int] = Field(
        default_factory=dict,
        description="Counts per origin stage, so a renderer can show the "
        "breakdown without re-scanning the list.",
    )
    summary: ReportSummary = Field(default_factory=ReportSummary)
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="System metadata: module and engine versions, the policies "
        "applied. Never PHI, never raw report text.",
    )
    fusion: DecisionFusionData = Field(
        default_factory=DecisionFusionData,
        description=(
            "Module 16's output nested VERBATIM -- and through it Module 15's "
            "collection. The report is a view, not a replacement: Module 32 and "
            "Modules 28-30 can always reach the exact rule, model or raw "
            "decision behind any line above."
        ),
    )


class ReportRejectedFeature(BaseModel):

    model_config = ConfigDict(extra="ignore")

    name: Optional[str] = None
    value: Optional[Any] = None
    unit: Optional[str] = None
    canonical_unit: bool = True
    source: Optional[str] = None
    provenance: Optional[FeatureProvenance] = None
    status: str = "rejected"
    reason_code: Optional[str] = None
    reason: Optional[str] = None


class ClinicalReportRequest(DecisionFusionRequest):

    model_config = ConfigDict(extra="ignore")

    rejected_features: Dict[str, ReportRejectedFeature] = Field(
        default_factory=dict,
        description="Module 6's `rejected` map. Read ONLY by Modules 17 and 20, "
        "to explain an exclusion -- never by a rule or a model.",
    )


class ClinicalReportResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    success: bool = True
    data: ClinicalReport


def _self_check() -> None:
    from app.data.recommendation_catalog import assert_safe

    fixed = {
        "report.CAVEAT_NOTHING_ASSESSED": CAVEAT_NOTHING_ASSESSED,
        "report.CAVEAT_NO_LAB_RESULT_ASSESSED": CAVEAT_NO_LAB_RESULT_ASSESSED,
        "report.CAVEAT_ASSESSMENT_INCOMPLETE": CAVEAT_ASSESSMENT_INCOMPLETE,
        "report.OVERALL_STATUS_POLICY": OVERALL_STATUS_POLICY,
        "report.PRIORITIZATION_POLICY": PRIORITIZATION_POLICY,
        "report.EXPLAINABILITY_POLICY": EXPLAINABILITY_POLICY,
        "report.ML_IMPORTANCE_CAVEAT": ML_IMPORTANCE_CAVEAT,
        "report.ML_PROBABILITY_SEMANTICS": ML_PROBABILITY_SEMANTICS,
        "report.EXPLANATION_OBSERVED": EXPLANATION_OBSERVED,
        "report.EXPLANATION_NOT_PRESENT": EXPLANATION_NOT_PRESENT,
        "report.EXPLANATION_UNREADABLE": EXPLANATION_UNREADABLE,
        "report.EXPLANATION_FOUND_BUT_NOT_TRUSTED": (
            EXPLANATION_FOUND_BUT_NOT_TRUSTED
        ),
    }
    for where, text in fixed.items():
        assert_safe(text, where)

    if set(AVAILABILITY_EXPLANATION) != set(AVAILABILITY_VALUES):
        raise ValueError("every availability value needs fixed explanation text")
    if STATUS_NOT_ASSESSED in (
        STATUS_HEALTHY,
        STATUS_NEEDS_MONITORING,
        STATUS_NEEDS_MEDICAL_ATTENTION,
    ):
        raise ValueError(
            "the fourth outcome must be distinguishable from the spec's three"
        )


_self_check()


__all__ = [
    "AVAILABILITY_EXPLANATION",
    "AVAILABILITY_FOUND_BUT_NOT_TRUSTED",
    "AVAILABILITY_NOT_PRESENT",
    "AVAILABILITY_OBSERVED",
    "AVAILABILITY_UNREADABLE",
    "AVAILABILITY_VALUES",
    "CAVEAT_ASSESSMENT_INCOMPLETE",
    "CAVEAT_NOTHING_ASSESSED",
    "CAVEAT_NO_LAB_RESULT_ASSESSED",
    "EVIDENCE_CHAIN",
    "EXPLAINABILITY_POLICY",
    "EXPLANATION_FOUND_BUT_NOT_TRUSTED",
    "EXPLANATION_NOT_PRESENT",
    "EXPLANATION_OBSERVED",
    "EXPLANATION_UNREADABLE",
    "ML_IMPORTANCE_CAVEAT",
    "ML_PROBABILITY_SEMANTICS",
    "OVERALL_STATUS_LABELS",
    "STATUS_HEALTHY_PARTIAL",
    "OVERALL_STATUS_POLICY",
    "OVERALL_STATUS_RULES",
    "PRIORITIZATION_POLICY",
    "PRIORITY_BANDS",
    "PRIORITY_HIGH",
    "PRIORITY_LOW",
    "PRIORITY_MEDIUM",
    "PRIORITY_NOT_ASSESSED",
    "REPORT_MODULE",
    "RULE_ABNORMAL_WITHOUT_HIGH_RISK",
    "RULE_ABNORMAL_WITH_HIGH_RISK",
    "RULE_NOTHING_ASSESSED",
    "RULE_NO_ABNORMAL_FINDINGS",
    "RULE_NO_LAB_RESULT_ASSESSED",
    "STAGE_REPORT",
    "STATUS_NOT_ASSESSED",
    "TIER_FLAGGED",
    "TIER_NORMAL",
    "TIER_UNASSESSED",
    "ClinicalReport",
    "ClinicalReportRequest",
    "ClinicalReportResponse",
    "ConditionExplanation",
    "ContributionView",
    "DocumentQuality",
    "EvidenceLine",
    "ExplainabilitySection",
    "LaboratoryValue",
    "MLExplanation",
    "OverallHealthStatus",
    "PatientInformation",
    "PrioritizedFinding",
    "ReportRecommendation",
    "ReportRejectedFeature",
    "ReportSummary",
    "ReportedCondition",
    "RuleExplanation",
    "SourceExplanation",
]
