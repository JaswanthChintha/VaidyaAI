from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.data import conditions as C
from app.data.feature_catalog import FEATURES, SOURCE_LAB_REPORT
from app.schemas.decisions import (
    ClinicalDecision,
    DecisionSourceKind,
    DecisionStatus,
    RiskLevel,
)
from app.schemas.features import StageWarning
from app.schemas.fusion import (
    BASIS_CONFLICT_NOTE,
    BASIS_FAMILY,
    BASIS_NOT_ASSESSED,
    CONFLICTING_FAMILY,
    FUSION_MODULE,
    STAGE_FUSION,
    STATUS_HEALTHY,
    STATUS_NEEDS_MEDICAL_ATTENTION,
    STATUS_NEEDS_MONITORING,
    CollectedDecision,
    DecisionCollectionData,
    DecisionContribution,
    DecisionFusionData,
    DecisionGroup,
    FusedDecision,
    FusionSummary,
    PrioritizedCondition,
)
from app.services.decision_engine import (
    CONFIDENCE_RULE,
    STATUS_FUSION_RULE,
    collect_decisions,
    collection_from_decisions,
    merge_decision_set,
    merge_stage_warnings,
    unique,
)

FUSION_ENGINE_VERSION = "1.0.0"

FUSION_POLICY = (
    "Decisions about the same condition are fused into one. The highest "
    "applicable risk is retained, the strongest available probability is used "
    "(a component that produces no probability is absent from that maximum and "
    "is never read as zero), evidence and recommendations are unioned without "
    "duplicates, and the contributing sources are reported de-duplicated. A "
    "fused decision is only ever built from decisions that were actually "
    "produced: no condition is invented, no recommendation is composed, and a "
    "source that could not assess is recorded rather than hidden."
)

_RISK_PRIORITY: Dict[Optional[RiskLevel], int] = {
    RiskLevel.HIGH: 0,
    RiskLevel.MEDIUM: 1,
    RiskLevel.LOW: 2,
    None: 3,
}


def _fuse_one(condition: str, groups: Sequence[DecisionGroup]) -> FusedDecision:
    ordered = list(groups)
    per_source = [g.decision for g in ordered]
    merged = merge_decision_set(per_source)

    assessed_groups = [g for g in ordered if g.assessed]
    unassessed_groups = [g for g in ordered if not g.assessed]

    sources = unique(g.source for g in ordered)
    source_kinds = unique(g.source_kind for g in ordered)
    hybrid = len({g.source_kind for g in assessed_groups}) > 1

    bases = unique(
        g.assessment_basis
        for g in assessed_groups
        if g.assessment_basis != BASIS_NOT_ASSESSED
    )
    families = {BASIS_FAMILY.get(b, b) for b in bases}
    basis_conflict = CONFLICTING_FAMILY in families and len(families) > 1

    contributions = [
        DecisionContribution(
            source=g.source,
            source_kind=g.source_kind,
            status=g.decision.status,
            risk=g.decision.risk,
            confidence=g.decision.confidence,
            assessment_basis=g.assessment_basis,
            decision_ids=list(g.decision_ids),
            traces=list(g.traces),
            band_labels=list(g.band_labels),
            evidence_features=g.decision.evidence_features(),
            recommendation_codes=[r.code for r in g.decision.recommendations],
        )
        for g in ordered
    ]

    decision_ids = [i for g in ordered for i in g.decision_ids]

    metadata: Dict[str, Any] = {
        "fusion_engine_version": FUSION_ENGINE_VERSION,
        "policy": FUSION_POLICY,
        "condition": condition,
        "fused": True,
        "sources": sources,
        "source_kinds": [k.value for k in source_kinds],
        "hybrid": hybrid,
        "contributing_decision_ids": decision_ids,
        "source_status": {g.source: g.decision.status.value for g in ordered},
        "source_risk": {
            g.source: (g.decision.risk.value if g.decision.risk else None)
            for g in ordered
        },
        "source_confidence": {g.source: g.decision.confidence for g in ordered},
        "source_basis": {g.source: g.assessment_basis for g in ordered},
        "source_traces": {g.source: list(g.traces) for g in ordered},
        "source_band_labels": {g.source: list(g.band_labels) for g in ordered},
        "assessed_sources": [g.source for g in assessed_groups],
        "unassessed_sources": [g.source for g in unassessed_groups],
        "partially_assessed": bool(assessed_groups) and bool(unassessed_groups),
        "status_rule": STATUS_FUSION_RULE,
        "risk_rule": "highest applicable risk is retained (Low < Medium < High)",
        "confidence_rule": CONFIDENCE_RULE,
        "confidence_basis": merged.confidence_basis,
        "confidence_semantics": (
            "maximum probability of the positive class across the contributing "
            "models; None when no contributor produced a probability"
        ),
        "evidence_scope": (
            "evidence of the sources that assessed the condition; when no "
            "source could assess, the evidence of what was missing"
        ),
        "assessment_bases": bases,
        "basis_conflict": basis_conflict,
    }
    if basis_conflict:
        metadata["basis_note"] = BASIS_CONFLICT_NOTE

    fused_decision = ClinicalDecision(
        condition=condition,
        status=merged.status,
        risk=merged.risk,
        confidence=merged.confidence,
        source=" + ".join(sources) if sources else "Fusion Engine",
        source_kind=DecisionSourceKind.FUSION,
        evidence=merged.evidence,
        recommendations=merged.recommendations,
        metadata=metadata,
    )

    return FusedDecision(
        condition=condition,
        decision=fused_decision,
        status=fused_decision.status,
        risk=fused_decision.risk,
        confidence=fused_decision.confidence,
        sources=sources,
        source_kinds=source_kinds,
        hybrid=hybrid,
        contributions=contributions,
        decision_ids=decision_ids,
        assessed_source_count=len(assessed_groups),
        unassessed_sources=[g.source for g in unassessed_groups],
        partially_assessed=bool(assessed_groups) and bool(unassessed_groups),
        confidence_basis=merged.confidence_basis,
        assessment_bases=bases,
        basis_conflict=basis_conflict,
        basis_note=BASIS_CONFLICT_NOTE if basis_conflict else None,
        evidence_count=len(fused_decision.evidence),
        recommendation_count=len(fused_decision.recommendations),
    )


def fuse_decisions(collection: Any) -> DecisionFusionData:
    collection = _as_collection(collection)

    by_condition: Dict[str, List[DecisionGroup]] = {}
    for group in collection.groups:
        by_condition.setdefault(group.condition, []).append(group)

    fused = [
        _fuse_one(condition, by_condition[condition])
        for condition in sorted(by_condition, key=C.condition_rank)
    ]

    own_warnings = _fusion_warnings(fused, collection)

    upstream_warnings = merge_stage_warnings(collection.all_warnings)
    all_warnings = list(upstream_warnings) + [
        StageWarning(stage=STAGE_FUSION, module=FUSION_MODULE, message=message)
        for message in own_warnings
    ]

    return DecisionFusionData(
        fused=fused,
        collection=collection,
        warnings=own_warnings,
        upstream_warnings=upstream_warnings,
        all_warnings=all_warnings,
        upstream=collection.upstream,
        upstream_summary=collection.upstream_summary,
        summary=_summarise(fused, collection),
        metadata={
            "fusion_engine_version": FUSION_ENGINE_VERSION,
            "decision_engine_version": collection.metadata.get("engine_version"),
            "policy": FUSION_POLICY,
            "status_rule": STATUS_FUSION_RULE,
            "confidence_rule": CONFIDENCE_RULE,
            "grouped_by": ["condition", "source"],
            "fused_by": ["condition"],
            "input_kind": collection.summary.input_kind,
        },
    )


def run_decision_fusion(
    validated: Any = None,
    *,
    engineered: Any = None,
    registry: Any = None,
) -> DecisionFusionData:
    return fuse_decisions(
        collect_decisions(validated, engineered=engineered, registry=registry)
    )


def _as_collection(value: Any) -> DecisionCollectionData:
    if isinstance(value, DecisionCollectionData):
        return value
    if isinstance(value, ClinicalDecision):
        value = [value]
    if isinstance(value, (list, tuple)):
        return collection_from_decisions(list(value))
    raise TypeError(
        "fuse_decisions() takes Module 15's DecisionCollectionData or a "
        f"sequence of ClinicalDecision, not {type(value).__name__}"
    )


def _fusion_warnings(
    fused: Sequence[FusedDecision], collection: DecisionCollectionData
) -> List[str]:
    warnings: List[str] = []
    for item in fused:
        if item.partially_assessed:
            warnings.append(
                f"{item.condition} was assessed by "
                f"{_join(sorted(set(item.sources) - set(item.unassessed_sources)))} "
                f"but {_join(sorted(item.unassessed_sources))} could not assess "
                "it, so this result rests on fewer analyses than usual"
            )
    for item in fused:
        if item.basis_conflict:
            warnings.append(f"{item.condition}: {BASIS_CONFLICT_NOTE}")
    if not fused and not collection.summary.sources_failed:
        warnings.append(
            "no clinical decision was available to fuse, so no condition is "
            "reported for this analysis"
        )
    return warnings


def _join(names: Sequence[str]) -> str:
    names = list(names)
    if not names:
        return "no source"
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " and " + names[-1]


def rests_on_lab_result(decision: Any) -> bool:
    for item in getattr(decision, "evidence", None) or []:
        definition = FEATURES.get(getattr(item, "feature", None))
        if (
            definition is not None
            and definition.source == SOURCE_LAB_REPORT
            and getattr(item, "value", None) is not None
            and getattr(item, "source_stage", None) != "not_available"
        ):
            return True
    return False


def _summarise(
    fused: Sequence[FusedDecision], collection: DecisionCollectionData
) -> FusionSummary:
    flagged = [f for f in fused if f.decision.is_flagged]
    assessed = [f for f in fused if f.decision.was_assessed]
    unassessed = [f for f in fused if not f.decision.was_assessed]
    lab_backed = any(rests_on_lab_result(f.decision) for f in assessed)
    clean_without_lab = bool(assessed) and not flagged and not lab_backed

    overall_risk = (
        None
        if clean_without_lab
        else RiskLevel.highest([f.risk for f in fused if f.risk is not None])
    )

    if not assessed or clean_without_lab:
        overall_status: Optional[str] = None
    elif not flagged:
        overall_status = STATUS_HEALTHY
    elif any(f.risk is RiskLevel.HIGH for f in flagged):
        overall_status = STATUS_NEEDS_MEDICAL_ATTENTION
    else:
        overall_status = STATUS_NEEDS_MONITORING

    prioritized = [
        PrioritizedCondition(
            condition=f.condition,
            status=f.status,
            risk=f.risk,
            flagged=f.decision.is_flagged,
            hybrid=f.hybrid,
            sources=list(f.sources),
        )
        for f in sorted(
            fused,
            key=lambda f: (
                0 if f.decision.is_flagged else 1,
                _RISK_PRIORITY.get(f.risk, 3),
                C.condition_rank(f.condition),
            ),
        )
    ]

    raw_count = len(collection.collected)

    return FusionSummary(
        fused_count=len(fused),
        condition_count=len({f.condition for f in fused}),
        hybrid_condition_count=sum(1 for f in fused if f.hybrid),
        raw_decision_count=raw_count,
        collapsed_decision_count=max(raw_count - len(fused), 0),
        overall_status=overall_status,
        overall_risk=overall_risk,
        any_assessed=bool(assessed) and not clean_without_lab,
        assessment_incomplete=bool(unassessed)
        or bool(collection.summary.sources_failed)
        or any(f.partially_assessed for f in fused),
        critical_conditions=[
            f.condition
            for f in fused
            if f.decision.is_flagged and f.risk is RiskLevel.HIGH
        ],
        abnormal_conditions=[f.condition for f in flagged],
        normal_conditions=[
            f.condition for f in fused if f.status is DecisionStatus.NOT_INDICATED
        ],
        unassessed_conditions=[f.condition for f in unassessed],
        prioritized=prioritized,
        sources_used=unique(s for f in fused for s in f.sources),
        sources_failed=list(collection.summary.sources_failed),
        basis_conflict_conditions=[f.condition for f in fused if f.basis_conflict],
        partially_assessed_conditions=[
            f.condition for f in fused if f.partially_assessed
        ],
        partial_document=collection.summary.partial_document,
        input_kind=collection.summary.input_kind,
    )


__all__ = [
    "FUSION_ENGINE_VERSION",
    "FUSION_POLICY",
    "fuse_decisions",
    "run_decision_fusion",
]
