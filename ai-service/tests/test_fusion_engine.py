from __future__ import annotations

from typing import Any, Dict, List

import pytest

from app.data import conditions as C
from app.data.recommendation_catalog import scan_text
from app.schemas.decisions import (
    ClinicalDecision,
    DecisionSourceKind,
    DecisionStatus,
    EvidenceItem,
    Recommendation,
    RiskLevel,
)
from app.schemas.fusion import (
    BASIS_CONFLICT_NOTE,
    BASIS_MODEL_PROBABILITY,
    BASIS_RISK_FACTOR_COUNT,
    BASIS_THRESHOLD,
    STAGE_FUSION,
    STATUS_HEALTHY,
    STATUS_NEEDS_MEDICAL_ATTENTION,
    STATUS_NEEDS_MONITORING,
)
from app.services import decision_engine as DE
from app.services.decision_engine import (
    CONFIDENCE_MAX_PROBABILITY,
    CONFIDENCE_NONE_PRODUCED,
)
from app.services.fusion_engine import fuse_decisions, run_decision_fusion
from tests.test_decision_engine import (
    FULL_FEATURES,
    TWO_RULE_DIABETES_FEATURES,
    FakeDiabetesPredictor,
    SilentRegistry,
    decision,
    rec,
    registry_with,
)


def fuse(decisions: List[ClinicalDecision]):
    return fuse_decisions(decisions)


def only(decisions: List[ClinicalDecision]):
    data = fuse(decisions)
    assert len(data.fused) == 1
    return data.fused[0]


def ml(
    condition: str = C.DIABETES,
    *,
    status: DecisionStatus = DecisionStatus.INDICATED,
    risk: RiskLevel | None = RiskLevel.HIGH,
    confidence: float | None = 0.8,
    source: str = "Random Forest",
    **kwargs: Any,
) -> ClinicalDecision:
    return decision(
        condition,
        status,
        risk,
        source=source,
        kind=DecisionSourceKind.MACHINE_LEARNING,
        confidence=confidence,
        **kwargs,
    )


def test_a_rule_and_a_model_about_one_condition_become_one_decision():
    fused = only([decision(C.DIABETES), ml(C.DIABETES)])
    assert fused.condition == C.DIABETES
    assert fused.decision.source_kind is DecisionSourceKind.FUSION
    assert fused.sources == ["Clinical Rule Engine", "Random Forest"]
    assert fused.hybrid is True


def test_different_conditions_are_never_fused_together():
    data = fuse([decision(C.DIABETES), decision(C.ANEMIA, risk=RiskLevel.MEDIUM)])
    assert [f.condition for f in data.fused] == [C.DIABETES, C.ANEMIA]


def test_fused_decisions_come_out_in_canonical_condition_order():
    data = fuse(
        [
            decision(C.OBESITY, risk=RiskLevel.MEDIUM),
            decision(C.KIDNEY_DISEASE, risk=RiskLevel.LOW),
            decision(C.DIABETES),
        ]
    )
    assert [f.condition for f in data.fused] == [
        C.DIABETES,
        C.KIDNEY_DISEASE,
        C.OBESITY,
    ]


@pytest.mark.parametrize(
    "rule_risk, model_risk, expected",
    [
        (RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.MEDIUM),
        (RiskLevel.MEDIUM, RiskLevel.LOW, RiskLevel.MEDIUM),
        (RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.HIGH),
        (RiskLevel.HIGH, RiskLevel.MEDIUM, RiskLevel.HIGH),
        (RiskLevel.LOW, RiskLevel.HIGH, RiskLevel.HIGH),
        (RiskLevel.HIGH, RiskLevel.LOW, RiskLevel.HIGH),
        (RiskLevel.LOW, RiskLevel.LOW, RiskLevel.LOW),
        (RiskLevel.MEDIUM, RiskLevel.MEDIUM, RiskLevel.MEDIUM),
        (RiskLevel.HIGH, RiskLevel.HIGH, RiskLevel.HIGH),
    ],
)
def test_the_highest_applicable_risk_is_retained(rule_risk, model_risk, expected):
    fused = only(
        [
            decision(status=DecisionStatus.BORDERLINE, risk=rule_risk),
            ml(status=DecisionStatus.BORDERLINE, risk=model_risk),
        ]
    )
    assert fused.risk is expected
    assert fused.decision.risk is expected


def test_nothing_assessed_never_becomes_low_risk():
    fused = only(
        [decision(status=DecisionStatus.INSUFFICIENT_DATA, risk=None)]
    )
    assert fused.risk is None
    assert fused.decision.risk is None
    assert fused.status is DecisionStatus.INSUFFICIENT_DATA


def test_an_empty_input_produces_no_fused_decisions_and_no_overall_risk():
    data = fuse([])
    assert data.fused == []
    assert data.summary.overall_risk is None
    assert data.summary.overall_status is None
    assert data.summary.any_assessed is False


def test_a_rule_producing_no_probability_does_not_suppress_the_models():
    fused = only([decision(confidence=None), ml(confidence=0.87)])
    assert fused.confidence == 0.87
    assert fused.confidence_basis == CONFIDENCE_MAX_PROBABILITY


def test_a_model_that_ran_and_was_maximally_unconfident_is_not_treated_as_absent():
    fused = only(
        [
            decision(status=DecisionStatus.NOT_INDICATED, risk=RiskLevel.LOW),
            ml(status=DecisionStatus.NOT_INDICATED, risk=RiskLevel.LOW, confidence=0.0),
        ]
    )
    assert fused.confidence == 0.0
    assert fused.confidence is not None
    assert fused.confidence_basis == CONFIDENCE_MAX_PROBABILITY


def test_two_rules_alone_yield_no_confidence_rather_than_zero():
    fused = only([decision(confidence=None), decision(confidence=None)])
    assert fused.confidence is None
    assert fused.confidence_basis == CONFIDENCE_NONE_PRODUCED
    assert fused.decision.confidence is None


def test_the_strongest_available_probability_is_used():
    fused = only(
        [ml(source="Model A", confidence=0.31), ml(source="Model B", confidence=0.94)]
    )
    assert fused.confidence == 0.94


def test_each_sources_own_confidence_survives_for_module_20():
    fused = only([decision(confidence=None), ml(confidence=0.87)])
    by_source = {c.source: c.confidence for c in fused.contributions}
    assert by_source == {"Clinical Rule Engine": None, "Random Forest": 0.87}
    assert fused.decision.metadata["source_confidence"] == by_source


def test_evidence_from_several_sources_is_combined():
    fused = only(
        [
            decision(evidence=[EvidenceItem(feature="hba1c", value=6.8, unit="%")]),
            ml(
                evidence=[
                    EvidenceItem(feature="bmi", value=31.4),
                    EvidenceItem(feature="age", value=54.0),
                ]
            ),
        ]
    )
    assert fused.decision.evidence_features() == ["hba1c", "bmi", "age"]
    assert fused.evidence_count == 3


def test_the_same_evidence_cited_by_both_sources_appears_once():
    shared = EvidenceItem(feature="hba1c", value=6.8, unit="%", threshold=6.5)
    fused = only(
        [decision(evidence=[shared]), ml(evidence=[shared.model_copy()])]
    )
    assert len(fused.decision.evidence) == 1


def test_recommendations_are_consolidated_and_de_duplicated():
    fused = only(
        [
            decision(recommendations=[rec("NOT_A_DIAGNOSIS"), rec("MONITOR_OVER_TIME")]),
            ml(recommendations=[rec("NOT_A_DIAGNOSIS"), rec("DISCUSS_WITH_CLINICIAN")]),
        ]
    )
    assert [r.code for r in fused.decision.recommendations] == [
        "NOT_A_DIAGNOSIS",
        "MONITOR_OVER_TIME",
        "DISCUSS_WITH_CLINICIAN",
    ]
    assert fused.recommendation_count == 3


def test_fusion_never_invents_a_recommendation():
    incoming = {"NOT_A_DIAGNOSIS", "MONITOR_OVER_TIME"}
    fused = only(
        [
            decision(recommendations=[rec("NOT_A_DIAGNOSIS")]),
            ml(recommendations=[rec("MONITOR_OVER_TIME")]),
        ]
    )
    assert {r.code for r in fused.decision.recommendations} <= incoming


def test_one_engine_firing_twice_is_ONE_source_not_two():
    fused = only(
        [
            decision(status=DecisionStatus.INDICATED, risk=RiskLevel.HIGH),
            decision(status=DecisionStatus.BORDERLINE, risk=RiskLevel.MEDIUM),
        ]
    )
    assert fused.sources == ["Clinical Rule Engine"]
    assert fused.decision.metadata["sources"] == ["Clinical Rule Engine"]
    assert len(fused.contributions) == 1
    assert len(fused.contributions[0].decision_ids) == 2
    assert len(fused.decision_ids) == 2
    assert fused.hybrid is False


def test_a_rule_and_a_model_are_both_reported_as_contributing():
    fused = only([decision(), ml()])
    assert set(fused.source_kinds) == {
        DecisionSourceKind.CLINICAL_RULE,
        DecisionSourceKind.MACHINE_LEARNING,
    }
    assert fused.hybrid is True
    assert fused.decision.source == "Clinical Rule Engine + Random Forest"


def test_two_rules_and_a_model_give_two_sources_not_three():
    fused = only([decision(), decision(), ml()])
    assert fused.sources == ["Clinical Rule Engine", "Random Forest"]
    assert len(fused.decision_ids) == 3
    assert fused.hybrid is True


def test_a_fused_finding_traces_back_to_the_exact_rule_or_model():
    data = run_decision_fusion(
        engineered=TWO_RULE_DIABETES_FEATURES,
        registry=registry_with(FakeDiabetesPredictor()),
    )
    diabetes = next(f for f in data.fused if f.condition == C.DIABETES)
    known = {item.decision_id: item for item in data.collection.collected}
    assert diabetes.decision_ids
    for decision_id in diabetes.decision_ids:
        assert decision_id in known, decision_id
        assert known[decision_id].trace
    traces = [t for c in diabetes.contributions for t in c.traces]
    assert "fake_diabetes" in traces
    assert any(t.startswith("HBA1C") or "HBA1C" in t for t in traces)


def test_a_model_that_could_not_assess_does_not_hide_a_rule_that_fired():
    fused = only(
        [
            decision(C.KIDNEY_DISEASE, DecisionStatus.INDICATED, RiskLevel.HIGH),
            ml(
                C.KIDNEY_DISEASE,
                status=DecisionStatus.INSUFFICIENT_DATA,
                risk=None,
                confidence=None,
            ),
        ]
    )
    assert fused.status is DecisionStatus.INDICATED
    assert fused.risk is RiskLevel.HIGH


def test_but_the_models_abstention_is_never_silently_discarded():
    data = fuse(
        [
            decision(C.KIDNEY_DISEASE, DecisionStatus.INDICATED, RiskLevel.HIGH),
            ml(
                C.KIDNEY_DISEASE,
                status=DecisionStatus.INSUFFICIENT_DATA,
                risk=None,
                confidence=None,
            ),
        ]
    )
    fused = data.fused[0]
    assert fused.partially_assessed is True
    assert fused.unassessed_sources == ["Random Forest"]
    assert fused.assessed_source_count == 1
    assert fused.decision.metadata["unassessed_sources"] == ["Random Forest"]
    assert any("could not assess" in w for w in data.warnings)
    assert any(w.stage == STAGE_FUSION for w in data.all_warnings)
    assert C.KIDNEY_DISEASE in data.summary.partially_assessed_conditions
    assert data.summary.assessment_incomplete is True


def test_a_condition_nothing_assessed_is_reported_as_insufficient_data():
    fused = only(
        [
            decision(
                C.KIDNEY_DISEASE, DecisionStatus.INSUFFICIENT_DATA, None
            ),
            ml(
                C.KIDNEY_DISEASE,
                status=DecisionStatus.INSUFFICIENT_DATA,
                risk=None,
                confidence=None,
            ),
        ]
    )
    assert fused.status is DecisionStatus.INSUFFICIENT_DATA
    assert fused.risk is None
    assert fused.confidence is None
    assert fused.partially_assessed is False, "nothing assessed is not PARTIAL"
    assert fused.assessed_source_count == 0
    assert fused.hybrid is False, "abstaining together is not corroboration"


def test_the_fused_status_is_the_most_severe_of_the_sources_that_assessed():
    fused = only(
        [
            decision(status=DecisionStatus.NOT_INDICATED, risk=RiskLevel.LOW),
            ml(status=DecisionStatus.BORDERLINE, risk=RiskLevel.MEDIUM),
        ]
    )
    assert fused.status is DecisionStatus.BORDERLINE
    assert fused.risk is RiskLevel.MEDIUM


def test_a_fused_decision_satisfies_every_schema_invariant():
    for decisions in (
        [decision(), ml()],
        [decision(status=DecisionStatus.INSUFFICIENT_DATA, risk=None)],
        [ml(confidence=0.0, status=DecisionStatus.NOT_INDICATED, risk=RiskLevel.LOW)],
    ):
        fused = only(decisions).decision
        assert isinstance(fused, ClinicalDecision)
        ClinicalDecision.model_validate(fused.model_dump())
        if fused.status is DecisionStatus.INSUFFICIENT_DATA:
            assert fused.risk is None
        else:
            assert fused.risk is not None


def test_a_risk_factor_count_beside_a_model_likelihood_is_flagged_not_blended():
    rule = decision(
        C.HEART_DISEASE,
        metadata={
            "rule_id": "COMPOSITE_CARDIOVASCULAR",
            "factors_counted": ["a", "b", "c"],
            "factor_count": 3,
            "band_label": (
                "three or more major cardiovascular risk factors were counted"
            ),
        },
    )
    model = ml(
        C.HEART_DISEASE,
        confidence=0.71,
        metadata={"predictor": "heart_rf", "band_meaning": "a modelled likelihood"},
    )
    fused = only([rule, model])

    assert fused.condition == C.HEART_DISEASE
    assert fused.hybrid is True
    assert len(fused.contributions) == 2

    assert fused.basis_conflict is True
    assert fused.basis_note == BASIS_CONFLICT_NOTE
    assert set(fused.assessment_bases) == {
        BASIS_RISK_FACTOR_COUNT,
        BASIS_MODEL_PROBABILITY,
    }
    by_source = {c.source: c.assessment_basis for c in fused.contributions}
    assert by_source["Clinical Rule Engine"] == BASIS_RISK_FACTOR_COUNT
    assert by_source["Random Forest"] == BASIS_MODEL_PROBABILITY

    labels = {c.source: c.band_labels for c in fused.contributions}
    assert "three or more major cardiovascular risk factors were counted" in (
        labels["Clinical Rule Engine"]
    )
    assert labels["Random Forest"] == ["a modelled likelihood"]


def test_a_threshold_rule_beside_a_model_is_NOT_flagged_as_a_conflict():
    fused = only(
        [
            decision(C.DIABETES, metadata={"rule_id": "HBA1C_HIGH"}),
            ml(C.DIABETES, confidence=0.8),
        ]
    )
    assert set(fused.assessment_bases) == {BASIS_THRESHOLD, BASIS_MODEL_PROBABILITY}
    assert fused.basis_conflict is False
    assert fused.basis_note is None


def test_the_conflict_note_reaches_the_warnings_and_is_safe_to_display():
    data = fuse(
        [
            decision(
                C.HEART_DISEASE,
                metadata={"factor_count": 3, "band_label": "counted"},
            ),
            ml(C.HEART_DISEASE, confidence=0.7),
        ]
    )
    assert C.HEART_DISEASE in data.summary.basis_conflict_conditions
    assert any(BASIS_CONFLICT_NOTE in w for w in data.warnings)
    assert scan_text(BASIS_CONFLICT_NOTE) == []


LAB_EVIDENCE = [EvidenceItem(feature="hba1c", value=5.2, unit="%", source_stage="lab_report")]
PROFILE_EVIDENCE = [
    EvidenceItem(feature="bmi", value=24.97, unit="kg/m2", source_stage="patient_profile")
]


def test_no_abnormal_findings_is_healthy():
    data = fuse(
        [
            decision(C.DIABETES, DecisionStatus.NOT_INDICATED, RiskLevel.LOW, evidence=LAB_EVIDENCE),
            decision(C.ANEMIA, DecisionStatus.NOT_INDICATED, RiskLevel.LOW),
        ]
    )
    assert data.summary.overall_status == STATUS_HEALTHY
    assert data.summary.abnormal_conditions == []
    assert set(data.summary.normal_conditions) == {C.DIABETES, C.ANEMIA}


def test_abnormal_without_high_risk_is_needs_monitoring():
    data = fuse(
        [
            decision(C.DIABETES, DecisionStatus.BORDERLINE, RiskLevel.MEDIUM),
            decision(C.ANEMIA, DecisionStatus.NOT_INDICATED, RiskLevel.LOW),
        ]
    )
    assert data.summary.overall_status == STATUS_NEEDS_MONITORING
    assert data.summary.abnormal_conditions == [C.DIABETES]
    assert data.summary.critical_conditions == []


def test_abnormal_with_high_risk_is_needs_medical_attention():
    data = fuse(
        [
            decision(C.DIABETES, DecisionStatus.INDICATED, RiskLevel.HIGH),
            decision(C.ANEMIA, DecisionStatus.BORDERLINE, RiskLevel.MEDIUM),
        ]
    )
    assert data.summary.overall_status == STATUS_NEEDS_MEDICAL_ATTENTION
    assert data.summary.critical_conditions == [C.DIABETES]
    assert data.summary.overall_risk is RiskLevel.HIGH


def test_a_report_where_nothing_could_be_assessed_is_NOT_healthy():
    data = fuse(
        [
            decision(C.DIABETES, DecisionStatus.INSUFFICIENT_DATA, None),
            decision(C.KIDNEY_DISEASE, DecisionStatus.INSUFFICIENT_DATA, None),
        ]
    )
    assert data.summary.overall_status is None
    assert data.summary.any_assessed is False
    assert data.summary.assessment_incomplete is True
    assert set(data.summary.unassessed_conditions) == {C.DIABETES, C.KIDNEY_DISEASE}


def test_a_partly_readable_report_is_still_given_a_status_but_flagged():
    data = fuse(
        [
            decision(C.DIABETES, DecisionStatus.NOT_INDICATED, RiskLevel.LOW, evidence=LAB_EVIDENCE),
            decision(C.KIDNEY_DISEASE, DecisionStatus.INSUFFICIENT_DATA, None),
        ]
    )
    assert data.summary.overall_status == STATUS_HEALTHY
    assert data.summary.any_assessed is True
    assert data.summary.assessment_incomplete is True
    assert data.summary.unassessed_conditions == [C.KIDNEY_DISEASE]


def test_clean_from_the_profile_alone_is_not_healthy_and_has_no_risk():
    data = fuse(
        [
            decision(C.OBESITY, DecisionStatus.NOT_INDICATED, RiskLevel.LOW, evidence=PROFILE_EVIDENCE),
            decision(C.UNDERWEIGHT, DecisionStatus.NOT_INDICATED, RiskLevel.LOW, evidence=PROFILE_EVIDENCE),
        ]
    )
    assert data.summary.overall_status is None
    assert data.summary.overall_risk is None
    assert data.summary.any_assessed is False


def test_a_model_whose_lab_inputs_were_all_imputed_is_not_a_lab_result():
    imputed = [
        EvidenceItem(feature="hba1c", value=None, source_stage="model_input"),
        EvidenceItem(feature="age", value=20, unit="years", source_stage="model_input"),
    ]
    data = fuse([ml(C.HEART_DISEASE, status=DecisionStatus.NOT_INDICATED, risk=RiskLevel.LOW,
                    confidence=0.05, evidence=imputed)])
    assert data.summary.overall_status is None


def test_one_test_result_anywhere_is_enough_for_healthy():
    data = fuse(
        [
            decision(C.OBESITY, DecisionStatus.NOT_INDICATED, RiskLevel.LOW, evidence=PROFILE_EVIDENCE),
            decision(C.DIABETES, DecisionStatus.NOT_INDICATED, RiskLevel.LOW, evidence=LAB_EVIDENCE),
        ]
    )
    assert data.summary.overall_status == STATUS_HEALTHY
    assert data.summary.overall_risk is RiskLevel.LOW


def test_a_flagged_profile_finding_is_still_reported():
    data = fuse(
        [decision(C.OBESITY, DecisionStatus.INDICATED, RiskLevel.MEDIUM, evidence=PROFILE_EVIDENCE)]
    )
    assert data.summary.overall_status == STATUS_NEEDS_MONITORING
    assert data.summary.overall_risk is RiskLevel.MEDIUM


def test_prioritisation_orders_by_risk_and_lists_each_condition_once():
    data = fuse(
        [
            decision(C.ANEMIA, DecisionStatus.BORDERLINE, RiskLevel.MEDIUM),
            decision(C.DIABETES, DecisionStatus.INDICATED, RiskLevel.HIGH),
            decision(C.DIABETES, DecisionStatus.BORDERLINE, RiskLevel.MEDIUM),
            decision(C.OBESITY, DecisionStatus.NOT_INDICATED, RiskLevel.LOW),
        ]
    )
    rows = data.summary.prioritized
    assert [r.condition for r in rows] == [C.DIABETES, C.ANEMIA, C.OBESITY]
    assert len({r.condition for r in rows}) == len(rows), "a condition was counted twice"
    assert [r.risk for r in rows] == [RiskLevel.HIGH, RiskLevel.MEDIUM, RiskLevel.LOW]


def test_two_rules_on_one_condition_do_not_double_weight_it():
    data = fuse([decision(C.DIABETES), decision(C.DIABETES), decision(C.DIABETES)])
    assert len(data.summary.prioritized) == 1
    assert data.summary.condition_count == 1
    assert data.summary.raw_decision_count == 3
    assert data.summary.collapsed_decision_count == 2


def test_unflagged_conditions_sort_below_flagged_ones():
    data = fuse(
        [
            decision(C.DIABETES, DecisionStatus.NOT_INDICATED, RiskLevel.LOW),
            decision(C.ANEMIA, DecisionStatus.BORDERLINE, RiskLevel.MEDIUM),
        ]
    )
    assert [r.condition for r in data.summary.prioritized] == [C.ANEMIA, C.DIABETES]
    assert [r.flagged for r in data.summary.prioritized] == [True, False]


def test_every_upstream_warning_reaches_the_fused_result_with_its_origin():
    canary = "CANARY: page 2 could not be read"
    data = run_decision_fusion(
        engineered={**FULL_FEATURES, "warnings": [canary]},
        registry=registry_with(FakeDiabetesPredictor()),
    )
    matches = [w for w in data.all_warnings if w.message == canary]
    assert len(matches) == 1, "dropped or duplicated by Modules 15/16"
    assert matches[0].stage not in ("decisions", STAGE_FUSION)


def test_module_16_stamps_its_own_stage_on_its_own_warnings():
    data = fuse(
        [
            decision(C.KIDNEY_DISEASE, DecisionStatus.INDICATED, RiskLevel.HIGH),
            ml(
                C.KIDNEY_DISEASE,
                status=DecisionStatus.INSUFFICIENT_DATA,
                risk=None,
                confidence=None,
            ),
        ]
    )
    own = [w for w in data.all_warnings if w.stage == STAGE_FUSION]
    assert own and all(w.module == 16 for w in own)
    assert {w.message for w in own} == set(data.warnings)


def test_every_warning_module_16_produces_is_safe_to_show_a_patient():
    data = fuse(
        [
            decision(
                C.HEART_DISEASE, metadata={"factor_count": 3, "band_label": "counted"}
            ),
            ml(C.HEART_DISEASE, confidence=0.7),
            decision(C.KIDNEY_DISEASE, DecisionStatus.INDICATED, RiskLevel.HIGH),
            ml(
                C.KIDNEY_DISEASE,
                status=DecisionStatus.INSUFFICIENT_DATA,
                risk=None,
                confidence=None,
            ),
        ]
    )
    assert data.warnings
    for message in data.warnings:
        assert scan_text(message) == [], message


def test_one_source_failing_still_produces_fused_decisions(monkeypatch):
    monkeypatch.setattr(DE, "predict_all", lambda *a, **k: 1 / 0)
    data = run_decision_fusion(engineered=FULL_FEATURES)
    assert data.fused, "the rule engine's decisions were lost with the model's"
    assert data.summary.sources_failed == [DE.ML_SOURCE_NAME]
    assert data.summary.assessment_incomplete is True


def test_both_sources_failing_yields_no_status_rather_than_a_reassuring_one(monkeypatch):
    monkeypatch.setattr(DE, "evaluate_rules", lambda *a, **k: 1 / 0)
    monkeypatch.setattr(DE, "predict_all", lambda *a, **k: 1 / 0)
    data = run_decision_fusion(engineered=FULL_FEATURES)
    assert data.fused == []
    assert data.summary.overall_status is None
    assert data.summary.overall_risk is None
    assert len(data.summary.sources_failed) == 2


def test_a_realistic_report_end_to_end():
    data = run_decision_fusion(
        engineered=FULL_FEATURES, registry=registry_with(FakeDiabetesPredictor())
    )

    assert len({f.condition for f in data.fused}) == len(data.fused)
    assert data.summary.raw_decision_count > data.summary.fused_count

    diabetes = next(f for f in data.fused if f.condition == C.DIABETES)
    assert diabetes.hybrid is True
    assert diabetes.sources == ["Clinical Rule Engine", "Fake Forest"]
    assert diabetes.confidence == pytest.approx(0.77)
    assert diabetes.risk is RiskLevel.HIGH
    assert len(diabetes.decision_ids) >= 2

    for fused in data.fused:
        assert len(fused.sources) == len(set(fused.sources))

    assert data.summary.overall_status == STATUS_NEEDS_MEDICAL_ATTENTION
    assert data.summary.overall_risk is RiskLevel.HIGH
    assert data.summary.critical_conditions
    assert data.summary.prioritized
    assert isinstance(data.all_warnings, list)
    assert data.upstream_summary is not None

    assert data.collection.collected
    assert data.collection.groups
    assert data.metadata["fused_by"] == ["condition"]


def test_the_whole_result_serialises_to_json():
    data = run_decision_fusion(
        engineered=FULL_FEATURES, registry=registry_with(FakeDiabetesPredictor())
    )
    payload = data.model_dump(mode="json")
    assert payload["fused"]
    assert payload["summary"]["overall_status"]
    assert payload["collection"]["collected"]


def test_fuse_decisions_accepts_module_15s_object_and_a_bare_list_alike():
    from app.services.decision_engine import collect_decisions

    collection = collect_decisions(
        engineered=FULL_FEATURES, registry=SilentRegistry()
    )
    from_collection = fuse_decisions(collection)
    from_list = fuse_decisions(collection.raw_decisions())
    assert [f.condition for f in from_collection.fused] == [
        f.condition for f in from_list.fused
    ]
    assert [f.risk for f in from_collection.fused] == [f.risk for f in from_list.fused]


def test_fuse_decisions_refuses_something_that_is_not_a_decision_set():
    with pytest.raises(TypeError, match="DecisionCollectionData"):
        fuse_decisions("not decisions")
