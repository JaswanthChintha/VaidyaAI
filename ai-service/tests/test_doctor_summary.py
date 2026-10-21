from __future__ import annotations

import ast
import logging
import os
from typing import Any, Dict, List, Optional, Set

import pytest

import app.services.doctor_summary as doctor_summary_module
from app.core.logging import get_logger, safe_meta
from app.schemas.doctor_summary import (
    LOW_DETECTION_RECALL,
    METRICS_NOT_RECORDED,
    METRICS_OPERATING_POINT_INCOMPLETE,
    SECTION_ANALYSIS_REFUSED,
    SECTION_DISABLED,
    SECTION_NOTHING_TO_GROUND,
    SECTION_NO_HISTORY,
    SECTION_NO_MATCH,
    SECTION_REASON_CODES,
    SECTION_RETRIEVAL_UNAVAILABLE,
    SECTION_SINGLE_REPORT,
    WEAK_DISCRIMINATION_ROC_AUC,
    DoctorSummary,
    DoctorSummaryRequest,
    OverallStatusView,
    SectionStatus,
)
from app.services.doctor_summary import (
    DISCLAIMER,
    build_doctor_summary,
    doctor_summary_document,
)
from app.services.report_builder import generate_report


def feature(
    name: str,
    number: Any,
    unit: Optional[str] = None,
    source: str = "lab_report",
) -> Dict[str, Any]:
    return {"name": name, "value": number, "unit": unit, "source": source}


def engineered(**features: Dict[str, Any]) -> Dict[str, Any]:
    return {"features": dict(features)}


def abnormal_payload() -> Dict[str, Any]:
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
        smoking_history=feature("smoking_history", "current", None, "patient_profile"),
    )


def healthy_payload() -> Dict[str, Any]:
    return engineered(
        hba1c=feature("hba1c", 5.1, "%"),
        blood_glucose=feature("blood_glucose", 88.0, "mg/dl"),
        hemoglobin=feature("hemoglobin", 14.2, "g/dl"),
        creatinine=feature("creatinine", 0.9, "mg/dl"),
        cholesterol=feature("cholesterol", 170.0, "mg/dl"),
        triglycerides=feature("triglycerides", 110.0, "mg/dl"),
        vitamin_d=feature("vitamin_d", 42.0, "ng/ml"),
        vitamin_b12=feature("vitamin_b12", 480.0, "pg/ml"),
        alt=feature("alt", 18.0, "u/l"),
        ast=feature("ast", 21.0, "u/l"),
        bilirubin_total=feature("bilirubin_total", 0.6, "mg/dl"),
        bmi=feature("bmi", 22.4, "kg/m2", "patient_profile"),
        age=feature("age", 34, "years", "patient_profile"),
        gender=feature("gender", "female", None, "patient_profile"),
        hypertension=feature("hypertension", False, None, "patient_profile"),
        heart_disease=feature("heart_disease", False, None, "patient_profile"),
        smoking_history=feature("smoking_history", "never", None, "patient_profile"),
    )


def value_entry(
    name: str,
    number: Any,
    unit: Optional[str] = None,
    *,
    ref_low: Optional[float] = None,
    ref_high: Optional[float] = None,
) -> Dict[str, Any]:
    provenance: Dict[str, Any] = {"source": "lab_report"}
    if ref_low is not None:
        provenance["reference_low"] = ref_low
    if ref_high is not None:
        provenance["reference_high"] = ref_high
    return {
        "name": name,
        "value": number,
        "unit": unit,
        "canonical_unit": True,
        "source": "lab_report",
        "provenance": provenance,
    }


def history_entry(report_id: str, date: str, **values: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "report_id": report_id,
        "chrono_date": date,
        "validated": {"valid": dict(values)},
    }


EARLIER = "2025-01-01T00:00:00Z"
LATER = "2025-07-01T00:00:00Z"


def two_report_history() -> List[Dict[str, Any]]:
    return [
        history_entry(
            "h1",
            EARLIER,
            hba1c=value_entry("hba1c", 7.0, "%", ref_low=4.0, ref_high=5.6),
            creatinine=value_entry(
                "creatinine", 1.4, "mg/dl", ref_low=0.7, ref_high=1.3
            ),
            cholesterol=value_entry("cholesterol", 240.0, "mg/dl", ref_high=200.0),
        ),
        history_entry(
            "h2",
            LATER,
            hba1c=value_entry("hba1c", 8.4, "%", ref_low=4.0, ref_high=5.6),
            creatinine=value_entry(
                "creatinine", 2.1, "mg/dl", ref_low=0.7, ref_high=1.3
            ),
            cholesterol=value_entry("cholesterol", 268.0, "mg/dl", ref_high=200.0),
        ),
    ]


def summarise(payload: Optional[Dict[str, Any]] = None, **request: Any) -> DoctorSummary:
    report = generate_report(engineered=payload if payload is not None else abnormal_payload())
    return build_doctor_summary(DoctorSummaryRequest(report=report, **request))


def app_import_closure(root: str) -> Set[str]:
    import importlib.util

    seen: Set[str] = set()
    queue = [root]
    while queue:
        name = queue.pop()
        if name in seen or not name.startswith("app"):
            continue
        seen.add(name)
        try:
            spec = importlib.util.find_spec(name)
        except (ImportError, AttributeError, ValueError):
            continue
        if spec is None or not spec.origin or not spec.origin.endswith(".py"):
            continue
        with open(spec.origin, encoding="utf-8") as handle:
            tree = ast.parse(handle.read(), filename=spec.origin)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                queue.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                queue.append(node.module)
                queue.extend(f"{node.module}.{a.name}" for a in node.names)
    return seen


MODEL_CLIENT_MODULES = (
    "app.services.gemini_client",
    "app.services.gemini_text",
    "app.services.explanation",
)


def test_build_doctor_summary_runs_on_a_realistic_report():
    summary = summarise(report_ref="report-abc")

    assert isinstance(summary, DoctorSummary)
    assert summary.summary_version
    assert summary.purpose.title.strip()
    assert summary.disclaimer == DISCLAIMER
    assert summary.laboratory.total == 14
    assert summary.laboratory.rows
    assert summary.abnormal_findings
    assert summary.assessments
    assert summary.evidence.status.present and summary.evidence.lines
    assert summary.attribution.report_ref == "report-abc"
    assert "identified by the calling system" in summary.attribution.attribution_note


def test_the_document_survives_every_degradation_path_at_once():
    monkey = pytest.MonkeyPatch()
    try:
        def boom(*_args: Any, **_kwargs: Any) -> Any:
            raise RuntimeError("upstream refused")

        monkey.setattr(doctor_summary_module, "analyse_trends", boom)
        monkey.setattr(doctor_summary_module, "compare_reports", boom)

        import app.rag.retriever as retriever

        monkey.setattr(retriever, "retrieve", boom)

        summary = summarise(history=two_report_history())
    finally:
        monkey.undo()

    assert summary.trends.present is False
    assert summary.trends.reason_code == SECTION_ANALYSIS_REFUSED
    assert summary.comparison.present is False
    assert summary.comparison.reason_code == SECTION_ANALYSIS_REFUSED
    assert summary.knowledge.status.present is False
    assert summary.knowledge.status.reason_code == SECTION_RETRIEVAL_UNAVAILABLE
    assert summary.abnormal_findings
    assert summary.evidence.lines
    assert len(summary.warnings) == 2
    assert all("could not be" in w for w in summary.warnings)


def _without_generated_at(value):
    if isinstance(value, dict):
        return {
            k: _without_generated_at(v)
            for k, v in value.items()
            if k != "generated_at"
        }
    if isinstance(value, list):
        return [_without_generated_at(v) for v in value]
    return value


def test_the_summary_is_deterministic_apart_from_its_timestamp():
    report = generate_report(engineered=abnormal_payload())
    first = build_doctor_summary(
        DoctorSummaryRequest(report=report, history=two_report_history())
    )
    second = build_doctor_summary(
        DoctorSummaryRequest(report=report, history=two_report_history())
    )
    assert _without_generated_at(first.model_dump(mode="json")) == (
        _without_generated_at(second.model_dump(mode="json"))
    )


def test_a_reserved_log_record_key_is_rekeyed_not_raised():
    logger = get_logger("tests.doctor_summary.reserved_key")
    records: List[logging.LogRecord] = []

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = Capture()
    logger.addHandler(handler)
    previous_level = logger.level
    logger.setLevel(logging.INFO)
    try:
        logger.info(
            "doctor_summary.smoke",
            extra=safe_meta(module=32, name="x", filename="y", version="1.0.0"),
        )
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)

    assert len(records) == 1
    record = records[0]
    assert record.meta_module == 32, "the tag must be re-keyed, never dropped"
    assert record.version == "1.0.0", "a non-colliding key is left alone"
    assert record.module != 32, "the real LogRecord attribute is intact"


def test_the_service_wide_logger_factory_installs_the_safe_logger():
    from app.core.logging import _SafeLogger

    assert isinstance(get_logger("tests.doctor_summary.factory"), _SafeLogger)
    assert isinstance(doctor_summary_module.logger, _SafeLogger)


def test_no_module_under_app_calls_logging_get_logger_directly():
    offenders: List[str] = []
    for root, _dirs, files in os.walk(os.path.dirname(doctor_summary_module.__file__)):
        pass
    app_root = os.path.dirname(os.path.dirname(doctor_summary_module.__file__))
    for root, dirs, files in os.walk(app_root):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in files:
            if not name.endswith(".py"):
                continue
            path = os.path.join(root, name)
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
            if "logging.getLogger(" in text and "core/logging" not in path.replace(
                "\\", "/"
            ):
                offenders.append(path)
    assert offenders == [], f"direct logging.getLogger bypasses _SafeLogger: {offenders}"


def test_no_model_client_is_reachable_from_the_doctor_summary_module():
    closure = app_import_closure("app.services.doctor_summary")
    assert "app.services.report_builder" in closure, "sanity: the walk found something"
    for banned in MODEL_CLIENT_MODULES:
        assert banned not in closure, f"doctor_summary can reach {banned}"


def test_the_request_schema_has_no_field_able_to_carry_generated_text():
    from app.schemas.report import ClinicalReport

    assert ClinicalReport.model_config.get("extra") == "forbid"
    assert "explanation" not in ClinicalReport.model_fields
    assert "patient_explanation" not in ClinicalReport.model_fields
    assert set(DoctorSummaryRequest.model_fields) == {
        "patient_ref",
        "report_ref",
        "report_date",
        "report",
        "history",
        "options",
    }


def test_the_integrity_block_reports_the_checks_it_actually_ran():
    summary = summarise(history=two_report_history())
    integrity = summary.integrity
    assert integrity.model_generated_text_included is False
    assert integrity.llm_calls_made == 0
    assert integrity.assembled_text_violations == 0
    assert integrity.source_report_text_violations == 0
    assert integrity.source_report_violation_locations == []
    assert "No language model was called" in integrity.narrative_source
    assert "Module 24" in integrity.scanner


def test_every_emittable_template_passes_the_module_24_safety_scanner():
    from app.data.recommendation_catalog import scan_text

    for key, template in doctor_summary_module._TEMPLATES.items():
        assert scan_text(template) == [], f"template {key} trips the scanner"
    for text in (
        DISCLAIMER,
        doctor_summary_module.DOCUMENT_TITLE,
        doctor_summary_module.DOCUMENT_PURPOSE,
        doctor_summary_module.INTENDED_READER,
        doctor_summary_module.DECISION_SUPPORT_STATEMENT,
    ):
        assert scan_text(text) == []
    for line in doctor_summary_module.DOCUMENT_IS_NOT:
        assert scan_text(line) == []
    for line in doctor_summary_module.HOW_TO_READ:
        assert scan_text(line) == []


def test_the_policy_document_states_the_two_caveat_cutoffs_as_numbers():
    doc = doctor_summary_document()
    text = repr(doc)
    assert str(WEAK_DISCRIMINATION_ROC_AUC) in text
    assert str(LOW_DETECTION_RECALL) in text


def test_a_report_where_nothing_could_be_assessed_is_not_a_normal_result():
    summary = summarise(engineered())

    assert summary.overall.status is None
    assert summary.overall.any_assessed is False
    assert summary.overall.clean_bill_of_health is False
    assert summary.overall.status_label == "Not Assessed"
    assert summary.abnormal_findings == []
    assert summary.normal_findings == []
    assert summary.unassessed_conditions
    assert summary.overall.unassessed_condition_count == len(
        summary.unassessed_conditions
    )
    assert all(not a.assessed for a in summary.assessments)
    assert all(not a.normal for a in summary.assessments)
    for assessment in summary.assessments:
        assert "could not be assessed" in assessment.reading_note
        assert "open question, not a negative result" in assessment.reading_note
    reading = summary.overall.assessment_reading
    assert "must not be read as" in reading
    assert "not a normal result" in reading
    assert "Healthy" not in summary.overall.status_label


def test_clean_bill_of_health_cannot_be_true_without_an_assessment():
    with pytest.raises(Exception) as excinfo:
        OverallStatusView(
            status=None,
            status_label="Not Assessed",
            rule_applied="nothing_assessed",
            any_assessed=False,
            complete=False,
            clean_bill_of_health=True,
            assessment_reading="anything",
        )
    assert "absence of findings is not a finding" in str(excinfo.value)


def test_clean_bill_of_health_cannot_sit_beside_an_abnormal_finding():
    with pytest.raises(Exception) as excinfo:
        OverallStatusView(
            status="Healthy",
            status_label="Healthy",
            rule_applied="no_abnormal_findings",
            any_assessed=True,
            complete=True,
            abnormal_condition_count=1,
            clean_bill_of_health=True,
            assessment_reading="anything",
        )
    assert "beside an abnormal finding" in str(excinfo.value)


def test_a_genuinely_clear_complete_report_does_say_so():
    summary = summarise(healthy_payload())
    assert summary.overall.any_assessed is True
    assert summary.overall.complete is True
    assert summary.overall.abnormal_condition_count == 0
    assert summary.overall.clean_bill_of_health is True
    assert summary.abnormal_findings == []
    assert summary.unassessed_conditions == []
    assert "nothing wider" in summary.overall.assessment_reading


def test_a_flagged_report_is_never_reported_as_clean():
    summary = summarise()
    assert summary.overall.clean_bill_of_health is False
    assert summary.abnormal_findings
    assert summary.overall.abnormal_condition_count == len(summary.abnormal_findings)
    assert "flagged" in summary.overall.assessment_reading


def test_turning_off_normal_findings_never_hides_an_unassessed_condition():
    report = generate_report(engineered=engineered(hba1c=feature("hba1c", 5.1, "%")))
    summary = build_doctor_summary(
        DoctorSummaryRequest(
            report=report, options={"include_normal_findings": False}
        )
    )
    assert summary.normal_findings == []
    assert summary.unassessed_conditions, "an open question must never be hidden"
    assert any(not a.assessed for a in summary.assessments)


def test_every_declared_section_reason_code_is_reachable():
    produced: Set[str] = set()

    produced.add(summarise().trends.reason_code)
    produced.add(
        summarise(
            history=two_report_history(), report_ref="not-in-this-history"
        ).trends.reason_code
    )
    produced.add(summarise(history=two_report_history()[:1]).trends.reason_code)
    produced.add(
        summarise(
            history=two_report_history(), options={"include_trends": False}
        ).trends.reason_code
    )
    produced.add(summarise(healthy_payload()).knowledge.status.reason_code)

    monkey = pytest.MonkeyPatch()
    try:
        import app.rag.retriever as retriever

        monkey.setattr(retriever, "retrieve", lambda **_k: [])
        produced.add(summarise().knowledge.status.reason_code)

        def boom(**_k: Any) -> Any:
            raise RuntimeError("index missing")

        monkey.setattr(retriever, "retrieve", boom)
        produced.add(summarise().knowledge.status.reason_code)

        monkey.setattr(
            doctor_summary_module,
            "analyse_trends",
            lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("refused")),
        )
        produced.add(
            summarise(history=two_report_history()).trends.reason_code
        )
    finally:
        monkey.undo()

    assert produced == set(SECTION_REASON_CODES), (
        f"unreached: {sorted(set(SECTION_REASON_CODES) - produced)}"
    )


def test_with_one_report_trends_and_comparison_are_absent_with_a_stated_reason():
    summary = summarise(history=two_report_history()[:1])

    assert summary.trends.present is False
    assert summary.trends.reason_code == SECTION_SINGLE_REPORT
    assert summary.trend_data is None
    assert summary.comparison.present is False
    assert summary.comparison.reason_code == SECTION_SINGLE_REPORT
    assert summary.comparison_data is None

    assert "This is not a finding of stability." in summary.trends.reason
    assert "not a finding that values are unchanged" in summary.comparison.reason
    for text in (summary.trends.reason, summary.comparison.reason):
        lowered = text.lower()
        assert "stable" not in lowered.replace("stability", "")
        assert "no change" not in lowered


def test_with_no_history_the_reason_says_no_history_not_no_change():
    summary = summarise()
    assert summary.trends.reason_code == SECTION_NO_HISTORY
    assert summary.comparison.reason_code == SECTION_NO_HISTORY
    assert "should be read as an absence of change" in summary.trends.reason


def test_with_two_reports_both_sections_are_present_and_populated():
    summary = summarise(history=two_report_history())
    assert summary.trends.present is True
    assert summary.trends.reason_code is None
    assert summary.trend_data is not None
    assert summary.comparison.present is True
    assert summary.comparison_data is not None
    assert summary.comparison_data.pair is not None


def test_a_section_cannot_be_absent_without_a_reason():
    with pytest.raises(Exception) as excinfo:
        SectionStatus(present=False, reason="no reason code given")
    assert "must carry a reason_code" in str(excinfo.value)


def test_a_present_section_and_its_data_can_never_disagree():
    summary = summarise(history=two_report_history())
    payload = summary.model_dump(mode="json")
    payload["trends"] = {
        "present": False,
        "reason_code": SECTION_DISABLED,
        "reason": "off",
    }
    with pytest.raises(Exception) as excinfo:
        DoctorSummary.model_validate(payload)
    assert "trends.present must match" in str(excinfo.value)


def test_a_disabled_section_says_it_was_disabled_not_that_there_was_nothing():
    summary = summarise(
        history=two_report_history(),
        options={
            "include_trends": False,
            "include_comparison": False,
            "include_knowledge": False,
            "include_evidence": False,
        },
    )
    for status in (
        summary.trends,
        summary.comparison,
        summary.knowledge.status,
        summary.evidence.status,
    ):
        assert status.present is False
        assert status.reason_code == SECTION_DISABLED
        assert "not requested by the calling system" in status.reason


def ml_bases(summary: DoctorSummary) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for assessment in summary.assessments:
        for basis in assessment.bases:
            if basis.ml is not None:
                out[assessment.condition] = basis.ml
    return out


def test_a_probability_is_never_shown_without_the_models_recorded_performance():
    summary = summarise()
    models = ml_bases(summary)
    assert models, "the abnormal panel must reach at least one model"
    for condition, ml in models.items():
        assert ml.probability is not None, condition
        limits = ml.limitations
        assert limits.metrics_available is True, condition
        assert limits.metrics_absent_code is None
        assert limits.roc_auc is not None, condition
        assert limits.artifact, condition
        assert limits.measured_on, condition
        assert any(
            "not a measured quantity" in caveat for caveat in limits.caveats
        ), condition
        assert any(
            "estimated likelihood" in caveat for caveat in limits.caveats
        ), condition


def test_the_heart_model_caveat_is_selected_by_its_measured_number():
    summary = summarise()
    heart = ml_bases(summary).get("Heart Disease")
    assert heart is not None, "the abnormal panel must reach the heart model"

    limits = heart.limitations
    assert limits.roc_auc is not None

    weak_caveat_present = any(
        "discrimination on held-out data is weak" in caveat
        for caveat in limits.caveats
    )
    if limits.roc_auc < WEAK_DISCRIMINATION_ROC_AUC:
        assert weak_caveat_present, limits.caveats
    else:
        assert not weak_caveat_present, limits.caveats
        assert limits.caveats

    assert limits.author_note.state == "CLEAN", limits.author_note.patterns
    assert limits.author_note.text
    assert any(
        word in limits.author_note.text for word in ("WEAK", "COARSE")
    ), limits.author_note.text


def test_a_strong_model_does_not_pick_up_the_weak_discrimination_caveat():
    summary = summarise()
    kidney = ml_bases(summary).get("Kidney Disease")
    assert kidney is not None
    assert kidney.limitations.roc_auc is not None
    assert kidney.limitations.roc_auc > WEAK_DISCRIMINATION_ROC_AUC
    assert not any(
        "discrimination on held-out data is weak" in caveat
        for caveat in kidney.limitations.caveats
    )


def test_an_absent_performance_record_is_stated_rather_than_passed_over():
    limits = doctor_summary_module._model_limitations(None)
    assert limits.metrics_available is False
    assert limits.metrics_absent_code == METRICS_NOT_RECORDED
    assert limits.roc_auc is None
    assert any("cannot be shown here" in caveat for caveat in limits.caveats)


def test_the_heart_models_low_detection_rate_reaches_the_clinician():
    summary = summarise()
    heart = ml_bases(summary)["Heart Disease"]
    limits = heart.limitations
    assert limits.recall_at_operating_threshold is not None
    assert limits.recall_at_operating_threshold < LOW_DETECTION_RECALL
    assert any(
        "rules nothing out" in caveat for caveat in limits.caveats
    )


def test_the_low_detection_caveat_does_fire_when_the_recall_is_carried():
    from app.schemas.report import MLExplanation

    from app.schemas.decisions import DecisionStatus

    explanation = MLExplanation(
        model_name="Random Forest",
        prediction=DecisionStatus.INDICATED,
        performance_reference={"roc_auc": 0.697},
        thresholds={"indicated": 0.673, "indicated_recall_achieved": 0.2678},
    )
    limits = doctor_summary_module._model_limitations(explanation)
    assert limits.recall_at_operating_threshold == 0.2678
    assert any("rules nothing out" in caveat for caveat in limits.caveats)


def test_a_rule_tally_and_a_model_probability_are_never_merged_into_one_figure():
    summary = summarise()
    hybrid = [a for a in summary.assessments if a.hybrid]
    assert hybrid, "the abnormal panel must produce at least one hybrid condition"
    for assessment in hybrid:
        families = {b.assessment_basis_family for b in assessment.bases}
        assert len(assessment.bases) >= 2
        assert len(families) >= 2
        for basis in assessment.bases:
            assert basis.what_this_source_answered.strip()
        assert "combined_probability" not in assessment.model_fields
        assert "merged_score" not in assessment.model_fields


def test_a_model_that_declined_to_estimate_is_not_a_negative_estimate():
    summary = summarise(engineered(hba1c=feature("hba1c", 5.1, "%")))
    for ml in ml_bases(summary).values():
        if ml.skipped:
            assert ml.probability is None
            assert ml.skip_reason
            assert any("not a negative estimate" in c for c in ml.limitations.caveats)


def test_a_parameter_the_report_did_not_carry_is_named_rather_than_omitted():
    summary = summarise(engineered(hba1c=feature("hba1c", 5.1, "%")))
    assert "hba1c" in {row.feature for row in summary.laboratory.rows}
    assert summary.laboratory.features_not_present
    assert "creatinine" in summary.laboratory.features_not_present
    assert "not present" in summary.laboratory.note


def test_a_row_with_no_usable_value_states_why_no_position_is_given():
    summary = summarise(engineered(hba1c=feature("hba1c", 5.1, "%")))
    rows = {row.feature: row for row in summary.laboratory.rows}
    assert rows["hba1c"].value == 5.1
    for row in summary.laboratory.rows:
        if row.value is None:
            assert row.position == "not_determinable"
            assert row.position_reason_code is not None
        if row.position == "not_determinable":
            assert row.position_reason_code is not None


def test_how_to_read_states_that_a_blank_cell_is_not_a_normal_result():
    summary = summarise()
    joined = " ".join(summary.purpose.how_to_read)
    assert "An absent assessment is not a normal result" in joined
    assert "never means zero and never means within range" in joined
    assert summary.purpose.contains_identity is False
    assert any("not a diagnosis" in line for line in summary.purpose.is_not)


def test_every_model_states_what_it_misses_at_its_own_threshold():
    bases = ml_bases(summarise())
    assert set(bases) >= {"Diabetes", "Heart Disease", "Kidney Disease"}

    for condition, base in bases.items():
        limits = base.limitations
        assert limits.metrics_available is True, condition
        assert limits.recall_at_operating_threshold is not None, condition
        assert limits.precision_at_operating_threshold is not None, condition
        assert limits.accuracy is not None, condition
        assert limits.baseline_accuracy is not None, condition
        assert limits.metrics_absent_code is None, condition


def test_the_low_detection_caveat_is_driven_by_the_number_not_the_model():
    bases = ml_bases(summarise())

    heart = bases["Heart Disease"].limitations
    assert heart.recall_at_operating_threshold < LOW_DETECTION_RECALL
    assert any("rules nothing out" in c for c in heart.caveats)

    kidney = bases["Kidney Disease"].limitations
    assert kidney.recall_at_operating_threshold > LOW_DETECTION_RECALL
    assert not any("rules nothing out" in c for c in kidney.caveats)


def test_a_partial_performance_record_says_so_rather_than_looking_complete():
    from app.schemas.decisions import DecisionStatus
    from app.schemas.report import MLExplanation

    explanation = MLExplanation(
        model_name="Random Forest",
        prediction=DecisionStatus.INDICATED,
        probability=0.5,
        performance_reference={"roc_auc": 0.94},
        thresholds={"indicated": 0.7, "borderline": 0.4},
    )
    limits = doctor_summary_module._model_limitations(explanation)

    assert limits.metrics_available is True
    assert limits.recall_at_operating_threshold is None
    assert limits.precision_at_operating_threshold is None
    assert limits.metrics_absent_code == METRICS_OPERATING_POINT_INCOMPLETE
    assert any("cannot be shown" in c for c in limits.caveats)


def test_a_skipped_model_does_not_explain_a_figure_it_never_showed():
    from app.schemas.decisions import DecisionStatus
    from app.schemas.report import MLExplanation

    skipped = MLExplanation(
        model_name="Random Forest",
        prediction=DecisionStatus.INSUFFICIENT_DATA,
        probability=None,
        skipped=True,
        skip_reason="required inputs absent",
    )
    limits = doctor_summary_module._model_limitations(skipped)

    assert not any(
        "the model's own estimated likelihood" in c for c in limits.caveats
    ), "a skipped model must not explain a probability it never produced"
    assert any("declined to produce an estimate" in c for c in limits.caveats)


def test_the_unassessed_count_prefers_the_upstream_summary():
    from types import SimpleNamespace

    from app.services.doctor_summary import _unmapped_count

    report = SimpleNamespace(
        document=SimpleNamespace(unmapped_count=0),
        fusion=SimpleNamespace(upstream_summary={"unmapped_count": 17}),
    )
    assert _unmapped_count(report) == 17


def test_the_document_count_is_used_when_the_upstream_has_none():
    from types import SimpleNamespace

    from app.services.doctor_summary import _unmapped_count

    report = SimpleNamespace(
        document=SimpleNamespace(unmapped_count=4),
        fusion=SimpleNamespace(upstream_summary={}),
    )
    assert _unmapped_count(report) == 4


def test_no_fusion_section_is_not_a_crash():
    from types import SimpleNamespace

    from app.services.doctor_summary import _unmapped_count

    report = SimpleNamespace(document=SimpleNamespace(unmapped_count=3), fusion=None)
    assert _unmapped_count(report) == 3


def test_a_defaulted_upstream_zero_does_not_beat_a_real_document_count():
    from types import SimpleNamespace

    from app.services.doctor_summary import _unmapped_count

    report = SimpleNamespace(
        document=SimpleNamespace(unmapped_count=17),
        fusion=SimpleNamespace(upstream_summary={"unmapped_count": 0}),
    )
    assert _unmapped_count(report) == 17
