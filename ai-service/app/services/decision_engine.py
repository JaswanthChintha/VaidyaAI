from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from app.core.logging import get_logger, safe_meta
from app.data import conditions as C
from app.data.clinical_rules import RULE_ENGINE_SOURCE
from app.ml.engine import predict_all
from app.schemas.decisions import (
    ClinicalDecision,
    DecisionSourceKind,
    DecisionStatus,
    EvidenceItem,
    Recommendation,
    RiskLevel,
)
from app.schemas.features import StageWarning
from app.schemas.fusion import (
    BASIS_MODEL_PROBABILITY,
    BASIS_NOT_ASSESSED,
    BASIS_RISK_FACTOR_COUNT,
    BASIS_THRESHOLD,
    DECISIONS_MODULE,
    STAGE_DECISIONS,
    CollectedDecision,
    DecisionCollectionData,
    DecisionCollectionSummary,
    DecisionGroup,
    SourceRunSummary,
)
from app.schemas.ml import ML_MODULE
from app.schemas.rules import RULES_MODULE
from app.services.rule_engine import evaluate_rules

logger = get_logger(__name__)

DECISION_ENGINE_VERSION = "1.0.0"

ORIGIN_RULES = "rules"
ORIGIN_ML = "ml"

RULES_SOURCE_NAME = RULE_ENGINE_SOURCE
ML_SOURCE_NAME = "ML Prediction Engine"

DECISION_ENGINE_POLICY = (
    "Every registered decision source is called independently and a source "
    "that raises is contained rather than propagated, so one failure cannot "
    "discard another source's decisions. Every decision keeps its raw form and "
    "gains a deterministic id. Decisions are then grouped by (condition, "
    "source) so that fusion sees one entry per source even when several of one "
    "source's rules fired on the same condition. No upstream warning is "
    "edited, filtered or dropped."
)

STATUS_FUSION_RULE = (
    "A merged decision is INSUFFICIENT_DATA only when NO contributing decision "
    "actually assessed the condition; risk is then None. Otherwise the status "
    "is the most severe status among the decisions that DID assess "
    "(Not Indicated < Borderline < Indicated) and the risk is the highest "
    "applicable risk among them. A contributor that could not assess never "
    "downgrades the result to 'insufficient data' and is never silently "
    "discarded: it is recorded in unassessed_sources and raises a warning."
)

_STATUS_SEVERITY: Dict[DecisionStatus, int] = {
    DecisionStatus.NOT_INDICATED: 0,
    DecisionStatus.BORDERLINE: 1,
    DecisionStatus.INDICATED: 2,
}

_SOURCE_KIND_RANK: Dict[DecisionSourceKind, int] = {
    DecisionSourceKind.CLINICAL_RULE: 0,
    DecisionSourceKind.MACHINE_LEARNING: 1,
    DecisionSourceKind.FUSION: 2,
}

_ORIGIN_RANK: Dict[str, int] = {ORIGIN_RULES: 0, ORIGIN_ML: 1}


class MergedFields:

    __slots__ = (
        "status",
        "risk",
        "confidence",
        "confidence_basis",
        "evidence",
        "recommendations",
        "assessed",
        "unassessed",
    )

    def __init__(
        self,
        status: DecisionStatus,
        risk: Optional[RiskLevel],
        confidence: Optional[float],
        confidence_basis: str,
        evidence: List[EvidenceItem],
        recommendations: List[Recommendation],
        assessed: List[ClinicalDecision],
        unassessed: List[ClinicalDecision],
    ) -> None:
        self.status = status
        self.risk = risk
        self.confidence = confidence
        self.confidence_basis = confidence_basis
        self.evidence = evidence
        self.recommendations = recommendations
        self.assessed = assessed
        self.unassessed = unassessed


CONFIDENCE_NONE_PRODUCED = "none_produced"
CONFIDENCE_MAX_PROBABILITY = "max_of_model_probabilities"

CONFIDENCE_RULE = (
    "'The strongest available confidence' is the MAXIMUM over the contributing "
    "decisions that actually produced a probability. A decision whose "
    "confidence is None produces no probability at all (a deterministic rule) "
    "and is therefore ABSENT from the maximum -- it is never read as 0.0, and "
    "it never suppresses a real probability from another source. A decision "
    "whose confidence is 0.0 DID produce a probability and does take part, so "
    "a fused confidence of 0.0 is a real, confident negative and is distinct "
    "from None. When no contributor produced a probability the fused "
    "confidence is None, never 0.0."
)


def merge_decision_set(decisions: Sequence[ClinicalDecision]) -> MergedFields:
    assessed = [d for d in decisions if d.was_assessed]
    unassessed = [d for d in decisions if not d.was_assessed]

    if assessed:
        risk = RiskLevel.highest([d.risk for d in assessed if d.risk is not None])
        if risk is None:
            status = DecisionStatus.INSUFFICIENT_DATA
        else:
            status = max(
                assessed, key=lambda d: _STATUS_SEVERITY[d.status]
            ).status
    else:
        risk = None
        status = DecisionStatus.INSUFFICIENT_DATA

    probabilities = [d.confidence for d in decisions if d.confidence is not None]
    if probabilities and status is not DecisionStatus.INSUFFICIENT_DATA:
        confidence: Optional[float] = max(probabilities)
        confidence_basis = CONFIDENCE_MAX_PROBABILITY
    else:
        confidence = None
        confidence_basis = CONFIDENCE_NONE_PRODUCED

    evidence_sources = assessed if assessed else list(decisions)
    evidence = _dedup(
        (item for d in evidence_sources for item in d.evidence),
        lambda item: item.dedup_key(),
    )
    recommendations = _dedup(
        (rec for d in decisions for rec in d.recommendations),
        lambda rec: rec.dedup_key(),
    )

    return MergedFields(
        status=status,
        risk=risk,
        confidence=confidence,
        confidence_basis=confidence_basis,
        evidence=evidence,
        recommendations=recommendations,
        assessed=assessed,
        unassessed=unassessed,
    )


def _dedup(items: Iterable[Any], key) -> List[Any]:
    seen: Dict[Any, None] = {}
    out: List[Any] = []
    for item in items:
        k = key(item)
        if k in seen:
            continue
        seen[k] = None
        out.append(item)
    return out


def unique(values: Iterable[Any]) -> List[Any]:
    return _dedup(values, lambda v: v)


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(value: Optional[str]) -> str:
    text = _SLUG_RE.sub("-", (value or "").strip().lower()).strip("-")
    return text or "unknown"


def decision_trace(decision: ClinicalDecision, origin: str) -> Optional[str]:
    meta = decision.metadata or {}
    if origin == ORIGIN_RULES:
        value = meta.get("rule_id")
    else:
        value = meta.get("predictor") or meta.get("model_name")
    if value is None:
        value = decision.source
    return str(value) if value is not None else None


def decision_band_label(decision: ClinicalDecision, origin: str) -> Optional[str]:
    meta = decision.metadata or {}
    if origin == ORIGIN_RULES:
        label = meta.get("band_label")
    else:
        label = meta.get("band_meaning") or meta.get("risk_band")
    if label is None:
        return None
    text = str(label).strip()
    return text or None


def assessment_basis(decision: ClinicalDecision, origin: str) -> str:
    if not decision.was_assessed:
        return BASIS_NOT_ASSESSED
    meta = decision.metadata or {}
    declared = meta.get("assessment_basis")
    if isinstance(declared, str) and declared.strip():
        return declared.strip()
    if origin == ORIGIN_RULES:
        if "factors_counted" in meta or "factor_count" in meta:
            return BASIS_RISK_FACTOR_COUNT
        return BASIS_THRESHOLD
    return BASIS_MODEL_PROBABILITY


def _assign_ids(records: List[Tuple[str, ClinicalDecision]]) -> List[str]:
    used: Dict[str, int] = {}
    ids: List[str] = []
    for origin, decision in records:
        base = (
            f"{origin}:{_slug(decision.condition)}:"
            f"{_slug(decision_trace(decision, origin))}"
        )
        count = used.get(base, 0) + 1
        used[base] = count
        ids.append(base if count == 1 else f"{base}#{count}")
    return ids


def merge_stage_warnings(*groups: Iterable[StageWarning]) -> List[StageWarning]:
    return _dedup(
        (w for group in groups for w in group),
        lambda w: (w.stage, w.module, w.message),
    )


def _stage_warnings(messages: Iterable[str]) -> List[StageWarning]:
    return [
        StageWarning(stage=STAGE_DECISIONS, module=DECISIONS_MODULE, message=m)
        for m in messages
    ]


class _SourceResult:
    __slots__ = ("data", "summary")

    def __init__(self, data: Any, summary: SourceRunSummary) -> None:
        self.data = data
        self.summary = summary


def _run_source(
    name: str,
    module: int,
    kind: DecisionSourceKind,
    call,
    warnings: List[str],
    failure_message: str,
) -> _SourceResult:
    try:
        data = call()
    except Exception as exc:
        logger.error(
            "decision_source_failed %s",
            safe_meta(source=name, error_type=type(exc).__name__),
        )
        warnings.append(failure_message)
        return _SourceResult(
            None,
            SourceRunSummary(
                name=name,
                module=module,
                kind=kind,
                ran=False,
                failed=True,
                error_type=type(exc).__name__,
                decision_count=0,
            ),
        )
    decisions = list(getattr(data, "decisions", ()) or ())
    return _SourceResult(
        data,
        SourceRunSummary(
            name=name,
            module=module,
            kind=kind,
            ran=True,
            failed=False,
            decision_count=len(decisions),
        ),
    )


def collect_decisions(
    validated: Any = None,
    *,
    engineered: Any = None,
    registry: Any = None,
) -> DecisionCollectionData:
    own_warnings: List[str] = []

    rules_result = _run_source(
        RULES_SOURCE_NAME,
        RULES_MODULE,
        DecisionSourceKind.CLINICAL_RULE,
        lambda: evaluate_rules(validated, engineered=engineered),
        own_warnings,
        "the clinical rule engine could not complete, so no rule-based "
        "decision is included in this analysis",
    )
    ml_result = _run_source(
        ML_SOURCE_NAME,
        ML_MODULE,
        DecisionSourceKind.MACHINE_LEARNING,
        lambda: predict_all(validated, engineered=engineered, registry=registry),
        own_warnings,
        "the machine-learning prediction layer could not complete, so no "
        "model-based decision is included in this analysis",
    )

    rules_data = rules_result.data
    ml_data = ml_result.data
    sources = [rules_result.summary, ml_result.summary]

    records: List[Tuple[str, ClinicalDecision]] = []
    for origin, data in ((ORIGIN_RULES, rules_data), (ORIGIN_ML, ml_data)):
        for decision in list(getattr(data, "decisions", ()) or ()):
            records.append((origin, decision))

    order = sorted(
        range(len(records)),
        key=lambda i: (
            C.condition_rank(records[i][1].condition),
            _ORIGIN_RANK.get(records[i][0], 9),
            i,
        ),
    )
    records = [records[i] for i in order]
    ids = _assign_ids(records)

    collected: List[CollectedDecision] = [
        CollectedDecision(
            decision_id=decision_id,
            origin=origin,
            trace=decision_trace(decision, origin),
            band_label=decision_band_label(decision, origin),
            assessment_basis=assessment_basis(decision, origin),
            decision=decision,
        )
        for decision_id, (origin, decision) in zip(ids, records)
    ]

    groups = group_decisions(collected)

    if not collected:
        own_warnings.append(
            "no analytical source produced a decision, so no condition could "
            "be assessed in this analysis"
        )

    upstream_warnings = merge_stage_warnings(
        list(getattr(rules_data, "all_warnings", ()) or ()),
        list(getattr(ml_data, "all_warnings", ()) or ()),
    )
    all_warnings = list(upstream_warnings) + _stage_warnings(own_warnings)

    upstream = _first_present(rules_data, ml_data, "upstream")
    upstream_summary = _first_present(rules_data, ml_data, "upstream_summary")
    partial_document = bool(getattr(upstream, "pages_unreadable", 0))
    input_kind = _input_kind(rules_data, ml_data)

    risks = [item.decision.risk for item in collected if item.decision.risk is not None]

    summary = DecisionCollectionSummary(
        decision_count=len(collected),
        group_count=len(groups),
        condition_count=len({g.condition for g in groups}),
        sources_run=[s.name for s in sources if s.ran],
        sources_failed=[s.name for s in sources if s.failed],
        conditions_assessed=sorted(
            {
                item.decision.condition
                for item in collected
                if item.decision.was_assessed
            },
            key=C.condition_rank,
        ),
        conditions_flagged=sorted(
            {item.decision.condition for item in collected if item.decision.is_flagged},
            key=C.condition_rank,
        ),
        highest_risk=RiskLevel.highest(risks),
        multi_decision_groups=[
            f"{g.condition} / {g.source}" for g in groups if g.member_count > 1
        ],
        partial_document=partial_document,
        input_kind=input_kind,
    )

    return DecisionCollectionData(
        collected=collected,
        groups=groups,
        sources=sources,
        warnings=own_warnings,
        upstream_warnings=upstream_warnings,
        all_warnings=all_warnings,
        upstream=upstream,
        upstream_summary=upstream_summary,
        summary=summary,
        metadata={
            "engine_version": DECISION_ENGINE_VERSION,
            "policy": DECISION_ENGINE_POLICY,
            "status_rule": STATUS_FUSION_RULE,
            "grouped_by": ["condition", "source"],
            "sources_attempted": [s.name for s in sources],
            "rules_metadata": dict(getattr(rules_data, "metadata", {}) or {}),
            "ml_metadata": dict(getattr(ml_data, "metadata", {}) or {}),
            "input_kind": input_kind,
        },
    )


def group_decisions(collected: Sequence[CollectedDecision]) -> List[DecisionGroup]:
    buckets: Dict[Tuple[str, str], List[CollectedDecision]] = {}
    order: List[Tuple[str, str]] = []
    for item in collected:
        key = (item.decision.condition, item.decision.source)
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(item)

    groups: List[DecisionGroup] = []
    for key in sorted(
        order,
        key=lambda k: (
            C.condition_rank(k[0]),
            _SOURCE_KIND_RANK.get(buckets[k][0].decision.source_kind, 9),
            k[1],
        ),
    ):
        members = buckets[key]
        condition, source = key
        source_kind = members[0].decision.source_kind
        merged = merge_decision_set([m.decision for m in members])
        basis = _primary_basis(members)

        metadata: Dict[str, Any] = {
            "grouped": True,
            "grouped_by": ["condition", "source"],
            "group_engine": "module_15_decision_engine",
            "engine_version": DECISION_ENGINE_VERSION,
            "condition": condition,
            "source": source,
            "member_count": len(members),
            "member_decision_ids": [m.decision_id for m in members],
            "member_traces": [m.trace for m in members if m.trace],
            "member_statuses": [m.decision.status.value for m in members],
            "band_labels": [m.band_label for m in members if m.band_label],
            "assessment_basis": basis,
            "status_rule": STATUS_FUSION_RULE,
            "confidence_rule": CONFIDENCE_RULE,
            "confidence_basis": merged.confidence_basis,
        }
        if len(members) == 1:
            metadata = {**dict(members[0].decision.metadata or {}), **metadata}

        groups.append(
            DecisionGroup(
                condition=condition,
                source=source,
                source_kind=source_kind,
                member_count=len(members),
                decision_ids=[m.decision_id for m in members],
                traces=[m.trace for m in members if m.trace],
                band_labels=[m.band_label for m in members if m.band_label],
                assessment_basis=basis,
                assessed=bool(merged.assessed),
                decision=ClinicalDecision(
                    condition=condition,
                    status=merged.status,
                    risk=merged.risk,
                    confidence=merged.confidence,
                    source=source,
                    source_kind=source_kind,
                    evidence=merged.evidence,
                    recommendations=merged.recommendations,
                    metadata=metadata,
                ),
            )
        )
    return groups


def collection_from_decisions(
    decisions: Sequence[ClinicalDecision],
) -> DecisionCollectionData:
    records: List[Tuple[str, ClinicalDecision]] = [
        (
            ORIGIN_RULES
            if d.source_kind is DecisionSourceKind.CLINICAL_RULE
            else ORIGIN_ML,
            d,
        )
        for d in decisions
    ]
    collected = [
        CollectedDecision(
            decision_id=decision_id,
            origin=origin,
            trace=decision_trace(decision, origin),
            band_label=decision_band_label(decision, origin),
            assessment_basis=assessment_basis(decision, origin),
            decision=decision,
        )
        for decision_id, (origin, decision) in zip(_assign_ids(records), records)
    ]
    groups = group_decisions(collected)
    risks = [c.decision.risk for c in collected if c.decision.risk is not None]
    return DecisionCollectionData(
        collected=collected,
        groups=groups,
        summary=DecisionCollectionSummary(
            decision_count=len(collected),
            group_count=len(groups),
            condition_count=len({g.condition for g in groups}),
            conditions_assessed=sorted(
                {c.decision.condition for c in collected if c.decision.was_assessed},
                key=C.condition_rank,
            ),
            conditions_flagged=sorted(
                {c.decision.condition for c in collected if c.decision.is_flagged},
                key=C.condition_rank,
            ),
            highest_risk=RiskLevel.highest(risks),
            multi_decision_groups=[
                f"{g.condition} / {g.source}" for g in groups if g.member_count > 1
            ],
        ),
        metadata={
            "engine_version": DECISION_ENGINE_VERSION,
            "policy": DECISION_ENGINE_POLICY,
            "grouped_by": ["condition", "source"],
            "input_source": "bare_decision_list",
        },
    )


def _primary_basis(members: Sequence[CollectedDecision]) -> str:
    assessed = [m for m in members if m.decision.was_assessed]
    if not assessed:
        return BASIS_NOT_ASSESSED
    best = max(assessed, key=lambda m: _STATUS_SEVERITY[m.decision.status])
    return best.assessment_basis


def _first_present(rules_data: Any, ml_data: Any, attribute: str) -> Any:
    for data in (rules_data, ml_data):
        value = getattr(data, attribute, None)
        if value is not None:
            return value
    from app.schemas.features import UpstreamExtraction
    from app.schemas.validation import FeatureValidationSummary

    return (
        UpstreamExtraction()
        if attribute == "upstream"
        else FeatureValidationSummary()
    )


def _input_kind(rules_data: Any, ml_data: Any) -> str:
    for data in (rules_data, ml_data):
        metadata = getattr(data, "metadata", None) or {}
        kind = metadata.get("input_kind")
        if kind:
            return str(kind)
    return "none"


__all__ = [
    "CONFIDENCE_MAX_PROBABILITY",
    "CONFIDENCE_NONE_PRODUCED",
    "CONFIDENCE_RULE",
    "DECISION_ENGINE_POLICY",
    "DECISION_ENGINE_VERSION",
    "ML_SOURCE_NAME",
    "ORIGIN_ML",
    "ORIGIN_RULES",
    "RULES_SOURCE_NAME",
    "STATUS_FUSION_RULE",
    "MergedFields",
    "assessment_basis",
    "collect_decisions",
    "collection_from_decisions",
    "decision_band_label",
    "decision_trace",
    "group_decisions",
    "merge_decision_set",
    "merge_stage_warnings",
    "unique",
]
