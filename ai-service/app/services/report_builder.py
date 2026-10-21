from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from app.core.logging import get_logger, safe_meta
from app.data import conditions as C
from app.data.egfr import EGFR_DISPLAY_NAME, EGFR_FEATURE
from app.data.feature_catalog import FEATURES

_CALCULATED_DISPLAY_NAMES = {EGFR_FEATURE: EGFR_DISPLAY_NAME}
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
    CAVEAT_NO_LAB_RESULT_ASSESSED,
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
    RULE_NO_LAB_RESULT_ASSESSED,
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
from app.services.fusion_engine import rests_on_lab_result, run_decision_fusion
from app.services.rule_engine import NOTE_FACTOR_NOT_MET

logger = get_logger(__name__)

REPORT_VERSION = "1.0.0"

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

_ABSENCE_NOTES = (
    "this value was not available in the submitted report",
    "part of the document could not be read, so this value may be missing "
    "rather than absent from the report",
    "the model needs this value and it was not available, so no prediction "
    "was made",
)


def overall_status(fusion: DecisionFusionData) -> OverallHealthStatus:
    summary = fusion.summary

    assessed = [f for f in fusion.fused if f.decision.was_assessed]
    flagged = [f for f in fusion.fused if f.decision.is_flagged]
    high = [f for f in flagged if f.risk is RiskLevel.HIGH]
    clean_without_lab = (
        bool(assessed)
        and not flagged
        and not any(rests_on_lab_result(f.decision) for f in assessed)
    )
    any_assessed = bool(assessed) and not clean_without_lab

    if clean_without_lab:
        rule = RULE_NO_LAB_RESULT_ASSESSED
        label = STATUS_NOT_ASSESSED
        status: Optional[str] = None
    elif not any_assessed:
        rule = RULE_NOTHING_ASSESSED
        label = STATUS_NOT_ASSESSED
        status = None
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

    if summary.overall_status != status:
        raise ValueError(
            "Module 17's overall status disagrees with Module 16's "
            f"summary.overall_status ({summary.overall_status!r} vs "
            f"{status!r}). One of the two layers has changed its rule."
        )

    complete = any_assessed and not summary.assessment_incomplete

    if status == STATUS_HEALTHY and not complete:
        label = STATUS_HEALTHY_PARTIAL

    if clean_without_lab:
        caveat: Optional[str] = CAVEAT_NO_LAB_RESULT_ASSESSED
    elif not any_assessed:
        caveat = CAVEAT_NOTHING_ASSESSED
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


def prioritise(fused: Sequence[FusedDecision]) -> List[PrioritizedFinding]:
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


def extract_rejected_features(body: Any) -> Dict[str, ReportRejectedFeature]:
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
    except Exception:
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
    if not item.sources:
        return None
    return " + ".join(item.sources)


def _explain_source(
    item: FusedDecision,
    contribution: Any,
    fusion: DecisionFusionData,
    line: Any,
) -> SourceExplanation:
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
    out: List[EvidenceLine] = []
    for decision in raw:
        classification = decision.metadata.get("band_label")
        for item in decision.evidence:
            if item.threshold is None:
                continue
            if isinstance(item.note, str) and item.note.startswith(NOTE_FACTOR_NOT_MET):
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
    metadata: Dict[str, Any] = {}
    for decision in raw:
        metadata.update(decision.metadata)

    skipped = contribution.status is DecisionStatus.INSUFFICIENT_DATA

    sufficiency = metadata.get("sufficiency")
    if not isinstance(sufficiency, Mapping):
        sufficiency = {}
    skip_reason = metadata.get("skipped_reason") or sufficiency.get("reason")

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
    wanted = list(decision_ids)
    by_id = {c.decision_id: c.decision for c in fusion.collection.collected}
    return [by_id[i] for i in wanted if i in by_id]


def _evidence_line(
    item: EvidenceItem,
    *,
    rejected: Mapping[str, ReportRejectedFeature],
    questionable: set,
    clinically_extreme: set,
    warnings_by_feature: Mapping[str, List[StageWarning]],
    classification: Optional[str] = None,
) -> EvidenceLine:
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
        display_name=(
            definition.description
            if definition
            else _CALCULATED_DISPLAY_NAMES.get(feature)
        ),
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


def generate_report(
    validated: Any = None,
    *,
    engineered: Any = None,
    rejected: Any = None,
    fusion: Optional[DecisionFusionData] = None,
    registry: Any = None,
) -> ClinicalReport:
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


class _FeatureView:

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
        self.input_received: str = "none"


def _resolve_features(validated: Any, engineered: Any) -> _FeatureView:
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
    counted = _get(summary, "unmapped_count")
    if isinstance(counted, int) and not isinstance(counted, bool) and counted >= 0:
        return counted
    return len(list(_get(data, "unmapped") or []))


def _merge_rejected(
    from_input: Mapping[str, ReportRejectedFeature], explicit: Any
) -> Dict[str, ReportRejectedFeature]:
    merged: Dict[str, ReportRejectedFeature] = {}
    if isinstance(explicit, Mapping):
        for name, record in explicit.items():
            parsed = _coerce_rejected(name, record)
            if parsed is not None:
                merged[str(name)] = parsed
    merged.update(dict(from_input))
    return merged


def _patient_information(view: _FeatureView) -> PatientInformation:
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
    out: List[LaboratoryValue] = []
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
    except Exception:
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


def report_text_violations(report: ClinicalReport) -> List[Tuple[str, str, List[str]]]:
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
