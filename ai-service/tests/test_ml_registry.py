"""Module 9 / 13 -- the predictor interface, the registry, and the engine.

These tests deliberately use FAKE predictors, not the diabetes one. The point
of Modules 9 and 13 is that the engine works for predictors that do not exist
yet, so the strongest evidence is a predictor invented inside a test file
dropping in and coming out the other end untouched.

NO TRAINING happens here and no artifact is loaded except where a test says so.
"""

from __future__ import annotations

import pytest

from app.data import conditions as C
from app.data.recommendation_catalog import scan_text
from app.ml.base import (
    BASE_NOTE_FRAGMENTS,
    ML_MODULE,
    STAGE_ML,
    PredictionContext,
    Predictor,
    PredictorError,
    SufficiencyReport,
)
from app.ml.engine import ML_ENGINE_VERSION, predict_all
from app.ml.registry import (
    DuplicatePredictorError,
    PredictorRegistry,
    UnknownPredictorError,
    build_default_registry,
    default_registry,
)
from app.schemas.decisions import (
    ClinicalDecision,
    DecisionSourceKind,
    DecisionStatus,
    EvidenceItem,
    RiskLevel,
)


# --------------------------------------------------------------------------
# Fakes -- exactly what a Module 11/12 author will write
# --------------------------------------------------------------------------


class FakeHeartPredictor(Predictor):
    """A predictor for a DIFFERENT condition, written the way Module 11 will be."""

    name = "fake_heart"
    condition = C.HEART_DISEASE
    source_label = "Fake Forest"
    version = "9.9.9"
    required_features = ("cholesterol",)
    optional_features = ("age", "gender")

    def __init__(self, probability: float = 0.8) -> None:
        self.probability = probability
        self.calls: list = []
        super().__init__()

    def _predict(self, features, context) -> ClinicalDecision:
        self.calls.append(dict(features))
        return ClinicalDecision(
            condition=self.condition,
            status=DecisionStatus.INDICATED,
            risk=RiskLevel.HIGH,
            confidence=self.probability,
            source=self.source_label,
            source_kind=DecisionSourceKind.MACHINE_LEARNING,
            evidence=[EvidenceItem(feature="cholesterol", value=features["cholesterol"])],
            metadata={"probability_positive": self.probability, "features_observed": ["cholesterol"]},
        )


class ExplodingPredictor(Predictor):
    name = "exploding"
    condition = C.KIDNEY_DISEASE
    required_features = ("creatinine",)

    def _predict(self, features, context):
        raise RuntimeError("the model blew up with value 1.9 mg/dl")


# --------------------------------------------------------------------------
# The interface refuses to be built wrong
# --------------------------------------------------------------------------


def test_a_predictor_cannot_be_built_with_a_non_canonical_condition():
    """The single most valuable check in `base.py`.

    A drifted condition string breaks Module 16 SILENTLY -- nothing raises, the
    user just sees two unfused cards. So it must raise here.
    """

    class Drifted(FakeHeartPredictor):
        condition = "heart disease"  # lower case: not the canonical constant

    with pytest.raises(PredictorError, match="conditions.py"):
        Drifted()


def test_a_predictor_cannot_be_built_with_no_required_features():
    class NeverSkips(FakeHeartPredictor):
        required_features = ()

    with pytest.raises(PredictorError, match="can never refuse"):
        NeverSkips()


def test_a_predictor_cannot_list_a_feature_as_both_required_and_optional():
    class Confused(FakeHeartPredictor):
        required_features = ("cholesterol",)
        optional_features = ("cholesterol", "age")

    with pytest.raises(PredictorError, match="both"):
        Confused()


def test_a_predictor_cannot_be_built_without_a_name():
    class Nameless(FakeHeartPredictor):
        name = "  "

    with pytest.raises(PredictorError, match="name"):
        Nameless()


def test_predictor_is_abstract():
    with pytest.raises(TypeError):
        Predictor()  # type: ignore[abstract]


# --------------------------------------------------------------------------
# Information sufficiency -- spec Module 12, inherited by every predictor
# --------------------------------------------------------------------------


def test_missing_required_feature_yields_insufficient_data_with_risk_none():
    predictor = FakeHeartPredictor()
    decision = predictor.predict({"age": 60})

    assert decision.status is DecisionStatus.INSUFFICIENT_DATA
    # decisions.py REQUIRES this, and it is the whole safety property: a topic
    # that was never assessed must not render as a reassuring "Low".
    assert decision.risk is None
    assert decision.confidence is None
    assert decision.was_assessed is False
    assert predictor.calls == [], "_predict must not be reached at all"


def test_sufficiency_gate_cannot_be_bypassed_by_a_subclass_that_forgets_it():
    """`_predict` is unreachable without its inputs, by construction."""
    predictor = FakeHeartPredictor()
    predictor.predict({})
    predictor.predict({"gender": "male"})
    assert predictor.calls == []

    predictor.predict({"cholesterol": 240})
    assert predictor.calls == [{"cholesterol": 240}]


def test_insufficient_decision_names_the_missing_features_in_evidence():
    predictor = FakeHeartPredictor()
    decision = predictor.predict({})
    assert [item.feature for item in decision.evidence] == ["cholesterol"]
    assert decision.evidence[0].value is None
    assert decision.metadata["sufficiency"]["required_missing"] == ["cholesterol"]


def test_insufficient_decision_recommends_only_catalogue_codes():
    from app.data.recommendation_catalog import RECOMMENDATIONS

    decision = FakeHeartPredictor().predict({})
    codes = [r.code for r in decision.recommendations]
    assert codes, "an insufficient-data decision must still say something"
    for code in codes:
        assert code in RECOMMENDATIONS
    assert "NOT_A_DIAGNOSIS" in codes


def test_explicit_false_is_present_not_absent():
    """`False` and `0` are ANSWERS. Only None/blank are absence.

    Collapsing an explicit "no" into absence is the mirror image of the bug
    this whole module exists to prevent.
    """
    assert Predictor._is_present(False) is True
    assert Predictor._is_present(0) is True
    assert Predictor._is_present(0.0) is True
    assert Predictor._is_present(None) is False
    assert Predictor._is_present("   ") is False
    assert Predictor._is_present("never") is True


def test_sufficiency_report_records_optional_features_too():
    report = FakeHeartPredictor().check_sufficiency({"cholesterol": 200, "age": 40})
    assert report.sufficient is True
    assert report.missing == ()
    assert report.optional_present == ("age",)
    assert report.optional_missing == ("gender",)


# --------------------------------------------------------------------------
# The output audit
# --------------------------------------------------------------------------


def test_a_predictor_emitting_the_wrong_condition_is_caught():
    class Liar(FakeHeartPredictor):
        def _predict(self, features, context):
            decision = super()._predict(features, context)
            return decision.model_copy(update={"condition": C.DIABETES})

    with pytest.raises(PredictorError, match="registered for"):
        Liar().predict({"cholesterol": 200})


def test_a_predictor_emitting_a_rule_source_kind_is_caught():
    class Mislabelled(FakeHeartPredictor):
        def _predict(self, features, context):
            decision = super()._predict(features, context)
            return decision.model_copy(
                update={"source_kind": DecisionSourceKind.CLINICAL_RULE}
            )

    with pytest.raises(PredictorError, match="machine_learning"):
        Mislabelled().predict({"cholesterol": 200})


def test_a_predictor_returning_a_non_decision_is_caught():
    class Wrong(FakeHeartPredictor):
        def _predict(self, features, context):
            return {"condition": "Heart Disease"}

    with pytest.raises(PredictorError, match="ClinicalDecision"):
        Wrong().predict({"cholesterol": 200})


def test_decisions_py_itself_forbids_an_ml_decision_without_confidence():
    """Belt and braces: the shared schema enforces this independently."""
    with pytest.raises(ValueError, match="must report confidence"):
        ClinicalDecision(
            condition=C.DIABETES,
            status=DecisionStatus.INDICATED,
            risk=RiskLevel.HIGH,
            confidence=None,
            source="Random Forest",
            source_kind=DecisionSourceKind.MACHINE_LEARNING,
        )


# --------------------------------------------------------------------------
# Registry -- register / look up / iterate
# --------------------------------------------------------------------------


def test_register_lookup_and_iterate():
    registry = PredictorRegistry()
    heart = FakeHeartPredictor()
    assert len(registry) == 0

    registry.register(heart)
    assert len(registry) == 1
    assert registry.get("fake_heart") is heart
    assert registry.find("fake_heart") is heart
    assert list(registry) == [heart]
    assert registry.names() == ("fake_heart",)
    assert heart in registry
    assert "fake_heart" in registry


def test_duplicate_registration_raises_rather_than_silently_replacing():
    registry = PredictorRegistry()
    first = FakeHeartPredictor()
    registry.register(first)
    with pytest.raises(DuplicatePredictorError):
        registry.register(FakeHeartPredictor())
    assert registry.get("fake_heart") is first


def test_replace_is_possible_but_must_be_deliberate():
    registry = PredictorRegistry()
    registry.register(FakeHeartPredictor())
    second = FakeHeartPredictor()
    registry.register(second, replace=True)
    assert registry.get("fake_heart") is second


def test_unknown_lookup_raises_and_find_returns_none():
    registry = PredictorRegistry()
    with pytest.raises(UnknownPredictorError):
        registry.get("nope")
    with pytest.raises(UnknownPredictorError):
        registry.unregister("nope")
    assert registry.find("nope") is None


def test_registry_rejects_a_non_predictor():
    registry = PredictorRegistry()

    class NotAPredictor:
        name = "sneaky"
        condition = C.DIABETES

    with pytest.raises(PredictorError, match="Predictor"):
        registry.register(NotAPredictor())  # type: ignore[arg-type]


def test_unregister_removes():
    registry = PredictorRegistry()
    heart = registry.register(FakeHeartPredictor())
    assert registry.unregister("fake_heart") is heart
    assert len(registry) == 0


def test_for_condition_and_conditions_use_canonical_order():
    registry = PredictorRegistry()
    registry.register(ExplodingPredictor())  # Kidney Disease
    heart = registry.register(FakeHeartPredictor())  # Heart Disease

    assert registry.for_condition(C.HEART_DISEASE) == [heart]
    assert registry.for_condition(C.DIABETES) == []
    # Canonical order, not registration order: Heart Disease outranks Kidney.
    assert registry.conditions() == (C.HEART_DISEASE, C.KIDNEY_DISEASE)


def test_iteration_is_a_snapshot():
    """Registering mid-run must not mutate the sequence being walked."""
    registry = PredictorRegistry()
    registry.register(FakeHeartPredictor())
    seen = []
    for predictor in registry:
        seen.append(predictor.name)
        if len(seen) == 1:
            registry.register(ExplodingPredictor())
    assert seen == ["fake_heart"]


def test_describe_carries_no_values():
    registry = build_default_registry()
    document = registry.describe()
    assert document["predictor_count"] == len(registry)
    assert C.DIABETES in document["conditions_covered"]
    entry = document["predictors"][0]
    assert set(entry) >= {
        "name",
        "condition",
        "source",
        "source_kind",
        "required_features",
        "optional_features",
        "available",
    }


def test_default_registry_is_a_singleton_and_carries_the_shipped_predictors():
    """UPDATED for Modules 11 and 12.

    This asserted `conditions() == (C.DIABETES,)` when Diabetes was the only
    registered predictor. The assertion is STRENGTHENED rather than relaxed:
    all three predictors must be present, each under its canonical condition,
    and `conditions()` must still come back in canonical rank order -- which is
    what makes the engine's output stable regardless of import order.
    """
    assert default_registry() is default_registry()
    assert set(default_registry().names()) == {
        "diabetes_rf",
        "heart_rf",
        "kidney_rf",
    }
    assert default_registry().conditions() == (
        C.DIABETES,
        C.HEART_DISEASE,
        C.KIDNEY_DISEASE,
    )
    # Every registered predictor is registered under a FUSION condition, so a
    # drifted condition string cannot slip through unnoticed.
    for predictor in default_registry():
        assert predictor.condition in C.FUSION_CONDITIONS
        assert C.is_canonical_condition(predictor.condition)


def test_build_default_registry_is_isolated_from_the_singleton():
    fresh = build_default_registry()
    assert fresh is not default_registry()
    fresh.register(FakeHeartPredictor())
    assert "fake_heart" not in default_registry().names()


# --------------------------------------------------------------------------
# The engine iterates the registry and knows nothing about any predictor
# --------------------------------------------------------------------------


def test_a_brand_new_predictor_drops_in_with_no_engine_change():
    """The Module 11 / 12 acceptance test, written before those modules exist."""
    registry = PredictorRegistry()
    registry.register(FakeHeartPredictor(probability=0.77))

    result = predict_all(
        {"valid": {"cholesterol": {"name": "cholesterol", "value": 260.0}}},
        registry=registry,
    )

    assert len(result.decisions) == 1
    decision = result.decisions[0]
    assert decision.condition == C.HEART_DISEASE
    assert decision.source_kind is DecisionSourceKind.MACHINE_LEARNING
    assert decision.confidence == 0.77
    assert result.summary.predictors_run == 1
    assert result.summary.conditions_assessed == [C.HEART_DISEASE]
    assert result.metadata["predictors_registered"] == ["fake_heart"]


def test_decisions_are_ordered_by_canonical_condition():
    registry = PredictorRegistry()
    registry.register(ExplodingPredictor())  # Kidney, registered FIRST
    registry.register(FakeHeartPredictor())  # Heart

    result = predict_all(
        {"valid": {"cholesterol": {"name": "cholesterol", "value": 260.0}}},
        registry=registry,
    )
    assert [d.condition for d in result.decisions] == [
        C.HEART_DISEASE,
        C.KIDNEY_DISEASE,
    ]


def test_one_broken_predictor_does_not_take_down_the_others():
    registry = PredictorRegistry()
    registry.register(ExplodingPredictor())
    registry.register(FakeHeartPredictor())

    result = predict_all(
        {"valid": {"cholesterol": {"name": "cholesterol", "value": 260.0},
                   "creatinine": {"name": "creatinine", "value": 1.9}}},
        registry=registry,
    )

    by_condition = {d.condition: d for d in result.decisions}
    assert by_condition[C.HEART_DISEASE].status is DecisionStatus.INDICATED
    kidney = by_condition[C.KIDNEY_DISEASE]
    assert kidney.status is DecisionStatus.INSUFFICIENT_DATA
    assert kidney.risk is None
    assert kidney.metadata["predictor_error"] is True
    assert any("could not complete" in w for w in result.warnings)


def test_a_model_exception_message_never_reaches_the_output():
    """The exception text embeds a medical value; only its TYPE may survive."""
    registry = PredictorRegistry()
    registry.register(ExplodingPredictor())
    result = predict_all(
        {"valid": {"creatinine": {"name": "creatinine", "value": 1.9}}},
        registry=registry,
    )
    blob = result.model_dump_json()
    assert "blew up" not in blob
    assert "1.9 mg/dl" not in blob
    assert result.decisions[0].metadata["predictor_error_type"] == "RuntimeError"


def test_empty_registry_warns_rather_than_returning_a_silent_empty_success():
    result = predict_all({"valid": {}}, registry=PredictorRegistry())
    assert result.decisions == []
    assert any("no ML predictors are registered" in w for w in result.warnings)
    # "nothing assessed" must NOT become "Low".
    assert result.summary.highest_risk is None


def test_every_registered_predictor_appears_in_the_run_summary_even_when_skipped():
    registry = PredictorRegistry()
    registry.register(FakeHeartPredictor())
    registry.register(ExplodingPredictor())

    result = predict_all({"valid": {}}, registry=registry)
    runs = {r.name: r for r in result.summary.predictor_runs}
    assert set(runs) == {"fake_heart", "exploding"}
    assert all(r.assessed is False for r in runs.values())
    assert runs["fake_heart"].required_missing == ["cholesterol"]
    assert runs["fake_heart"].probability_positive is None
    assert result.summary.predictors_skipped == 2


def test_non_canonical_feature_names_are_reported_not_silently_dropped():
    registry = PredictorRegistry()
    registry.register(FakeHeartPredictor())
    result = predict_all(
        {"valid": {"cholesterol": {"name": "cholesterol", "value": 260.0},
                   "ldl_cholesterol": {"name": "ldl_cholesterol", "value": 160.0}}},
        registry=registry,
    )
    assert any("ldl_cholesterol" in w for w in result.warnings)


def test_engine_metadata_and_warning_stage():
    registry = PredictorRegistry()
    registry.register(FakeHeartPredictor())
    result = predict_all({"valid": {}}, registry=registry)
    assert result.metadata["engine_version"] == ML_ENGINE_VERSION
    assert result.metadata["input_kind"] == "validated"
    stages = {w.stage for w in result.all_warnings}
    assert stages <= {STAGE_ML, "extraction", "feature_engineering", "validation"}
    for warning in result.all_warnings:
        if warning.stage == STAGE_ML:
            assert warning.module == ML_MODULE


def test_upstream_warnings_are_carried_through_untouched():
    """Dropping upstream warnings has already been a real defect twice here."""
    registry = PredictorRegistry()
    registry.register(FakeHeartPredictor())
    result = predict_all(
        {
            "valid": {},
            "all_warnings": [
                {"stage": "extraction", "module": 4, "message": "page 1 was recovered"}
            ],
        },
        registry=registry,
    )
    assert any(
        w.stage == "extraction" and "recovered" in w.message
        for w in result.upstream_warnings
    )
    assert any(
        w.stage == "extraction" and "recovered" in w.message
        for w in result.all_warnings
    )


def test_partial_document_is_flagged_and_changes_the_skip_note():
    registry = PredictorRegistry()
    registry.register(FakeHeartPredictor())
    result = predict_all(
        {"valid": {}, "upstream": {"pages_unreadable": [2]}},
        registry=registry,
    )
    assert result.summary.partial_document is True
    assert any("partially readable" in w for w in result.warnings)
    codes = [r.code for r in result.decisions[0].recommendations]
    assert "UNREADABLE_DOCUMENT_RECHECK" in codes


def test_no_input_at_all_is_not_an_error():
    result = predict_all(registry=PredictorRegistry())
    assert result.summary.input_kind == "none"
    assert result.decisions == []


# --------------------------------------------------------------------------
# Safety: the fixed note fragments are user-facing
# --------------------------------------------------------------------------


def test_base_note_fragments_pass_the_recommendation_safety_scanner():
    for fragment in BASE_NOTE_FRAGMENTS:
        assert scan_text(fragment) == [], fragment


def test_prediction_context_unit_lookup_tolerates_no_units():
    assert PredictionContext().unit_for("hba1c") is None
    assert PredictionContext(units={"hba1c": "%"}).unit_for("hba1c") == "%"


def test_sufficiency_report_metadata_round_trips():
    report = SufficiencyReport(
        sufficient=False, required=("a",), present=(), missing=("a",), reason="x"
    )
    assert report.as_metadata()["required_missing"] == ["a"]
    assert report.as_metadata()["reason"] == "x"
