from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.data import conditions as C
from app.data.recommendation_catalog import RECOMMENDATIONS, scan_text
from app.ml.artifacts import artifact_path, load_metrics, load_model
from app.ml.base import BASE_NOTE_FRAGMENTS, PredictionContext
from app.ml.heart import (
    ABSENT_CATEGORY,
    ASSESSMENT_BASIS_KEY,
    ASSESSMENT_KIND_KEY,
    ASSESSMENT_KIND_LIKELIHOOD,
    CHOLESTEROL_BAND_CUTOFFS,
    HEART_METRICS_FILE,
    HEART_MODEL_FILE,
    HEART_NOTE_FRAGMENTS,
    TRI_STATE_SMOKING,
    HeartPredictor,
    cholesterol_band,
    smoking_current,
)
from app.ml.registry import build_default_registry, default_registry
from app.schemas.decisions import (
    ClinicalDecision,
    DecisionSourceKind,
    DecisionStatus,
    RiskLevel,
)

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")


HIGH_RISK = {
    "age": 62,
    "bmi": 34.5,
    "cholesterol": 268.0,
    "gender": "male",
    "smoking_history": "current",
}

LOW_RISK = {
    "age": 31,
    "bmi": 21.4,
    "cholesterol": 165.0,
    "gender": "female",
    "smoking_history": "never",
}


@pytest.fixture(scope="module")
def predictor() -> HeartPredictor:
    return HeartPredictor()


@pytest.fixture(scope="module")
def bundle():
    loaded = load_model(HEART_MODEL_FILE)
    assert loaded is not None, (
        "the heart model artifact is missing. Run `python ml/train_heart.py`; "
        "tests never train."
    )
    return loaded


def _frame(predictor: HeartPredictor, features: dict):
    variant, _, _ = predictor.select_variant(features)
    frame, trace = predictor._model_row(features, variant)
    return variant, frame, trace


def test_the_committed_artifact_loads(predictor, bundle):
    assert predictor.is_available() is True
    assert predictor.unavailable_reason() is None
    assert set(bundle.pipelines) == {"with_smoking", "without_smoking"}


def test_the_metrics_document_describes_the_committed_model():
    metrics = load_metrics(HEART_METRICS_FILE)
    assert metrics is not None, "the heart metrics artifact is missing"

    model_file: Path = artifact_path(HEART_MODEL_FILE)
    digest = hashlib.sha256(model_file.read_bytes()).hexdigest()
    assert metrics["model_artifact"]["filename"] == HEART_MODEL_FILE
    assert metrics["model_artifact"]["sha256"] == digest
    assert metrics["model_artifact"]["bytes"] == model_file.stat().st_size


def test_the_metrics_document_and_the_model_agree_on_thresholds(bundle):
    metrics = load_metrics(HEART_METRICS_FILE)
    for name, spec in bundle.variants.items():
        recorded = metrics["variants"][name]["thresholds"]
        assert recorded["indicated"] == pytest.approx(spec["thresholds"]["indicated"])
        assert recorded["borderline"] == pytest.approx(spec["thresholds"]["borderline"])


def test_the_full_spec_metric_set_is_recorded(bundle):
    for name, spec in bundle.variants.items():
        metrics = spec["metrics"]
        assert 0.5 < metrics["roc_auc"] < 1.0
        assert 0.0 < metrics["pr_auc_average_precision"] < 1.0
        for key in ("precision", "recall", "f1", "support"):
            assert key in metrics["positive_class"], (name, key)
        assert len(metrics["confusion_matrix"]["matrix"]) == 2
        assert "accuracy" in metrics
        assert "majority_class_baseline_accuracy" in metrics
        assert metrics["cross_validation"]["folds"] == 5
        assert len(metrics["cross_validation"]["roc_auc"]["per_fold"]) == 5


def _variant_columns(variant_name):
    spec = load_model(HEART_MODEL_FILE).variants[variant_name]
    return list(spec["numeric_features"]) + list(spec["categorical_features"])


def test_provenance_is_recorded_so_a_prediction_can_be_traced(bundle):
    dataset = bundle.get("dataset")
    assert dataset["sha256"] and len(dataset["sha256"]) == 64
    assert dataset["rows_raw"] > 0
    assert 0 < dataset["rows_used"] <= dataset["rows_raw"]
    assert dataset["synthetic_rows"] == 0
    assert "no SMOTE" in dataset["resampling"]
    assert bundle.get("sklearn_version")
    assert bundle.get("hyperparameters")["n_estimators"] > 0


def test_no_synthetic_or_resampled_rows_were_used(bundle):
    dataset = bundle.get("dataset")
    assert dataset["synthetic_rows"] == 0
    assert "none" in dataset["resampling"]


def test_the_age_units_are_stated_and_the_model_sees_years(bundle):
    dataset = bundle.get("dataset")
    units = dataset["age_units_raw"]
    assert units in ("days", "years"), units
    if units == "days":
        assert "365" in dataset["age_conversion"]
    assert dataset.get("age_conversion")


def test_the_model_receives_age_in_years_not_days(predictor):
    _, frame, _ = _frame(predictor, dict(HIGH_RISK, age=62))
    assert frame["age"].iloc[0] == 62.0


@pytest.mark.parametrize(
    "mg_dl,expected",
    [
        (0.0, 1),
        (120.0, 1),
        (199.0, 1),
        (199.999, 1),
        (200.0, 2),
        (239.0, 2),
        (239.999, 2),
        (240.0, 3),
        (600.0, 3),
    ],
)
def test_cholesterol_mg_dl_maps_to_the_ordinal_band_at_its_boundaries(mg_dl, expected):
    assert cholesterol_band(mg_dl) == expected


def test_the_band_cutoffs_are_the_ncep_atp_iii_ones():
    assert CHOLESTEROL_BAND_CUTOFFS == (200.0, 240.0)


@pytest.mark.parametrize("junk", [None, "", "  ", "not a number", object()])
def test_an_unusable_cholesterol_is_none_rather_than_a_guessed_band(junk):
    assert cholesterol_band(junk) is None


def test_a_boolean_is_never_read_as_a_cholesterol_value():
    assert cholesterol_band(True) is None
    assert cholesterol_band(False) is None


def test_cholesterol_reaches_the_model_in_the_space_it_was_trained_on(
    predictor, bundle
):
    _, frame, trace = _frame(predictor, dict(HIGH_RISK, cholesterol=268.0))
    declared = set()
    for spec in bundle.variants.values():
        declared |= set(spec["numeric_features"]) | set(spec["categorical_features"])

    if "cholesterol_band" in declared:
        assert "cholesterol" not in frame.columns
        assert frame["cholesterol_band"].iloc[0] == 3.0
        assert trace["cholesterol"]["status"] == "banded"
    else:
        assert "cholesterol_band" not in frame.columns
        assert frame["cholesterol"].iloc[0] == 268.0
        assert trace["cholesterol"]["status"] == "observed"

    assert trace["cholesterol"]["value"] == 268.0


def test_the_artifact_records_its_cholesterol_semantics(bundle):
    dataset = bundle.get("dataset")
    semantics = dataset["cholesterol_semantics"]
    banded = any(
        "cholesterol_band" in spec["numeric_features"]
        for spec in bundle.variants.values()
    )
    if banded:
        assert "NOT mg/dL" in semantics
        assert dataset["cholesterol_band_cutoffs_mg_dl"] == [200.0, 240.0]
    else:
        assert "mg/dL" in semantics
        assert "CONTINUOUS" in semantics


def test_banding_is_lossy_and_the_artifact_is_consistent_about_it(predictor, bundle):
    banded = any(
        "cholesterol_band" in spec["numeric_features"]
        for spec in bundle.variants.values()
    )
    a = predictor.predict(dict(HIGH_RISK, cholesterol=205.0))
    b = predictor.predict(dict(HIGH_RISK, cholesterol=235.0))
    c = predictor.predict(dict(HIGH_RISK, cholesterol=245.0))

    if banded:
        assert a.confidence == pytest.approx(b.confidence, abs=1e-12)
        assert c.confidence != pytest.approx(a.confidence, abs=1e-6)
    else:
        assert a.confidence is not None and b.confidence is not None
        assert c.confidence is not None


def test_the_gender_mapping_is_recorded_with_its_basis(bundle):
    dataset = bundle.get("dataset")
    mapping = dataset["gender_mapping"]
    assert sorted(mapping.values()) == ["female", "male"]
    assert sorted(mapping.keys()) == ["1", "2"]
    basis = dataset["gender_mapping_basis"]
    assert "INFERRED" in basis or "DOCUMENTED" in basis, basis
    assert sorted(dataset["gender_levels"]) == ["female", "male"]


@pytest.mark.parametrize("token,expected", [
    ("never", 0),
    ("former", 0),
    ("not_current", 0),
    ("not current", 0),
    ("NOT CURRENT", 0),
    ("current", 1),
    ("Current", 1),
])
def test_a_stated_smoking_history_maps_to_the_binary_flag(token, expected):
    assert smoking_current(token) == expected


@pytest.mark.parametrize("token", ["ever", "no_info", "No Info", None, "", "unknown"])
def test_an_ambiguous_or_absent_smoking_history_is_unknown(token):
    assert smoking_current(token) is None


def test_an_unknown_smoking_history_is_absent_from_the_model_matrix(predictor):
    for token in (None, "no_info", "ever"):
        features = dict(HIGH_RISK)
        if token is None:
            features.pop(TRI_STATE_SMOKING)
        else:
            features[TRI_STATE_SMOKING] = token
        variant, frame, trace = _frame(predictor, features)
        assert variant == "without_smoking", token
        assert "smoking_current" not in frame.columns, token
        assert trace[TRI_STATE_SMOKING]["status"] == "not_asserted", token
        expected = [
            c
            for c in _variant_columns("without_smoking")
            if c != "smoking_current"
        ]
        assert list(frame.columns) == expected, token


def test_a_stated_non_smoker_IS_included_as_a_real_answer(predictor):
    variant, frame, trace = _frame(predictor, dict(HIGH_RISK, smoking_history="never"))
    assert variant == "with_smoking"
    assert frame["smoking_current"].iloc[0] == 0.0
    assert trace[TRI_STATE_SMOKING]["status"] == "observed"


def test_a_stated_smoker_reaches_the_model_as_one(predictor):
    variant, frame, _ = _frame(predictor, dict(HIGH_RISK, smoking_history="current"))
    assert variant == "with_smoking"
    assert frame["smoking_current"].iloc[0] == 1.0


def test_absent_and_stated_non_smoker_use_different_fitted_pipelines(predictor):
    absent = dict(HIGH_RISK)
    absent.pop(TRI_STATE_SMOKING)
    stated = dict(HIGH_RISK, smoking_history="never")
    assert predictor.select_variant(absent)[0] != predictor.select_variant(stated)[0]


def test_the_absent_smoking_history_still_appears_in_evidence_saying_so(predictor):
    features = dict(HIGH_RISK)
    features.pop(TRI_STATE_SMOKING)
    decision = predictor.predict(features)
    item = [e for e in decision.evidence if e.feature == TRI_STATE_SMOKING][0]
    assert item.source_stage == "not_available"
    assert "without it rather than assuming an answer" in (item.note or "")


@pytest.mark.parametrize("gender", ["other", "prefer_not_to_say", "Prefer Not To Say"])
def test_an_unsupported_gender_asserts_no_category_and_does_not_crash(
    predictor, gender
):
    variant, frame, trace = _frame(predictor, dict(HIGH_RISK, gender=gender))
    assert trace["gender"]["status"] == "unrecognised"
    decision = predictor.predict(dict(HIGH_RISK, gender=gender))
    assert isinstance(decision, ClinicalDecision)


def test_an_absent_gender_uses_the_sentinel_not_the_majority_category(predictor):
    features = {k: v for k, v in HIGH_RISK.items() if k != "gender"}
    _, frame, trace = _frame(predictor, features)
    assert frame["gender"].iloc[0] == ABSENT_CATEGORY
    assert trace["gender"]["status"] == "not_asserted"
    assert ABSENT_CATEGORY not in load_model(HEART_MODEL_FILE).get("dataset")[
        "gender_levels"
    ]


def test_an_unseen_category_is_encoded_as_all_zeros(predictor, bundle):
    variant, frame, _ = _frame(predictor, dict(HIGH_RISK, gender="prefer_not_to_say"))
    pipeline = bundle.pipelines[variant]
    encoded = pipeline.named_steps["preprocess"].transform(frame)
    row = encoded[0] if not hasattr(encoded, "toarray") else encoded.toarray()[0]
    levels = bundle.get("dataset")["gender_levels"]
    numeric_count = len(bundle.variants[variant]["numeric_features"])
    block = row[numeric_count : numeric_count + len(levels)]
    assert all(value == 0 for value in block), (
        "an unsupported gender must encode as all zeros -- 'no category "
        "asserted' -- never as the majority category"
    )


def test_required_features_are_the_three_the_model_is_built_on(predictor):
    assert predictor.required_features == ("age", "bmi", "cholesterol")
    assert set(predictor.optional_features) == {"gender", "smoking_history"}


@pytest.mark.parametrize("missing", ["age", "bmi", "cholesterol"])
def test_missing_any_required_feature_yields_insufficient_data(predictor, missing):
    features = {k: v for k, v in HIGH_RISK.items() if k != missing}
    decision = predictor.predict(features)
    assert decision.status is DecisionStatus.INSUFFICIENT_DATA
    assert decision.risk is None
    assert decision.confidence is None
    assert decision.metadata["sufficiency"]["required_missing"] == [missing]


def test_all_three_required_present_is_the_sufficiency_boundary(predictor):
    enough = {"age": 62, "bmi": 34.5, "cholesterol": 268.0}
    decision = predictor.predict(enough)
    assert decision.status is not DecisionStatus.INSUFFICIENT_DATA
    assert decision.confidence is not None

    not_enough = {"age": 62, "bmi": 34.5}
    assert predictor.predict(not_enough).status is DecisionStatus.INSUFFICIENT_DATA


def test_a_none_valued_required_feature_is_absent_not_zero(predictor):
    decision = predictor.predict(dict(HIGH_RISK, cholesterol=None))
    assert decision.status is DecisionStatus.INSUFFICIENT_DATA


def test_no_features_at_all_yields_insufficient_data(predictor):
    decision = predictor.predict({})
    assert decision.status is DecisionStatus.INSUFFICIENT_DATA
    assert decision.risk is None
    assert set(decision.metadata["sufficiency"]["required_missing"]) == {
        "age", "bmi", "cholesterol",
    }


def test_an_unavailable_model_skips_rather_than_predicting_or_crashing():
    broken = HeartPredictor(artifact_filename="heart_rf_does_not_exist.joblib")
    assert broken.is_available() is False
    decision = broken.predict(dict(HIGH_RISK))
    assert decision.status is DecisionStatus.INSUFFICIENT_DATA
    assert decision.risk is None
    assert decision.metadata["skipped_reason"] == "model_unavailable"


def test_band_boundaries_are_inclusive_at_the_lower_edge(predictor):
    borderline, indicated = 0.2847, 0.6732

    assert predictor.band(indicated, borderline, indicated) == (
        DecisionStatus.INDICATED, RiskLevel.HIGH, "high",
    )
    assert predictor.band(indicated - 1e-9, borderline, indicated)[0] is (
        DecisionStatus.BORDERLINE
    )
    assert predictor.band(borderline, borderline, indicated) == (
        DecisionStatus.BORDERLINE, RiskLevel.MEDIUM, "medium",
    )
    assert predictor.band(borderline - 1e-9, borderline, indicated)[0] is (
        DecisionStatus.NOT_INDICATED
    )
    assert predictor.band(0.0, borderline, indicated) == (
        DecisionStatus.NOT_INDICATED, RiskLevel.LOW, "low",
    )
    assert predictor.band(1.0, borderline, indicated)[1] is RiskLevel.HIGH


def test_the_shipped_thresholds_are_the_ones_the_bands_use(predictor, bundle):
    for name, spec in bundle.variants.items():
        borderline = spec["thresholds"]["borderline"]
        indicated = spec["thresholds"]["indicated"]
        assert 0.0 < borderline < indicated < 1.0
        assert round(indicated, 2) != indicated
        assert spec.get("threshold_basis") or (
            "precision_lift_indicated" in spec["thresholds"]
        )
        if "precision_lift_indicated" in spec["thresholds"]:
            assert spec["thresholds"]["precision_lift_indicated"] == 1.5
            assert spec["thresholds"]["borderline_minimum_recall"] == 0.95
            assert spec["thresholds"]["target_precision_reachable"] is True
        else:
            assert "OUT-OF-FOLD" in spec["threshold_basis"]
            assert 0.0 <= spec["thresholds"]["indicated_precision_achieved"] <= 1.0
            assert 0.0 <= spec["thresholds"]["indicated_recall_achieved"] <= 1.0


def test_the_bands_are_not_degenerate(bundle):
    for name, spec in bundle.variants.items():
        bands = spec["metrics"]["risk_bands_on_test"]
        for label in ("low", "medium", "high"):
            assert bands[label]["patients"] > 0, (name, label)
        assert (
            bands["low"]["observed_positive_rate"]
            < bands["medium"]["observed_positive_rate"]
            < bands["high"]["observed_positive_rate"]
        )


def test_a_high_risk_profile_scores_above_a_low_risk_one(predictor):
    high = predictor.predict(dict(HIGH_RISK))
    low = predictor.predict(dict(LOW_RISK))
    assert high.confidence > low.confidence
    assert high.risk >= low.risk


def test_predictions_are_deterministic(predictor):
    first = predictor.predict(dict(HIGH_RISK))
    second = predictor.predict(dict(HIGH_RISK))
    assert first.confidence == pytest.approx(second.confidence, abs=1e-12)
    assert first.status is second.status
    assert first.risk is second.risk
    assert first.metadata["risk_band"] == second.metadata["risk_band"]


def test_the_model_reports_the_canonical_condition_byte_for_byte(predictor):
    assert predictor.condition == C.HEART_DISEASE == "Heart Disease"
    assert C.is_canonical_condition(predictor.condition)


def test_an_assessed_decision_is_machine_learning_with_confidence(predictor):
    decision = predictor.predict(dict(HIGH_RISK))
    assert decision.source_kind is DecisionSourceKind.MACHINE_LEARNING
    assert decision.source == "Random Forest"
    assert decision.confidence is not None
    assert 0.0 <= decision.confidence <= 1.0


def test_confidence_is_the_probability_of_the_positive_class(predictor):
    decision = predictor.predict(dict(HIGH_RISK))
    assert decision.confidence == decision.metadata["probability_positive"]
    assert decision.metadata["confidence_semantics"] == "probability_of_positive_class"


def test_every_decision_says_it_is_a_likelihood_not_a_risk_factor_count(predictor):
    for features in (HIGH_RISK, LOW_RISK, {}):
        decision = predictor.predict(dict(features))
        assert decision.metadata[ASSESSMENT_KIND_KEY] == ASSESSMENT_KIND_LIKELIHOOD
        assert "RISK FACTORS" in decision.metadata["assessment_kind_note"]


def test_the_decision_carries_module_16s_own_basis_vocabulary(predictor):
    from app.schemas.fusion import BASIS_MODEL_PROBABILITY, BASIS_NOT_ASSESSED

    assessed = predictor.predict(dict(HIGH_RISK))
    assert assessed.metadata[ASSESSMENT_BASIS_KEY] == BASIS_MODEL_PROBABILITY
    skipped = predictor.predict({})
    assert skipped.status is DecisionStatus.INSUFFICIENT_DATA
    assert skipped.metadata[ASSESSMENT_BASIS_KEY] == BASIS_NOT_ASSESSED


def test_the_rule_engine_decision_for_the_same_condition_carries_no_such_key():
    from app.services.rule_engine import evaluate_rules

    result = evaluate_rules(
        {
            "valid": {
                "age": {"value": 62, "unit": "years"},
                "bmi": {"value": 34.5, "unit": "kg/m2"},
                "cholesterol": {"value": 268.0, "unit": "mg/dl"},
                "hba1c": {"value": 6.9, "unit": "%"},
                "hypertension": {"value": True, "unit": None},
            }
        }
    )
    heart = [d for d in result.decisions if d.condition == C.HEART_DISEASE]
    assert heart, "the rule engine should still assess Heart Disease"
    for decision in heart:
        assert ASSESSMENT_KIND_KEY not in decision.metadata


def test_evidence_names_the_features_the_spec_calls_for(predictor):
    decision = predictor.predict(dict(HIGH_RISK))
    features = set(decision.evidence_features())
    assert {"age", "gender", "bmi", "cholesterol", "smoking_history"} <= features


def test_every_model_input_appears_in_evidence(predictor):
    decision = predictor.predict(dict(HIGH_RISK))
    cited = set(decision.evidence_features())
    for name in ("age", "bmi", "cholesterol", "gender", "smoking_history"):
        assert name in cited


def test_evidence_carries_the_actual_values_and_canonical_units(predictor):
    context = PredictionContext(units={"cholesterol": "mg/dl", "bmi": "kg/m2"})
    decision = predictor.predict(dict(HIGH_RISK), context=context)
    by_name = {e.feature: e for e in decision.evidence}
    assert by_name["cholesterol"].value == 268.0
    assert by_name["cholesterol"].unit == "mg/dl"
    assert by_name["bmi"].value == 34.5


def test_ml_evidence_carries_no_threshold(predictor):
    decision = predictor.predict(dict(HIGH_RISK))
    for item in decision.evidence:
        assert item.threshold is None
        assert item.comparator is None


def test_evidence_is_ordered_by_global_importance(predictor):
    decision = predictor.predict(dict(HIGH_RISK))
    importance = decision.metadata["global_feature_importance"]
    ordered = [e.feature for e in decision.evidence]
    scores = [importance.get(name, 0.0) for name in ordered]
    assert scores == sorted(scores, reverse=True)


def test_feature_importance_is_labelled_global_and_never_per_patient(predictor):
    decision = predictor.predict(dict(HIGH_RISK))
    assert decision.metadata["feature_importance_scope"] == "global_model_level"
    assert "NOT a per-patient explanation" in (
        decision.metadata["feature_importance_caveat"]
    )


def test_importance_is_keyed_by_canonical_feature_not_model_column(predictor):
    decision = predictor.predict(dict(HIGH_RISK))
    importance = decision.metadata["global_feature_importance"]
    assert "cholesterol" in importance
    assert "cholesterol_band" not in importance
    assert "smoking_history" in importance
    assert "smoking_current" not in importance


def test_questionable_input_is_carried_into_evidence_and_recommendations(predictor):
    context = PredictionContext(questionable=frozenset({"cholesterol"}))
    decision = predictor.predict(dict(HIGH_RISK), context=context)
    assert decision.metadata["questionable_features_used"] == ["cholesterol"]
    assert "INPUT_QUALITY_CAVEAT" in [r.code for r in decision.recommendations]


def test_metadata_records_the_variant_and_its_reason(predictor):
    decision = predictor.predict(dict(HIGH_RISK))
    assert decision.metadata["variant"] == "with_smoking"
    assert "smoking_history=current" in decision.metadata["variant_reason"]


def test_metadata_carries_model_provenance(predictor):
    decision = predictor.predict(dict(HIGH_RISK))
    model = decision.metadata["model"]
    assert model["available"] is True
    assert model["algorithm"] == "RandomForestClassifier"
    assert model["dataset_sha256"]
    assert model["synthetic_rows"] == 0
    assert model["blood_pressure_excluded"] is True


def test_the_blood_pressure_exclusion_is_stated_and_its_cost_measured(bundle):
    reference = bundle.get("blood_pressure_reference_model")
    assert reference["shipped"] is False
    assert reference["roc_auc"] > 0.5
    assert reference["shipped_model_roc_auc"] > 0.5
    assert reference["roc_auc_cost_of_exclusion"] == pytest.approx(
        reference["roc_auc"] - reference["shipped_model_roc_auc"], abs=1e-9
    )
    assert "median-impute" in reference["why_not_shipped"]


def test_the_decision_does_not_overstate_the_model_it_actually_shipped(predictor):
    decision = predictor.predict(dict(HIGH_RISK))
    reference = decision.metadata["model_performance_reference"]
    roc_auc = reference["roc_auc"]
    honest = reference["honest_read"]

    assert reference["majority_class_baseline_accuracy"] is not None
    if roc_auc < 0.75:
        assert "WEAK" in honest
    else:
        assert any(word in honest for word in ("WEAK", "COARSE")), honest
    assert "never a finding" in honest or "coarse" in honest.lower()


def test_band_meaning_states_the_measured_positive_rate(predictor):
    for features in (HIGH_RISK, LOW_RISK):
        decision = predictor.predict(dict(features))
        assert "%" in decision.metadata["band_meaning"]


def test_the_cleaning_rule_and_its_effect_are_recorded(bundle):
    dataset = bundle.get("dataset")
    rule = dataset["cleaning_rule"]
    removed = rule["removed"]["rows_removed_total"]

    if rule.get("applied") is False:
        assert removed == 0
        assert rule["basis"]
    else:
        assert rule["bmi"] == [8.0, 200.0]
        assert rule["height_cm"] == [120.0, 220.0]
        assert removed > 0
        assert dataset["rows_used"] == dataset["rows_raw"] - removed


def test_every_recommendation_resolves_to_a_catalogue_code(predictor):
    for features in (HIGH_RISK, LOW_RISK, {}):
        decision = predictor.predict(dict(features))
        assert decision.recommendations
        for recommendation in decision.recommendations:
            assert recommendation.code in RECOMMENDATIONS
            assert recommendation.text == RECOMMENDATIONS[recommendation.code].text


def test_every_decision_carries_the_not_a_diagnosis_disclaimer(predictor):
    for features in (HIGH_RISK, LOW_RISK, {}):
        decision = predictor.predict(dict(features))
        assert "NOT_A_DIAGNOSIS" in [r.code for r in decision.recommendations]


def test_a_model_of_this_precision_does_not_issue_an_urgency_instruction(predictor):
    high = predictor.predict(dict(HIGH_RISK))
    assert high.status in (DecisionStatus.INDICATED, DecisionStatus.BORDERLINE)
    codes = [r.code for r in high.recommendations]
    assert "SEEK_PROMPT_MEDICAL_ADVICE" not in codes
    assert "DISCUSS_WITH_CLINICIAN" in codes


def test_smoking_cessation_is_offered_only_on_a_stated_current_smoker(predictor):
    smoker = predictor.predict(dict(HIGH_RISK, smoking_history="current"))
    unknown = dict(HIGH_RISK)
    unknown.pop(TRI_STATE_SMOKING)
    codes = [r.code for r in predictor.predict(unknown).recommendations]
    assert "GENERAL_SMOKING_CESSATION_SUPPORT" in [
        r.code for r in smoker.recommendations
    ]
    assert "GENERAL_SMOKING_CESSATION_SUPPORT" not in codes


def test_all_user_facing_note_fragments_pass_the_safety_scanner():
    for fragment in HEART_NOTE_FRAGMENTS + BASE_NOTE_FRAGMENTS:
        assert scan_text(fragment) == [], fragment


def test_the_decision_never_asserts_a_diagnosis(predictor):
    decision = predictor.predict(dict(HIGH_RISK))
    for item in decision.evidence:
        assert scan_text(item.note or "") == []
    for recommendation in decision.recommendations:
        assert scan_text(recommendation.text) == []


def test_decisions_round_trip_through_json(predictor):
    for features in (HIGH_RISK, LOW_RISK, {}):
        decision = predictor.predict(dict(features))
        payload = json.loads(decision.model_dump_json())
        restored = ClinicalDecision.model_validate(payload)
        assert restored.condition == decision.condition
        assert restored.status is decision.status
        assert restored.risk == decision.risk


def test_metadata_contains_no_raw_report_text(predictor):
    decision = predictor.predict(dict(HIGH_RISK))
    blob = json.dumps(decision.metadata)
    for forbidden in ("raw_text", "patient_name", "NORTHFIELD"):
        assert forbidden not in blob


def test_the_registry_carries_all_three_shipped_predictors():
    registry = build_default_registry()
    assert set(registry.names()) == {"diabetes_rf", "heart_rf", "kidney_rf"}
    assert registry.conditions() == (
        C.DIABETES,
        C.HEART_DISEASE,
        C.KIDNEY_DISEASE,
    )
    assert len(registry) == 3


def test_the_default_singleton_carries_them_too():
    assert set(default_registry().names()) == {
        "diabetes_rf", "heart_rf", "kidney_rf",
    }


def test_every_registered_predictor_covers_a_fusion_condition():
    for predictor in build_default_registry():
        assert predictor.condition in C.FUSION_CONDITIONS
        assert C.is_canonical_condition(predictor.condition)


def test_the_registry_describes_the_new_predictors_without_phi():
    payload = build_default_registry().describe()
    assert payload["predictor_count"] == 3
    names = {entry["name"] for entry in payload["predictors"]}
    assert names == {"diabetes_rf", "heart_rf", "kidney_rf"}
    for entry in payload["predictors"]:
        assert entry["available"] is True
        assert entry["source_kind"] == "machine_learning"


MODEL_REVIEWER_VOCABULARY = (
    "roc-auc",
    "roc auc",
    "pr-auc",
    "auc",
    "uci",
    "held-out",
    "holdout",
    "training data",
    "training set",
    "precision at",
    "recall at",
    "f1",
)


def test_the_honest_read_is_written_for_a_clinician(predictor):
    decision = predictor.predict(dict(HIGH_RISK))
    honest = decision.metadata["model_performance_reference"]["honest_read"]
    lowered = honest.lower()

    offenders = [word for word in MODEL_REVIEWER_VOCABULARY if word in lowered]
    assert not offenders, f"{offenders} in: {honest}"

    assert "never a finding" in honest
    assert "Blood pressure" in honest
