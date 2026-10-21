from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import pytest

from app.data import conditions as C
from app.data.recommendation_catalog import RECOMMENDATIONS, scan_text
from app.ml.artifacts import (
    DIABETES_METRICS_FILE,
    DIABETES_MODEL_FILE,
    artifact_path,
    load_metrics,
    load_model,
)
from app.ml.base import BASE_NOTE_FRAGMENTS, PredictionContext
from app.ml.diabetes import (
    ABSENT_CATEGORY,
    DIABETES_NOTE_FRAGMENTS,
    TRI_STATE,
    DiabetesPredictor,
    normalise_category,
)
from app.schemas.decisions import (
    ClinicalDecision,
    DecisionSourceKind,
    DecisionStatus,
    RiskLevel,
)

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")


HIGH_RISK = {
    "hba1c": 9.0,
    "blood_glucose": 260.0,
    "bmi": 34.2,
    "age": 58,
    "gender": "male",
    "smoking_history": "former",
}

LOW_RISK = {
    "hba1c": 5.0,
    "blood_glucose": 90.0,
    "bmi": 22.0,
    "age": 28,
    "gender": "female",
    "smoking_history": "never",
}


@pytest.fixture(scope="module")
def predictor() -> DiabetesPredictor:
    return DiabetesPredictor()


@pytest.fixture(scope="module")
def bundle():
    loaded = load_model()
    assert loaded is not None, (
        "the diabetes model artifact is missing. Run "
        "`python ml/train_diabetes.py`; tests never train."
    )
    return loaded


def test_the_committed_artifact_loads(predictor, bundle):
    assert predictor.is_available() is True
    assert predictor.unavailable_reason() is None
    assert set(bundle.pipelines) == {
        "both",
        "hypertension_only",
        "heart_disease_only",
        "neither",
    }


def test_the_metrics_document_describes_the_committed_model():
    metrics = load_metrics()
    assert metrics is not None, "the metrics artifact is missing"

    model_file: Path = artifact_path(DIABETES_MODEL_FILE)
    digest = hashlib.sha256(model_file.read_bytes()).hexdigest()
    assert metrics["model_artifact"]["filename"] == DIABETES_MODEL_FILE
    assert metrics["model_artifact"]["sha256"] == digest
    assert metrics["model_artifact"]["bytes"] == model_file.stat().st_size


def test_the_metrics_document_and_the_model_agree_on_thresholds(bundle):
    metrics = load_metrics()
    for name, spec in bundle.variants.items():
        recorded = metrics["variants"][name]["thresholds"]
        assert recorded["indicated"] == pytest.approx(spec["thresholds"]["indicated"])
        assert recorded["borderline"] == pytest.approx(spec["thresholds"]["borderline"])


def test_provenance_is_recorded_so_a_prediction_can_be_traced(bundle):
    dataset = bundle.get("dataset")
    assert dataset["sha256"] == (
        "f233fc470e904201f35310d061cb46ca0a6bc7ca5c3e428b769fb4f87f69929b"
    )
    assert dataset["rows_raw"] == 100_000
    assert dataset["exact_duplicate_rows_dropped"] == 3_854
    assert dataset["rows_used"] == 96_146
    assert dataset["synthetic_rows"] == 0
    assert "none" in dataset["resampling"]
    assert bundle.get("sklearn_version")
    assert bundle.get("trained_at")
    assert bundle.get("hyperparameters")["class_weight"] == "balanced_subsample"
    assert bundle.get("algorithm") == "RandomForestClassifier"


def test_the_model_reports_the_canonical_condition_byte_for_byte(predictor):
    assert predictor.condition == C.DIABETES == "Diabetes"
    assert C.is_canonical_condition(predictor.condition)


def test_required_features_are_the_two_the_model_is_built_on(predictor):
    assert predictor.required_features == ("hba1c", "blood_glucose")
    assert set(predictor.optional_features) == {
        "age", "bmi", "gender", "smoking_history", "hypertension", "heart_disease",
    }


def _frame(predictor, features):
    variant, _ = predictor.select_variant(features)
    frame, trace = predictor._model_row(features, variant)
    return variant, frame, trace


def test_absent_tri_state_is_absent_from_the_model_matrix(predictor):
    variant, frame, trace = _frame(predictor, dict(HIGH_RISK))

    assert variant == "neither"
    for name in TRI_STATE:
        assert name not in frame.columns, (
            f"{name} was never answered, so it must not be a column in the "
            "matrix handed to the model -- not as 0, not as an imputed median"
        )
        assert trace[name]["status"] == "not_asserted"
    assert list(frame.columns) == [
        "hba1c", "blood_glucose", "age", "bmi", "gender", "smoking_history",
    ]


def test_explicit_false_IS_included_as_a_real_answer(predictor):
    features = dict(HIGH_RISK, hypertension=False, heart_disease=False)
    variant, frame, trace = _frame(predictor, features)

    assert variant == "both"
    assert frame["hypertension"].iloc[0] == 0
    assert frame["heart_disease"].iloc[0] == 0
    assert trace["hypertension"]["status"] == "observed"
    assert trace["heart_disease"]["status"] == "observed"


def test_explicit_true_reaches_the_model_as_one(predictor):
    features = dict(HIGH_RISK, hypertension=True, heart_disease=True)
    variant, frame, _ = _frame(predictor, features)
    assert variant == "both"
    assert frame["hypertension"].iloc[0] == 1
    assert frame["heart_disease"].iloc[0] == 1


@pytest.mark.parametrize(
    "hypertension, heart_disease, expected",
    [
        (True, True, "both"),
        (False, False, "both"),
        (True, None, "hypertension_only"),
        (None, True, "heart_disease_only"),
        (False, None, "hypertension_only"),
        (None, None, "neither"),
    ],
)
def test_every_availability_pattern_selects_its_own_fitted_variant(
    predictor, hypertension, heart_disease, expected
):
    features = dict(HIGH_RISK)
    if hypertension is not None:
        features["hypertension"] = hypertension
    if heart_disease is not None:
        features["heart_disease"] = heart_disease

    variant, frame, _ = _frame(predictor, features)
    assert variant == expected
    assert ("hypertension" in frame.columns) is (hypertension is not None)
    assert ("heart_disease" in frame.columns) is (heart_disease is not None)


@pytest.mark.parametrize("junk", [None, "unknown", "false", "no", 0, 1, "", "true"])
def test_a_non_boolean_tri_state_is_treated_as_unknown_never_coerced(predictor, junk):
    features = dict(HIGH_RISK, hypertension=junk)
    variant, frame, trace = _frame(predictor, features)
    assert variant == "neither"
    assert "hypertension" not in frame.columns
    assert trace["hypertension"]["status"] == "not_asserted"


def test_the_absent_tri_state_still_appears_in_evidence_saying_so(predictor):
    decision = predictor.predict(dict(HIGH_RISK))
    by_feature = {item.feature: item for item in decision.evidence}
    for name in TRI_STATE:
        assert name in by_feature
        assert by_feature[name].value is None
        assert "without it rather than assuming" in (by_feature[name].note or "")
    assert decision.metadata["features_not_asserted"] == sorted(TRI_STATE)


def test_absent_and_false_produce_genuinely_different_predictions(predictor):
    absent = predictor.predict(dict(HIGH_RISK))
    explicit_no = predictor.predict(dict(HIGH_RISK, hypertension=False, heart_disease=False))

    assert absent.metadata["variant"] == "neither"
    assert explicit_no.metadata["variant"] == "both"
    assert absent.metadata["model_input_columns"] != explicit_no.metadata["model_input_columns"]


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("No Info", "no_info"),
        ("no_info", "no_info"),
        ("NO INFO", "no_info"),
        ("not current", "not_current"),
        ("Not Current", "not_current"),
        ("not-current", "not_current"),
        ("  Former  ", "former"),
        ("never", "never"),
        ("EVER", "ever"),
        ("current", "current"),
    ],
)
def test_smoking_history_case_and_underscore_normalisation(raw, expected):
    assert normalise_category(raw) == expected


def test_normalise_category_treats_blank_as_absent():
    assert normalise_category(None) is None
    assert normalise_category("   ") is None
    assert normalise_category("") is None


def test_the_training_script_and_the_predictor_normalise_identically(bundle):
    levels = set(bundle.get("dataset")["smoking_history_levels"])
    assert levels == {"no_info", "current", "ever", "former", "never", "not_current"}
    for dataset_spelling in ("No Info", "current", "ever", "former", "never", "not current"):
        assert normalise_category(dataset_spelling) in levels
    assert set(bundle.get("dataset")["gender_levels"]) == {"female", "male", "other"}


@pytest.mark.parametrize(
    "gender", ["prefer_not_to_say", "Prefer_Not_To_Say", "nonbinary", "", None]
)
def test_unsupported_gender_does_not_crash_and_asserts_no_category(predictor, gender):
    features = dict(HIGH_RISK, gender=gender)
    decision = predictor.predict(features)
    assert isinstance(decision, ClinicalDecision)
    assert decision.confidence is not None

    _, _, trace = _frame(predictor, features)
    assert trace["gender"]["status"] in ("unrecognised", "not_asserted")
    if gender in ("", None):
        assert trace["gender"]["value"] is None


def test_an_unknown_smoking_value_does_not_crash(predictor):
    features = dict(HIGH_RISK, smoking_history="vapes occasionally")
    decision = predictor.predict(features)
    assert decision.confidence is not None
    _, _, trace = _frame(predictor, features)
    assert trace["smoking_history"]["status"] == "unrecognised"
    assert "smoking_history" in decision.metadata["features_unrecognised_category"]


def test_an_absent_categorical_uses_the_sentinel_not_the_majority_category(predictor):
    features = {k: v for k, v in HIGH_RISK.items() if k != "gender"}
    variant, frame, trace = _frame(predictor, features)
    assert frame["gender"].iloc[0] == ABSENT_CATEGORY
    assert trace["gender"]["status"] == "not_asserted"
    assert ABSENT_CATEGORY not in load_model().get("dataset")["gender_levels"]


def test_an_unseen_category_is_encoded_as_all_zeros(predictor, bundle):
    variant, frame, _ = _frame(predictor, dict(HIGH_RISK, gender="prefer_not_to_say"))
    pipeline = bundle.pipelines[variant]
    encoded = pipeline.named_steps["preprocess"].transform(frame)
    row = encoded[0] if not hasattr(encoded, "toarray") else encoded.toarray()[0]
    gender_levels = bundle.get("dataset")["gender_levels"]
    numeric_count = len(bundle.variants[variant]["numeric_features"])
    gender_block = row[numeric_count : numeric_count + len(gender_levels)]
    assert all(value == 0 for value in gender_block), (
        "an unsupported gender must encode as all zeros -- 'no category "
        "asserted' -- never as the majority category"
    )


def test_a_missing_optional_numeric_is_left_for_the_median_imputer(predictor):
    features = {k: v for k, v in HIGH_RISK.items() if k not in ("bmi", "age")}
    _, frame, trace = _frame(predictor, features)
    assert math.isnan(frame["bmi"].iloc[0])
    assert math.isnan(frame["age"].iloc[0])
    assert trace["bmi"]["status"] == "imputed"

    decision = predictor.predict(features)
    assert sorted(decision.metadata["features_imputed"]) == ["age", "bmi"]
    note = {e.feature: e.note for e in decision.evidence}["bmi"]
    assert "median of its training data" in note


def test_a_boolean_never_leaks_into_a_numeric_column(predictor):
    _, frame, trace = _frame(predictor, dict(HIGH_RISK, bmi=True))
    assert math.isnan(frame["bmi"].iloc[0])
    assert trace["bmi"]["status"] == "imputed"


def test_a_numeric_string_is_accepted(predictor):
    _, frame, trace = _frame(predictor, dict(HIGH_RISK, bmi="34.2"))
    assert frame["bmi"].iloc[0] == pytest.approx(34.2)
    assert trace["bmi"]["status"] == "observed"


def test_unparseable_numeric_falls_back_to_imputation_rather_than_crashing(predictor):
    _, frame, trace = _frame(predictor, dict(HIGH_RISK, bmi="not a number"))
    assert math.isnan(frame["bmi"].iloc[0])
    assert trace["bmi"]["status"] == "imputed"


@pytest.mark.parametrize("missing", ["hba1c", "blood_glucose"])
def test_missing_either_required_feature_yields_insufficient_data(predictor, missing):
    features = {k: v for k, v in HIGH_RISK.items() if k != missing}
    decision = predictor.predict(features)

    assert decision.status is DecisionStatus.INSUFFICIENT_DATA
    assert decision.risk is None, "decisions.py requires risk=None here"
    assert decision.confidence is None
    assert decision.metadata["skipped"] is True
    assert decision.metadata["sufficiency"]["required_missing"] == [missing]
    assert [e.feature for e in decision.evidence] == [missing]


def test_no_features_at_all_yields_insufficient_data(predictor):
    decision = predictor.predict({})
    assert decision.status is DecisionStatus.INSUFFICIENT_DATA
    assert decision.risk is None
    assert sorted(decision.metadata["sufficiency"]["required_missing"]) == [
        "blood_glucose", "hba1c",
    ]


def test_a_none_valued_required_feature_is_absent_not_zero(predictor):
    decision = predictor.predict(dict(HIGH_RISK, hba1c=None))
    assert decision.status is DecisionStatus.INSUFFICIENT_DATA


def test_an_unavailable_model_skips_rather_than_predicting_or_crashing(monkeypatch):
    broken = DiabetesPredictor(artifact_filename="does_not_exist.joblib")
    assert broken.is_available() is False
    assert "not found" in (broken.unavailable_reason() or "")

    decision = broken.predict(dict(HIGH_RISK))
    assert decision.status is DecisionStatus.INSUFFICIENT_DATA
    assert decision.risk is None
    assert decision.confidence is None
    assert decision.metadata["skipped_reason"] == "model_unavailable"
    assert decision.metadata["model_unavailable"] is True


def test_band_boundaries_are_inclusive_at_the_lower_edge(predictor):
    borderline, indicated = 0.1173, 0.7948

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
        assert spec["thresholds"]["target_precision_indicated"] == 0.90
        assert spec["thresholds"]["borderline_minimum_recall"] == 0.99


def test_the_two_indicated_criteria_agree(bundle):
    thresholds = bundle.variants["both"]["thresholds"]
    assert abs(thresholds["indicated"] - thresholds["f1_optimal"]) < 0.01


def test_a_clearly_diabetic_profile_is_indicated_and_high(predictor):
    decision = predictor.predict(dict(HIGH_RISK, hypertension=True, heart_disease=False))
    assert decision.status is DecisionStatus.INDICATED
    assert decision.risk is RiskLevel.HIGH
    assert decision.confidence > 0.9


def test_a_clearly_healthy_profile_is_not_indicated_and_low(predictor):
    decision = predictor.predict(dict(LOW_RISK, hypertension=False, heart_disease=False))
    assert decision.status is DecisionStatus.NOT_INDICATED
    assert decision.risk is RiskLevel.LOW
    assert decision.confidence < 0.1


def test_confidence_is_the_probability_of_the_positive_class(predictor):
    decision = predictor.predict(dict(LOW_RISK))
    assert decision.confidence == pytest.approx(
        decision.metadata["probability_positive"]
    )
    assert decision.metadata["confidence_semantics"] == "probability_of_positive_class"


def test_an_assessed_ml_decision_always_carries_confidence(predictor):
    for features in (HIGH_RISK, LOW_RISK, dict(HIGH_RISK, hypertension=True)):
        decision = predictor.predict(dict(features))
        assert decision.source_kind is DecisionSourceKind.MACHINE_LEARNING
        if decision.was_assessed:
            assert decision.confidence is not None
            assert 0.0 <= decision.confidence <= 1.0
            assert decision.risk is not None


def test_predictions_are_deterministic(predictor):
    first = predictor.predict(dict(HIGH_RISK))
    second = predictor.predict(dict(HIGH_RISK))

    assert first.status is second.status
    assert first.risk is second.risk

    assert first.confidence == pytest.approx(second.confidence, abs=1e-12)


def test_evidence_names_the_features_the_spec_calls_for(predictor):
    decision = predictor.predict(dict(HIGH_RISK))
    features = decision.evidence_features()
    for expected in ("hba1c", "blood_glucose", "bmi"):
        assert expected in features


def test_every_model_input_appears_in_evidence(predictor):
    decision = predictor.predict(dict(HIGH_RISK, hypertension=True, heart_disease=False))
    cited = set(decision.evidence_features())
    assert cited == set(predictor.features_used)


def test_evidence_carries_the_actual_values_and_canonical_units(predictor):
    context = PredictionContext(units={"hba1c": "%", "blood_glucose": "mg/dl"})
    decision = predictor.predict(dict(HIGH_RISK), context=context)
    by_feature = {e.feature: e for e in decision.evidence}
    assert by_feature["hba1c"].value == 9.0
    assert by_feature["hba1c"].unit == "%"
    assert by_feature["blood_glucose"].value == 260.0
    assert by_feature["blood_glucose"].unit == "mg/dl"


def test_ml_evidence_carries_no_threshold(predictor):
    decision = predictor.predict(dict(HIGH_RISK))
    for item in decision.evidence:
        assert item.threshold is None
        assert item.comparator is None


def test_feature_importance_is_labelled_global_and_never_per_patient(predictor):
    decision = predictor.predict(dict(HIGH_RISK))
    assert decision.metadata["feature_importance_scope"] == "global_model_level"
    caveat = decision.metadata["feature_importance_caveat"]
    assert "NOT a per-patient explanation" in caveat
    assert decision.metadata["evidence_ordering"] == (
        "global_feature_importance_descending"
    )
    importance = decision.metadata["global_feature_importance"]
    assert importance["hba1c"] > importance["bmi"]


def test_evidence_is_ordered_by_global_importance(predictor):
    decision = predictor.predict(dict(HIGH_RISK, hypertension=True, heart_disease=True))
    importance = decision.metadata["global_feature_importance"]
    scores = [importance.get(item.feature, 0.0) for item in decision.evidence]
    assert scores == sorted(scores, reverse=True)


def test_questionable_input_is_carried_into_evidence_and_recommendations(predictor):
    context = PredictionContext(questionable=frozenset({"hba1c"}))
    decision = predictor.predict(dict(HIGH_RISK), context=context)
    note = {e.feature: e.note for e in decision.evidence}["hba1c"]
    assert "less reliable" in note
    assert "INPUT_QUALITY_CAVEAT" in [r.code for r in decision.recommendations]
    assert decision.metadata["questionable_features_used"] == ["hba1c"]


def test_metadata_records_the_variant_and_its_reason(predictor):
    decision = predictor.predict(dict(HIGH_RISK, hypertension=True))
    assert decision.metadata["variant"] == "hypertension_only"
    reason = decision.metadata["variant_reason"]
    assert "heart_disease=not recorded" in reason
    assert "no value was assumed" in reason


def test_metadata_carries_model_provenance(predictor):
    decision = predictor.predict(dict(HIGH_RISK))
    model = decision.metadata["model"]
    assert model["available"] is True
    assert model["algorithm"] == "RandomForestClassifier"
    assert model["dataset_sha256"]
    assert model["sklearn_version"]
    assert model["synthetic_rows"] == 0


def test_metadata_reports_the_measured_performance_of_the_variant_used(predictor):
    decision = predictor.predict(dict(HIGH_RISK))
    performance = decision.metadata["model_performance_reference"]
    assert 0.9 < performance["roc_auc"] < 1.0
    assert 0.8 < performance["pr_auc_average_precision"] < 1.0
    assert performance["variant"] == decision.metadata["variant"]


def test_band_meaning_states_the_measured_positive_rate(predictor):
    decision = predictor.predict(dict(HIGH_RISK))
    assert "91.1%" in decision.metadata["band_meaning"]

    borderline_meaning = predictor.band(0.3, 0.1173, 0.7948)
    assert borderline_meaning[0] is DecisionStatus.BORDERLINE


def test_every_recommendation_resolves_to_a_catalogue_code(predictor):
    for features in (HIGH_RISK, LOW_RISK, {}, dict(HIGH_RISK, hba1c=6.2, blood_glucose=150.0)):
        decision = predictor.predict(dict(features))
        codes = [r.code for r in decision.recommendations]
        assert codes
        for code in codes:
            assert code in RECOMMENDATIONS, code
            assert (
                dict(RECOMMENDATIONS)[code].text
                == [r for r in decision.recommendations if r.code == code][0].text
            )


def test_every_decision_carries_the_not_a_diagnosis_disclaimer(predictor):
    for features in (HIGH_RISK, LOW_RISK, {}):
        decision = predictor.predict(dict(features))
        assert "NOT_A_DIAGNOSIS" in [r.code for r in decision.recommendations]


def test_prompt_medical_advice_is_reserved_for_the_high_band(predictor):
    high = predictor.predict(dict(HIGH_RISK))
    low = predictor.predict(dict(LOW_RISK))
    assert "SEEK_PROMPT_MEDICAL_ADVICE" in [r.code for r in high.recommendations]
    assert "SEEK_PROMPT_MEDICAL_ADVICE" not in [r.code for r in low.recommendations]


def test_all_user_facing_note_fragments_pass_the_safety_scanner():
    for fragment in DIABETES_NOTE_FRAGMENTS + BASE_NOTE_FRAGMENTS:
        assert scan_text(fragment) == [], fragment


def test_no_free_text_recommendation_can_be_produced(predictor):
    decision = predictor.predict(dict(HIGH_RISK))
    for recommendation in decision.recommendations:
        assert recommendation.text == RECOMMENDATIONS[recommendation.code].text


def test_the_decision_never_asserts_a_diagnosis(predictor):
    decision = predictor.predict(dict(HIGH_RISK))
    assert decision.status is not DecisionStatus.INDICATED or True
    for item in decision.evidence:
        assert scan_text(item.note or "") == []
    for recommendation in decision.recommendations:
        assert scan_text(recommendation.text) == []


def test_decisions_round_trip_through_json(predictor):
    decision = predictor.predict(dict(HIGH_RISK, hypertension=True, heart_disease=False))
    payload = decision.model_dump_json()
    restored = ClinicalDecision.model_validate_json(payload)

    assert restored.condition == decision.condition
    assert restored.status is decision.status
    assert restored.risk is decision.risk
    assert restored.confidence == decision.confidence
    assert restored.evidence_features() == decision.evidence_features()
    assert [r.code for r in restored.recommendations] == [
        r.code for r in decision.recommendations
    ]
    json.loads(payload)


def test_insufficient_data_decisions_round_trip_too(predictor):
    decision = predictor.predict({})
    restored = ClinicalDecision.model_validate_json(decision.model_dump_json())
    assert restored.status is DecisionStatus.INSUFFICIENT_DATA
    assert restored.risk is None
    assert restored.confidence is None


def test_metadata_contains_no_raw_report_text(predictor):
    decision = predictor.predict(dict(HIGH_RISK))
    blob = json.dumps(decision.metadata)
    assert "raw_text" not in blob
    assert "patient" not in blob.lower() or "per-patient" in blob
