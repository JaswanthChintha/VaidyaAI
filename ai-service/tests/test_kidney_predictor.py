"""Module 12 -- the Kidney Disease Predictor.

THESE TESTS LOAD THE PERSISTED ARTIFACT. They never fit a model. If
`ml/artifacts/kidney_rf_v1.joblib` is missing, run `python ml/train_kidney.py`;
training inside a test run would make these numbers unfalsifiable.

No API key and no network are needed.

Two groups of tests carry most of the weight here:

  * THE SKIP. Spec Module 12's headline feature. Asserted on the decision's
    STATUS, RISK and CONFIDENCE, because an under-informed prediction rendered
    as a reassuring "Low" is the failure `app/schemas/decisions.py` calls the
    most dangerous one this type can have.
  * THE TRI-STATE. Asserted on the ACTUAL DataFrame handed to the pipeline,
    not on metadata and not on a comment. "Nobody asked" silently becoming
    "no hypertension" produces a perfectly plausible-looking prediction.
"""

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
    ASSESSMENT_BASIS_KEY,
    ASSESSMENT_KIND_KEY,
    ASSESSMENT_KIND_LIKELIHOOD,
)
from app.ml.kidney import (
    HYPERTENSION_LEVELS,
    KIDNEY_METRICS_FILE,
    KIDNEY_MODEL_FILE,
    KIDNEY_NOTE_FRAGMENTS,
    TRI_STATE_HYPERTENSION,
    KidneyPredictor,
)
from app.schemas.decisions import (
    ClinicalDecision,
    DecisionSourceKind,
    DecisionStatus,
    RiskLevel,
)

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")


# --------------------------------------------------------------------------
# Fixtures -- small hand-written feature maps. NOT training data.
# --------------------------------------------------------------------------

HIGH_RISK = {
    "creatinine": 4.6,
    "hemoglobin": 8.9,
    "blood_glucose": 168.0,
    "age": 61,
    "hypertension": True,
}

LOW_RISK = {
    "creatinine": 0.9,
    "hemoglobin": 14.6,
    "blood_glucose": 92.0,
    "age": 29,
    "hypertension": False,
}


@pytest.fixture(scope="module")
def predictor() -> KidneyPredictor:
    return KidneyPredictor()


@pytest.fixture(scope="module")
def bundle():
    loaded = load_model(KIDNEY_MODEL_FILE)
    assert loaded is not None, (
        "the kidney model artifact is missing. Run "
        "`python ml/train_kidney.py`; tests never train."
    )
    return loaded


def _frame(predictor: KidneyPredictor, features: dict):
    variant, _ = predictor.select_variant(features)
    frame, trace = predictor._model_row(features, variant)
    return variant, frame, trace


# --------------------------------------------------------------------------
# The artifact exists, is loadable, and matches its metrics document
# --------------------------------------------------------------------------


def test_the_committed_artifact_loads(predictor, bundle):
    assert predictor.is_available() is True
    assert predictor.unavailable_reason() is None
    assert set(bundle.pipelines) == {"with_hypertension", "without_hypertension"}


def test_the_metrics_document_describes_the_committed_model():
    metrics = load_metrics(KIDNEY_METRICS_FILE)
    assert metrics is not None, "the kidney metrics artifact is missing"

    model_file: Path = artifact_path(KIDNEY_MODEL_FILE)
    digest = hashlib.sha256(model_file.read_bytes()).hexdigest()
    assert metrics["model_artifact"]["filename"] == KIDNEY_MODEL_FILE
    assert metrics["model_artifact"]["sha256"] == digest
    assert metrics["model_artifact"]["bytes"] == model_file.stat().st_size


def test_the_metrics_document_and_the_model_agree_on_thresholds(bundle):
    metrics = load_metrics(KIDNEY_METRICS_FILE)
    for name, spec in bundle.variants.items():
        recorded = metrics["variants"][name]["thresholds"]
        assert recorded["indicated"] == pytest.approx(spec["thresholds"]["indicated"])
        assert recorded["borderline"] == pytest.approx(spec["thresholds"]["borderline"])


def test_the_full_spec_metric_set_is_recorded(bundle):
    for name, spec in bundle.variants.items():
        metrics = spec["metrics"]
        assert 0.5 < metrics["roc_auc"] <= 1.0
        assert 0.0 < metrics["pr_auc_average_precision"] <= 1.0
        for key in ("precision", "recall", "f1", "support"):
            assert key in metrics["positive_class"], (name, key)
        assert len(metrics["confusion_matrix"]["matrix"]) == 2
        assert "accuracy" in metrics
        assert "majority_class_baseline_accuracy" in metrics
        assert metrics["cross_validation"]["folds"] == 5
        assert len(metrics["cross_validation"]["roc_auc"]["per_fold"]) == 5


def test_the_small_sample_caveat_travels_with_the_numbers(bundle):
    """400 rows. A metric without its uncertainty invites over-reading."""
    for name, spec in bundle.variants.items():
        assert "n=100" in spec["metrics"]["small_sample_caveat"]
    assert "399-row" in bundle.get("honest_read")


def test_provenance_is_recorded_so_a_prediction_can_be_traced(bundle):
    dataset = bundle.get("dataset")
    assert dataset["sha256"] and len(dataset["sha256"]) == 64
    assert dataset["rows_raw"] == 400
    assert dataset["synthetic_rows"] == 0
    assert "no SMOTE" in dataset["resampling"]
    assert bundle.get("sklearn_version")


def test_no_synthetic_or_resampled_rows_were_used(bundle):
    dataset = bundle.get("dataset")
    assert dataset["synthetic_rows"] == 0
    assert "none" in dataset["resampling"]


# --------------------------------------------------------------------------
# The malformed class label
# --------------------------------------------------------------------------


def test_the_malformed_label_row_was_dropped_not_repaired(bundle):
    """`ckd` 250 / `notckd` 149 / `no` 1. Guessing the label is fabrication."""
    dataset = bundle.get("dataset")
    assert dataset["raw_class_counts"]["no"] == 1
    assert dataset["malformed_label_rows_dropped"] == 1
    assert dataset["rows_used"] == 399
    assert dataset["positives"] == 250
    assert dataset["negatives"] == 149
    assert "not repaired" in dataset["malformed_label_policy"]


def test_missingness_was_imputed_not_dropped(bundle):
    """1,013 missing cells across 400 rows -- dropping them would gut the file."""
    dataset = bundle.get("dataset")
    assert dataset["missing_cells_total_raw"] > 1000
    assert dataset["missing_cells_in_used_features"]["hemoglobin"] == 52
    assert "No row is dropped for" in dataset["missing_value_policy"]


def test_the_units_match_the_feature_catalogue_without_conversion(bundle):
    from app.data.feature_catalog import FEATURES

    units = bundle.get("dataset")["units"]
    assert units["creatinine"] == FEATURES["creatinine"].canonical_unit
    assert units["hemoglobin"] == FEATURES["hemoglobin"].canonical_unit
    assert units["age"] == FEATURES["age"].canonical_unit
    assert bundle.get("dataset")["unit_conversion"].startswith("none")


# --------------------------------------------------------------------------
# THE TRI-STATE. ASSERTED ON THE REAL MATRIX.
# --------------------------------------------------------------------------


def test_an_absent_hypertension_is_absent_from_the_model_matrix(predictor):
    """THE test of this module. Absent must NEVER become 'no'."""
    features = {k: v for k, v in HIGH_RISK.items() if k != TRI_STATE_HYPERTENSION}
    variant, frame, trace = _frame(predictor, features)
    assert variant == "without_hypertension"
    assert TRI_STATE_HYPERTENSION not in frame.columns
    assert list(frame.columns) == [
        "creatinine", "hemoglobin", "blood_glucose", "age",
    ]
    assert trace[TRI_STATE_HYPERTENSION]["status"] == "not_asserted"
    # And nothing anywhere in the row stands in for the missing answer.
    assert "no" not in [str(v) for v in frame.iloc[0].tolist()]


def test_an_explicit_false_IS_included_as_a_real_answer(predictor):
    """'No, I do not have hypertension' is information. Not the same as absent."""
    variant, frame, trace = _frame(predictor, dict(HIGH_RISK, hypertension=False))
    assert variant == "with_hypertension"
    assert frame[TRI_STATE_HYPERTENSION].iloc[0] == HYPERTENSION_LEVELS[False] == "no"
    assert trace[TRI_STATE_HYPERTENSION]["status"] == "observed"
    assert trace[TRI_STATE_HYPERTENSION]["value"] is False


def test_an_explicit_true_reaches_the_model_as_yes(predictor):
    variant, frame, _ = _frame(predictor, dict(HIGH_RISK, hypertension=True))
    assert variant == "with_hypertension"
    assert frame[TRI_STATE_HYPERTENSION].iloc[0] == "yes"


@pytest.mark.parametrize("junk", [0, 1, "no", "yes", "false", "unknown", "", None])
def test_a_non_boolean_tri_state_is_treated_as_unknown_never_coerced(predictor, junk):
    """`bool("false")` is True and `bool(0)` is False. Both fabricate an answer."""
    variant, frame, _ = _frame(predictor, dict(HIGH_RISK, hypertension=junk))
    assert variant == "without_hypertension", junk
    assert TRI_STATE_HYPERTENSION not in frame.columns, junk


def test_absent_and_false_use_different_fitted_pipelines(predictor):
    absent = {k: v for k, v in HIGH_RISK.items() if k != TRI_STATE_HYPERTENSION}
    stated = dict(HIGH_RISK, hypertension=False)
    assert predictor.select_variant(absent)[0] == "without_hypertension"
    assert predictor.select_variant(stated)[0] == "with_hypertension"


def test_the_absent_tri_state_still_appears_in_evidence_saying_so(predictor):
    features = {k: v for k, v in HIGH_RISK.items() if k != TRI_STATE_HYPERTENSION}
    decision = predictor.predict(features)
    item = [e for e in decision.evidence if e.feature == TRI_STATE_HYPERTENSION][0]
    assert item.value is None
    assert item.source_stage == "not_available"
    assert "without it rather than assuming an answer" in (item.note or "")


def test_the_variant_reason_states_that_nothing_was_assumed(predictor):
    features = {k: v for k, v in HIGH_RISK.items() if k != TRI_STATE_HYPERTENSION}
    decision = predictor.predict(features)
    assert "never encoded as 'no'" in decision.metadata["variant_reason"]


def test_the_tri_state_policy_is_recorded_in_the_artifact(bundle):
    assert "NEVER encoded as 'no'" in bundle.get("tri_state_policy")


def test_a_boolean_never_leaks_into_a_numeric_column(predictor):
    """isinstance(True, int) is True; without the guard it becomes 1.0."""
    _, frame, trace = _frame(predictor, dict(HIGH_RISK, creatinine=True))
    assert trace["creatinine"]["status"] == "imputed"
    assert frame["creatinine"].isna().iloc[0]


# --------------------------------------------------------------------------
# INFORMATION SUFFICIENCY -- spec Module 12's headline feature
# --------------------------------------------------------------------------


def test_required_features_are_the_load_bearing_pair(predictor):
    assert predictor.required_features == ("creatinine", "hemoglobin")
    assert set(predictor.optional_features) == {
        "blood_glucose", "age", "hypertension",
    }


@pytest.mark.parametrize("missing", ["creatinine", "hemoglobin"])
def test_missing_either_required_feature_skips_the_prediction(predictor, missing):
    """The spec's own words: skip rather than blindly producing a result."""
    features = {k: v for k, v in HIGH_RISK.items() if k != missing}
    decision = predictor.predict(features)
    assert decision.status is DecisionStatus.INSUFFICIENT_DATA
    assert decision.risk is None, "a skipped topic must never render as Low"
    assert decision.confidence is None
    assert decision.metadata["skipped"] is True
    assert decision.metadata["sufficiency"]["required_missing"] == [missing]


@pytest.mark.parametrize("optional", ["blood_glucose", "age", "hypertension"])
def test_missing_an_optional_feature_still_produces_a_prediction(predictor, optional):
    """A predictor that skips too eagerly is not safer, only silent."""
    features = {k: v for k, v in HIGH_RISK.items() if k != optional}
    decision = predictor.predict(features)
    assert decision.status is not DecisionStatus.INSUFFICIENT_DATA
    assert decision.confidence is not None


def test_the_sufficiency_boundary_is_exactly_the_two_required_features(predictor):
    """One step either side of the line."""
    exactly_enough = {"creatinine": 4.6, "hemoglobin": 8.9}
    decision = predictor.predict(exactly_enough)
    assert decision.status is not DecisionStatus.INSUFFICIENT_DATA
    assert decision.risk is not None

    one_short = {"creatinine": 4.6}
    skipped = predictor.predict(one_short)
    assert skipped.status is DecisionStatus.INSUFFICIENT_DATA
    assert skipped.risk is None


def test_a_none_valued_required_feature_is_absent_not_zero(predictor):
    decision = predictor.predict(dict(HIGH_RISK, hemoglobin=None))
    assert decision.status is DecisionStatus.INSUFFICIENT_DATA


def test_no_features_at_all_yields_insufficient_data(predictor):
    decision = predictor.predict({})
    assert decision.status is DecisionStatus.INSUFFICIENT_DATA
    assert decision.risk is None
    assert decision.confidence is None
    assert set(decision.metadata["sufficiency"]["required_missing"]) == {
        "creatinine", "hemoglobin",
    }


def test_the_skip_explains_itself_with_its_basis(predictor):
    decision = predictor.predict({"creatinine": 1.1})
    rule = decision.metadata["sufficiency_rule"]
    assert rule["required_features"] == ["creatinine", "hemoglobin"]
    assert "defines renal function" in rule["basis"]


def test_the_skip_names_the_missing_feature_in_evidence(predictor):
    decision = predictor.predict({"creatinine": 1.1})
    cited = {e.feature for e in decision.evidence}
    assert cited == {"hemoglobin"}
    assert all(e.value is None for e in decision.evidence)


def test_a_skip_is_still_a_decision_so_the_topic_is_never_silent(predictor):
    """`Kidney Disease` is always_assessed; silence would read as 'nothing found'."""
    assert C.CONDITIONS[C.KIDNEY_DISEASE].always_assessed is True
    decision = predictor.predict({})
    assert isinstance(decision, ClinicalDecision)
    assert decision.condition == C.KIDNEY_DISEASE
    assert decision.recommendations


def test_an_unreadable_document_changes_the_wording_of_the_skip(predictor):
    context = PredictionContext(partial_document=True)
    decision = predictor.predict({"creatinine": 1.1}, context=context)
    assert decision.status is DecisionStatus.INSUFFICIENT_DATA
    assert decision.metadata["partial_document"] is True
    assert "UNREADABLE_DOCUMENT_RECHECK" in [r.code for r in decision.recommendations]


def test_the_sufficiency_rule_is_backed_by_measured_numbers(bundle):
    """The rule must rest on evidence, not on intuition."""
    evidence = bundle.get("sufficiency_evidence")
    subsets = evidence["subsets"]
    assert subsets["creatinine+hemoglobin"] > 0.95
    # Every single-feature model is materially worse than the required pair.
    for single in ("creatinine", "hemoglobin", "blood_glucose", "age"):
        assert subsets[single] < subsets["creatinine+hemoglobin"]
    # And blanking a required input at RUN TIME costs more than any optional.
    blanked = evidence["imputed_at_prediction_time"]["blanked"]
    assert blanked["hemoglobin"]["delta"] < blanked["age"]["delta"]
    assert blanked["hemoglobin"]["delta"] < blanked["hypertension"]["delta"]


def test_an_unavailable_model_skips_rather_than_predicting_or_crashing():
    broken = KidneyPredictor(artifact_filename="kidney_rf_does_not_exist.joblib")
    assert broken.is_available() is False
    decision = broken.predict(dict(HIGH_RISK))
    assert decision.status is DecisionStatus.INSUFFICIENT_DATA
    assert decision.risk is None
    assert decision.metadata["skipped_reason"] == "model_unavailable"


# --------------------------------------------------------------------------
# Imputation of optional numerics
# --------------------------------------------------------------------------


def test_a_missing_optional_numeric_is_left_for_the_median_imputer(predictor):
    features = {k: v for k, v in HIGH_RISK.items() if k != "blood_glucose"}
    _, frame, trace = _frame(predictor, features)
    assert frame["blood_glucose"].isna().iloc[0]
    assert trace["blood_glucose"]["status"] == "imputed"


def test_an_imputed_value_says_so_in_evidence(predictor):
    features = {k: v for k, v in HIGH_RISK.items() if k != "age"}
    decision = predictor.predict(features)
    item = [e for e in decision.evidence if e.feature == "age"][0]
    assert "median of its training data" in (item.note or "")
    assert item.value is None


def test_a_numeric_string_is_accepted(predictor):
    _, frame, trace = _frame(predictor, dict(HIGH_RISK, creatinine=" 4.6 "))
    assert frame["creatinine"].iloc[0] == 4.6
    assert trace["creatinine"]["status"] == "observed"


def test_unparseable_numeric_falls_back_to_imputation_rather_than_crashing(predictor):
    decision = predictor.predict(dict(HIGH_RISK, blood_glucose="not a number"))
    assert decision.status is not DecisionStatus.INSUFFICIENT_DATA
    assert decision.metadata["features_imputed"] == ["blood_glucose"]


# --------------------------------------------------------------------------
# Risk bands
# --------------------------------------------------------------------------


def test_band_boundaries_are_inclusive_at_the_lower_edge(predictor):
    borderline, indicated = 0.18, 0.4112

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
        assert spec["thresholds"]["indicated_minimum_recall"] == 0.98
        assert spec["thresholds"]["borderline_minimum_recall"] == 0.99
        # The rule Module 10 uses is recorded, and is non-binding here.
        assert spec["thresholds"]["module_10_rule_would_give"] is not None
        assert (
            spec["thresholds"]["indicated_precision_achieved"]
            >= spec["thresholds"]["module_10_rule_target_precision"]
        )


def test_the_borderline_band_is_not_collapsed_onto_the_indicated_one(bundle):
    """The degenerate case the criteria were changed to avoid."""
    for name, spec in bundle.variants.items():
        assert spec["thresholds"]["borderline"] < spec["thresholds"]["indicated"]


def test_a_clearly_impaired_profile_is_indicated_and_high(predictor):
    decision = predictor.predict(dict(HIGH_RISK))
    assert decision.status is DecisionStatus.INDICATED
    assert decision.risk is RiskLevel.HIGH
    assert decision.confidence > 0.5


def test_a_clearly_healthy_profile_is_not_indicated_and_low(predictor):
    decision = predictor.predict(dict(LOW_RISK))
    assert decision.status is DecisionStatus.NOT_INDICATED
    assert decision.risk is RiskLevel.LOW
    assert decision.confidence < 0.5


def test_predictions_are_deterministic(predictor):
    """The band a reader sees is identical; the float may differ by one ulp
    because the forest sums 300 tree votes across worker threads."""
    first = predictor.predict(dict(HIGH_RISK))
    second = predictor.predict(dict(HIGH_RISK))
    assert first.confidence == pytest.approx(second.confidence, abs=1e-12)
    assert first.status is second.status
    assert first.metadata["risk_band"] == second.metadata["risk_band"]


# --------------------------------------------------------------------------
# The decision contract
# --------------------------------------------------------------------------


def test_the_model_reports_the_canonical_condition_byte_for_byte(predictor):
    assert predictor.condition == C.KIDNEY_DISEASE == "Kidney Disease"
    assert C.is_canonical_condition(predictor.condition)


def test_an_assessed_decision_is_machine_learning_with_confidence(predictor):
    decision = predictor.predict(dict(HIGH_RISK))
    assert decision.source_kind is DecisionSourceKind.MACHINE_LEARNING
    assert decision.source == "Random Forest"
    assert decision.confidence is not None


def test_confidence_is_the_probability_of_the_positive_class(predictor):
    decision = predictor.predict(dict(HIGH_RISK))
    assert decision.confidence == decision.metadata["probability_positive"]
    assert decision.metadata["confidence_semantics"] == "probability_of_positive_class"


def test_every_decision_says_it_is_a_likelihood(predictor):
    for features in (HIGH_RISK, LOW_RISK, {}):
        decision = predictor.predict(dict(features))
        assert decision.metadata[ASSESSMENT_KIND_KEY] == ASSESSMENT_KIND_LIKELIHOOD


def test_the_decision_carries_module_16s_own_basis_vocabulary(predictor):
    """A skip must not claim `model_probability`: no model ran."""
    from app.schemas.fusion import BASIS_MODEL_PROBABILITY, BASIS_NOT_ASSESSED

    assessed = predictor.predict(dict(HIGH_RISK))
    assert assessed.metadata[ASSESSMENT_BASIS_KEY] == BASIS_MODEL_PROBABILITY
    skipped = predictor.predict({})
    assert skipped.status is DecisionStatus.INSUFFICIENT_DATA
    assert skipped.metadata[ASSESSMENT_BASIS_KEY] == BASIS_NOT_ASSESSED


# --------------------------------------------------------------------------
# Evidence
# --------------------------------------------------------------------------


def test_evidence_names_the_features_the_spec_calls_for(predictor):
    """Spec Module 12: creatinine, haemoglobin, blood glucose, age, hypertension."""
    decision = predictor.predict(dict(HIGH_RISK))
    assert set(decision.evidence_features()) == {
        "creatinine", "hemoglobin", "blood_glucose", "age", "hypertension",
    }


def test_every_model_input_appears_in_evidence(predictor):
    decision = predictor.predict(dict(HIGH_RISK))
    cited = set(decision.evidence_features())
    for column in decision.metadata["model_input_columns"]:
        assert column in cited


def test_evidence_carries_the_actual_values_and_canonical_units(predictor):
    context = PredictionContext(
        units={"creatinine": "mg/dl", "hemoglobin": "g/dl", "age": "years"}
    )
    decision = predictor.predict(dict(HIGH_RISK), context=context)
    by_name = {e.feature: e for e in decision.evidence}
    assert by_name["creatinine"].value == 4.6
    assert by_name["creatinine"].unit == "mg/dl"
    assert by_name["hemoglobin"].unit == "g/dl"


def test_ml_evidence_carries_no_threshold(predictor):
    decision = predictor.predict(dict(HIGH_RISK))
    for item in decision.evidence:
        assert item.threshold is None
        assert item.comparator is None


def test_evidence_is_ordered_by_global_importance(predictor):
    decision = predictor.predict(dict(HIGH_RISK))
    importance = decision.metadata["global_feature_importance"]
    scores = [importance.get(e.feature, 0.0) for e in decision.evidence]
    assert scores == sorted(scores, reverse=True)


def test_feature_importance_is_labelled_global_and_never_per_patient(predictor):
    decision = predictor.predict(dict(HIGH_RISK))
    assert decision.metadata["feature_importance_scope"] == "global_model_level"
    assert "NOT a per-patient explanation" in (
        decision.metadata["feature_importance_caveat"]
    )


def test_a_clinically_extreme_low_haemoglobin_is_described_as_low(predictor):
    """Wording matters: 'far above the usual range' would be simply wrong."""
    context = PredictionContext(clinically_extreme=frozenset({"hemoglobin"}))
    decision = predictor.predict(dict(HIGH_RISK), context=context)
    item = [e for e in decision.evidence if e.feature == "hemoglobin"][0]
    assert "far below" in (item.note or "")


def test_questionable_input_is_carried_into_evidence_and_recommendations(predictor):
    context = PredictionContext(questionable=frozenset({"creatinine"}))
    decision = predictor.predict(dict(HIGH_RISK), context=context)
    assert decision.metadata["questionable_features_used"] == ["creatinine"]
    assert "INPUT_QUALITY_CAVEAT" in [r.code for r in decision.recommendations]


# --------------------------------------------------------------------------
# Metadata and honesty about the model
# --------------------------------------------------------------------------


def test_metadata_carries_model_provenance(predictor):
    decision = predictor.predict(dict(HIGH_RISK))
    model = decision.metadata["model"]
    assert model["available"] is True
    assert model["algorithm"] == "RandomForestClassifier"
    assert model["dataset_sha256"]
    assert model["malformed_label_rows_dropped"] == 1
    # The 19 kidney parameters VaidyaAI cannot supply are named, not hidden.
    assert "bu" in model["kidney_parameters_unavailable_to_vaidyaai"]


def test_the_decision_does_not_overstate_a_tiny_dataset(predictor):
    decision = predictor.predict(dict(HIGH_RISK))
    reference = decision.metadata["model_performance_reference"]
    assert reference["roc_auc"] > 0.95
    # THE SMALL-SAMPLE FACT, not one phrasing of it and not the count.
    #
    # This asserted the literal "399 rows", then "399". The note no longer
    # carries the count at all: a clinician reads it on the doctor summary and
    # the dataset arithmetic is the EVIDENCE for the caveat rather than the
    # caveat. The invariant is unchanged and is what the count was a proxy for
    # -- a near-perfect metric must never appear without the fact that the
    # dataset was small and the accuracy does not transfer. The exact figures
    # stay in the artifact metrics, whose audience is a model reviewer.
    honest = reference["honest_read"]
    lowered_note = honest.lower()
    assert any(word in lowered_note for word in ("small", "tiny", "limited")), honest
    assert "screening population" in honest
    assert reference["majority_class_baseline_accuracy"] == pytest.approx(0.63)


def test_band_meaning_states_the_measured_positive_rate(predictor):
    for features in (HIGH_RISK, LOW_RISK):
        decision = predictor.predict(dict(features))
        assert "%" in decision.metadata["band_meaning"]


# --------------------------------------------------------------------------
# Recommendations -- catalogue codes only
# --------------------------------------------------------------------------


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


def test_prompt_medical_advice_is_reserved_for_the_high_band(predictor):
    high = predictor.predict(dict(HIGH_RISK))
    low = predictor.predict(dict(LOW_RISK))
    assert "SEEK_PROMPT_MEDICAL_ADVICE" in [r.code for r in high.recommendations]
    assert "SEEK_PROMPT_MEDICAL_ADVICE" not in [r.code for r in low.recommendations]


def test_a_skip_recommends_completing_the_information(predictor):
    codes = [r.code for r in predictor.predict({}).recommendations]
    assert "INFORMATION_INCOMPLETE" in codes


def test_all_user_facing_note_fragments_pass_the_safety_scanner():
    for fragment in KIDNEY_NOTE_FRAGMENTS + BASE_NOTE_FRAGMENTS:
        assert scan_text(fragment) == [], fragment


def test_the_decision_never_asserts_a_diagnosis(predictor):
    for features in (HIGH_RISK, LOW_RISK, {}):
        decision = predictor.predict(dict(features))
        for item in decision.evidence:
            assert scan_text(item.note or "") == []
        for recommendation in decision.recommendations:
            assert scan_text(recommendation.text) == []


# --------------------------------------------------------------------------
# Serialisation and privacy
# --------------------------------------------------------------------------


def test_decisions_round_trip_through_json(predictor):
    for features in (HIGH_RISK, LOW_RISK, {}):
        decision = predictor.predict(dict(features))
        payload = json.loads(decision.model_dump_json())
        restored = ClinicalDecision.model_validate(payload)
        assert restored.condition == decision.condition
        assert restored.status is decision.status
        assert restored.risk == decision.risk


def test_insufficient_data_decisions_round_trip_too(predictor):
    decision = predictor.predict({"creatinine": 1.1})
    restored = ClinicalDecision.model_validate(
        json.loads(decision.model_dump_json())
    )
    assert restored.status is DecisionStatus.INSUFFICIENT_DATA
    assert restored.risk is None
    assert restored.confidence is None


def test_metadata_contains_no_raw_report_text(predictor):
    decision = predictor.predict(dict(HIGH_RISK))
    blob = json.dumps(decision.metadata)
    for forbidden in ("raw_text", "patient_name", "NORTHFIELD"):
        assert forbidden not in blob


# --------------------------------------------------------------------------
# The note's audience
# --------------------------------------------------------------------------

#: Vocabulary that belongs to whoever trained the model, not to the clinician
#: the doctor summary is addressed to. `honest_read` is rendered VERBATIM on
#: that page (Module 32), so this is the only layer that can keep it readable:
#: a check in the frontend runs against a fixture and cannot see this string.
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
    """The caveat is worth nothing to a reader who stops at the vocabulary.

    It is rendered verbatim on the document a patient hands to a clinician, and
    a clinician is not obliged to know what a ROC-AUC is. Every FACT stays --
    the dataset size, the easy separation, the fragility of the test split --
    only the register changed.
    """
    decision = predictor.predict(dict(HIGH_RISK))
    honest = decision.metadata["model_performance_reference"]["honest_read"]
    lowered = honest.lower()

    offenders = [word for word in MODEL_REVIEWER_VOCABULARY if word in lowered]
    assert not offenders, f"{offenders} in: {honest}"

    # ...and the substance did not go with the jargon. Not the COUNT: the
    # dataset arithmetic is the evidence for the caveat, not the caveat, and a
    # clinician acts on the smallness rather than on 399.
    assert any(word in lowered for word in ("small", "tiny", "limited")), honest
    # THE DIRECTION OF THE CLAIM, not just the phrase. Asserting that
    # "screening population" appears passes just as happily for "it HOLDS in a
    # screening population" -- the inversion of the one thing this note exists
    # to say about a near-perfect number. Several phrasings are allowed so the
    # sentence can still be reworded; the negation cannot be dropped.
    assert any(
        phrase in lowered
        for phrase in (
            "nothing shows it holds",
            "no evidence it holds",
            "not shown to hold",
        )
    ), honest
