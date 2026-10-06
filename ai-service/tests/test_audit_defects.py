"""Regression tests for the defects the independent integration audit found.

One file, because these tests exist to be re-audited as a set. Each section
names the defect it closes and, in its docstring, what the code did BEFORE the
fix -- so that a future reader can tell a test that is guarding something from
a test that is merely restating an implementation.

    D1  the information-sufficiency gate accepted a non-numeric value as
        "present", so all three models predicted on median-imputed inputs
    D2  Module 12's skip reason never reached the report (key mismatch)
    D3  the artifact<->metrics sha256 binding was never enforced at runtime
    D4  `status_label` could not distinguish a complete from a partial report
    D5  the safety inspector false-positived on the system's own boilerplate,
        and did not walk every caller-controlled laboratory-value field
    D6  `ClinicalDecision` allowed INSUFFICIENT_DATA to carry a confidence
    D7  the scanner's diagnosis and drug patterns were thinner than claimed

NO TRAINING, no network.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

import pytest
from fastapi.testclient import TestClient

from app.api import routes_ml, routes_report
from app.core.auth import SERVICE_KEY_HEADER
from app.data import conditions as C
from app.data.recommendation_catalog import scan_text
from app.ml.artifacts import (
    INTEGRITY_MISMATCH,
    INTEGRITY_VERIFIED,
    metrics_filename_for,
    verify_artifact_integrity,
)
from app.ml.base import (
    REASON_MODEL_UNAVAILABLE,
    REASON_REQUIRED_IMPUTED,
    REASON_REQUIRED_MISSING,
    PredictionContext,
    Predictor,
)
from app.ml.diabetes import DiabetesPredictor
from app.ml.heart import HeartPredictor
from app.ml.kidney import KidneyPredictor
from app.main import app
from app.schemas.decisions import (
    ClinicalDecision,
    DecisionSourceKind,
    DecisionStatus,
    RiskLevel,
)
from app.schemas.report import (
    STATUS_HEALTHY,
    STATUS_HEALTHY_PARTIAL,
    STATUS_NEEDS_MEDICAL_ATTENTION,
    STATUS_NEEDS_MONITORING,
    STATUS_NOT_ASSESSED,
    OVERALL_STATUS_LABELS,
)
from app.services.report_builder import generate_report, report_text_violations
from tests.conftest import TEST_SERVICE_KEY


# --------------------------------------------------------------------------
# Shared helpers
# --------------------------------------------------------------------------


def feature(
    name: str, value: Any, unit: Optional[str] = None, source: str = "lab_report"
) -> Dict[str, Any]:
    return {"name": name, "value": value, "unit": unit, "source": source}


def engineered(**features: Dict[str, Any]) -> Dict[str, Any]:
    return {"features": dict(features)}


def _mount_once(path: str, router) -> None:
    def walk(routes):
        flat = []
        for route in routes:
            included = getattr(route, "original_router", None)
            nested = getattr(included, "routes", None) or getattr(route, "routes", None)
            if nested:
                flat.extend(walk(nested))
            else:
                flat.append(route)
        return flat

    if any(getattr(r, "path", "") == path for r in walk(app.routes)):
        return
    app.include_router(router)


_mount_once("/api/v1/report/generate", routes_report.router)
_mount_once("/api/v1/ml/predict", routes_ml.router)


@pytest.fixture(scope="module")
def api() -> TestClient:
    return TestClient(app)


HEADERS = {SERVICE_KEY_HEADER: TEST_SERVICE_KEY}


#: The exact values the audit posted. Every one of them is a value that is not
#: `None` and not blank -- which is all the old gate checked -- and none of them
#: is a creatinine.
NON_NUMERIC_CREATININE = ("Negative", "n/a", True, "1.2 mg/dL", float("nan"))


# ==========================================================================
# D1 -- the information-sufficiency gate is type-aware
# ==========================================================================
#
# BEFORE: `_is_present` returned True for any value that was not None and not
# a blank string, so `creatinine="Negative"` satisfied the gate, the sklearn
# ColumnTransformer coerced it to NaN, the numeric imputer median-filled it
# from the training cohort, and the kidney model returned
# `Indicated / High / 0.9924899057873485`. The report ranked "Kidney Disease"
# first under Critical Findings for a patient whose creatinine was never
# measured.


@pytest.mark.parametrize("bad", NON_NUMERIC_CREATININE)
def test_kidney_refuses_a_non_numeric_creatinine(bad):
    decision = KidneyPredictor().predict({"creatinine": bad, "hemoglobin": 9.5})

    assert decision.status is DecisionStatus.INSUFFICIENT_DATA
    assert decision.risk is None
    assert decision.confidence is None
    assert "creatinine" in decision.metadata["sufficiency"]["required_missing"]


def test_heart_refuses_non_numeric_bmi_and_cholesterol():
    decision = HeartPredictor().predict(
        {"age": 55, "bmi": "obese", "cholesterol": "high"}
    )
    assert decision.status is DecisionStatus.INSUFFICIENT_DATA
    assert decision.risk is None
    assert decision.confidence is None
    missing = decision.metadata["sufficiency"]["required_missing"]
    assert "bmi" in missing and "cholesterol" in missing


def test_diabetes_refuses_non_numeric_hba1c_and_glucose():
    decision = DiabetesPredictor().predict(
        {"hba1c": "high", "blood_glucose": "N/A"}
    )
    assert decision.status is DecisionStatus.INSUFFICIENT_DATA
    assert decision.risk is None
    assert decision.confidence is None
    missing = decision.metadata["sufficiency"]["required_missing"]
    assert "hba1c" in missing and "blood_glucose" in missing


def test_the_gate_still_admits_the_values_it_should():
    """The fix must not turn a usable value into a skip.

    A numeric string IS a number and the pipeline consumes it as one, so it is
    admitted; `False` and `0` remain explicit answers, not absences.
    """
    decision = KidneyPredictor().predict({"creatinine": "3.1", "hemoglobin": 9.5})
    assert decision.status is not DecisionStatus.INSUFFICIENT_DATA
    assert decision.confidence is not None

    assert Predictor._is_present(False) is True
    assert Predictor._is_present(0, "age") is True
    assert Predictor._is_present(0.0, "creatinine") is True
    assert Predictor._is_present(False, "hypertension") is True
    assert Predictor._is_present("never", "smoking_history") is True
    assert Predictor._is_present("Female", "gender") is True


def test_the_gate_rejects_by_declared_type_not_by_emptiness():
    assert Predictor._is_present("Negative", "creatinine") is False
    assert Predictor._is_present(True, "creatinine") is False
    assert Predictor._is_present(float("nan"), "creatinine") is False
    assert Predictor._is_present(float("inf"), "creatinine") is False
    assert Predictor._is_present("1.2 mg/dL", "creatinine") is False
    assert Predictor._is_present("sometimes", "smoking_history") is False
    assert Predictor._is_present("yes", "hypertension") is False
    # ...and the same values are still "present" to a type-agnostic caller,
    # so the loose form has not silently changed meaning.
    assert Predictor._is_present("Negative") is True


@pytest.mark.parametrize(
    "endpoint_features, condition",
    [
        ({"creatinine": "Negative", "hemoglobin": 9.5}, C.KIDNEY_DISEASE),
        ({"age": 55, "bmi": "obese", "cholesterol": "high"}, C.HEART_DISEASE),
        ({"hba1c": "high", "blood_glucose": "N/A"}, C.DIABETES),
    ],
)
def test_the_exploit_is_closed_over_http(api, endpoint_features, condition):
    payload = {
        "engineered": {
            "features": {
                name: feature(name, value)
                for name, value in endpoint_features.items()
            }
        }
    }
    response = api.post("/api/v1/ml/predict", json=payload, headers=HEADERS)
    assert response.status_code == 200
    decisions = response.json()["data"]["decisions"]
    mine = [d for d in decisions if d["condition"] == condition]
    assert mine, f"no decision for {condition}"
    for decision in mine:
        assert decision["status"] == DecisionStatus.INSUFFICIENT_DATA.value
        assert decision["risk"] is None
        assert decision["confidence"] is None


def test_report_generate_no_longer_flags_kidney_disease_from_a_word(api):
    """The audit's headline reproduction, end to end.

    Returned HTTP 200 with `Needs Medical Attention`, `overall_risk=High`,
    `critical_conditions=["Kidney Disease"]` and Kidney Disease
    `Indicated / High / 0.99` ranked first -- from a report in which
    creatinine was never measured.
    """
    payload = {
        "validated": {
            "valid": {
                "creatinine": {
                    "name": "creatinine",
                    "value": "Negative",
                    "unit": "mg/dl",
                    "canonical_unit": True,
                    "status": "valid",
                },
                "hemoglobin": {
                    "name": "hemoglobin",
                    "value": 9.5,
                    "unit": "g/dl",
                    "canonical_unit": True,
                    "status": "valid",
                },
            },
            "questionable": {},
            "clinically_extreme": [],
            "missing_features": [],
            "unmapped": [],
        }
    }
    response = api.post("/api/v1/report/generate", json=payload, headers=HEADERS)
    assert response.status_code == 200
    data = response.json()["data"]

    assert C.KIDNEY_DISEASE not in data["critical_conditions"]
    kidney = [c for c in data["conditions"] if c["condition"] == C.KIDNEY_DISEASE]
    assert kidney, "Kidney Disease must still appear -- it is always_assessed"
    assert kidney[0]["status"] == DecisionStatus.INSUFFICIENT_DATA.value
    assert kidney[0]["risk"] is None
    assert kidney[0]["confidence"] is None


# ---- the PredictorBase-level guarantee ------------------------------------


class _LyingPredictor(Predictor):
    """A predictor whose own trace admits a required input was imputed.

    This is what a FUTURE predictor looks like when it reads a required feature
    under a model column name the base class does not know, or adds a value
    type the gate has not been taught. `predict()` must catch it from the trace
    alone, without understanding anything about this subclass.
    """

    name = "lying_predictor"
    condition = C.DIABETES
    source_label = "Fake Forest"
    required_features = ("hba1c", "blood_glucose")
    optional_features = ("age",)

    def __init__(self, imputed=("hba1c",), not_asserted=()) -> None:
        self._imputed = list(imputed)
        self._not_asserted = list(not_asserted)
        self.calls = 0
        super().__init__()

    def _predict(
        self, features: Mapping[str, Any], context: PredictionContext
    ) -> ClinicalDecision:
        self.calls += 1
        return ClinicalDecision(
            condition=self.condition,
            status=DecisionStatus.INDICATED,
            risk=RiskLevel.HIGH,
            confidence=0.99,
            source=self.source_label,
            source_kind=DecisionSourceKind.MACHINE_LEARNING,
            metadata={
                "features_observed": ["blood_glucose"],
                "features_imputed": list(self._imputed),
                "features_not_asserted": list(self._not_asserted),
            },
        )


def test_a_prediction_whose_trace_shows_an_imputed_required_input_is_discarded():
    predictor = _LyingPredictor(imputed=("hba1c",))
    decision = predictor.predict({"hba1c": 6.9, "blood_glucose": 130.0})

    assert predictor.calls == 1, "the model DID run; the result is discarded"
    assert decision.status is DecisionStatus.INSUFFICIENT_DATA
    assert decision.risk is None
    assert decision.confidence is None
    assert decision.metadata["skipped"] is True
    assert decision.metadata["skipped_reason"] == REASON_REQUIRED_IMPUTED
    assert decision.metadata["required_features_substituted"] == ["hba1c"]
    assert decision.metadata["sufficiency"]["required_missing"] == ["hba1c"]


def test_a_required_input_excluded_from_the_matrix_is_caught_too():
    predictor = _LyingPredictor(imputed=(), not_asserted=("blood_glucose",))
    decision = predictor.predict({"hba1c": 6.9, "blood_glucose": 130.0})
    assert decision.status is DecisionStatus.INSUFFICIENT_DATA
    assert decision.metadata["required_features_substituted"] == ["blood_glucose"]


def test_an_imputed_OPTIONAL_input_is_not_a_reason_to_skip():
    """The assertion must be about REQUIRED features only.

    Every real predictor imputes optional inputs on almost every call -- that
    is what makes them optional. A check that fired on those would turn the
    whole ML layer off.
    """
    predictor = _LyingPredictor(imputed=("age",))
    decision = predictor.predict({"hba1c": 6.9, "blood_glucose": 130.0})
    assert decision.status is DecisionStatus.INDICATED
    assert decision.confidence == 0.99


def test_the_shipped_predictors_still_impute_their_optional_inputs():
    """Guards the test above against being vacuously true."""
    decision = KidneyPredictor().predict({"creatinine": 3.1, "hemoglobin": 9.5})
    assert decision.status is not DecisionStatus.INSUFFICIENT_DATA
    assert set(decision.metadata["features_imputed"]) == {"age", "blood_glucose"}
    assert not set(decision.metadata["features_imputed"]) & set(
        decision.metadata["sufficiency_rule"]["required_features"]
    )


# ==========================================================================
# D2 -- the skip reason reaches the report
# ==========================================================================
#
# BEFORE: `_explain_ml` read `skip_reason` / `insufficiency_reason` /
# `sufficiency_reason`; no producer in the service emits any of those three.
# A genuine Module 12 skip rendered as `skip_reason=None`,
# `features_missing=[]` -- "Random Forest -- skipped -- (no reason)", which a
# reader cannot tell from "the model broke".


def _ml_records(report):
    return [
        (explanation.condition, source.ml)
        for explanation in report.explainability.conditions
        for source in explanation.sources
        if source.ml is not None
    ]


def test_a_module_12_skip_renders_with_a_reason_naming_the_missing_feature():
    report = generate_report(
        engineered=engineered(hba1c=feature("hba1c", 5.1, "%"))
    )
    kidney = [ml for condition, ml in _ml_records(report)
              if condition == C.KIDNEY_DISEASE]
    assert kidney, "Kidney Disease is always_assessed; its ML record must exist"
    ml = kidney[0]

    assert ml.skipped is True
    assert ml.prediction is DecisionStatus.INSUFFICIENT_DATA
    assert ml.skip_reason == REASON_REQUIRED_MISSING
    assert "creatinine" in ml.features_missing
    assert ml.skip_explanation and "creatinine" in ml.skip_explanation


def test_every_skipped_ml_record_states_a_reason():
    report = generate_report(
        engineered=engineered(hba1c=feature("hba1c", 5.1, "%"))
    )
    skipped = [ml for _, ml in _ml_records(report) if ml.skipped]
    assert len(skipped) >= 2
    for ml in skipped:
        assert ml.skip_reason, "a skip must never render without a reason"
        assert ml.features_missing, "a skip must name what it needed"
        assert ml.skip_explanation


def test_the_skip_explanation_is_safety_clean():
    report = generate_report(
        engineered=engineered(hba1c=feature("hba1c", 5.1, "%"))
    )
    for _, ml in _ml_records(report):
        if ml.skip_explanation:
            assert scan_text(ml.skip_explanation) == []
    assert report_text_violations(report) == []


def test_a_prediction_that_ran_carries_no_skip_reason():
    report = generate_report(
        engineered=engineered(
            hba1c=feature("hba1c", 8.4, "%"),
            blood_glucose=feature("blood_glucose", 186.0, "mg/dl"),
            age=feature("age", 62, "years", "patient_profile"),
            bmi=feature("bmi", 33.8, "kg/m2", "patient_profile"),
        )
    )
    ran = [ml for _, ml in _ml_records(report) if not ml.skipped]
    assert ran, "the fixture stopped producing a prediction"
    for ml in ran:
        assert ml.skip_reason is None
        assert ml.skip_explanation is None


# ==========================================================================
# D3 -- the artifact <-> metrics sha256 binding is enforced at load time
# ==========================================================================
#
# BEFORE: `sha256_of()` was defined, exported, and had zero callers in `app/`.
# Verification existed only in the test suite, so a substituted joblib under an
# overridden `ML_ARTIFACT_DIR` loaded silently and was served with the previous
# model's thresholds, metrics and `global_feature_importance`.


@pytest.mark.parametrize(
    "filename",
    ["kidney_rf_v1.joblib", "heart_rf_v1.joblib", "diabetes_rf_v1.joblib"],
)
def test_the_shipped_artifacts_verify(filename):
    result = verify_artifact_integrity(filename)
    assert result["status"] == INTEGRITY_VERIFIED
    assert result["verified"] is True
    assert result["recorded_sha256"] == result["actual_sha256"]


def test_metrics_filename_derivation():
    assert metrics_filename_for("kidney_rf_v1.joblib") == "kidney_rf_v1.metrics.json"


@pytest.mark.parametrize(
    "predictor_cls", [KidneyPredictor, HeartPredictor, DiabetesPredictor]
)
def test_every_prediction_carries_the_integrity_flag(predictor_cls):
    predictor = predictor_cls()
    assert predictor.artifact_integrity()["status"] == INTEGRITY_VERIFIED
    assert predictor.describe()["artifact_integrity"]["verified"] is True
    provenance = predictor.model_provenance()
    assert provenance["artifact_integrity_verified"] is True
    assert provenance["artifact_integrity"]["status"] == INTEGRITY_VERIFIED


def test_a_substituted_artifact_is_detected_and_flagged(tmp_path, monkeypatch):
    """A retrained or swapped joblib served with the recorded metrics.

    CHOSEN FAILURE MODE: the service keeps running and every affected decision
    carries the flag. See the rationale in `app/ml/artifacts.py`. This test
    pins BOTH halves -- detected, and not fatal.
    """
    import shutil

    from app.ml import artifacts

    source = artifacts.DEFAULT_ARTIFACT_DIR
    for name in ("kidney_rf_v1.joblib", "kidney_rf_v1.metrics.json"):
        shutil.copy(source / name, tmp_path / name)
    # Substitute the model file. The metrics document -- and therefore every
    # threshold and every published number -- is left untouched.
    with (tmp_path / "kidney_rf_v1.joblib").open("ab") as handle:
        handle.write(b"\x00")

    monkeypatch.setenv("ML_ARTIFACT_DIR", str(tmp_path))
    artifacts.reset_cache()
    try:
        result = artifacts.verify_artifact_integrity("kidney_rf_v1.joblib")
        assert result["status"] == INTEGRITY_MISMATCH
        assert result["verified"] is False
        assert result["recorded_sha256"] != result["actual_sha256"]
        assert result["caveat"]
    finally:
        artifacts.reset_cache()


def test_a_missing_metrics_document_does_not_claim_verification(tmp_path, monkeypatch):
    import shutil

    from app.ml import artifacts

    shutil.copy(
        artifacts.DEFAULT_ARTIFACT_DIR / "kidney_rf_v1.joblib",
        tmp_path / "kidney_rf_v1.joblib",
    )
    monkeypatch.setenv("ML_ARTIFACT_DIR", str(tmp_path))
    artifacts.reset_cache()
    try:
        result = artifacts.verify_artifact_integrity("kidney_rf_v1.joblib")
        assert result["verified"] is False
        assert result["status"] != INTEGRITY_VERIFIED
    finally:
        artifacts.reset_cache()


# ==========================================================================
# D4 -- `status_label` distinguishes complete from partial
# ==========================================================================
#
# BEFORE: a report with exactly one normal HbA1c returned status="Healthy",
# status_label="Healthy", overall_risk="Low" -- byte-identical in those three
# fields to a fully-assessed healthy report.


def _complete_healthy():
    return engineered(
        hba1c=feature("hba1c", 5.1, "%"),
        blood_glucose=feature("blood_glucose", 88.0, "mg/dl"),
        hemoglobin=feature("hemoglobin", 14.2, "g/dl"),
        creatinine=feature("creatinine", 0.9, "mg/dl"),
        cholesterol=feature("cholesterol", 170.0, "mg/dl"),
        triglycerides=feature("triglycerides", 110.0, "mg/dl"),
        vitamin_d=feature("vitamin_d", 42.0, "ng/ml"),
        vitamin_b12=feature("vitamin_b12", 480.0, "pg/ml"),
        # The liver panel (2026-10-04) -- part of a COMPLETE panel now.
        alt=feature("alt", 18.0, "u/l"),
        ast=feature("ast", 21.0, "u/l"),
        bilirubin_total=feature("bilirubin_total", 0.6, "mg/dl"),
        bmi=feature("bmi", 22.4, "kg/m2", "patient_profile"),
        age=feature("age", 34, "years", "patient_profile"),
        gender=feature("gender", "female", None, "patient_profile"),
        hypertension=feature("hypertension", False, None, "patient_profile"),
        heart_disease=feature("heart_disease", False, None, "patient_profile"),
        smoking_history=feature(
            "smoking_history", "never", None, "patient_profile"
        ),
    )


def test_case_1_complete_healthy():
    overall = generate_report(engineered=_complete_healthy()).overall
    assert overall.status == STATUS_HEALTHY
    assert overall.status_label == STATUS_HEALTHY
    assert overall.complete is True
    assert overall.caveat is None


def test_case_2_needs_monitoring():
    report = generate_report(
        engineered=engineered(
            hemoglobin=feature("hemoglobin", 14.2, "g/dl"),
            vitamin_d=feature("vitamin_d", 24.0, "ng/ml"),
            age=feature("age", 34, "years", "patient_profile"),
        )
    )
    assert report.overall.status == STATUS_NEEDS_MONITORING
    assert report.overall.status_label == STATUS_NEEDS_MONITORING


def test_case_3_needs_medical_attention():
    report = generate_report(
        engineered=engineered(
            hba1c=feature("hba1c", 8.4, "%"),
            blood_glucose=feature("blood_glucose", 186.0, "mg/dl"),
            hemoglobin=feature("hemoglobin", 10.4, "g/dl"),
            creatinine=feature("creatinine", 2.1, "mg/dl"),
            cholesterol=feature("cholesterol", 268.0, "mg/dl"),
            bmi=feature("bmi", 33.8, "kg/m2", "patient_profile"),
            age=feature("age", 62, "years", "patient_profile"),
        )
    )
    assert report.overall.status == STATUS_NEEDS_MEDICAL_ATTENTION
    assert report.overall.status_label == STATUS_NEEDS_MEDICAL_ATTENTION


def test_case_4_nothing_assessed_must_not_regress():
    """The Module 18 fourth case. Verified clean by the audit; pinned here."""
    overall = generate_report().overall
    assert overall.status is None
    assert overall.status_label == STATUS_NOT_ASSESSED
    assert overall.status_label != STATUS_HEALTHY
    assert overall.status_label != STATUS_HEALTHY_PARTIAL
    assert overall.any_assessed is False
    assert overall.complete is False
    assert overall.risk is None
    assert overall.caveat


def test_case_6_profile_only_is_not_healthy():
    """THE RÉSUMÉ (live site, 2026-10-06). No test result was read; BMI 24.97,
    age 20, male, non-smoker, no hypertension or heart disease. The real rules
    and models judged Obesity, Underweight and Heart Disease from those alone
    and the report said "Healthy (partial assessment) -- Overall risk: Low"."""
    overall = generate_report(
        engineered=engineered(
            bmi=feature("bmi", 24.97, "kg/m2", "patient_profile"),
            age=feature("age", 20, "years", "patient_profile"),
            gender=feature("gender", "male", None, "patient_profile"),
            hypertension=feature("hypertension", False, None, "patient_profile"),
            heart_disease=feature("heart_disease", False, None, "patient_profile"),
            smoking_history=feature("smoking_history", "never", None, "patient_profile"),
        )
    ).overall
    assert overall.status is None
    assert overall.status_label == STATUS_NOT_ASSESSED
    assert overall.risk is None
    assert overall.any_assessed is False
    assert overall.rule_applied == "no_lab_result_assessed"
    assert "details entered" in overall.caveat


def test_case_7_one_real_test_result_restores_healthy():
    overall = generate_report(
        engineered=engineered(
            hba1c=feature("hba1c", 5.1, "%"),
            bmi=feature("bmi", 24.97, "kg/m2", "patient_profile"),
            age=feature("age", 20, "years", "patient_profile"),
            gender=feature("gender", "male", None, "patient_profile"),
        )
    ).overall
    assert overall.status == STATUS_HEALTHY
    assert overall.rule_applied == "no_abnormal_findings"


def test_case_5_partial_healthy_is_labelled_as_partial():
    """THE DEFECT. One normal HbA1c is not a clean bill of health."""
    partial = generate_report(
        engineered=engineered(hba1c=feature("hba1c", 5.1, "%"))
    ).overall
    complete = generate_report(engineered=_complete_healthy()).overall

    # `status` stays at its spec value, so a three-value consumer still works.
    assert partial.status == STATUS_HEALTHY
    assert partial.complete is False
    assert partial.caveat
    assert partial.unassessed_conditions

    # ...but a LABEL-ONLY renderer can now tell the two apart.
    assert partial.status_label == STATUS_HEALTHY_PARTIAL
    assert partial.status_label != complete.status_label
    assert STATUS_HEALTHY_PARTIAL in OVERALL_STATUS_LABELS


def test_case_6_partial_abnormal_keeps_its_finding_label():
    """An abnormal finding IS a finding; incompleteness does not qualify it.

    Only the falsely-reassuring CLEAN case is relabelled. The incompleteness is
    still carried structurally here.
    """
    partial = generate_report(
        engineered=engineered(hba1c=feature("hba1c", 8.4, "%"))
    ).overall
    assert partial.status in (
        STATUS_NEEDS_MONITORING,
        STATUS_NEEDS_MEDICAL_ATTENTION,
    )
    assert partial.status_label == partial.status
    assert partial.complete is False
    assert partial.caveat


def test_every_label_the_builder_can_emit_is_declared():
    for payload in (None, _complete_healthy(), engineered(
        hba1c=feature("hba1c", 5.1, "%")
    ), engineered(hba1c=feature("hba1c", 8.4, "%"))):
        report = (
            generate_report() if payload is None
            else generate_report(engineered=payload)
        )
        assert report.overall.status_label in OVERALL_STATUS_LABELS


# ==========================================================================
# D5 -- the safety inspector does not fire on the system's own output
# ==========================================================================


MODULE_6_BOILERPLATE = (
    "Feature 'bmi' is usable but flagged (DERIVED_VALUE); treat it with "
    "reduced confidence."
)


def test_the_inspector_does_not_fire_on_module_6s_own_warning():
    """BEFORE: this matched `treatment_instruction` on the verb "treat".

    A checker that fires on its own boilerplate trains readers to ignore it.
    """
    assert scan_text(MODULE_6_BOILERPLATE) == []


@pytest.mark.parametrize(
    "text",
    [
        "treat it with metformin",
        "treat this with antibiotics",
        "we will treat them with insulin",
        "treated with surgery",
        "start treatment now",
        "treating high cholesterol",
        "treat it with a course of drugs",
        "treat them with care and a statin",
    ],
)
def test_a_real_treatment_instruction_is_still_caught(text):
    """The D5 fix must be a carve-out, not a weakening.

    Every one of these still trips `treatment_instruction` ITSELF -- not merely
    some other pattern that happens to co-fire -- so the carve-out cannot be
    passing these by accident.
    """
    assert "treatment_instruction" in scan_text(text)


def test_the_inspector_walks_every_caller_controlled_lab_value_field():
    """BEFORE: `unit`, `original_unit`, `original_test_name` and `feature` were
    rendered but never scanned.
    """
    from app.schemas.report import LaboratoryValue

    injected = (
        "You definitely have diabetes. Take metformin 500 mg twice a day. "
        "No need to see a doctor."
    )
    report = generate_report(engineered=_complete_healthy())
    assert report_text_violations(report) == []

    for field in ("unit", "original_test_name", "original_unit", "feature"):
        value = report.laboratory_values[0]
        poisoned = LaboratoryValue(
            **{**value.model_dump(), field: injected}
        )
        tampered = report.model_copy(
            update={"laboratory_values": [poisoned] + list(
                report.laboratory_values[1:]
            )}
        )
        violations = report_text_violations(tampered)
        assert violations, f"{field} is not covered by the inspector's walk"
        assert any(field in where for where, _, _ in violations)


# ==========================================================================
# D7 -- the diagnosis and drug patterns are not enumerations
# ==========================================================================


@pytest.mark.parametrize(
    "text",
    [
        "the diagnosis is diabetes",
        "Your diagnosis: anaemia",
        "she was diagnosed with CKD",
        "diagnostic of anaemia",
        "diagnosis of anaemia",
        "the diagnoses are clear",
        "we diagnose chronic kidney disease",
    ],
)
def test_diagnostic_assertions_are_caught_in_every_inflection(text):
    assert "diagnostic_assertion" in scan_text(text)


@pytest.mark.parametrize(
    "text",
    [
        "This is an automated educational analysis, not a diagnosis, and it "
        "does not replace assessment by a qualified healthcare professional.",
        "An estimated probability produced by a statistical model from records "
        "resembling this one. It is not a measurement of this person and it is "
        "not a diagnosis.",
    ],
)
def test_the_platforms_own_disclaimer_is_not_a_diagnostic_assertion(text):
    assert scan_text(text) == []


@pytest.mark.parametrize(
    "drug",
    [
        "ranitidine",
        "canagliflozin",
        "amoxicillin",
        "vildagliptin",
        "pioglitazone",
        "pantoprazole",
        "azithromycin",
        "doxycycline",
        "candesartan",
        "bisoprolol",
        "nifedipine",
        "pravastatin",
        "enalapril",
        "ciprofloxacin",
        "adalimumab",
    ],
)
def test_unlisted_drugs_no_longer_pass(drug):
    """BEFORE: the drug list was an enumeration, so anything unlisted passed."""
    assert scan_text(f"start {drug} today")


def test_the_catalogue_itself_is_still_clean_under_the_hardened_patterns():
    from app.data.recommendation_catalog import RECOMMENDATIONS

    for code, entry in RECOMMENDATIONS.items():
        assert scan_text(entry.text) == [], code


# ==========================================================================
# D6 -- INSUFFICIENT_DATA may not carry a confidence
# ==========================================================================


def test_insufficient_data_may_not_carry_a_confidence():
    """The same invariant as the risk one, one field over."""
    with pytest.raises(ValueError, match="confidence must be None"):
        ClinicalDecision(
            condition=C.DIABETES,
            status=DecisionStatus.INSUFFICIENT_DATA,
            risk=None,
            confidence=0.99,
            source="Random Forest",
            source_kind=DecisionSourceKind.MACHINE_LEARNING,
        )


def test_insufficient_data_may_not_carry_a_zero_confidence_either():
    with pytest.raises(ValueError, match="confidence must be None"):
        ClinicalDecision(
            condition=C.DIABETES,
            status=DecisionStatus.INSUFFICIENT_DATA,
            risk=None,
            confidence=0.0,
            source="Random Forest",
            source_kind=DecisionSourceKind.MACHINE_LEARNING,
        )


def test_the_risk_invariant_is_untouched():
    with pytest.raises(ValueError, match="risk must be None"):
        ClinicalDecision(
            condition=C.DIABETES,
            status=DecisionStatus.INSUFFICIENT_DATA,
            risk=RiskLevel.LOW,
            source="Random Forest",
            source_kind=DecisionSourceKind.MACHINE_LEARNING,
        )


def test_no_shipped_producer_emits_a_confidence_carrying_abstention():
    """Every real skip path, exercised, must satisfy the new constraint."""
    for predictor in (KidneyPredictor(), HeartPredictor(), DiabetesPredictor()):
        decision = predictor.predict({})
        assert decision.status is DecisionStatus.INSUFFICIENT_DATA
        assert decision.confidence is None
        assert decision.metadata["skipped_reason"] in (
            REASON_REQUIRED_MISSING,
            REASON_REQUIRED_IMPUTED,
            REASON_MODEL_UNAVAILABLE,
        )
