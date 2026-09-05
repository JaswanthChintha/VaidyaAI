"""Module 15 -- the Decision Engine.

The load-bearing behaviours here are all about NOT LOSING THINGS: not losing a
source's decisions when the other source raises, not losing an upstream
warning, not losing per-rule traceability while still collapsing the rule
engine's several decisions per condition down to one entry per source.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from app.data import conditions as C
from app.data.recommendation_catalog import scan_text
from app.ml.base import Predictor
from app.ml.registry import PredictorRegistry
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
    STAGE_DECISIONS,
)
from app.services import decision_engine as DE
from app.services.decision_engine import (
    CONFIDENCE_MAX_PROBABILITY,
    CONFIDENCE_NONE_PRODUCED,
    collect_decisions,
    collection_from_decisions,
    group_decisions,
    merge_decision_set,
    merge_stage_warnings,
)

# --------------------------------------------------------------------------
# Fixtures and helpers
# --------------------------------------------------------------------------

#: HbA1c 6.8 AND fasting glucose 112 -- the exact patient from the integration
#: audit, for whom the rule engine correctly emits TWO Diabetes decisions.
TWO_RULE_DIABETES_FEATURES: Dict[str, Any] = {
    "features": {
        "hba1c": {"name": "hba1c", "value": 6.8, "unit": "%"},
        "blood_glucose": {"name": "blood_glucose", "value": 112.0, "unit": "mg/dL"},
    }
}

FULL_FEATURES: Dict[str, Any] = {
    "features": {
        "hba1c": {"name": "hba1c", "value": 6.8, "unit": "%"},
        "blood_glucose": {"name": "blood_glucose", "value": 112.0, "unit": "mg/dL"},
        "age": {"name": "age", "value": 54.0, "unit": "years"},
        "gender": {"name": "gender", "value": "male"},
        "bmi": {"name": "bmi", "value": 31.4, "unit": "kg/m2"},
        "creatinine": {"name": "creatinine", "value": 1.1, "unit": "mg/dL"},
        "hemoglobin": {"name": "hemoglobin", "value": 14.2, "unit": "g/dL"},
        "cholesterol": {"name": "cholesterol", "value": 245.0, "unit": "mg/dL"},
        "triglycerides": {"name": "triglycerides", "value": 180.0, "unit": "mg/dL"},
        "vitamin_d": {"name": "vitamin_d", "value": 18.0, "unit": "ng/mL"},
    }
}


def decision(
    condition: str = C.DIABETES,
    status: DecisionStatus = DecisionStatus.INDICATED,
    risk: RiskLevel | None = RiskLevel.HIGH,
    *,
    source: str = "Clinical Rule Engine",
    kind: DecisionSourceKind = DecisionSourceKind.CLINICAL_RULE,
    confidence: float | None = None,
    evidence: List[EvidenceItem] | None = None,
    recommendations: List[Recommendation] | None = None,
    metadata: Dict[str, Any] | None = None,
) -> ClinicalDecision:
    return ClinicalDecision(
        condition=condition,
        status=status,
        risk=risk,
        confidence=confidence,
        source=source,
        source_kind=kind,
        evidence=evidence or [],
        recommendations=recommendations or [],
        metadata=metadata or {},
    )


def rec(code: str) -> Recommendation:
    return Recommendation(code=code, text=f"text for {code}", category="monitoring")


class SilentRegistry(PredictorRegistry):
    """An empty registry -- no model runs, so the rule engine is alone."""


class FakeDiabetesPredictor(Predictor):
    name = "fake_diabetes"
    condition = C.DIABETES
    source_label = "Fake Forest"
    version = "0.0.1"
    required_features = ("hba1c",)

    def __init__(self, probability: float = 0.77) -> None:
        self.probability = probability
        super().__init__()

    def _predict(self, features, context) -> ClinicalDecision:
        return ClinicalDecision(
            condition=self.condition,
            status=DecisionStatus.INDICATED,
            risk=RiskLevel.HIGH,
            confidence=self.probability,
            source=self.source_label,
            source_kind=DecisionSourceKind.MACHINE_LEARNING,
            evidence=[EvidenceItem(feature="hba1c", value=features.get("hba1c"))],
            metadata={
                "predictor": self.name,
                "probability_positive": self.probability,
                "band_meaning": "a modelled probability, not a measurement",
            },
        )


def registry_with(*predictors: Predictor) -> PredictorRegistry:
    registry = PredictorRegistry()
    for predictor in predictors:
        registry.register(predictor)
    return registry


# --------------------------------------------------------------------------
# THE AUDIT REQUIREMENT: group by (condition, source)
# --------------------------------------------------------------------------


def test_two_rules_on_one_condition_become_one_group_with_the_union_of_evidence():
    """The exact defect the integration audit carried into this brief.

    HbA1c 6.8 fires the HbA1c rule; fasting glucose 112 fires the glucose rule.
    Both are `Diabetes`, both from `Clinical Rule Engine`. That is CORRECT at
    Module 8 -- the unit of a rule decision is one rule -- and must collapse to
    ONE entry before fusion.
    """
    data = collect_decisions(
        engineered=TWO_RULE_DIABETES_FEATURES, registry=SilentRegistry()
    )

    raw = [
        item
        for item in data.collected
        if item.decision.condition == C.DIABETES
        and item.decision.source_kind is DecisionSourceKind.CLINICAL_RULE
    ]
    assert len(raw) >= 2, "the rule engine no longer emits two Diabetes decisions"

    groups = [
        g
        for g in data.groups
        if g.condition == C.DIABETES
        and g.source_kind is DecisionSourceKind.CLINICAL_RULE
    ]
    assert len(groups) == 1
    group = groups[0]
    assert group.member_count == len(raw)
    assert group.decision_ids == [item.decision_id for item in raw]

    # The union of evidence, not one rule's slice of it.
    union = {item.dedup_key() for d in raw for item in d.decision.evidence}
    assert {item.dedup_key() for item in group.decision.evidence} == union
    assert "hba1c" in group.decision.evidence_features()
    assert "blood_glucose" in group.decision.evidence_features()

    # And the collapse is visible rather than silent.
    assert f"{C.DIABETES} / Clinical Rule Engine" in data.summary.multi_decision_groups


def test_the_group_keeps_the_highest_risk_and_most_severe_status():
    """Indicated/High (HbA1c) beside Borderline/Medium (glucose) -> Indicated/High."""
    group = group_decisions(
        collection_from_decisions(
            [
                decision(status=DecisionStatus.BORDERLINE, risk=RiskLevel.MEDIUM),
                decision(status=DecisionStatus.INDICATED, risk=RiskLevel.HIGH),
            ]
        ).collected
    )[0]
    assert group.decision.status is DecisionStatus.INDICATED
    assert group.decision.risk is RiskLevel.HIGH
    assert group.member_count == 2


def test_a_within_source_merge_is_not_a_hybrid_decision():
    """Merging two rule decisions yields a RULE decision. Only 16 emits FUSION."""
    group = group_decisions(
        collection_from_decisions([decision(), decision()]).collected
    )[0]
    assert group.decision.source_kind is DecisionSourceKind.CLINICAL_RULE
    assert group.decision.source == "Clinical Rule Engine"


def test_different_sources_stay_in_different_groups():
    collection = collection_from_decisions(
        [
            decision(),
            decision(
                source="Random Forest",
                kind=DecisionSourceKind.MACHINE_LEARNING,
                confidence=0.9,
            ),
        ]
    )
    assert len(collection.groups) == 2
    assert {g.source for g in collection.groups} == {
        "Clinical Rule Engine",
        "Random Forest",
    }


def test_different_conditions_stay_in_different_groups():
    collection = collection_from_decisions(
        [decision(C.DIABETES), decision(C.ANEMIA, risk=RiskLevel.MEDIUM)]
    )
    assert {g.condition for g in collection.groups} == {C.DIABETES, C.ANEMIA}


def test_groups_come_out_in_canonical_condition_order():
    collection = collection_from_decisions(
        [
            decision(C.OBESITY, risk=RiskLevel.MEDIUM),
            decision(C.DIABETES),
            decision(C.KIDNEY_DISEASE, risk=RiskLevel.LOW),
        ]
    )
    assert [g.condition for g in collection.groups] == [
        C.DIABETES,
        C.KIDNEY_DISEASE,
        C.OBESITY,
    ]


# --------------------------------------------------------------------------
# Stable ids
# --------------------------------------------------------------------------


def test_ids_are_deterministic_across_runs():
    first = collect_decisions(
        engineered=TWO_RULE_DIABETES_FEATURES, registry=SilentRegistry()
    )
    second = collect_decisions(
        engineered=TWO_RULE_DIABETES_FEATURES, registry=SilentRegistry()
    )
    assert [i.decision_id for i in first.collected] == [
        i.decision_id for i in second.collected
    ]


def test_ids_are_unique_and_name_the_rule_that_produced_the_decision():
    data = collect_decisions(engineered=FULL_FEATURES, registry=SilentRegistry())
    ids = [item.decision_id for item in data.collected]
    assert len(ids) == len(set(ids))
    for item in data.collected:
        assert item.decision_id.startswith(("rules:", "ml:"))
        # Module 20 must be able to name the exact rule.
        assert item.trace, f"{item.decision_id} carries no trace"
        assert item.trace == item.decision.metadata.get("rule_id")


def test_a_repeated_trace_is_disambiguated_rather_than_randomised():
    collection = collection_from_decisions(
        [
            decision(metadata={"rule_id": "SAME"}),
            decision(metadata={"rule_id": "SAME"}),
        ]
    )
    ids = [item.decision_id for item in collection.collected]
    assert ids == ["rules:diabetes:same", "rules:diabetes:same#2"]


def test_every_group_member_id_exists_in_the_collection():
    """Module 20 traces a fused finding back through these ids; no dangling ones."""
    data = collect_decisions(engineered=FULL_FEATURES, registry=SilentRegistry())
    known = {item.decision_id for item in data.collected}
    for group in data.groups:
        assert set(group.decision_ids) <= known
    assert sum(g.member_count for g in data.groups) == len(data.collected)


# --------------------------------------------------------------------------
# Resilience: one source failing must not lose the other's decisions
# --------------------------------------------------------------------------


def test_the_rule_engine_failing_keeps_the_model_decisions(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("rule table exploded with hba1c 6.8")

    monkeypatch.setattr(DE, "evaluate_rules", boom)
    data = collect_decisions(
        engineered=TWO_RULE_DIABETES_FEATURES,
        registry=registry_with(FakeDiabetesPredictor()),
    )

    assert [i.origin for i in data.collected] == ["ml"]
    assert data.collected[0].decision.source == "Fake Forest"

    rules_run = next(s for s in data.sources if s.name == "Clinical Rule Engine")
    assert rules_run.failed is True and rules_run.ran is False
    assert rules_run.error_type == "RuntimeError"
    assert rules_run.decision_count == 0
    assert data.summary.sources_failed == ["Clinical Rule Engine"]


def test_the_model_layer_failing_keeps_the_rule_decisions(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("the model blew up")

    monkeypatch.setattr(DE, "predict_all", boom)
    data = collect_decisions(engineered=TWO_RULE_DIABETES_FEATURES)

    assert data.collected, "the rule engine's decisions were lost with the model's"
    assert {i.origin for i in data.collected} == {"rules"}
    ml_run = next(s for s in data.sources if s.name == DE.ML_SOURCE_NAME)
    assert ml_run.failed is True
    assert data.summary.sources_run == ["Clinical Rule Engine"]


def test_a_failure_message_never_carries_the_exception_text(monkeypatch):
    """The exception message quotes a patient value. It must not be relayed."""

    def boom(*args, **kwargs):
        raise RuntimeError("model blew up with hba1c 6.8 and glucose 112")

    monkeypatch.setattr(DE, "predict_all", boom)
    data = collect_decisions(engineered=TWO_RULE_DIABETES_FEATURES)
    blob = " ".join(data.warnings) + " ".join(
        s.error_type or "" for s in data.sources
    )
    assert "6.8" not in blob and "112" not in blob


def test_both_sources_failing_still_returns_a_well_formed_result(monkeypatch):
    monkeypatch.setattr(DE, "evaluate_rules", lambda *a, **k: 1 / 0)
    monkeypatch.setattr(DE, "predict_all", lambda *a, **k: 1 / 0)
    data = collect_decisions(engineered=TWO_RULE_DIABETES_FEATURES)
    assert data.collected == [] and data.groups == []
    assert len(data.summary.sources_failed) == 2
    assert data.summary.highest_risk is None, "nothing assessed must not become Low"
    assert any("no analytical source produced a decision" in w for w in data.warnings)


# --------------------------------------------------------------------------
# Warnings: origins intact, nothing dropped, nothing duplicated
# --------------------------------------------------------------------------


def test_an_upstream_warning_survives_with_its_original_origin():
    canary = "CANARY: page 2 could not be read"
    data = collect_decisions(
        engineered={**FULL_FEATURES, "warnings": [canary]},
        registry=SilentRegistry(),
    )
    matches = [w for w in data.all_warnings if w.message == canary]
    assert matches, "an upstream warning was dropped by Module 15"
    assert matches[0].stage != STAGE_DECISIONS, "the origin was overwritten"
    assert matches[0].module < 15


def test_a_warning_both_sources_relayed_appears_exactly_once():
    canary = "CANARY: shared upstream warning"
    data = collect_decisions(
        engineered={**FULL_FEATURES, "warnings": [canary]},
        registry=registry_with(FakeDiabetesPredictor()),
    )
    assert sum(1 for w in data.all_warnings if w.message == canary) == 1


def test_module_15_stamps_its_own_stage_on_its_own_warnings(monkeypatch):
    monkeypatch.setattr(DE, "evaluate_rules", lambda *a, **k: 1 / 0)
    data = collect_decisions(engineered=FULL_FEATURES, registry=SilentRegistry())
    own = [w for w in data.all_warnings if w.stage == STAGE_DECISIONS]
    assert own and all(w.module == 15 for w in own)
    assert {w.message for w in own} == set(data.warnings)


def test_merge_stage_warnings_keeps_two_stages_that_said_the_same_thing():
    """De-duplication is on (stage, module, message), never on the message alone."""
    merged = merge_stage_warnings(
        [StageWarning(stage="extraction", module=4, message="same")],
        [
            StageWarning(stage="extraction", module=4, message="same"),
            StageWarning(stage="rules", module=8, message="same"),
        ],
    )
    assert [(w.stage, w.module) for w in merged] == [("extraction", 4), ("rules", 8)]


def test_every_warning_module_15_produces_is_safe_to_show_a_patient(monkeypatch):
    monkeypatch.setattr(DE, "evaluate_rules", lambda *a, **k: 1 / 0)
    monkeypatch.setattr(DE, "predict_all", lambda *a, **k: 1 / 0)
    data = collect_decisions(engineered=FULL_FEATURES)
    for message in data.warnings:
        assert scan_text(message) == [], message


# --------------------------------------------------------------------------
# The shared merge core
# --------------------------------------------------------------------------


def test_risk_merge_at_every_ordering_boundary():
    cases = [
        ([RiskLevel.LOW, RiskLevel.MEDIUM], RiskLevel.MEDIUM),
        ([RiskLevel.MEDIUM, RiskLevel.LOW], RiskLevel.MEDIUM),
        ([RiskLevel.MEDIUM, RiskLevel.HIGH], RiskLevel.HIGH),
        ([RiskLevel.HIGH, RiskLevel.MEDIUM], RiskLevel.HIGH),
        ([RiskLevel.LOW, RiskLevel.HIGH], RiskLevel.HIGH),
        ([RiskLevel.LOW, RiskLevel.LOW], RiskLevel.LOW),
        ([RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH], RiskLevel.HIGH),
    ]
    for risks, expected in cases:
        merged = merge_decision_set(
            [decision(status=DecisionStatus.BORDERLINE, risk=r) for r in risks]
        )
        assert merged.risk is expected, risks


def test_an_empty_set_yields_no_risk_and_no_status_of_assessment():
    """`RiskLevel.highest([])` is None, not LOW. Module 15 must not undo that."""
    merged = merge_decision_set([])
    assert merged.risk is None
    assert merged.status is DecisionStatus.INSUFFICIENT_DATA
    assert merged.confidence is None


def test_status_merge_takes_the_most_severe_assessed_value():
    cases = [
        ([DecisionStatus.NOT_INDICATED, DecisionStatus.BORDERLINE], DecisionStatus.BORDERLINE),
        ([DecisionStatus.BORDERLINE, DecisionStatus.INDICATED], DecisionStatus.INDICATED),
        ([DecisionStatus.NOT_INDICATED, DecisionStatus.INDICATED], DecisionStatus.INDICATED),
        ([DecisionStatus.NOT_INDICATED, DecisionStatus.NOT_INDICATED], DecisionStatus.NOT_INDICATED),
    ]
    for statuses, expected in cases:
        merged = merge_decision_set(
            [decision(status=s, risk=RiskLevel.LOW) for s in statuses]
        )
        assert merged.status is expected, statuses


# ---- confidence: None is NOT 0.0 -----------------------------------------


def test_none_confidence_is_absent_from_the_maximum_not_read_as_zero():
    merged = merge_decision_set(
        [
            decision(confidence=None),
            decision(
                source="Random Forest",
                kind=DecisionSourceKind.MACHINE_LEARNING,
                confidence=0.4,
            ),
        ]
    )
    assert merged.confidence == 0.4
    assert merged.confidence_basis == CONFIDENCE_MAX_PROBABILITY


def test_a_zero_confidence_model_takes_part_and_is_not_treated_as_absent():
    """`0.0` means a model RAN and was maximally unconfident. It is a value."""
    merged = merge_decision_set(
        [
            decision(
                source="Random Forest",
                kind=DecisionSourceKind.MACHINE_LEARNING,
                status=DecisionStatus.NOT_INDICATED,
                risk=RiskLevel.LOW,
                confidence=0.0,
            )
        ]
    )
    assert merged.confidence == 0.0
    assert merged.confidence is not None
    assert merged.confidence_basis == CONFIDENCE_MAX_PROBABILITY


def test_only_deterministic_rules_means_no_probability_at_all():
    merged = merge_decision_set([decision(confidence=None), decision(confidence=None)])
    assert merged.confidence is None
    assert merged.confidence_basis == CONFIDENCE_NONE_PRODUCED


def test_the_strongest_probability_wins():
    merged = merge_decision_set(
        [
            decision(
                source="Model A",
                kind=DecisionSourceKind.MACHINE_LEARNING,
                confidence=0.2,
            ),
            decision(
                source="Model B",
                kind=DecisionSourceKind.MACHINE_LEARNING,
                confidence=0.91,
            ),
        ]
    )
    assert merged.confidence == 0.91


def test_nothing_assessed_carries_no_confidence():
    merged = merge_decision_set(
        [decision(status=DecisionStatus.INSUFFICIENT_DATA, risk=None)]
    )
    assert merged.confidence is None
    assert merged.status is DecisionStatus.INSUFFICIENT_DATA


# ---- evidence and recommendations ----------------------------------------


def test_identical_evidence_from_two_sources_is_shown_once():
    item = EvidenceItem(feature="hba1c", value=6.8, unit="%", threshold=6.5)
    merged = merge_decision_set(
        [
            decision(evidence=[item]),
            decision(
                source="Random Forest",
                kind=DecisionSourceKind.MACHINE_LEARNING,
                confidence=0.8,
                evidence=[item.model_copy(), EvidenceItem(feature="bmi", value=31.4)],
            ),
        ]
    )
    assert [e.feature for e in merged.evidence] == ["hba1c", "bmi"]


def test_evidence_differing_only_in_value_is_kept_as_two_items():
    merged = merge_decision_set(
        [
            decision(evidence=[EvidenceItem(feature="hba1c", value=6.8)]),
            decision(evidence=[EvidenceItem(feature="hba1c", value=7.4)]),
        ]
    )
    assert len(merged.evidence) == 2


def test_recommendations_are_consolidated_without_duplicates():
    merged = merge_decision_set(
        [
            decision(recommendations=[rec("NOT_A_DIAGNOSIS"), rec("MONITOR_OVER_TIME")]),
            decision(
                recommendations=[rec("NOT_A_DIAGNOSIS"), rec("DISCUSS_WITH_CLINICIAN")]
            ),
        ]
    )
    assert [r.code for r in merged.recommendations] == [
        "NOT_A_DIAGNOSIS",
        "MONITOR_OVER_TIME",
        "DISCUSS_WITH_CLINICIAN",
    ]


def test_an_unassessed_contributor_does_not_contradict_an_assessed_one():
    """A "value not available" item beside a quoted value would confuse a reader.

    The abstention is not lost -- it stays in the collection and in the
    contribution record -- but its evidence does not join a real finding's.
    """
    merged = merge_decision_set(
        [
            decision(evidence=[EvidenceItem(feature="hba1c", value=6.8, unit="%")]),
            decision(
                source="Random Forest",
                kind=DecisionSourceKind.MACHINE_LEARNING,
                status=DecisionStatus.INSUFFICIENT_DATA,
                risk=None,
                evidence=[
                    EvidenceItem(
                        feature="hba1c",
                        value=None,
                        note="this value was not available in the submitted report",
                    )
                ],
            ),
        ]
    )
    assert [(e.feature, e.value) for e in merged.evidence] == [("hba1c", 6.8)]


def test_when_nothing_could_be_assessed_the_evidence_is_what_was_missing():
    merged = merge_decision_set(
        [
            decision(
                status=DecisionStatus.INSUFFICIENT_DATA,
                risk=None,
                evidence=[EvidenceItem(feature="creatinine", value=None)],
            )
        ]
    )
    assert [e.feature for e in merged.evidence] == ["creatinine"]


def test_an_unassessed_contributors_recommendations_are_still_carried():
    """Evidence can contradict; "consider a repeat test" cannot. Union it."""
    merged = merge_decision_set(
        [
            decision(recommendations=[rec("NOT_A_DIAGNOSIS")]),
            decision(
                status=DecisionStatus.INSUFFICIENT_DATA,
                risk=None,
                recommendations=[rec("INFORMATION_INCOMPLETE")],
            ),
        ]
    )
    assert {r.code for r in merged.recommendations} == {
        "NOT_A_DIAGNOSIS",
        "INFORMATION_INCOMPLETE",
    }


# --------------------------------------------------------------------------
# Assessment basis -- the Heart Disease hazard, at the collection layer
# --------------------------------------------------------------------------


def test_a_composite_risk_factor_rule_is_labelled_as_a_count_not_a_measurement():
    data = collect_decisions(engineered=FULL_FEATURES, registry=SilentRegistry())
    heart = [
        item for item in data.collected if item.decision.condition == C.HEART_DISEASE
    ]
    assert heart, "the rule engine no longer emits a Heart Disease decision"
    assert heart[0].assessment_basis == BASIS_RISK_FACTOR_COUNT
    # And the rule's own wording travels with it, so Module 17 can quote it.
    assert heart[0].band_label


def test_a_threshold_rule_is_labelled_as_a_measurement():
    data = collect_decisions(
        engineered=TWO_RULE_DIABETES_FEATURES, registry=SilentRegistry()
    )
    diabetes = [
        item
        for item in data.collected
        if item.decision.condition == C.DIABETES and item.decision.was_assessed
    ]
    assert diabetes
    assert all(i.assessment_basis == BASIS_THRESHOLD for i in diabetes)


def test_a_model_is_labelled_as_a_probability_unless_it_says_otherwise():
    data = collect_decisions(
        engineered=TWO_RULE_DIABETES_FEATURES,
        registry=registry_with(FakeDiabetesPredictor()),
    )
    ml = [i for i in data.collected if i.origin == "ml"]
    assert ml and ml[0].assessment_basis == BASIS_MODEL_PROBABILITY


def test_a_predictor_may_declare_its_own_basis():
    """The hook Module 11 uses to say it estimates likelihood, not burden."""
    item = collection_from_decisions(
        [
            decision(
                C.HEART_DISEASE,
                source="Random Forest",
                kind=DecisionSourceKind.MACHINE_LEARNING,
                confidence=0.6,
                metadata={"assessment_basis": "model_probability", "predictor": "heart_rf"},
            )
        ]
    ).collected[0]
    assert item.assessment_basis == BASIS_MODEL_PROBABILITY
    assert item.trace == "heart_rf"


def test_an_abstention_answers_no_question_and_so_declares_no_basis():
    item = collection_from_decisions(
        [
            decision(
                C.KIDNEY_DISEASE,
                status=DecisionStatus.INSUFFICIENT_DATA,
                risk=None,
                metadata={"factors_counted": ["a"], "rule_id": "X"},
            )
        ]
    ).collected[0]
    assert item.assessment_basis == BASIS_NOT_ASSESSED


# --------------------------------------------------------------------------
# End to end over a realistic feature set
# --------------------------------------------------------------------------


def test_a_realistic_report_collects_groups_and_summarises():
    data = collect_decisions(engineered=FULL_FEATURES, registry=SilentRegistry())

    assert len(data.collected) > len(data.groups), "nothing was collapsed at all"
    assert data.summary.decision_count == len(data.collected)
    assert data.summary.group_count == len(data.groups)
    assert data.summary.highest_risk is not None
    assert C.DIABETES in data.summary.conditions_flagged
    assert data.summary.input_kind == "engineered"
    assert data.metadata["grouped_by"] == ["condition", "source"]

    # Every group's source really is one source.
    for group in data.groups:
        members = [
            i for i in data.collected if i.decision_id in set(group.decision_ids)
        ]
        assert {m.decision.source for m in members} == {group.source}
        assert {m.decision.condition for m in members} == {group.condition}


def test_a_validated_feature_set_is_accepted_directly():
    from app.services.validator import validate_features

    validated = validate_features(FULL_FEATURES)
    data = collect_decisions(validated, registry=SilentRegistry())
    assert data.collected
    assert data.summary.input_kind == "validated"


def test_no_input_at_all_assesses_nothing_and_says_so():
    data = collect_decisions(registry=SilentRegistry())
    assert data.summary.highest_risk is None
    assert data.summary.conditions_assessed == []
    # The always-assessed conditions are still MENTIONED, as INSUFFICIENT_DATA.
    assert {g.condition for g in data.groups} >= set(C.FUSION_CONDITIONS)
    for group in data.groups:
        assert group.decision.status is DecisionStatus.INSUFFICIENT_DATA
        assert group.decision.risk is None
