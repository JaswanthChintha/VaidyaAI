"""Modules 17-20 -- Clinical Report, overall status, priority, explainability.

Framework-independent tests: no HTTP, no API key, no network, no training.
Every feature payload here is hand-written from invented values.

The four things this file exists to hold in place, all of them failure modes
that a passing "it built a report" test would not catch:

1. An absence of findings must NEVER render as a clean bill of health.
2. Prioritisation must be per CONDITION, and a skipped condition must not sort
   as low-risk.
3. A value that was read and refused must be reported as found-but-not-trusted,
   never as absent.
4. A model's global feature importances must never be labelled as a
   per-patient explanation.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from app.data import conditions as C
from app.data.recommendation_catalog import RECOMMENDATIONS, scan_text
from app.schemas.decisions import DecisionStatus, RiskLevel
from app.schemas.report import (
    AVAILABILITY_FOUND_BUT_NOT_TRUSTED,
    AVAILABILITY_NOT_PRESENT,
    OVERALL_STATUS_LABELS,
    PRIORITY_LOW,
    PRIORITY_NOT_ASSESSED,
    RULE_ABNORMAL_WITHOUT_HIGH_RISK,
    RULE_ABNORMAL_WITH_HIGH_RISK,
    RULE_NOTHING_ASSESSED,
    RULE_NO_ABNORMAL_FINDINGS,
    STATUS_NOT_ASSESSED,
    TIER_FLAGGED,
    TIER_NORMAL,
    TIER_UNASSESSED,
    ClinicalReport,
)
from app.schemas.fusion import (
    STATUS_HEALTHY,
    STATUS_NEEDS_MEDICAL_ATTENTION,
    STATUS_NEEDS_MONITORING,
)
from app.services.report_builder import (
    extract_rejected_features,
    generate_report,
    overall_status,
    prioritise,
    report_text_violations,
)


# --------------------------------------------------------------------------
# Payload helpers -- invented values, never real patient data
# --------------------------------------------------------------------------


def feature(
    name: str,
    value: Any,
    unit: Optional[str] = None,
    source: str = "lab_report",
    **extra: Any,
) -> Dict[str, Any]:
    return {"name": name, "value": value, "unit": unit, "source": source, **extra}


def engineered(**features: Dict[str, Any]) -> Dict[str, Any]:
    return {"features": dict(features)}


def healthy_payload() -> Dict[str, Any]:
    """Every value inside its configured band."""
    return engineered(
        hba1c=feature("hba1c", 5.1, "%"),
        blood_glucose=feature("blood_glucose", 88.0, "mg/dl"),
        hemoglobin=feature("hemoglobin", 14.2, "g/dl"),
        creatinine=feature("creatinine", 0.9, "mg/dl"),
        cholesterol=feature("cholesterol", 170.0, "mg/dl"),
        triglycerides=feature("triglycerides", 110.0, "mg/dl"),
        vitamin_d=feature("vitamin_d", 42.0, "ng/ml"),
        vitamin_b12=feature("vitamin_b12", 480.0, "pg/ml"),
        bmi=feature("bmi", 22.4, "kg/m2", "patient_profile"),
        age=feature("age", 34, "years", "patient_profile"),
        gender=feature("gender", "female", None, "patient_profile"),
        hypertension=feature("hypertension", False, None, "patient_profile"),
        heart_disease=feature("heart_disease", False, None, "patient_profile"),
        smoking_history=feature(
            "smoking_history", "never", None, "patient_profile"
        ),
    )


def borderline_payload() -> Dict[str, Any]:
    """One abnormal finding, nothing in a High band."""
    return engineered(
        hemoglobin=feature("hemoglobin", 14.2, "g/dl"),
        vitamin_d=feature("vitamin_d", 24.0, "ng/ml"),
        age=feature("age", 34, "years", "patient_profile"),
    )


def high_risk_payload() -> Dict[str, Any]:
    """A realistic, heavily abnormal panel -- the full end-to-end case."""
    return engineered(
        hba1c=feature("hba1c", 8.4, "%"),
        blood_glucose=feature("blood_glucose", 186.0, "mg/dl"),
        hemoglobin=feature("hemoglobin", 10.4, "g/dl"),
        creatinine=feature("creatinine", 2.1, "mg/dl"),
        cholesterol=feature("cholesterol", 268.0, "mg/dl"),
        triglycerides=feature("triglycerides", 320.0, "mg/dl"),
        vitamin_d=feature("vitamin_d", 12.0, "ng/ml"),
        vitamin_b12=feature("vitamin_b12", 140.0, "pg/ml"),
        bmi=feature("bmi", 33.8, "kg/m2", "patient_profile"),
        age=feature("age", 62, "years", "patient_profile"),
        gender=feature("gender", "male", None, "patient_profile"),
        hypertension=feature("hypertension", True, None, "patient_profile"),
        heart_disease=feature("heart_disease", False, None, "patient_profile"),
        smoking_history=feature(
            "smoking_history", "current", None, "patient_profile"
        ),
    )


def rejected_creatinine_payload() -> Dict[str, Any]:
    """Creatinine printed in a unit Module 5 could not convert.

    THE CASE THE AUDIT NAMED. The value IS in the report. Module 6 reads it and
    refuses it. Modules 8 and 9/10 never see it, so their evidence says it "was
    not available in the submitted report" -- which is false.
    """
    return engineered(
        hba1c=feature("hba1c", 6.8, "%"),
        creatinine=feature(
            "creatinine",
            88.4,
            "umol/L",
            canonical_unit=False,
            provenance={
                "source": "lab_report",
                "original_test_name": "Serum Creatinine",
                "original_unit": "umol/L",
                "original_value_numeric": 88.4,
                "unit_recognised": False,
                "page_number": 1,
            },
        ),
    )


def report_for(payload: Dict[str, Any]) -> ClinicalReport:
    return generate_report(engineered=payload)


# ==========================================================================
# Module 18 -- the three spec outcomes, the fourth case and the fifth
# ==========================================================================


def test_no_abnormal_findings_gives_healthy():
    report = report_for(healthy_payload())
    assert report.overall.status == STATUS_HEALTHY
    assert report.overall.status_label == STATUS_HEALTHY
    assert report.overall.rule_applied == RULE_NO_ABNORMAL_FINDINGS
    assert report.overall.any_assessed is True
    assert report.abnormal_findings == []


def test_abnormal_findings_without_high_risk_gives_needs_monitoring():
    report = report_for(borderline_payload())
    assert report.abnormal_findings, "the fixture stopped producing a finding"
    assert all(
        c.risk is not RiskLevel.HIGH for c in report.conditions if c.flagged
    ), "the fixture now produces a High risk; it is meant to be the middle case"
    assert report.overall.status == STATUS_NEEDS_MONITORING
    assert report.overall.rule_applied == RULE_ABNORMAL_WITHOUT_HIGH_RISK


def test_an_abnormal_finding_with_high_risk_gives_needs_medical_attention():
    report = report_for(high_risk_payload())
    assert report.overall.status == STATUS_NEEDS_MEDICAL_ATTENTION
    assert report.overall.rule_applied == RULE_ABNORMAL_WITH_HIGH_RISK
    assert report.overall.high_risk_condition_count >= 1
    assert report.critical_conditions


# ---- THE FOURTH CASE -----------------------------------------------------


def test_nothing_assessed_is_never_reported_as_healthy():
    """The single most dangerous output this system can produce.

    "No abnormal findings -> Healthy" is VACUOUSLY true for a report in which
    nothing could be read. It must not fire.
    """
    report = generate_report()
    assert report.overall.status is None
    assert report.overall.status_label == STATUS_NOT_ASSESSED
    assert report.overall.status_label != STATUS_HEALTHY
    assert report.overall.rule_applied == RULE_NOTHING_ASSESSED
    assert report.overall.any_assessed is False
    assert report.overall.complete is False
    assert report.overall.caveat, "the fourth case must carry its caveat"
    assert report.overall_risk is None, "no risk may be invented from nothing"


def test_the_fourth_case_label_is_not_one_of_the_specs_three():
    assert STATUS_NOT_ASSESSED in OVERALL_STATUS_LABELS
    assert STATUS_NOT_ASSESSED not in (
        STATUS_HEALTHY,
        STATUS_NEEDS_MONITORING,
        STATUS_NEEDS_MEDICAL_ATTENTION,
    )


def test_nothing_assessed_says_so_in_a_warning_too():
    report = generate_report()
    messages = [w.message for w in report.validation_warnings if w.stage == "report"]
    assert any("nothing in this report could be assessed" in m for m in messages)


# ---- THE FIFTH CASE: PARTIAL ASSESSMENT ----------------------------------


def test_a_partially_assessed_report_is_not_presented_as_complete():
    report = report_for(
        engineered(hemoglobin=feature("hemoglobin", 14.2, "g/dl"))
    )
    assert report.overall.status == STATUS_HEALTHY, "what was assessed was clean"
    assert report.overall.complete is False
    assert report.overall.caveat is not None
    assert report.overall.unassessed_conditions, "the gap must be named, not vague"
    assert report.overall.unassessed_condition_count == len(
        report.overall.unassessed_conditions
    )


def test_a_complete_assessment_carries_no_caveat():
    report = report_for(high_risk_payload())
    assert report.overall.complete is True
    assert report.overall.caveat is None


def test_the_caveat_is_non_null_exactly_when_incomplete():
    for payload in (
        healthy_payload(),
        borderline_payload(),
        high_risk_payload(),
        rejected_creatinine_payload(),
    ):
        report = report_for(payload)
        assert (report.overall.caveat is not None) is (not report.overall.complete)


def test_module_17_and_module_16_never_disagree_about_the_status():
    for payload in (healthy_payload(), borderline_payload(), high_risk_payload()):
        report = report_for(payload)
        assert report.overall.status == report.fusion.summary.overall_status
        assert report.overall.risk == report.fusion.summary.overall_risk


def test_overall_status_is_callable_on_its_own():
    """Module 27 wants the health card without building a whole report."""
    report = report_for(high_risk_payload())
    assert overall_status(report.fusion) == report.overall


# ==========================================================================
# Module 19 -- prioritisation
# ==========================================================================


def test_prioritisation_is_one_row_per_condition():
    report = report_for(high_risk_payload())
    conditions = [p.condition for p in report.prioritized]
    assert len(conditions) == len(set(conditions))
    assert set(conditions) == {f.condition for f in report.fusion.fused}


def test_two_rule_decisions_for_one_condition_do_not_double_weight_it():
    """The audit's requirement, stated as a test.

    HbA1c 8.4 AND fasting glucose 186 both fire a `Diabetes` rule. The rule
    engine is right to emit two decisions -- one per RULE -- but Diabetes must
    appear ONCE in the priority list, and must not outrank anything merely
    because two relevant tests were ordered.
    """
    report = report_for(high_risk_payload())

    raw = [
        c
        for c in report.fusion.collection.collected
        if c.decision.condition == C.DIABETES
        and c.decision.source == "Clinical Rule Engine"
    ]
    assert len(raw) >= 2, "the rule engine no longer emits two Diabetes decisions"

    rows = [p for p in report.prioritized if p.condition == C.DIABETES]
    assert len(rows) == 1
    assert rows[0].contributing_decision_count >= 2

    # And the count is not part of the ordering: a row with more contributing
    # decisions does not outrank a row of equal tier and risk with fewer.
    for earlier, later in zip(report.prioritized, report.prioritized[1:]):
        if (earlier.tier, earlier.risk) == (later.tier, later.risk):
            assert C.condition_rank(earlier.condition) < C.condition_rank(
                later.condition
            ), "ties are broken by canonical order, not by decision count"


def test_an_unassessed_condition_does_not_sort_as_low_risk():
    """It has NO risk level. Filing it under Low would bury an open question."""
    report = report_for(
        engineered(hemoglobin=feature("hemoglobin", 14.2, "g/dl"))
    )
    unassessed = [p for p in report.prioritized if not p.assessed]
    normal_low = [
        p for p in report.prioritized if p.assessed and not p.flagged
    ]
    assert unassessed, "the fixture must leave something unassessed"
    assert normal_low, "the fixture must also produce a settled finding"

    for row in unassessed:
        assert row.risk is None
        assert row.priority == PRIORITY_NOT_ASSESSED
        assert row.priority != PRIORITY_LOW
        assert row.tier == TIER_UNASSESSED

    assert max(p.rank for p in unassessed) < min(p.rank for p in normal_low), (
        "an unassessed condition must appear ABOVE a settled normal finding"
    )


def test_flagged_findings_outrank_unassessed_conditions():
    report = report_for(high_risk_payload())
    flagged = [p for p in report.prioritized if p.flagged]
    unassessed = [p for p in report.prioritized if not p.assessed]
    assert flagged
    if unassessed:
        assert max(p.rank for p in flagged) < min(p.rank for p in unassessed)


def test_priority_order_is_high_then_medium_then_low_within_the_flagged_tier():
    report = report_for(high_risk_payload())
    flagged = [p for p in report.prioritized if p.tier == TIER_FLAGGED]
    ranks = {RiskLevel.HIGH: 0, RiskLevel.MEDIUM: 1, RiskLevel.LOW: 2, None: 3}
    seen = [ranks[p.risk] for p in flagged]
    assert seen == sorted(seen)


def test_tiers_are_ordered_flagged_then_unassessed_then_normal():
    report = report_for(high_risk_payload())
    tiers = [p.tier for p in report.prioritized]
    assert tiers == sorted(tiers)
    assert set(tiers) <= {TIER_FLAGGED, TIER_UNASSESSED, TIER_NORMAL}


def test_prioritise_is_callable_on_its_own():
    report = report_for(high_risk_payload())
    assert prioritise(report.fusion.fused) == report.prioritized


def test_the_condition_list_follows_the_priority_order():
    report = report_for(high_risk_payload())
    assert [c.condition for c in report.conditions] == [
        p.condition for p in report.prioritized
    ]
    assert [c.rank for c in report.conditions] == sorted(
        c.rank for c in report.conditions
    )


# ==========================================================================
# Module 20 -- evidence and explainability
# ==========================================================================


def test_a_rejected_value_is_found_but_not_trusted_never_absent():
    """THE JOIN. The audit's item 3, stated as a test.

    A reader must be told "we found this and could not trust its unit", never
    "it wasn't there".
    """
    report = report_for(rejected_creatinine_payload())
    assert "creatinine" in report.explainability.rejected_features_joined

    lines = [
        line
        for explanation in report.explainability.conditions
        for line in explanation.evidence
        if line.feature == "creatinine"
    ]
    assert lines, "no evidence cites creatinine at all"

    for line in lines:
        assert line.availability == AVAILABILITY_FOUND_BUT_NOT_TRUSTED
        assert line.availability != AVAILABILITY_NOT_PRESENT
        assert line.rejected is True
        assert line.rejection_code == "NON_CANONICAL_UNIT"
        assert line.rejection_reason
        assert line.rejected_value == 88.4
        assert line.rejected_unit == "umol/L"
        assert "not found in the submitted report" not in line.explanation
        assert "was printed in the submitted report" in line.explanation


def test_the_producers_original_note_is_kept_but_no_longer_what_is_shown():
    """The trace back to what Module 8 actually said must survive the join."""
    report = report_for(rejected_creatinine_payload())
    line = next(
        line
        for explanation in report.explainability.conditions
        for line in explanation.evidence
        if line.feature == "creatinine"
    )
    assert line.note == "this value was not available in the submitted report"
    assert line.explanation != line.note
    assert line.availability == AVAILABILITY_FOUND_BUT_NOT_TRUSTED


def test_the_rejection_reason_reaches_the_evidence_with_its_origin():
    report = report_for(rejected_creatinine_payload())
    line = next(
        line
        for explanation in report.explainability.conditions
        for line in explanation.evidence
        if line.feature == "creatinine"
    )
    assert line.related_warnings, "the validation warning was not joined"
    assert all(w.stage == "validation" for w in line.related_warnings)
    assert all(w.module == 6 for w in line.related_warnings)


def test_a_genuinely_absent_value_still_reads_as_absent():
    """The correction must apply ONLY to values that were actually rejected."""
    report = report_for(engineered(hba1c=feature("hba1c", 6.8, "%")))
    absent = [
        line
        for explanation in report.explainability.conditions
        for line in explanation.evidence
        if line.feature == "creatinine"
    ]
    assert absent, "the kidney topic no longer cites creatinine"
    assert all(
        line.availability == AVAILABILITY_NOT_PRESENT for line in absent
    )
    assert all(line.rejected is False for line in absent)


def test_a_rejected_value_still_appears_as_a_laboratory_row():
    report = report_for(rejected_creatinine_payload())
    row = next(v for v in report.laboratory_values if v.feature == "creatinine")
    assert row.usable is False
    assert row.status == "rejected"
    assert row.value == 88.4
    assert row.rejection_code == "NON_CANONICAL_UNIT"
    assert "creatinine" in report.document.rejected_features


def test_rule_evidence_names_the_value_the_threshold_and_the_classification():
    """Spec Module 20: rule-triggering value, condition, classification."""
    report = report_for(high_risk_payload())
    diabetes = next(
        e for e in report.explainability.conditions if e.condition == C.DIABETES
    )
    rule_sources = [s for s in diabetes.sources if s.rule is not None]
    assert rule_sources, "no rule contribution for Diabetes"

    rule = rule_sources[0].rule
    assert rule.rule_ids, "the rule that fired is not named"
    assert rule.classifications, "the rule's own band wording is missing"
    assert rule.triggering_values, "nothing is named as having triggered it"
    for line in rule.triggering_values:
        assert line.feature
        assert line.value is not None
        assert line.threshold is not None
        assert line.comparator
        assert line.classification


def test_ml_evidence_names_model_prediction_probability_and_inputs():
    """Spec Module 20: model source, prediction, probability, input evidence."""
    report = report_for(high_risk_payload())
    ml_sources = [
        source
        for explanation in report.explainability.conditions
        for source in explanation.sources
        if source.ml is not None and not source.ml.skipped
    ]
    assert ml_sources, "no model produced a prediction for this panel"

    for source in ml_sources:
        ml = source.ml
        assert ml.model_name
        assert ml.prediction in set(DecisionStatus)
        assert ml.probability is not None
        assert 0.0 <= ml.probability <= 1.0
        assert ml.input_evidence, "a prediction with no input evidence"
        assert ml.probability_semantics


def test_ml_feature_importance_is_labelled_global_not_per_patient():
    """Spec section 24 forbids unsupported certainty.

    Module 10/11/12 importances are mean impurity decrease over the TRAINING
    SET. They rank features for the model; they are not why THIS patient got
    THIS result, and the report must not imply that they are.
    """
    report = report_for(high_risk_payload())
    with_importance = [
        source.ml
        for explanation in report.explainability.conditions
        for source in explanation.sources
        if source.ml is not None and source.ml.global_feature_importance
    ]
    assert with_importance, "no model reported feature importances at all"

    for ml in with_importance:
        assert ml.importance_scope == "global_model_level"
        assert ml.importance_is_per_patient is False
        assert ml.importance_caveat
        lowered = ml.importance_caveat.lower()
        assert "not a per-patient explanation" in lowered
        assert "per_patient" not in ml.importance_scope

    assert report.explainability.ml_importance_scope == "global_model_level"


def test_every_condition_shows_the_input_evidence_decision_chain():
    report = report_for(high_risk_payload())
    assert report.explainability.conditions
    for explanation in report.explainability.conditions:
        assert explanation.chain == ("Input", "Evidence", "Decision")
        assert explanation.sources, f"{explanation.condition} has no source"
        for source in explanation.sources:
            assert source.assessment_basis
            assert source.assessment_basis_family


def test_fusion_explainability_names_the_contributing_sources():
    """Spec section 13: 'Clinical Rule Engine + Random Forest = Fused'."""
    report = report_for(high_risk_payload())
    hybrid = [e for e in report.explainability.conditions if e.hybrid]
    assert hybrid, "no condition was assessed by both a rule and a model"
    for explanation in hybrid:
        assert explanation.fusion_explanation
        assert " + " in explanation.fusion_explanation


def test_extract_rejected_features_finds_the_map_in_every_relayed_shape():
    record = {
        "name": "creatinine",
        "value": 884.0,
        "unit": "umol/L",
        "reason_code": "NON_CANONICAL_UNIT",
        "reason": "reported in a unit that could not be converted",
    }
    shapes: List[Dict[str, Any]] = [
        {"rejected_features": {"creatinine": record}},
        {"rejected": {"creatinine": record}},
        {"validated": {"valid": {}, "rejected": {"creatinine": record}}},
        {"data": {"valid": {}, "rejected": {"creatinine": record}}},
        {"success": True, "data": {"valid": {}, "rejected": {"creatinine": record}}},
    ]
    for shape in shapes:
        found = extract_rejected_features(shape)
        assert "creatinine" in found, shape
        assert found["creatinine"].reason_code == "NON_CANONICAL_UNIT"

    assert extract_rejected_features({}) == {}
    assert extract_rejected_features(None) == {}


def test_a_malformed_rejection_record_does_not_fail_the_report():
    found = extract_rejected_features(
        {"rejected": {"creatinine": "not an object", "hba1c": {"reason": "x"}}}
    )
    assert "creatinine" not in found
    assert found["hba1c"].name == "hba1c"


# ==========================================================================
# Module 17 -- the report itself
# ==========================================================================


def test_a_realistic_full_feature_set_produces_every_section():
    report = report_for(high_risk_payload())

    assert report.report_version
    assert report.patient.provided_fields
    assert report.laboratory_values
    assert report.conditions
    assert report.overall.status_label
    assert report.overall_risk is not None
    assert report.critical_conditions
    assert report.normal_findings or report.abnormal_findings
    assert report.prioritized
    assert report.explainability.conditions
    assert report.recommendations
    assert report.validation_warnings is not None
    assert report.metadata["modules"]["clinical_report"] == 17
    assert report.summary.condition_count == len(report.conditions)
    # The whole fusion layer is nested verbatim, so Module 32 and Modules
    # 28-30 can always reach the raw decision behind any line above.
    assert report.fusion.fused
    assert report.fusion.collection.collected


def test_the_report_round_trips_through_json():
    """Backend and frontend consume the same standardized format (spec 17)."""
    report = report_for(high_risk_payload())
    restored = ClinicalReport.model_validate(report.model_dump(mode="json"))
    assert restored.overall.status_label == report.overall.status_label
    assert [c.condition for c in restored.conditions] == [
        c.condition for c in report.conditions
    ]


def test_warnings_from_every_stage_reach_the_report_with_their_origin():
    """Dropping upstream warnings has been a real defect twice on this project."""
    report = generate_report(
        engineered={
            **high_risk_payload(),
            "upstream": {
                "provided": True,
                "extraction_confidence": 0.61,
                "pages": [
                    {"page_number": 1, "raw_text_available": True},
                    {"page_number": 2, "raw_text_available": False},
                ],
                "pages_unreadable": [2],
            },
            "warnings": ["CANARY-MODULE-5"],
            "all_warnings": [
                {
                    "stage": "extraction",
                    "module": 4,
                    "message": "CANARY-MODULE-4",
                },
                {
                    "stage": "feature_engineering",
                    "module": 5,
                    "message": "CANARY-MODULE-5",
                },
            ],
        }
    )

    messages = {w.message: w for w in report.validation_warnings}
    assert "CANARY-MODULE-4" in messages
    assert messages["CANARY-MODULE-4"].stage == "extraction"
    assert messages["CANARY-MODULE-4"].module == 4
    assert "CANARY-MODULE-5" in messages
    assert messages["CANARY-MODULE-5"].stage == "feature_engineering"
    assert messages["CANARY-MODULE-5"].module == 5

    stages = {w.stage for w in report.validation_warnings}
    assert {"extraction", "feature_engineering"} <= stages
    assert report.warnings_by_stage["extraction"] >= 1
    assert sum(report.warnings_by_stage.values()) == len(report.validation_warnings)


def test_pages_unreadable_and_extraction_confidence_are_surfaced():
    report = generate_report(
        engineered={
            **high_risk_payload(),
            "upstream": {
                "provided": True,
                "extraction_confidence": 0.42,
                "pages": [
                    {"page_number": 1, "raw_text_available": True},
                    {"page_number": 2, "raw_text_available": False},
                    {"page_number": 3, "raw_text_available": False},
                ],
                "pages_unreadable": [2, 3],
            },
        }
    )
    assert report.document.pages_unreadable == [2, 3]
    assert report.document.pages_unreadable_count == 2
    assert report.document.partial_document is True
    assert report.document.extraction_confidence == pytest.approx(0.42)
    assert report.document.page_count == 3
    assert any(
        "could not be read" in w.message
        for w in report.validation_warnings
        if w.stage == "report"
    )


def test_recommendations_are_deduplicated_and_catalogue_sourced():
    report = report_for(high_risk_payload())
    codes = [r.code for r in report.recommendations]
    assert codes, "no recommendation reached the report"
    assert len(codes) == len(set(codes)), "a recommendation was repeated"

    for rec in report.recommendations:
        assert rec.code in RECOMMENDATIONS, "a code outside the catalogue"
        # The text is RE-READ from the catalogue, not copied from the decision.
        assert rec.text == RECOMMENDATIONS[rec.code].text
        assert rec.category == RECOMMENDATIONS[rec.code].category
        assert rec.conditions, "a recommendation with no condition behind it"

    # A recommendation carried by several conditions is consolidated into one
    # entry that records every condition behind it (spec Module 16 point 5).
    consolidated = [r for r in report.recommendations if r.occurrences > 1]
    assert consolidated
    assert all(len(r.conditions) >= 1 for r in consolidated)


def test_no_report_text_asserts_a_diagnosis_a_medication_or_a_dosage():
    """The structural safety property, verified rather than trusted.

    Recommendation text comes from the reviewed catalogue by code, band labels
    are import-time scanned by Module 8, and every fixed string in
    `app/schemas/report.py` is scanned at import. This asserts the structure
    actually held over a real report.
    """
    for payload in (
        healthy_payload(),
        borderline_payload(),
        high_risk_payload(),
        rejected_creatinine_payload(),
    ):
        report = report_for(payload)
        assert report_text_violations(report) == []

    assert report_text_violations(generate_report()) == []


def test_the_violation_scanner_can_actually_fail():
    """A scanner that matches nothing is not a safety mechanism."""
    report = report_for(high_risk_payload())
    report.recommendations[0].text = "You have diabetes; take 500 mg daily."
    violations = report_text_violations(report)
    assert violations
    assert any("recommendations[0].text" == where for where, _, _ in violations)
    assert scan_text("You have diabetes"), "the scanner itself has rotted"


def test_basis_conflict_is_surfaced_side_by_side_and_not_blended():
    """The `Heart Disease` hazard: a risk-factor tally is not a probability."""
    report = report_for(high_risk_payload())
    conflicted = [c for c in report.conditions if c.basis_conflict]
    assert conflicted, "the fixture no longer produces a basis conflict"

    for condition in conflicted:
        assert condition.render_contributions_separately is True
        assert condition.basis_note
        assert len(condition.contributions) >= 2
        families = {c.assessment_basis_family for c in condition.contributions}
        assert len(families) >= 2, "the two questions were blended into one"
        for contribution in condition.contributions:
            # Each keeps ITS OWN wording, status and risk.
            assert contribution.band_labels
            assert contribution.status
        assert condition.condition in report.summary.basis_conflict_conditions

    explanation = next(
        e
        for e in report.explainability.conditions
        if e.condition == conflicted[0].condition
    )
    assert explanation.basis_conflict is True
    assert len(explanation.sources) >= 2


def test_patient_information_carries_context_but_no_identity():
    report = report_for(high_risk_payload())
    assert report.patient.contains_identity is False
    assert report.patient.age == 62
    assert report.patient.gender == "male"
    assert report.patient.bmi == pytest.approx(33.8)
    assert set(report.patient.model_dump()) == {
        "age",
        "gender",
        "bmi",
        "hypertension",
        "heart_disease",
        "smoking_history",
        "provided_fields",
        "contains_identity",
    }


def test_an_unknown_tri_state_is_reported_as_unknown_not_as_false():
    """The tri-state has survived every hop; this is the last place to lose it."""
    report = report_for(engineered(hba1c=feature("hba1c", 6.8, "%")))
    assert report.patient.hypertension is None
    assert report.patient.heart_disease is None
    assert "hypertension" not in report.patient.provided_fields

    recorded = report_for(high_risk_payload())
    assert recorded.patient.heart_disease is False
    assert "heart_disease" in recorded.patient.provided_fields


def test_laboratory_values_carry_the_reference_information_module_32_needs():
    report = generate_report(
        engineered=engineered(
            hba1c=feature(
                "hba1c",
                6.8,
                "%",
                provenance={
                    "source": "lab_report",
                    "original_test_name": "Glycated Haemoglobin",
                    "original_unit": "%",
                    "reference_low": 4.0,
                    "reference_high": 5.6,
                    "reference_range_raw": "4.0 - 5.6",
                    "flag": "high",
                    "page_number": 1,
                    "confidence": 0.94,
                },
            )
        )
    )
    row = next(v for v in report.laboratory_values if v.feature == "hba1c")
    assert row.reference_low == 4.0
    assert row.reference_high == 5.6
    assert row.reference_range_raw == "4.0 - 5.6"
    assert row.flag == "high"
    assert row.original_test_name == "Glycated Haemoglobin"
    assert row.page_number == 1
    assert row.extraction_confidence == pytest.approx(0.94)
    assert row.display_name


def test_the_report_never_invents_a_condition_or_a_risk():
    report = generate_report()
    assert report.conditions
    assert all(not c.assessed for c in report.conditions)
    assert all(c.risk is None for c in report.conditions)
    assert report.abnormal_findings == []
    assert report.critical_conditions == []
    assert report.normal_findings == []
    assert report.overall_risk is None


def test_generating_from_a_precomputed_fusion_does_not_re_run_the_models():
    """Modules 27/32 re-render a stored analysis without a second prediction."""
    first = report_for(high_risk_payload())
    again = generate_report(fusion=first.fusion)
    assert again.overall.status_label == first.overall.status_label
    assert [c.condition for c in again.conditions] == [
        c.condition for c in first.conditions
    ]
    assert [p.rank for p in again.prioritized] == [p.rank for p in first.prioritized]


def test_no_medical_value_reaches_the_logs(caplog):
    """The report holds clinical values by design. The logs must not."""
    import logging

    with caplog.at_level(logging.DEBUG):
        report_for(high_risk_payload())

    text = "\n".join(record.getMessage() for record in caplog.records)
    for canary in ("8.4", "186", "2.1", "268", "33.8", "hba1c", "creatinine"):
        assert canary not in text, f"{canary!r} reached the logs"


# --------------------------------------------------------------------------
# THE UNMAPPED COUNT SURVIVES THE HTTP BOUNDARY
#
# `ValidatedFeaturesInput` declares no `unmapped` field and sets
# `extra="ignore"`, so Module 6's unmapped rows are dropped silently on the way
# in. Deriving the count with `len(unmapped or [])` then returns 0 -- and 0
# here is not a missing number, it is the report stating that every parameter
# on the document was assessed.
#
# Measured on `Test 2.pdf` through the running service: seventeen sent, zero
# recorded, and the clinician summary went on to list four values as "the
# reported values". §6u found the same 0 on the patient page and routed around
# it in `dashboardService` rather than fixing it here.
# --------------------------------------------------------------------------


def test_the_count_comes_from_the_summary_when_the_list_was_dropped():
    """THE SHAPE THAT ARRIVES OVER HTTP: a summary, and no `unmapped` key."""
    from app.services.report_builder import _resolve_features

    view = _resolve_features(
        {
            "valid": {},
            "questionable": {},
            "missing_features": [],
            # No "unmapped" key at all -- this is what the request model leaves.
            "summary": {"unmapped_count": 17},
        },
        None,
    )
    assert view.unmapped_count == 17


def test_the_list_is_still_used_when_there_is_no_summary_count():
    """In-process callers hand over the whole object, list included."""
    from app.services.report_builder import _resolve_features

    view = _resolve_features(
        {
            "valid": {},
            "questionable": {},
            "missing_features": [],
            "unmapped": [{"test_name": "CRP"}, {"test_name": "SGPT"}],
            "summary": {},
        },
        None,
    )
    assert view.unmapped_count == 2


def test_a_report_with_nothing_unmapped_still_counts_zero():
    """Zero must remain reachable: it is the truth for a fully mapped report,
    and only a FALSE zero is the defect."""
    from app.services.report_builder import _resolve_features

    view = _resolve_features(
        {
            "valid": {},
            "questionable": {},
            "missing_features": [],
            "unmapped": [],
            "summary": {"unmapped_count": 0},
        },
        None,
    )
    assert view.unmapped_count == 0
