"""Modules 17-20 -- Clinical Report Generation.

    Module 16 fusion  ─>  generate_report()  ─>  Module 27 dashboard
                                                 Module 32 doctor summary

Framework-independent, exactly as `evaluate_rules`, `predict_all` and
`fuse_decisions` are: `app/api/routes_report.py` is a thin HTTP wrapper, and
Modules 27/32 and the Node backend call these functions in-process.

Four public entry points, one per spec module:

    generate_report(...)     Module 17  the whole structured report
    overall_status(...)      Module 18  the overall health status
    prioritise(...)          Module 19  findings ordered by significance
    build_explainability(...) Module 20 Input -> Evidence -> Decision

Each is callable on its own, because Module 27 wants the health card without
building a whole report and Module 32 wants the evidence without the card.

==========================================================================
WHAT THIS LAYER ADDS THAT NOTHING UPSTREAM COULD
==========================================================================

1. THE REJECTED-FEATURE JOIN (Module 20; the integration audit's item 3).
   Modules 8 and 9/10 do not parse Module 6's `rejected` map AT ALL -- that
   absence is what makes "a clinical rule can never read a rejected value"
   structural. The cost is that their evidence for such a feature says "this
   value was not available in the submitted report", which is FACTUALLY WRONG:
   the value was in the report, it was read, and it was refused. This layer is
   the first one that holds both halves, so this is where they are joined. See
   `_evidence_line`.

2. THE OVERALL STATUS'S FOURTH AND FIFTH CASES (Module 18). See
   `overall_status`.

3. THE LABORATORY VALUES. Fusion carries decisions, not values; a report needs
   both, and Module 27's laboratory cards and Module 32's reference columns
   read the same rows.

4. CATALOGUE RE-SOURCING OF RECOMMENDATION TEXT. See `_recommendations`.

==========================================================================
LOGGING
==========================================================================

This module logs COUNTS ONLY, through `safe_meta`. The report object holds
clinical values by design -- that is what it is for -- but a log line is a
different artifact with a different lifetime and a different audience, and no
laboratory value, feature value, patient attribute or report text is ever
written to it.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from app.core.logging import get_logger, safe_meta
from app.data import conditions as C
from app.data.feature_catalog import FEATURES
from app.data.recommendation_catalog import RECOMMENDATIONS
from app.ml.base import REASON_MODEL_UNAVAILABLE, REASON_REQUIRED_IMPUTED
from app.schemas.decisions import (
    ClinicalDecision,
    DecisionSourceKind,
    DecisionStatus,
    EvidenceItem,
    RiskLevel,
)
from app.schemas.features import StageWarning
from app.schemas.fusion import (
    BASIS_FAMILY,
    DecisionFusionData,
    FusedDecision,
    FAMILY_NONE,
    STATUS_HEALTHY,
    STATUS_NEEDS_MEDICAL_ATTENTION,
    STATUS_NEEDS_MONITORING,
)
from app.schemas.report import (
    AVAILABILITY_EXPLANATION,
    AVAILABILITY_FOUND_BUT_NOT_TRUSTED,
    AVAILABILITY_NOT_PRESENT,
    AVAILABILITY_OBSERVED,
    AVAILABILITY_UNREADABLE,
    CAVEAT_ASSESSMENT_INCOMPLETE,
    CAVEAT_NOTHING_ASSESSED,
    EXPLAINABILITY_POLICY,
    ML_IMPORTANCE_CAVEAT,
    OVERALL_STATUS_POLICY,
    PRIORITIZATION_POLICY,
    PRIORITY_HIGH,
    PRIORITY_LOW,
    PRIORITY_MEDIUM,
    PRIORITY_NOT_ASSESSED,
    REPORT_MODULE,
    RULE_ABNORMAL_WITHOUT_HIGH_RISK,
    RULE_ABNORMAL_WITH_HIGH_RISK,
    RULE_NOTHING_ASSESSED,
    RULE_NO_ABNORMAL_FINDINGS,
    STAGE_REPORT,
    STATUS_HEALTHY_PARTIAL,
    STATUS_NOT_ASSESSED,
    TIER_FLAGGED,
    TIER_NORMAL,
    TIER_UNASSESSED,
    ClinicalReport,
    ConditionExplanation,
    ContributionView,
    DocumentQuality,
    EvidenceLine,
    ExplainabilitySection,
    LaboratoryValue,
    MLExplanation,
    OverallHealthStatus,
    PatientInformation,
    PrioritizedFinding,
    ReportRecommendation,
    ReportRejectedFeature,
    ReportSummary,
    ReportedCondition,
    RuleExplanation,
    SourceExplanation,
)
from app.services.decision_engine import unique
from app.services.fusion_engine import run_decision_fusion

logger = get_logger(__name__)

#: Bumped when THIS layer's output shape or behaviour changes.
REPORT_VERSION = "1.0.0"

#: Fixed, reviewed wording for the Module 12 skip (integration audit D2). The
#: only runtime part is the list of CANONICAL feature names, so this can never
#: carry producer free text into a reader-facing string.
SKIP_EXPLANATION_MISSING = (
    "This model was not run because the following value(s) it needs were not "
    "available in the submitted report: {features}."
)
SKIP_EXPLANATION_NOT_MEASURED = (
    "This model was not run because the following value(s) it needs were not "
    "measured, and a stand-in figure would not have been this person's: "
    "{features}."
)
SKIP_EXPLANATION_MODEL_UNAVAILABLE = (
    "This model could not be loaded, so it was not run and nothing here was "
    "assessed by it."
)
SKIP_EXPLANATION_UNSPECIFIED = (
    "This model was not run because it did not have the information it needs."
)

REPORT_POLICY = (
    "The report re-shapes what Modules 15 and 16 produced and adds what only "
    "this layer holds: the laboratory values, the join between a refused value "
    "and the reason it was refused, and the overall interpretation. It never "
    "invents a condition, never composes a recommendation, never upgrades a "
    "status, and never presents an absence of findings as a finding of health. "
    "Every warning from every earlier stage is carried through with its origin "
    "intact."
)

#: Order recommendations are presented in. Safety first, then what to do about
#: it, then background. Fixed so two renderers cannot order it differently.
_CATEGORY_ORDER: Tuple[str, ...] = (
    "information",
    "consultation",
    "retest",
    "monitoring",
    "data_quality",
    "lifestyle",
)

_RISK_TO_PRIORITY: Dict[Optional[RiskLevel], str] = {
    RiskLevel.HIGH: PRIORITY_HIGH,
    RiskLevel.MEDIUM: PRIORITY_MEDIUM,
    RiskLevel.LOW: PRIORITY_LOW,
    None: PRIORITY_NOT_ASSESSED,
}

_RISK_RANK: Dict[Optional[RiskLevel], int] = {
    RiskLevel.HIGH: 0,
    RiskLevel.MEDIUM: 1,
    RiskLevel.LOW: 2,
    None: 3,
}

#: The producer notes this layer is allowed to CORRECT. Both are Module 8's and
#: Module 9's wording for "the feature was not in the usable set", which is
#: true from where they stand and false from where the report stands.
_ABSENCE_NOTES = (
    "this value was not available in the submitted report",
    "part of the document could not be read, so this value may be missing "
    "rather than absent from the report",
    "the model needs this value and it was not available, so no prediction "
    "was made",
)


# ==========================================================================
# Module 18 -- overall health status
# ==========================================================================


def overall_status(fusion: DecisionFusionData) -> OverallHealthStatus:
    """Spec Module 18, with the case the spec does not name.

    THE SPEC'S THREE OUTCOMES
    -------------------------
        No abnormal findings              -> Healthy
        Abnormal findings + no High risk  -> Needs Monitoring
        Abnormal finding + High risk      -> Needs Medical Attention

    THE FOURTH CASE: NOTHING WAS ASSESSED
    -------------------------------------
    `summary.overall_status` is None when nothing was assessed at all, and this
    function must NOT fill that in. "No abnormal findings" is vacuously true of
    a report whose every test was unreadable, in exactly the way an empty set
    has no members -- so the first branch of the spec's rule would fire and
    hand a reader whose document could not be read the word "Healthy".

    That is the same failure `app/schemas/decisions.py` forbids at the type
    level when it refuses to let an INSUFFICIENT_DATA decision carry a risk
    level, and calls "the most dangerous failure mode this type can have". The
    report gives a FOURTH label, `Not Assessed`, and `status` stays None so a
    consumer that only knows the spec's three vocabulary values cannot silently
    read it as one of them.

    THE FIFTH CASE: SOME THINGS COULD NOT BE ASSESSED
    -------------------------------------------------
    Here the spec's status still applies to what WAS assessed, and it is kept.
    Downgrading a clean partial report to `Needs Monitoring` would be worse,
    not safer: it would report a finding nobody made, and a caveat that fires
    on every incomplete report is a caveat nobody reads by the third one.

    So the incompleteness is made STRUCTURAL instead of editorial:
    `complete=False`, a non-null fixed `caveat`, and the specific conditions
    named -- AND, since the integration audit (D4), it is carried in the LABEL
    too. A partial clean report is labelled `Healthy (partial assessment)`
    while `status` stays `Healthy`, so a renderer that shows only
    `status_label` no longer presents a one-test report as a full clean bill of
    health. The abnormal statuses keep their labels: an abnormal finding IS a
    finding, and another topic going unassessed does not qualify it.

    The `status` value itself is taken from Module 16's summary rather than
    recomputed, so the two layers cannot disagree; the branch is re-derived
    only to record WHICH rule fired.
    """
    summary = fusion.summary

    assessed = [f for f in fusion.fused if f.decision.was_assessed]
    flagged = [f for f in fusion.fused if f.decision.is_flagged]
    high = [f for f in flagged if f.risk is RiskLevel.HIGH]
    any_assessed = bool(assessed)

    if not any_assessed:
        rule = RULE_NOTHING_ASSESSED
        label = STATUS_NOT_ASSESSED
        status: Optional[str] = None
    elif not flagged:
        rule = RULE_NO_ABNORMAL_FINDINGS
        label = STATUS_HEALTHY
        status = STATUS_HEALTHY
    elif high:
        rule = RULE_ABNORMAL_WITH_HIGH_RISK
        label = STATUS_NEEDS_MEDICAL_ATTENTION
        status = STATUS_NEEDS_MEDICAL_ATTENTION
    else:
        rule = RULE_ABNORMAL_WITHOUT_HIGH_RISK
        label = STATUS_NEEDS_MONITORING
        status = STATUS_NEEDS_MONITORING

    # Module 16 is the authority on the value itself. If this layer ever
    # derived a DIFFERENT one, the two would be reporting different reports.
    if summary.overall_status != status:
        raise ValueError(
            "Module 17's overall status disagrees with Module 16's "
            f"summary.overall_status ({summary.overall_status!r} vs "
            f"{status!r}). One of the two layers has changed its rule."
        )

    complete = any_assessed and not summary.assessment_incomplete

    # THE FIFTH LABEL (integration audit D4). `status` stays at its spec value
    # -- consumers reading the three-value vocabulary are untouched -- but the
    # always-renderable LABEL now distinguishes "we looked at everything and
    # found nothing" from "we found nothing in the part we could look at".
    # Before this, those two reports were byte-identical in `status`,
    # `status_label` and `overall_risk`, so the docstring's claim above that a
    # label-only renderer "is demonstrably wrong" was not actually true: the
    # label showed no difference to detect. It is true now.
    #
    # Only the HEALTHY branch is relabelled. `Needs Monitoring` and `Needs
    # Medical Attention` are statements about a finding that WAS made, and that
    # finding is not made less real by another topic going unassessed; the
    # incompleteness there is carried by `complete=False` and the caveat, as
    # before. It is the clean result that is falsely reassuring when partial.
    if status == STATUS_HEALTHY and not complete:
        label = STATUS_HEALTHY_PARTIAL

    if not any_assessed:
        caveat: Optional[str] = CAVEAT_NOTHING_ASSESSED
    elif not complete:
        caveat = CAVEAT_ASSESSMENT_INCOMPLETE
    else:
        caveat = None

    return OverallHealthStatus(
        status=status,
        status_label=label,
        risk=summary.overall_risk,
        rule_applied=rule,
        any_assessed=any_assessed,
        complete=complete,
        caveat=caveat,
        assessed_condition_count=len(assessed),
        unassessed_condition_count=len(summary.unassessed_conditions),
        unassessed_conditions=list(summary.unassessed_conditions),
        partially_assessed_conditions=list(summary.partially_assessed_conditions),
        sources_failed=list(summary.sources_failed),
        abnormal_condition_count=len(flagged),
        high_risk_condition_count=len(high),
        policy=OVERALL_STATUS_POLICY,
    )


# ==========================================================================
# Module 19 -- risk prioritisation
# ==========================================================================


def prioritise(fused: Sequence[FusedDecision]) -> List[PrioritizedFinding]:
    """Spec Module 19. ONE ROW PER CONDITION, ordered by significance.

    BY CONDITION, NEVER BY DECISION COUNT
    -------------------------------------
    The rule engine emits one decision per RULE, so a patient with HbA1c 6.8
    AND fasting glucose 112 produces two `Diabetes` decisions. That is correct
    -- it is what makes per-rule traceability possible -- but it means any
    ranking that counts decisions gives `Diabetes` double weight purely because
    two relevant tests were ordered. Module 15 groups by `(condition, source)`
    and Module 16 fuses to one per condition, so this function reads `fused`
    and counts nothing. `contributing_decision_count` is carried for display
    and is deliberately absent from the sort key.

    AN UNASSESSED CONDITION IS NOT A LOW-RISK CONDITION
    ---------------------------------------------------
    It has `risk=None`: not "low", NONE. Filing it in the Low band would sort
    an open question in among settled ones and bury it -- the same class of
    error as letting an absence of findings read as health. It gets its own
    band, `Not Assessed`, placed:

        tier 0  FLAGGED findings   High -> Medium -> Low
        tier 1  NOT ASSESSED
        tier 2  NORMAL findings    High -> Medium -> Low

    A flagged Low-risk finding still outranks an open question, because it IS a
    finding and somebody looked. A NORMAL finding does not, because "we looked
    and found nothing" is settled and "we could not look" is not.

    Ties break on `app/data/conditions.py`'s canonical order, so the list is
    stable across runs and two dashboards cannot disagree about the order.
    """
    ordered = sorted(fused, key=_priority_sort_key)
    return [
        PrioritizedFinding(
            rank=index + 1,
            condition=item.condition,
            priority=_RISK_TO_PRIORITY[item.risk]
            if item.decision.was_assessed
            else PRIORITY_NOT_ASSESSED,
            tier=_tier(item),
            status=item.status,
            risk=item.risk,
            flagged=item.decision.is_flagged,
            assessed=item.decision.was_assessed,
            critical=item.decision.is_flagged and item.risk is RiskLevel.HIGH,
            hybrid=item.hybrid,
            sources=list(item.sources),
            confidence=item.confidence,
            partially_assessed=item.partially_assessed,
            basis_conflict=item.basis_conflict,
            contributing_decision_count=len(item.decision_ids),
        )
        for index, item in enumerate(ordered)
    ]


def _tier(item: FusedDecision) -> int:
    if item.decision.is_flagged:
        return TIER_FLAGGED
    if not item.decision.was_assessed:
        return TIER_UNASSESSED
    return TIER_NORMAL


def _priority_sort_key(item: FusedDecision) -> Tuple[int, int, int]:
    return (
        _tier(item),
        _RISK_RANK.get(item.risk, 3),
        C.condition_rank(item.condition),
    )


# ==========================================================================
# Module 20 -- evidence and explainability
# ==========================================================================


def extract_rejected_features(body: Any) -> Dict[str, ReportRejectedFeature]:
    """Find Module 6's `rejected` map in whatever shape the caller relayed.

    The decision chain's request models deliberately DO NOT parse `rejected`
    (see `app/schemas/rules.py`), so it has to be recovered from the raw body.
    Every shape `/decisions/fuse` accepts is covered:

        {"validated": {... "rejected": {...}}}      explicit
        {"rejected_features": {...}}                explicit, this layer's own
        {"success": true, "data": {... "rejected"}} a relayed envelope
        {"valid": {...}, "rejected": {...}}         a bare Module 6 object

    Anything unusable is skipped rather than raised on: a malformed rejection
    record must not be able to fail a whole report, and the worst case of
    skipping one is that the report says "not present" where it could have said
    "found but not trusted" -- which is exactly what happens today.
    """
    if not isinstance(body, Mapping):
        return {}

    containers: List[Any] = [
        body.get("rejected_features"),
        body.get("rejected"),
    ]
    for key in ("validated", "data", "engineered"):
        nested = body.get(key)
        if isinstance(nested, Mapping):
            containers.append(nested.get("rejected"))
            inner = nested.get("data")
            if isinstance(inner, Mapping):
                containers.append(inner.get("rejected"))

    for candidate in containers:
        if not isinstance(candidate, Mapping) or not candidate:
            continue
        out: Dict[str, ReportRejectedFeature] = {}
        for name, record in candidate.items():
            parsed = _coerce_rejected(name, record)
            if parsed is not None:
                out[str(name)] = parsed
        if out:
            return out
    return {}


def _coerce_rejected(name: Any, record: Any) -> Optional[ReportRejectedFeature]:
    if isinstance(record, ReportRejectedFeature):
        return record
    if hasattr(record, "model_dump"):
        record = record.model_dump()
    if not isinstance(record, Mapping):
        return None
    try:
        parsed = ReportRejectedFeature.model_validate(dict(record))
    except Exception:  # noqa: BLE001 -- one bad record must not fail a report
        return None
    if parsed.name is None:
        parsed = parsed.model_copy(update={"name": str(name)})
    return parsed


def build_explainability(
    fusion: DecisionFusionData,
    rejected: Optional[Mapping[str, ReportRejectedFeature]] = None,
    *,
    questionable: Sequence[str] = (),
    clinically_extreme: Sequence[str] = (),
) -> ExplainabilitySection:
    """Spec Module 20: `Input -> Evidence -> Decision`, for every condition.

    For a RULE decision it records the triggering laboratory value, the
    threshold it was compared against and the rule's own classification. For an
    ML decision it records the model, the prediction, the probability and the
    input evidence -- and labels the model's feature importances as GLOBAL,
    because that is what the artifacts contain and spec section 24 forbids
    presenting them as more.

    THE REJECTED-FEATURE JOIN happens in `_evidence_line`, applied to every
    line this function builds, so no path through the explainability layer can
    emit "not available" for a value that was read and refused.
    """
    rejected = dict(rejected or {})
    questionable_set = set(questionable)
    extreme_set = set(clinically_extreme)
    warnings_by_feature = _warnings_by_feature(fusion.all_warnings, rejected)

    joined: List[str] = []

    def line(item: EvidenceItem, classification: Optional[str] = None) -> EvidenceLine:
        built = _evidence_line(
            item,
            rejected=rejected,
            questionable=questionable_set,
            clinically_extreme=extreme_set,
            warnings_by_feature=warnings_by_feature,
            classification=classification,
        )
        if built.rejected and built.feature not in joined:
            joined.append(built.feature)
        return built

    conditions: List[ConditionExplanation] = []
    for item in fusion.fused:
        sources = [
            _explain_source(item, contribution, fusion, line)
            for contribution in item.contributions
        ]
        conditions.append(
            ConditionExplanation(
                condition=item.condition,
                status=item.status,
                risk=item.risk,
                confidence=item.confidence,
                sources=sources,
                evidence=[line(e) for e in item.decision.evidence],
                basis_conflict=item.basis_conflict,
                basis_note=item.basis_note,
                hybrid=item.hybrid,
                fusion_explanation=_fusion_explanation(item),
            )
        )

    return ExplainabilitySection(
        policy=EXPLAINABILITY_POLICY,
        conditions=conditions,
        rejected_features_joined=joined,
        ml_importance_caveat=ML_IMPORTANCE_CAVEAT,
    )


def _fusion_explanation(item: FusedDecision) -> Optional[str]:
    """Spec section 13's 'Fusion Explainability': which sources combined.

    A list of source names joined by ' + '. It states WHICH analyses were
    combined and nothing about what they mean, so there is no clinical claim
    here to get wrong.
    """
    if not item.sources:
        return None
    return " + ".join(item.sources)


def _explain_source(
    item: FusedDecision,
    contribution: Any,
    fusion: DecisionFusionData,
    line: Any,
) -> SourceExplanation:
    """One source's half of `Input -> Evidence -> Decision`."""
    raw = _raw_decisions_for(fusion, contribution.decision_ids)
    assessed = contribution.status is not DecisionStatus.INSUFFICIENT_DATA
    evidence = [line(e) for d in raw for e in d.evidence]
    evidence = _dedup_lines(evidence)

    rule: Optional[RuleExplanation] = None
    ml: Optional[MLExplanation] = None

    if contribution.source_kind is DecisionSourceKind.CLINICAL_RULE:
        rule = RuleExplanation(
            rule_ids=list(contribution.traces),
            classifications=list(contribution.band_labels),
            triggering_values=_triggering_values(raw, line),
            deterministic=True,
        )
    elif contribution.source_kind is DecisionSourceKind.MACHINE_LEARNING:
        ml = _explain_ml(contribution, raw, evidence)

    return SourceExplanation(
        source=contribution.source,
        source_kind=contribution.source_kind,
        status=contribution.status,
        risk=contribution.risk,
        confidence=contribution.confidence,
        assessed=assessed,
        assessment_basis=contribution.assessment_basis,
        assessment_basis_family=BASIS_FAMILY.get(
            contribution.assessment_basis, FAMILY_NONE
        ),
        band_labels=list(contribution.band_labels),
        decision_ids=list(contribution.decision_ids),
        rule=rule,
        ml=ml,
        evidence=evidence,
    )


def _triggering_values(
    raw: Sequence[ClinicalDecision], line: Any
) -> List[EvidenceLine]:
    """The values that actually TRIGGERED a rule -- those with a threshold.

    Spec Module 20 asks for "the rule-triggering laboratory value", which is
    narrower than "every value the rule looked at". A context value used only
    to select which threshold applied (age, sex) is evidence, but it did not
    trigger anything, and presenting it as the trigger would misstate what the
    rule did.
    """
    out: List[EvidenceLine] = []
    for decision in raw:
        classification = decision.metadata.get("band_label")
        for item in decision.evidence:
            if item.threshold is None:
                continue
            out.append(
                line(
                    item,
                    classification if isinstance(classification, str) else None,
                )
            )
    return _dedup_lines(out)


def _explain_ml(
    contribution: Any,
    raw: Sequence[ClinicalDecision],
    evidence: Sequence[EvidenceLine],
) -> MLExplanation:
    """Spec Module 20's ML record: source, prediction, probability, inputs.

    HONESTY ABOUT IMPORTANCE. `global_feature_importance` is copied from the
    predictor's own metadata, where every artifact records it with
    `feature_importance_scope: global_model_level` and a caveat saying it is
    not a per-patient explanation. This function preserves BOTH and sets
    `importance_is_per_patient=False` on the wire, so a renderer cannot
    reasonably label a training-set ranking "why you got this result". Spec
    section 24 forbids unsupported certainty; a global ranking dressed as a
    personal reason is exactly that.
    """
    metadata: Dict[str, Any] = {}
    for decision in raw:
        metadata.update(decision.metadata)

    skipped = contribution.status is DecisionStatus.INSUFFICIENT_DATA

    # THE KEY ALIGNMENT (integration audit D2). This used to look for
    # `skip_reason` / `insufficiency_reason` / `sufficiency_reason`; no producer
    # in the service emits any of the three. Both producers -- `Predictor.
    # insufficient_decision` in `app/ml/base.py` and the rule engine in
    # `app/services/rule_engine.py` -- stamp `skipped_reason`, so THAT is the
    # canonical key and it is read here, with the nested `sufficiency.reason`
    # the predictors also record as the fallback. The consequence of the old
    # mismatch was a Module 12 skip rendering as "Random Forest -- skipped --
    # (no reason)", which a reader cannot tell from "the model broke".
    sufficiency = metadata.get("sufficiency")
    if not isinstance(sufficiency, Mapping):
        sufficiency = {}
    skip_reason = metadata.get("skipped_reason") or sufficiency.get("reason")

    # Likewise `features_missing`: the rule engine stamps that key directly,
    # the predictors record the same list as `sufficiency.required_missing`.
    missing_features: List[str] = []
    for candidate in (
        metadata.get("features_missing"),
        sufficiency.get("required_missing"),
        metadata.get("features_not_asserted") if not skipped else None,
    ):
        if candidate:
            missing_features = [str(n) for n in candidate]
            break

    importance = metadata.get("global_feature_importance") or {}
    if not isinstance(importance, Mapping):
        importance = {}

    caveat = metadata.get("feature_importance_caveat")
    scope = metadata.get("feature_importance_scope") or "global_model_level"

    return MLExplanation(
        model_name=metadata.get("model_name") or contribution.source,
        model_version=_as_str(metadata.get("model_version")),
        prediction=contribution.status,
        risk_band=_as_str(metadata.get("risk_band")),
        band_meaning=_as_str(metadata.get("band_meaning")),
        probability=contribution.confidence,
        thresholds=dict(metadata.get("thresholds") or {}),
        input_evidence=list(evidence),
        features_observed=list(metadata.get("features_observed") or []),
        features_imputed=list(metadata.get("features_imputed") or []),
        features_missing=list(missing_features),
        global_feature_importance={
            str(k): float(v) for k, v in importance.items()
        },
        importance_scope=str(scope),
        importance_is_per_patient=False,
        importance_caveat=(
            caveat if isinstance(caveat, str) and caveat else ML_IMPORTANCE_CAVEAT
        ),
        performance_reference=dict(
            metadata.get("model_performance_reference") or {}
        ),
        skipped=skipped,
        skip_reason=_as_str(skip_reason) if skipped else None,
        skip_explanation=(
            _skip_explanation(skip_reason, missing_features) if skipped else None
        ),
    )


def _skip_explanation(
    reason: Optional[str], missing: Sequence[str]
) -> Optional[str]:
    """A fixed sentence naming the inputs the model needed and did not get.

    Composed from a small closed set of wordings plus CANONICAL feature names
    (`app/data/feature_catalog.py`), never from producer free text -- so this
    string cannot become an injection surface and cannot drift into clinical
    language. `report_text_violations` scans it anyway.
    """
    names = ", ".join(str(n) for n in missing)
    if reason == REASON_MODEL_UNAVAILABLE:
        return SKIP_EXPLANATION_MODEL_UNAVAILABLE
    if reason == REASON_REQUIRED_IMPUTED and names:
        return SKIP_EXPLANATION_NOT_MEASURED.format(features=names)
    if names:
        return SKIP_EXPLANATION_MISSING.format(features=names)
    if reason:
        return SKIP_EXPLANATION_UNSPECIFIED
    return None


def _as_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    return str(value)


def _raw_decisions_for(
    fusion: DecisionFusionData, decision_ids: Sequence[str]
) -> List[ClinicalDecision]:
    """The raw `ClinicalDecision` objects behind a contribution.

    Module 16 kept Module 15's whole collection precisely so this trace-back is
    always possible; nothing here re-runs anything.
    """
    wanted = list(decision_ids)
    by_id = {c.decision_id: c.decision for c in fusion.collection.collected}
    return [by_id[i] for i in wanted if i in by_id]


# --------------------------------------------------------------------------
# The join itself
# --------------------------------------------------------------------------


def _evidence_line(
    item: EvidenceItem,
    *,
    rejected: Mapping[str, ReportRejectedFeature],
    questionable: set,
    clinically_extreme: set,
    warnings_by_feature: Mapping[str, List[StageWarning]],
    classification: Optional[str] = None,
) -> EvidenceLine:
    """Turn one `EvidenceItem` into a renderable line -- AND CORRECT IT.

    THIS IS THE REJECTED-FEATURE JOIN (integration audit §6h item 3).

    Modules 8 and 9/10 attach "this value was not available in the submitted
    report" whenever a feature is not in Module 6's USABLE set. From where they
    stand that is true: `rejected` is not a field they parse, so the value is
    genuinely not available TO THEM. From where the reader stands it is false
    and materially so. "No creatinine was ordered" and "creatinine was printed
    in a unit we could not read" call for completely different next steps, and
    the second one is a fixable problem with the document.

    So: if the cited feature is in Module 6's `rejected` map, this line is
    `found_but_not_trusted`, carries the validator's own `reason_code` and
    `reason`, preserves the value that was actually printed, and says the value
    was read. The producer's original note is kept in `note` -- unedited, so
    the trace back to what Module 8 actually said stays intact -- but
    `availability` and `explanation`, which are what a renderer shows, are
    corrected. The upstream warnings that name the feature are attached too,
    with their origin stage, which is the other half of the join the audit
    described.

    The correction is applied ONLY to a feature that is genuinely in the
    rejected map. A feature that really was absent still reads as absent.
    """
    feature = item.feature
    record = rejected.get(feature)
    definition = FEATURES.get(feature)

    if record is not None:
        availability = AVAILABILITY_FOUND_BUT_NOT_TRUSTED
    elif _is_absence_note(item.note) or item.value is None:
        availability = (
            AVAILABILITY_UNREADABLE
            if _is_unreadable_note(item.note)
            else AVAILABILITY_NOT_PRESENT
        )
    else:
        availability = AVAILABILITY_OBSERVED

    return EvidenceLine(
        feature=feature,
        display_name=definition.description if definition else None,
        value=item.value,
        unit=item.unit,
        threshold=item.threshold,
        comparator=item.comparator,
        classification=classification,
        reference_low=item.reference_low,
        reference_high=item.reference_high,
        note=item.note,
        source_stage=item.source_stage,
        availability=availability,
        explanation=AVAILABILITY_EXPLANATION[availability],
        rejected=record is not None,
        rejection_code=record.reason_code if record else None,
        rejection_reason=record.reason if record else None,
        rejected_value=record.value if record else None,
        rejected_unit=record.unit if record else None,
        questionable=feature in questionable,
        clinically_extreme=feature in clinically_extreme,
        related_warnings=list(warnings_by_feature.get(feature, ())),
    )


def _is_absence_note(note: Optional[str]) -> bool:
    return bool(note) and any(note == fragment for fragment in _ABSENCE_NOTES)


def _is_unreadable_note(note: Optional[str]) -> bool:
    return bool(note) and "could not be read" in note


def _warnings_by_feature(
    warnings: Sequence[StageWarning],
    rejected: Mapping[str, ReportRejectedFeature],
) -> Dict[str, List[StageWarning]]:
    """Index upstream warnings by the rejected feature they name.

    Only rejected features are indexed. A broad substring match across every
    feature would attach a warning about `hemoglobin` to a line about
    `hba1c`, and a wrong join is worse than no join.
    """
    index: Dict[str, List[StageWarning]] = {}
    for name in rejected:
        needle = name.lower()
        hits = [w for w in warnings if needle in (w.message or "").lower()]
        if hits:
            index[name] = hits
    return index


def _dedup_lines(lines: Sequence[EvidenceLine]) -> List[EvidenceLine]:
    seen: Dict[Tuple[Any, ...], None] = {}
    out: List[EvidenceLine] = []
    for one in lines:
        key = (one.feature, str(one.value), one.unit, str(one.threshold))
        if key in seen:
            continue
        seen[key] = None
        out.append(one)
    return out


# ==========================================================================
# Module 17 -- the report
# ==========================================================================


def generate_report(
    validated: Any = None,
    *,
    engineered: Any = None,
    rejected: Any = None,
    fusion: Optional[DecisionFusionData] = None,
    registry: Any = None,
) -> ClinicalReport:
    """Spec Module 17. Build the structured Clinical Report.

    `validated`  -- Module 6's `FeatureValidationData`, a `ValidatedFeaturesInput`
                    or the equivalent dict. PREFERRED, and when it is Module 6's
                    own object the rejected map comes with it for free.
    `engineered` -- Module 5's output. Module 6 is then run in-process, so the
                    report's laboratory values and rejected map are the real
                    ones and not a guess.
    `rejected`   -- Module 6's `rejected` map, when the caller had to relay it
                    separately (see `extract_rejected_features`).
    `fusion`     -- an already-computed `DecisionFusionData`. Supplying it skips
                    re-running the rules and the models, which is how Modules
                    27/32 re-render a stored analysis without a second
                    prediction that might not reproduce bit-for-bit.
    `registry`   -- an ML `PredictorRegistry`; defaults to the process registry.

    Framework-independent. No FastAPI, no I/O, no global state.
    """
    features_view = _resolve_features(validated, engineered)
    if fusion is None:
        fusion = run_decision_fusion(
            features_view.for_decisions, engineered=None, registry=registry
        )

    rejected_map = _merge_rejected(features_view.rejected, rejected)

    own_warnings = _report_warnings(fusion, rejected_map, features_view)
    warnings = list(fusion.all_warnings) + [
        StageWarning(stage=STAGE_REPORT, module=REPORT_MODULE, message=message)
        for message in own_warnings
    ]

    prioritized = prioritise(fusion.fused)
    rank_by_condition = {p.condition: p for p in prioritized}

    explainability = build_explainability(
        fusion,
        rejected_map,
        questionable=list(features_view.questionable),
        clinically_extreme=list(features_view.clinically_extreme),
    )

    conditions = [
        _reported_condition(item, rank_by_condition.get(item.condition))
        for item in sorted(
            fusion.fused,
            key=lambda f: rank_by_condition[f.condition].rank
            if f.condition in rank_by_condition
            else 0,
        )
    ]

    laboratory_values = _laboratory_values(features_view, rejected_map)
    recommendations = _recommendations(fusion.fused, own_warnings)
    document = _document_quality(fusion, features_view, rejected_map)
    summary = _summary(
        fusion, conditions, laboratory_values, recommendations, warnings,
        explainability,
    )

    report = ClinicalReport(
        report_version=REPORT_VERSION,
        patient=_patient_information(features_view),
        laboratory_values=laboratory_values,
        conditions=conditions,
        overall=overall_status(fusion),
        overall_risk=fusion.summary.overall_risk,
        critical_conditions=list(fusion.summary.critical_conditions),
        abnormal_findings=list(fusion.summary.abnormal_conditions),
        normal_findings=list(fusion.summary.normal_conditions),
        unassessed_conditions=list(fusion.summary.unassessed_conditions),
        prioritized=prioritized,
        explainability=explainability,
        recommendations=recommendations,
        document=document,
        validation_warnings=warnings,
        warnings_by_stage=_warnings_by_stage(warnings),
        summary=summary,
        metadata=_metadata(fusion, features_view.input_received),
        fusion=fusion,
    )

    # COUNTS ONLY. No feature name, no value, no report text -- see the module
    # docstring. `safe_meta` drops content-bearing keys as a second line of
    # defence, but nothing content-bearing is passed to it in the first place.
    logger.info(
        "report_generated %s",
        safe_meta(
            condition_count=summary.condition_count,
            abnormal_count=summary.abnormal_count,
            critical_count=summary.critical_count,
            unassessed_count=summary.unassessed_count,
            warning_count=summary.warning_count,
            rejected_value_count=summary.rejected_laboratory_value_count,
        ),
    )
    return report


# --------------------------------------------------------------------------
# Resolving the feature view
# --------------------------------------------------------------------------


class _FeatureView:
    """Everything about the INPUT the report needs, from any accepted shape."""

    __slots__ = (
        "valid",
        "questionable",
        "rejected",
        "clinically_extreme",
        "missing",
        "unmapped_count",
        "summary",
        "for_decisions",
        "input_received",
    )

    def __init__(self) -> None:
        self.valid: Dict[str, Any] = {}
        self.questionable: Dict[str, Any] = {}
        self.rejected: Dict[str, ReportRejectedFeature] = {}
        self.clinically_extreme: List[str] = []
        self.missing: List[str] = []
        self.unmapped_count: int = 0
        self.summary: Any = None
        self.for_decisions: Any = None
        #: What the CALLER actually sent, before Module 6 was run in-process.
        #: `fusion.summary.input_kind` reports what the DECISION CHAIN saw,
        #: which is always "validated" once this layer has validated -- so both
        #: are recorded, and neither is a guess about the other.
        self.input_received: str = "none"


def _resolve_features(validated: Any, engineered: Any) -> _FeatureView:
    """Normalise every accepted input into one view.

    When only `engineered` is supplied, Module 6 is RUN here rather than
    approximated. Its output is then what both the decision chain and the
    report read, so the laboratory values the report shows and the values the
    rules saw cannot diverge -- and the rejected map, which is the whole point
    of the Module 20 join, is the real one.
    """
    view = _FeatureView()
    if validated is not None:
        view.input_received = "validated"
    elif engineered is not None:
        view.input_received = "engineered"

    if validated is None and engineered is not None:
        from app.services.validator import validate_features

        validated = validate_features(engineered)

    view.for_decisions = validated

    if validated is None:
        return view

    data: Any = validated
    if isinstance(validated, Mapping):
        # A relayed envelope or a bare Module 6 object.
        inner = validated.get("data")
        if isinstance(inner, Mapping) and "valid" in inner:
            data = inner
        view.valid = dict(_get(data, "valid") or {})
        view.questionable = dict(_get(data, "questionable") or {})
        view.rejected = extract_rejected_features({"validated": dict(data)})
        view.clinically_extreme = list(_get(data, "clinically_extreme") or [])
        view.missing = list(_get(data, "missing_features") or [])
        view.summary = _get(data, "summary")
        view.unmapped_count = _unmapped_count(data, view.summary)
        return view

    view.valid = dict(getattr(data, "valid", {}) or {})
    view.questionable = dict(getattr(data, "questionable", {}) or {})
    raw_rejected = getattr(data, "rejected", None)
    if raw_rejected:
        view.rejected = {
            name: parsed
            for name, record in dict(raw_rejected).items()
            if (parsed := _coerce_rejected(name, record)) is not None
        }
    view.clinically_extreme = list(getattr(data, "clinically_extreme", []) or [])
    view.missing = list(getattr(data, "missing_features", []) or [])
    view.summary = getattr(data, "summary", None)
    view.unmapped_count = _unmapped_count(data, view.summary)
    return view


def _get(container: Any, key: str) -> Any:
    if isinstance(container, Mapping):
        return container.get(key)
    return getattr(container, key, None)


def _unmapped_count(data: Any, summary: Any) -> int:
    """How many extracted parameters never became a feature.

    COUNTED FROM THE PRODUCER'S OWN COUNT, NOT FROM THE LIST -- because over
    HTTP the list is not here. `ValidatedFeaturesInput` declares no `unmapped`
    field and sets `extra="ignore"`, so Module 6's seventeen unmapped rows are
    dropped silently at the boundary; `len(unmapped or [])` then returns 0 and
    the report states, as a fact, that every parameter on the document was
    assessed. Measured on `Test 2.pdf`: seventeen sent, zero recorded.

    `summary.unmapped_count` is the SAME number computed by the feature stage
    (`feature_engineer` sets it to `len(unmapped)`), and it survives the
    boundary because `summary` is a declared field. So it is preferred, and the
    list is the fallback for in-process callers whose summary is absent.

    §6u FOUND THIS ON THE PATIENT PAGE AND ROUTED AROUND IT rather than fixing
    it here: `dashboardService` reads `fusion.upstream_summary.unmapped_count`
    instead, with a comment calling the 0 "not merely missing information but a
    false statement". The clinician document was never brought along and still
    read this field. A count of nothing, where a reader will take it to mean
    nothing was set aside, is this project's fourth case -- "we did not look"
    rendered as "we looked and found nothing".
    """
    counted = _get(summary, "unmapped_count")
    if isinstance(counted, int) and not isinstance(counted, bool) and counted >= 0:
        return counted
    return len(list(_get(data, "unmapped") or []))


def _merge_rejected(
    from_input: Mapping[str, ReportRejectedFeature], explicit: Any
) -> Dict[str, ReportRejectedFeature]:
    """The input's own rejected map, plus anything relayed separately.

    The input's own entries win: they came from the object the decisions were
    actually made from.
    """
    merged: Dict[str, ReportRejectedFeature] = {}
    if isinstance(explicit, Mapping):
        for name, record in explicit.items():
            parsed = _coerce_rejected(name, record)
            if parsed is not None:
                merged[str(name)] = parsed
    merged.update(dict(from_input))
    return merged


# --------------------------------------------------------------------------
# Sections
# --------------------------------------------------------------------------


def _patient_information(view: _FeatureView) -> PatientInformation:
    """Spec Module 17's patient information -- clinical context, no identity.

    `hypertension` and `heart_disease` stay TRI-STATE: absent means UNKNOWN and
    is reported as None, never as False. That distinction has survived every
    hop from Module 4 to here and this is the last place it could be lost.
    """
    provided: List[str] = []

    def value(name: str) -> Any:
        entry = view.valid.get(name)
        if entry is None:
            return None
        provided.append(name)
        return _feature_value(entry)

    age = value("age")
    gender = value("gender")
    bmi = value("bmi")
    hypertension = value("hypertension")
    heart_disease = value("heart_disease")
    smoking = value("smoking_history")

    return PatientInformation(
        age=int(age) if isinstance(age, (int, float)) else None,
        gender=str(gender) if gender is not None else None,
        bmi=float(bmi) if isinstance(bmi, (int, float)) else None,
        hypertension=hypertension if isinstance(hypertension, bool) else None,
        heart_disease=heart_disease if isinstance(heart_disease, bool) else None,
        smoking_history=str(smoking) if smoking is not None else None,
        provided_fields=provided,
        contains_identity=False,
    )


def _feature_value(entry: Any) -> Any:
    if isinstance(entry, Mapping):
        return entry.get("value")
    return getattr(entry, "value", None)


def _laboratory_values(
    view: _FeatureView, rejected: Mapping[str, ReportRejectedFeature]
) -> List[LaboratoryValue]:
    """Spec Module 17's laboratory values -- Module 27's cards, Module 32's rows.

    A REJECTED value appears here too, marked `usable=False` with its reason.
    Hiding it would reproduce the exact defect Module 20's join exists to fix,
    one layer up: the reader would see a report with no creatinine row and
    conclude none was ordered.
    """
    out: List[LaboratoryValue] = []
    # Catalogue order, so two reports of the same panel list rows identically.
    names = [n for n in FEATURES if n in view.valid or n in rejected]
    names += [n for n in view.valid if n not in FEATURES]
    names += [n for n in rejected if n not in FEATURES and n not in view.valid]

    for name in unique(names):
        definition = FEATURES.get(name)
        record = rejected.get(name)
        entry = view.valid.get(name)

        if entry is not None:
            provenance = _provenance(entry)
            questionable = name in view.questionable
            out.append(
                LaboratoryValue(
                    feature=name,
                    display_name=definition.description if definition else None,
                    value=_feature_value(entry),
                    unit=_get(entry, "unit"),
                    value_type=definition.value_type if definition else None,
                    status="questionable" if questionable else "valid",
                    usable=True,
                    questionable=questionable,
                    clinically_extreme=name in view.clinically_extreme,
                    extreme_direction=_get(entry, "extreme_direction"),
                    source=_get(entry, "source"),
                    provenance=provenance,
                    **_provenance_fields(provenance),
                )
            )
            continue

        provenance = record.provenance if record else None
        out.append(
            LaboratoryValue(
                feature=name,
                display_name=definition.description if definition else None,
                value=record.value if record else None,
                unit=record.unit if record else None,
                value_type=definition.value_type if definition else None,
                status="rejected",
                usable=False,
                source=record.source if record else None,
                rejection_code=record.reason_code if record else None,
                rejection_reason=record.reason if record else None,
                provenance=provenance,
                **_provenance_fields(provenance),
            )
        )
    return out


def _provenance(entry: Any) -> Any:
    raw = _get(entry, "provenance")
    if raw is None or hasattr(raw, "original_test_name"):
        return raw
    try:
        from app.schemas.features import FeatureProvenance

        return FeatureProvenance.model_validate(raw)
    except Exception:  # noqa: BLE001 -- provenance is context, never load-bearing
        return None


def _provenance_fields(provenance: Any) -> Dict[str, Any]:
    if provenance is None:
        return {}
    return {
        "reference_low": provenance.reference_low,
        "reference_high": provenance.reference_high,
        "reference_range_raw": provenance.reference_range_raw,
        "flag": provenance.flag.value
        if getattr(provenance.flag, "value", None)
        else provenance.flag,
        "original_test_name": provenance.original_test_name,
        "original_unit": provenance.original_unit,
        "unit_converted": provenance.unit_converted,
        "unit_assumed": provenance.unit_assumed,
        "derived": provenance.derived,
        "censored": provenance.censored,
        "page_number": provenance.page_number,
        "extraction_confidence": provenance.confidence,
    }


def _reported_condition(
    item: FusedDecision, priority: Optional[PrioritizedFinding]
) -> ReportedCondition:
    """One Module 27 condition card.

    `basis_conflict` IS SURFACED, NOT BLENDED. When Module 16 flagged that a
    risk-factor burden is sitting beside a different kind of claim -- the
    `Heart Disease` hazard, where a composite rule counts recorded risk factors
    and Module 11 estimates a likelihood -- `contributions` carries each source
    separately with its OWN band labels, status and risk, and
    `render_contributions_separately` says so in a field. Merging them into one
    sentence would tell the reader a tally was a probability.
    """
    return ReportedCondition(
        condition=item.condition,
        status=item.status,
        risk=item.risk,
        confidence=item.confidence,
        confidence_basis=item.confidence_basis,
        priority=priority.priority if priority else PRIORITY_NOT_ASSESSED,
        rank=priority.rank if priority else 0,
        flagged=item.decision.is_flagged,
        assessed=item.decision.was_assessed,
        critical=item.decision.is_flagged and item.risk is RiskLevel.HIGH,
        normal=item.status is DecisionStatus.NOT_INDICATED,
        hybrid=item.hybrid,
        sources=list(item.sources),
        source_kinds=list(item.source_kinds),
        contributions=[
            ContributionView(
                source=c.source,
                source_kind=c.source_kind,
                status=c.status,
                risk=c.risk,
                confidence=c.confidence,
                assessed=c.status is not DecisionStatus.INSUFFICIENT_DATA,
                assessment_basis=c.assessment_basis,
                assessment_basis_family=BASIS_FAMILY.get(
                    c.assessment_basis, FAMILY_NONE
                ),
                band_labels=list(c.band_labels),
                traces=list(c.traces),
                evidence_features=list(c.evidence_features),
                recommendation_codes=list(c.recommendation_codes),
                decision_ids=list(c.decision_ids),
            )
            for c in item.contributions
        ],
        basis_conflict=item.basis_conflict,
        basis_note=item.basis_note,
        render_contributions_separately=item.basis_conflict,
        partially_assessed=item.partially_assessed,
        unassessed_sources=list(item.unassessed_sources),
        evidence_features=item.decision.evidence_features(),
        recommendation_codes=[r.code for r in item.decision.recommendations],
        decision_ids=list(item.decision_ids),
        contributing_decision_count=len(item.decision_ids),
    )


def _recommendations(
    fused: Sequence[FusedDecision], own_warnings: List[str]
) -> List[ReportRecommendation]:
    """Consolidate and de-duplicate, CATALOGUE-SOURCED BY CODE.

    Spec Module 16 point 5: "Recommendations from different decision sources
    are consolidated and duplicates are removed."

    Two properties this function guarantees that a naive union would not:

    * `text` is re-read from `app/data/recommendation_catalog.py` by CODE, not
      copied from the `Recommendation` object that carried it. So even if some
      producer somewhere constructed a recommendation with its own wording,
      that wording cannot reach a report. The catalogue is import-time scanned
      by the safety scanner, so this is what makes "no free text, no
      medication, no dosage, no diagnostic assertion, no certainty claim" a
      property of the report rather than a property of every producer.
    * a code that is NOT in the catalogue is DROPPED, with a warning. Dropping
      is the safe direction: a missing educational line is a smaller harm than
      an unreviewed one, and the warning means the drop is not silent.

    Nothing here composes, rewrites or personalises text.
    """
    seen: Dict[str, ReportRecommendation] = {}
    unknown: List[str] = []

    for item in fused:
        for rec in item.decision.recommendations:
            entry = RECOMMENDATIONS.get(rec.code)
            if entry is None:
                if rec.code not in unknown:
                    unknown.append(rec.code)
                continue
            existing = seen.get(rec.code)
            if existing is None:
                seen[rec.code] = ReportRecommendation(
                    code=entry.code,
                    text=entry.text,
                    category=entry.category,
                    conditions=[item.condition],
                    occurrences=1,
                )
            else:
                existing.occurrences += 1
                if item.condition not in existing.conditions:
                    existing.conditions.append(item.condition)

    if unknown:
        own_warnings.append(
            "one or more recommendation codes were not in the approved "
            "catalogue and were left out of this report"
        )

    def sort_key(rec: ReportRecommendation) -> Tuple[int, str]:
        category = rec.category or ""
        rank = (
            _CATEGORY_ORDER.index(category)
            if category in _CATEGORY_ORDER
            else len(_CATEGORY_ORDER)
        )
        return (rank, rec.code)

    return sorted(seen.values(), key=sort_key)


def _document_quality(
    fusion: DecisionFusionData,
    view: _FeatureView,
    rejected: Mapping[str, ReportRejectedFeature],
) -> DocumentQuality:
    """Carry `pages_unreadable` and `extraction_confidence` into the report.

    A report built from a partially unreadable scan MUST say so. Module 4
    records which pages could not be read and how confident the extraction was;
    Modules 5, 6, 15 and 16 each carried it forward without editing it; this is
    the last hop and it does not drop it either.
    """
    upstream = fusion.upstream
    summary = fusion.upstream_summary
    return DocumentQuality(
        extraction_provided=upstream.provided,
        extraction_confidence=upstream.extraction_confidence,
        page_count=len(upstream.pages),
        pages_unreadable=list(upstream.pages_unreadable),
        pages_unreadable_count=len(upstream.pages_unreadable),
        partial_document=bool(upstream.pages_unreadable),
        features_received=getattr(summary, "features_received", 0) or 0,
        valid_count=len(view.valid),
        questionable_count=len(view.questionable),
        rejected_count=len(rejected),
        rejected_features=list(rejected),
        missing_features=list(view.missing),
        unmapped_count=view.unmapped_count,
        upstream=upstream,
    )


def _report_warnings(
    fusion: DecisionFusionData,
    rejected: Mapping[str, ReportRejectedFeature],
    view: _FeatureView,
) -> List[str]:
    """Module 17's OWN warnings.

    Each exists because the report would otherwise present something as more
    settled than it is.
    """
    warnings: List[str] = []
    summary = fusion.summary

    if not summary.any_assessed:
        warnings.append(
            "nothing in this report could be assessed, so no overall health "
            "status is given and no absence of findings should be read as a "
            "sign of good health"
        )
    elif summary.assessment_incomplete:
        warnings.append(
            "this overall status rests only on the topics that could be "
            "assessed, and at least one topic could not be"
        )

    if rejected:
        warnings.append(
            f"{len(rejected)} value(s) present in the submitted report could "
            "not be relied on and were excluded from every decision; each one "
            "is listed with the reason rather than reported as missing"
        )

    if fusion.upstream.pages_unreadable:
        warnings.append(
            f"{len(fusion.upstream.pages_unreadable)} page(s) of the submitted "
            "document could not be read, so a value absent from this report "
            "may be unread rather than absent from the original"
        )

    return warnings


def _warnings_by_stage(warnings: Sequence[StageWarning]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for warning in warnings:
        counts[warning.stage] = counts.get(warning.stage, 0) + 1
    return counts


def _summary(
    fusion: DecisionFusionData,
    conditions: Sequence[ReportedCondition],
    laboratory_values: Sequence[LaboratoryValue],
    recommendations: Sequence[ReportRecommendation],
    warnings: Sequence[StageWarning],
    explainability: ExplainabilitySection,
) -> ReportSummary:
    return ReportSummary(
        condition_count=len(conditions),
        abnormal_count=sum(1 for c in conditions if c.flagged),
        critical_count=sum(1 for c in conditions if c.critical),
        normal_count=sum(1 for c in conditions if c.normal),
        unassessed_count=sum(1 for c in conditions if not c.assessed),
        hybrid_count=sum(1 for c in conditions if c.hybrid),
        laboratory_value_count=len(laboratory_values),
        usable_laboratory_value_count=sum(1 for v in laboratory_values if v.usable),
        rejected_laboratory_value_count=sum(
            1 for v in laboratory_values if not v.usable
        ),
        recommendation_count=len(recommendations),
        warning_count=len(warnings),
        evidence_line_count=sum(len(c.evidence) for c in explainability.conditions),
        sources_used=list(fusion.summary.sources_used),
        sources_failed=list(fusion.summary.sources_failed),
        basis_conflict_conditions=list(fusion.summary.basis_conflict_conditions),
        input_kind=fusion.summary.input_kind,
    )


def _metadata(fusion: DecisionFusionData, input_received: str) -> Dict[str, Any]:
    """System metadata (spec Module 17). Versions and policies. Never PHI.

    `input_received` is what the CALLER sent; `upstream.input_kind` is what the
    DECISION CHAIN saw. They differ by design when Module 5 output is posted:
    this layer runs Module 6 in-process first, so the rules and the models
    consume validated features and the report's laboratory values and rejected
    map are the real ones rather than an approximation. Recording both means
    neither has to be inferred from the other.
    """
    return {
        "report_version": REPORT_VERSION,
        "input_received": input_received,
        "modules": {
            "clinical_report": 17,
            "overall_health_status": 18,
            "risk_prioritization": 19,
            "evidence_and_explainability": 20,
        },
        "policy": REPORT_POLICY,
        "overall_status_policy": OVERALL_STATUS_POLICY,
        "prioritization_policy": PRIORITIZATION_POLICY,
        "explainability_policy": EXPLAINABILITY_POLICY,
        "recommendation_sourcing": (
            "consolidated by catalogue code and de-duplicated; the text is "
            "re-read from the approved catalogue rather than copied from the "
            "decision that carried it"
        ),
        "prioritised_by": ["condition"],
        "upstream": dict(fusion.metadata),
        "not_a_diagnostic_system": True,
    }


# ==========================================================================
# Safety inspection -- used by the test suite and available to Module 24
# ==========================================================================


def report_text_violations(report: ClinicalReport) -> List[Tuple[str, str, List[str]]]:
    """Scan every user-facing string in a report with the safety scanner.

    Returns `(where, text, patterns)` for each violation; an empty list means
    the report asserts no diagnosis, prescribes no medication, states no dosage
    and claims no certainty.

    This is an INSPECTION, not a filter. The report's safety is structural --
    recommendation text comes from the reviewed catalogue by code, band labels
    are import-time scanned by Module 8, and every fixed string in
    `app/schemas/report.py` is scanned at import. This function is how a test,
    a reviewer or Module 24 can verify that the structure actually held instead
    of trusting that it did.
    """
    from app.data.recommendation_catalog import scan_text

    out: List[Tuple[str, str, List[str]]] = []

    def check(where: str, text: Any) -> None:
        if not isinstance(text, str) or not text:
            return
        hits = scan_text(text)
        if hits:
            out.append((where, text, hits))

    check("overall.caveat", report.overall.caveat)
    check("overall.policy", report.overall.policy)
    for index, rec in enumerate(report.recommendations):
        check(f"recommendations[{index}].text", rec.text)
    for condition in report.conditions:
        check(f"conditions[{condition.condition}].basis_note", condition.basis_note)
        for contribution in condition.contributions:
            for label in contribution.band_labels:
                check(f"conditions[{condition.condition}].band_label", label)
    for explanation in report.explainability.conditions:
        check(f"explainability[{explanation.condition}].note", explanation.basis_note)
        check(
            f"explainability[{explanation.condition}].fusion",
            explanation.fusion_explanation,
        )
        for source in explanation.sources:
            if source.ml is not None:
                check("ml.importance_caveat", source.ml.importance_caveat)
                check("ml.probability_semantics", source.ml.probability_semantics)
                check("ml.band_meaning", source.ml.band_meaning)
                check("ml.skip_explanation", source.ml.skip_explanation)
            if source.rule is not None:
                for label in source.rule.classifications:
                    check("rule.classification", label)
            for line in source.evidence:
                check("evidence.explanation", line.explanation)
                check("evidence.note", line.note)
                check("evidence.rejection_reason", line.rejection_reason)
        for line in explanation.evidence:
            check("evidence.explanation", line.explanation)
            check("evidence.note", line.note)
            check("evidence.rejection_reason", line.rejection_reason)
    for index, value in enumerate(report.laboratory_values):
        # EVERY caller-controlled string on a laboratory value, not just the
        # rejection reason (integration audit D5). `unit`, `original_unit`,
        # `original_test_name` and `feature` all originate in the submitted
        # document or in a caller-posted payload, all four are rendered, and
        # none of them was walked before.
        check(f"laboratory_values[{index}].reason", value.rejection_reason)
        check(f"laboratory_values[{index}].feature", value.feature)
        check(f"laboratory_values[{index}].unit", value.unit)
        check(
            f"laboratory_values[{index}].original_test_name",
            value.original_test_name,
        )
        check(f"laboratory_values[{index}].original_unit", value.original_unit)
    for warning in report.validation_warnings:
        check(f"validation_warnings[{warning.stage}]", warning.message)
    return out


__all__ = [
    "REPORT_POLICY",
    "REPORT_VERSION",
    "build_explainability",
    "extract_rejected_features",
    "generate_report",
    "overall_status",
    "prioritise",
    "report_text_violations",
]
