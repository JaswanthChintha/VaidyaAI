"""The Module 15 (Decision Engine) and Module 16 (Fusion Engine) contract.

Like Modules 8 and 9/10, nothing here redefines, subclasses or wraps
`ClinicalDecision`. The Module 14 object is the currency; these types describe
how a *set* of them is organised, grouped and fused.

==========================================================================
THE REQUEST SHAPE IS INHERITED, FOR THE SAME REASON MODULE 9's IS
==========================================================================

`DecisionFusionRequest` SUBCLASSES `RuleEvaluationRequest` and adds nothing, so
`POST /api/v1/decisions/fuse` accepts byte-for-byte what
`POST /api/v1/rules/evaluate` and `POST /api/v1/ml/predict` accept, and rejects
the same ambiguities with the same 422s. Re-implementing the unwrap logic would
let the tolerances drift, and the failure mode of a drift is not an error -- it
is an HTTP 200 carrying `fused: []`.

==========================================================================
TWO LAYERS, DELIBERATELY SEPARATE
==========================================================================

    evaluate_rules() ─┐
                      ├─> collect_decisions()  ─> fuse_decisions() ─> report
    predict_all()   ──┘        (Module 15)          (Module 16)

Module 15 is "an intermediate decision management layer before fusion" (spec).
Its job is NOT to merge across analytical approaches -- that is fusion's -- but
to collect, identify and GROUP BY ``(condition, source)``.

WHY THE GROUPING LIVES IN MODULE 15 AND NOT IN MODULE 8
-------------------------------------------------------
The rule engine legitimately emits MORE THAN ONE decision for one condition
from one source. A patient with HbA1c 6.8 and fasting glucose 112 gets
``Diabetes / Indicated / High`` from the HbA1c rule AND
``Diabetes / Borderline / Medium`` from the glucose rule. That is correct: the
unit of a rule decision is one RULE, not one condition, which is exactly what
makes per-rule traceability possible.

But handed straight to fusion those two produce
``sources = ["Clinical Rule Engine", "Clinical Rule Engine"]``, double-weight
the condition in Module 19's prioritisation, and render two contradictory cards
on one dashboard. So they are collapsed HERE, upstream of fusion and downstream
of the rule engine, where neither of those modules has to change.

==========================================================================
STABLE DECISION IDS
==========================================================================

Every collected decision is given a deterministic id built from its origin,
condition and the rule id or predictor name that produced it. Ids are stable
across runs for the same input, which is what lets Module 20 trace a fused
finding back to the exact rule or model -- and lets a reviewer diff two runs.
Nothing random, nothing time-based: a UUID would make the grouping unauditable.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.decisions import (
    ClinicalDecision,
    DecisionSourceKind,
    DecisionStatus,
    RiskLevel,
)
from app.schemas.features import StageWarning, UpstreamExtraction
from app.schemas.rules import RuleEvaluationRequest
from app.schemas.validation import FeatureValidationSummary

#: Stage identifiers stamped on each layer's own warnings.
STAGE_DECISIONS = "decisions"
DECISIONS_MODULE = 15
STAGE_FUSION = "fusion"
FUSION_MODULE = 16


# --------------------------------------------------------------------------
# Assessment basis -- the "Heart Disease means two things" hazard
# --------------------------------------------------------------------------
#
# `Heart Disease` is emitted by the composite clinical rule as a COUNT OF
# RECORDED RISK FACTORS, and by Module 11's predictor as an ESTIMATED
# LIKELIHOOD. Both are legitimately about the same topic, so they must still
# fuse -- renaming either would break fusion, which is the one thing Module 16
# exists to do. What must NOT happen is the two being blended into a single
# sentence that reads as though one number meant the other.
#
# So the basis travels with each contribution, machine-readable, and a fused
# decision whose contributions disagree about the basis is FLAGGED. Module 17
# renders the contributions separately in that case instead of one merged
# claim, and Module 20 has the label it needs to say which question was asked.

BASIS_THRESHOLD = "threshold_comparison"
BASIS_RISK_FACTOR_COUNT = "risk_factor_count"
BASIS_MODEL_PROBABILITY = "model_probability"
BASIS_NOT_ASSESSED = "not_assessed"

#: The QUESTION each basis answers.
FAMILY_MEASURED_VALUE = "measured_value"
FAMILY_RISK_FACTOR_BURDEN = "risk_factor_burden"
FAMILY_ESTIMATED_LIKELIHOOD = "estimated_likelihood"
FAMILY_NONE = "none"

BASIS_FAMILY: Dict[str, str] = {
    BASIS_THRESHOLD: FAMILY_MEASURED_VALUE,
    BASIS_RISK_FACTOR_COUNT: FAMILY_RISK_FACTOR_BURDEN,
    BASIS_MODEL_PROBABILITY: FAMILY_ESTIMATED_LIKELIHOOD,
    BASIS_NOT_ASSESSED: FAMILY_NONE,
}

#: NOT every pair of families conflicts, and over-flagging would be its own
#: defect -- a caveat attached to every fused decision is a caveat nobody
#: reads.
#:
#: A threshold comparison on HbA1c and a model's probability of diabetes are
#: two METHODS of answering ONE question ("what is this patient's glycaemic
#: status?"). Combining them is the entire point of a hybrid system, and
#: flagging that pair as a conflict would flag the normal case.
#:
#: A RISK-FACTOR COUNT is different in kind. "Three or more major
#: cardiovascular risk factors were counted" is a statement about BURDEN -- how
#: many adverse things are on record -- not about how likely the condition is.
#: Presenting it interchangeably with a model's likelihood tells the reader
#: that a tally was a probability. So the burden family, and only the burden
#: family, conflicts with anything else.
CONFLICTING_FAMILY = FAMILY_RISK_FACTOR_BURDEN

#: Fixed, reviewed, user-facing wording -- never composed at runtime, and
#: scanned by the recommendation catalogue's safety scanner at import time (see
#: `_self_check` below), exactly as Module 8's band labels are.
BASIS_CONFLICT_NOTE = (
    "The analyses contributing to this topic answer different questions: one "
    "counts recorded risk factors, the other estimates a statistical "
    "likelihood from a model. They are shown side by side because they are "
    "not interchangeable and one does not confirm the other."
)


# --------------------------------------------------------------------------
# Overall health status (spec Module 18)
# --------------------------------------------------------------------------

STATUS_HEALTHY = "Healthy"
STATUS_NEEDS_MONITORING = "Needs Monitoring"
STATUS_NEEDS_MEDICAL_ATTENTION = "Needs Medical Attention"

OVERALL_STATUSES: Tuple[str, ...] = (
    STATUS_HEALTHY,
    STATUS_NEEDS_MONITORING,
    STATUS_NEEDS_MEDICAL_ATTENTION,
)


# --------------------------------------------------------------------------
# Request
# --------------------------------------------------------------------------


class DecisionFusionRequest(RuleEvaluationRequest):
    """Byte-for-byte the same accepted shapes as Modules 8 and 9. See above."""

    model_config = ConfigDict(extra="ignore")


# --------------------------------------------------------------------------
# Module 15 -- collection
# --------------------------------------------------------------------------


class SourceRunSummary(BaseModel):
    """What one decision SOURCE did on this request.

    Present for every source the Decision Engine tried, including one that
    FAILED. `failed: true` with `decision_count: 0` is not the same as a source
    that ran and produced nothing, and collapsing the two would let a crashed
    predictor read as a clean result -- the same reasoning that makes the three
    fusion conditions `always_assessed` in `app/data/conditions.py`.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="e.g. 'Clinical Rule Engine'.")
    module: int = Field(description="Spec module number: 8 or 9.")
    kind: DecisionSourceKind
    ran: bool = Field(
        default=False, description="The source returned without raising."
    )
    failed: bool = Field(
        default=False,
        description="The source raised. Its decisions are absent from this "
        "run; every OTHER source's decisions are still present.",
    )
    error_type: Optional[str] = Field(
        default=None,
        description="Exception TYPE only. A message can echo input values, "
        "which are medical data.",
    )
    decision_count: int = 0


class CollectedDecision(BaseModel):
    """One raw `ClinicalDecision` plus the identity Module 20 traces through."""

    model_config = ConfigDict(extra="forbid")

    decision_id: str = Field(
        description="Deterministic. Same input, same id, every run."
    )
    origin: str = Field(description="'rules' | 'ml' -- which engine returned it.")
    trace: Optional[str] = Field(
        default=None,
        description="The rule id or predictor name that produced it. The exact "
        "thing Module 20 must be able to name.",
    )
    band_label: Optional[str] = Field(
        default=None,
        description="The rule band's own user-facing wording, verbatim, or the "
        "model's band meaning. Carried so Module 17 can state what a source "
        "actually claimed rather than re-deriving it from the status.",
    )
    assessment_basis: str = BASIS_NOT_ASSESSED
    decision: ClinicalDecision


class DecisionGroup(BaseModel):
    """Every decision for one ``(condition, source)`` pair, collapsed to one.

    THIS is the audit requirement from the integration audit. `member_count > 1`
    is normal and correct for the rule engine; what matters is that fusion sees
    ONE entry per source, so `sources` cannot repeat and Module 19 cannot
    double-weight the condition.
    """

    model_config = ConfigDict(extra="forbid")

    condition: str
    source: str
    source_kind: DecisionSourceKind
    member_count: int = Field(
        description="How many raw decisions were collapsed. >1 for the rule "
        "engine whenever two of its rules fired on one condition."
    )
    decision_ids: List[str] = Field(
        default_factory=list, description="The raw ids, in collection order."
    )
    traces: List[str] = Field(
        default_factory=list, description="Rule ids / predictor names."
    )
    band_labels: List[str] = Field(default_factory=list)
    assessment_basis: str = BASIS_NOT_ASSESSED
    assessed: bool = Field(
        default=False,
        description="At least one member actually assessed the condition.",
    )
    decision: ClinicalDecision = Field(
        description="The within-source merge. Keeps the source's OWN "
        "`source_kind` -- merging two rule decisions does not create a hybrid."
    )


class DecisionCollectionSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_count: int = 0
    group_count: int = 0
    condition_count: int = 0
    sources_run: List[str] = Field(default_factory=list)
    sources_failed: List[str] = Field(default_factory=list)
    conditions_assessed: List[str] = Field(default_factory=list)
    conditions_flagged: List[str] = Field(default_factory=list)
    highest_risk: Optional[RiskLevel] = Field(
        default=None,
        description="RiskLevel.highest() over every decision carrying a risk. "
        "None when nothing was assessable -- never defaulted to Low.",
    )
    multi_decision_groups: List[str] = Field(
        default_factory=list,
        description="'<condition> / <source>' for each group that collapsed "
        "more than one decision. Makes the collapse visible rather than silent.",
    )
    partial_document: bool = False
    input_kind: str = "none"


class DecisionCollectionData(BaseModel):
    """Module 15's output. The intermediate layer, before fusion."""

    model_config = ConfigDict(extra="forbid")

    collected: List[CollectedDecision] = Field(
        default_factory=list,
        description="Every raw decision from every source that ran, ordered by "
        "canonical condition then by source then by production order. NOT "
        "de-duplicated -- per-rule traceability lives here.",
    )
    groups: List[DecisionGroup] = Field(default_factory=list)
    sources: List[SourceRunSummary] = Field(default_factory=list)
    warnings: List[str] = Field(
        default_factory=list,
        description="Warnings raised by MODULE 15 ITSELF.",
    )
    upstream_warnings: List[StageWarning] = Field(
        default_factory=list,
        description="Every warning from Modules 4-6 AND from Modules 8 and "
        "9/10, carried forward with its original stage, de-duplicated by "
        "(stage, module, message) so a warning both sources relayed appears "
        "once WITH ITS ORIGINAL ORIGIN. Never edited, never dropped.",
    )
    all_warnings: List[StageWarning] = Field(
        default_factory=list,
        description="Every warning from every stage, upstream first. Module "
        "15's own carry stage='decisions'.",
    )
    upstream: UpstreamExtraction = Field(default_factory=UpstreamExtraction)
    upstream_summary: FeatureValidationSummary = Field(
        default_factory=FeatureValidationSummary
    )
    summary: DecisionCollectionSummary = Field(
        default_factory=DecisionCollectionSummary
    )
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def raw_decisions(self) -> List[ClinicalDecision]:
        """Every collected `ClinicalDecision`, ungrouped."""
        return [item.decision for item in self.collected]


# --------------------------------------------------------------------------
# Module 16 -- fusion
# --------------------------------------------------------------------------


class DecisionContribution(BaseModel):
    """What ONE analytical source contributed to a fused decision.

    Spec Module 16 point 6: "the system identifies the analytical sources
    contributing to the final decision". This is that identification, kept
    machine-readable so Module 20 can trace the fused finding back to the exact
    rule or model and Module 17 can show a rule and a model side by side when
    they answered different questions.
    """

    model_config = ConfigDict(extra="forbid")

    source: str
    source_kind: DecisionSourceKind
    status: DecisionStatus
    risk: Optional[RiskLevel] = None
    confidence: Optional[float] = Field(
        default=None,
        description="This source's own probability. None means the source "
        "produces none (a deterministic rule) -- NOT zero.",
    )
    assessment_basis: str = BASIS_NOT_ASSESSED
    decision_ids: List[str] = Field(
        default_factory=list,
        description="Every raw decision id this source contributed. More than "
        "one when several of its rules fired on the condition.",
    )
    traces: List[str] = Field(default_factory=list)
    band_labels: List[str] = Field(default_factory=list)
    evidence_features: List[str] = Field(default_factory=list)
    recommendation_codes: List[str] = Field(default_factory=list)


class FusedDecision(BaseModel):
    """One condition, one consolidated decision, provenance intact."""

    model_config = ConfigDict(extra="forbid")

    condition: str
    decision: ClinicalDecision = Field(
        description="The Module 14 object, `source_kind=FUSION`. Satisfies "
        "every invariant the schema enforces."
    )
    status: DecisionStatus = Field(description="Mirror of `decision.status`.")
    risk: Optional[RiskLevel] = Field(
        default=None, description="Mirror of `decision.risk`."
    )
    confidence: Optional[float] = Field(
        default=None, description="Mirror of `decision.confidence`."
    )
    sources: List[str] = Field(
        default_factory=list,
        description="DE-DUPLICATED. A condition backed by one rule engine "
        "firing twice has ONE source here, not two.",
    )
    source_kinds: List[DecisionSourceKind] = Field(default_factory=list)
    hybrid: bool = Field(
        default=False,
        description="A clinical rule AND a model both contributed -- stronger "
        "evidence than either alone, and the reason this is a hybrid system.",
    )
    contributions: List[DecisionContribution] = Field(default_factory=list)
    decision_ids: List[str] = Field(
        default_factory=list, description="Every raw decision id fused here."
    )
    assessed_source_count: int = 0
    unassessed_sources: List[str] = Field(
        default_factory=list,
        description="Sources that could NOT assess this condition. Never "
        "silently dropped: a fused INDICATED whose model abstained must still "
        "say the model abstained.",
    )
    partially_assessed: bool = Field(
        default=False,
        description="At least one source assessed and at least one could not.",
    )
    confidence_basis: str = Field(
        default="none_produced",
        description="'none_produced' | 'max_of_model_probabilities'.",
    )
    assessment_bases: List[str] = Field(default_factory=list)
    basis_conflict: bool = Field(
        default=False,
        description="The contributions answer different questions (risk-factor "
        "burden vs estimated likelihood). Module 17 must show them separately.",
    )
    basis_note: Optional[str] = Field(
        default=None, description="Fixed wording; set only when basis_conflict."
    )
    evidence_count: int = 0
    recommendation_count: int = 0


class PrioritizedCondition(BaseModel):
    """One row of Module 19's priority list -- one CONDITION, never one decision."""

    model_config = ConfigDict(extra="forbid")

    condition: str
    status: DecisionStatus
    risk: Optional[RiskLevel] = None
    flagged: bool = False
    hybrid: bool = False
    sources: List[str] = Field(default_factory=list)


class FusionSummary(BaseModel):
    """Everything Modules 17, 18 and 19 need WITHOUT re-deriving it."""

    model_config = ConfigDict(extra="forbid")

    fused_count: int = 0
    condition_count: int = 0
    hybrid_condition_count: int = 0
    raw_decision_count: int = 0
    collapsed_decision_count: int = Field(
        default=0,
        description="raw_decision_count minus fused_count: how many decisions "
        "grouping and fusion absorbed. Non-zero is normal.",
    )

    # -- Module 18 ------------------------------------------------------
    overall_status: Optional[str] = Field(
        default=None,
        description=(
            "Healthy | Needs Monitoring | Needs Medical Attention, per spec "
            "Module 18. **None when NOTHING was assessed at all.** 'No abnormal "
            "findings' would otherwise render as 'Healthy' for a report in "
            "which no test could be read -- the exact failure `decisions.py` "
            "calls the most dangerous one this type can have. Read it together "
            "with `any_assessed` and `assessment_incomplete`."
        ),
    )
    overall_risk: Optional[RiskLevel] = Field(
        default=None,
        description="Highest risk across FUSED decisions. None when nothing "
        "was assessed -- never defaulted to Low.",
    )
    any_assessed: bool = False
    assessment_incomplete: bool = Field(
        default=False,
        description="At least one condition could not be assessed, or a source "
        "failed. Module 17 must caveat the overall status when this is true.",
    )

    critical_conditions: List[str] = Field(
        default_factory=list, description="Flagged AND High risk."
    )
    abnormal_conditions: List[str] = Field(
        default_factory=list, description="INDICATED or BORDERLINE."
    )
    normal_conditions: List[str] = Field(
        default_factory=list, description="NOT_INDICATED -- assessed, nothing found."
    )
    unassessed_conditions: List[str] = Field(
        default_factory=list, description="INSUFFICIENT_DATA."
    )

    # -- Module 19 ------------------------------------------------------
    prioritized: List[PrioritizedCondition] = Field(
        default_factory=list,
        description="High -> Medium -> Low -> unassessed, then canonical "
        "condition order. ONE ROW PER CONDITION.",
    )

    # -- provenance -----------------------------------------------------
    sources_used: List[str] = Field(default_factory=list)
    sources_failed: List[str] = Field(default_factory=list)
    basis_conflict_conditions: List[str] = Field(default_factory=list)
    partially_assessed_conditions: List[str] = Field(default_factory=list)
    partial_document: bool = False
    input_kind: str = "none"


class DecisionFusionData(BaseModel):
    """The `data` object of a successful fusion response."""

    model_config = ConfigDict(extra="forbid")

    fused: List[FusedDecision] = Field(
        default_factory=list,
        description="ONE PER CONDITION, in canonical condition order.",
    )
    collection: DecisionCollectionData = Field(
        default_factory=DecisionCollectionData,
        description="Module 15's layer, nested verbatim: every raw decision, "
        "its id, and the (condition, source) groups. Fusion never discards it, "
        "so Module 20 can always reach the exact rule or model.",
    )
    warnings: List[str] = Field(
        default_factory=list, description="Warnings raised by MODULE 16 ITSELF."
    )
    upstream_warnings: List[StageWarning] = Field(
        default_factory=list,
        description="Every warning from every earlier stage, origins intact.",
    )
    all_warnings: List[StageWarning] = Field(
        default_factory=list,
        description="Every warning from every stage, upstream first. Module "
        "16's own carry stage='fusion'. THIS is what Module 17 renders as its "
        "validation warnings.",
    )
    upstream: UpstreamExtraction = Field(default_factory=UpstreamExtraction)
    upstream_summary: FeatureValidationSummary = Field(
        default_factory=FeatureValidationSummary
    )
    summary: FusionSummary = Field(default_factory=FusionSummary)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DecisionFusionResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    success: bool = True
    data: DecisionFusionData


# --------------------------------------------------------------------------
# Import-time enforcement
# --------------------------------------------------------------------------


def _self_check() -> None:
    """Fail at import if the fixed user-facing wording is unsafe or drifts."""
    from app.data.recommendation_catalog import assert_safe

    assert_safe(BASIS_CONFLICT_NOTE, "fusion.BASIS_CONFLICT_NOTE")
    for basis in (
        BASIS_THRESHOLD,
        BASIS_RISK_FACTOR_COUNT,
        BASIS_MODEL_PROBABILITY,
        BASIS_NOT_ASSESSED,
    ):
        if basis not in BASIS_FAMILY:
            raise ValueError(f"basis {basis!r} has no family in BASIS_FAMILY")


_self_check()


__all__ = [
    "BASIS_CONFLICT_NOTE",
    "BASIS_FAMILY",
    "CONFLICTING_FAMILY",
    "FAMILY_ESTIMATED_LIKELIHOOD",
    "FAMILY_MEASURED_VALUE",
    "FAMILY_NONE",
    "FAMILY_RISK_FACTOR_BURDEN",
    "BASIS_MODEL_PROBABILITY",
    "BASIS_NOT_ASSESSED",
    "BASIS_RISK_FACTOR_COUNT",
    "BASIS_THRESHOLD",
    "DECISIONS_MODULE",
    "FUSION_MODULE",
    "OVERALL_STATUSES",
    "STAGE_DECISIONS",
    "STAGE_FUSION",
    "STATUS_HEALTHY",
    "STATUS_NEEDS_MEDICAL_ATTENTION",
    "STATUS_NEEDS_MONITORING",
    "CollectedDecision",
    "DecisionCollectionData",
    "DecisionCollectionSummary",
    "DecisionContribution",
    "DecisionFusionData",
    "DecisionFusionRequest",
    "DecisionFusionResponse",
    "DecisionGroup",
    "FusedDecision",
    "FusionSummary",
    "PrioritizedCondition",
    "SourceRunSummary",
]
