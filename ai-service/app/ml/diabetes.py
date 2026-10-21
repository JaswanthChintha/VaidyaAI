from __future__ import annotations

import math

from typing import Any, Dict, List, Mapping, Optional, Tuple

from app.data import conditions as C
from app.data.recommendation_catalog import (
    CONFIRM_WITH_REPEAT_TESTING,
    DISCUSS_WITH_CLINICIAN,
    GENERAL_BALANCED_DIET,
    GENERAL_LIMIT_ADDED_SUGAR,
    GENERAL_PHYSICAL_ACTIVITY,
    INPUT_QUALITY_CAVEAT,
    MONITOR_OVER_TIME,
    NOTHING_FLAGGED_EDUCATIONAL,
    NOT_A_DIAGNOSIS,
    SEEK_PROMPT_MEDICAL_ADVICE,
    recommendations as resolve_recommendations,
)
from app.ml.artifacts import (
    DIABETES_MODEL_FILE,
    load_failure_reason,
    load_model,
)
from app.ml.operating_metrics import (
    operating_metrics,
    performance_figures,
)
from app.ml.base import (
    EMPTY_CONTEXT,
    PredictionContext,
    Predictor,
    PredictorError,
)
from app.schemas.decisions import (
    ClinicalDecision,
    DecisionSourceKind,
    DecisionStatus,
    EvidenceItem,
    RiskLevel,
)


NOTE_MODEL_INPUT = "this value was given to the model"
NOTE_IMPUTED = (
    "this value was not available, so the model used the median of its "
    "training data in its place"
)
NOTE_NOT_ASSERTED = (
    "this was not recorded, and the model used for this report was built "
    "without it rather than assuming an answer"
)
NOTE_UNRECOGNISED_CATEGORY = (
    "this answer is not one the model was built on, so no category was "
    "assumed for it"
)
NOTE_QUESTIONABLE = (
    "this value was marked less reliable when the report was read"
)
NOTE_EXTREME_HIGH = (
    "this value is far above the usual range and was flagged for priority"
)
NOTE_EXTREME_LOW = (
    "this value is far below the usual range and was flagged for priority"
)

DIABETES_NOTE_FRAGMENTS: Tuple[str, ...] = (
    NOTE_MODEL_INPUT,
    NOTE_IMPUTED,
    NOTE_NOT_ASSERTED,
    NOTE_UNRECOGNISED_CATEGORY,
    NOTE_QUESTIONABLE,
    NOTE_EXTREME_HIGH,
    NOTE_EXTREME_LOW,
)

ABSENT_CATEGORY = "__absent__"

TRI_STATE: Tuple[str, str] = ("hypertension", "heart_disease")

VARIANT_BY_AVAILABILITY: Dict[Tuple[bool, bool], str] = {
    (True, True): "both",
    (True, False): "hypertension_only",
    (False, True): "heart_disease_only",
    (False, False): "neither",
}


def normalise_category(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    return text.replace(" ", "_").replace("-", "_")


class DiabetesPredictor(Predictor):

    name = "diabetes_rf"
    condition = C.DIABETES
    source_label = "Random Forest"
    version = "1.0.0"

    required_features: Tuple[str, ...] = ("hba1c", "blood_glucose")
    optional_features: Tuple[str, ...] = (
        "age",
        "bmi",
        "gender",
        "smoking_history",
        "hypertension",
        "heart_disease",
    )

    def __init__(self, artifact_filename: str = DIABETES_MODEL_FILE) -> None:
        self._artifact_filename = artifact_filename
        super().__init__()


    @property
    def artifact(self):
        return load_model(self._artifact_filename)

    def is_available(self) -> bool:
        return self.artifact is not None

    def unavailable_reason(self) -> Optional[str]:
        return load_failure_reason(self._artifact_filename)

    def artifact_integrity(self) -> Dict[str, Any]:
        bundle = self.artifact
        return dict(bundle.integrity or {}) if bundle is not None else {}

    def model_provenance(self) -> Dict[str, Any]:
        bundle = self.artifact
        if bundle is None:
            return {"available": False, "reason": self.unavailable_reason()}
        dataset = bundle.get("dataset", {}) or {}
        integrity = dict(bundle.integrity or {})
        return {
            "available": True,
            "artifact_file": self._artifact_filename,
            "artifact_integrity": integrity,
            "artifact_integrity_verified": bool(integrity.get("verified")),
            "artifact_version": bundle.get("artifact_version"),
            "model_id": bundle.get("model_id"),
            "algorithm": bundle.get("algorithm"),
            "trained_at": bundle.get("trained_at"),
            "sklearn_version": bundle.get("sklearn_version"),
            "hyperparameters": bundle.get("hyperparameters"),
            "dataset_sha256": dataset.get("sha256"),
            "dataset_rows_used": dataset.get("rows_used"),
            "dataset_prevalence": dataset.get("prevalence"),
            "synthetic_rows": dataset.get("synthetic_rows"),
            "resampling": dataset.get("resampling"),
        }


    @staticmethod
    def _tri_state(value: Any) -> Optional[bool]:
        if isinstance(value, bool):
            return value
        return None

    def select_variant(self, features: Mapping[str, Any]) -> Tuple[str, Dict[str, Optional[bool]]]:
        known = {name: self._tri_state(features.get(name)) for name in TRI_STATE}
        key = (known["hypertension"] is not None, known["heart_disease"] is not None)
        return VARIANT_BY_AVAILABILITY[key], known


    def _model_row(
        self, features: Mapping[str, Any], variant_name: str
    ) -> Tuple[Any, Dict[str, Any]]:
        import numpy as np
        import pandas as pd

        bundle = self.artifact
        if bundle is None:
            raise PredictorError("diabetes model artifact is not loaded")
        spec = bundle.variants.get(variant_name)
        if spec is None:
            raise PredictorError(
                f"the diabetes artifact has no variant {variant_name!r}; it "
                f"has {sorted(bundle.variants)}"
            )

        numeric: List[str] = list(spec["numeric_features"])
        categorical: List[str] = list(spec["categorical_features"])
        trace: Dict[str, Any] = {}
        row: Dict[str, Any] = {}

        for name in numeric:
            if name in TRI_STATE:
                value = self._tri_state(features.get(name))
                row[name] = int(value)
                trace[name] = {"status": "observed", "value": value}
                continue
            raw = features.get(name)
            number = _as_float(raw)
            if number is None:
                row[name] = np.nan
                trace[name] = {"status": "imputed", "value": None}
            else:
                row[name] = number
                trace[name] = {"status": "observed", "value": number}

        known_levels = _known_levels(bundle, categorical)
        for name in categorical:
            token = normalise_category(features.get(name))
            if token is None:
                row[name] = ABSENT_CATEGORY
                trace[name] = {"status": "not_asserted", "value": None}
            elif token in known_levels.get(name, ()):
                row[name] = token
                trace[name] = {"status": "observed", "value": token}
            else:
                row[name] = token
                trace[name] = {"status": "unrecognised", "value": token}

        for name in TRI_STATE:
            if name not in numeric:
                trace[name] = {"status": "not_asserted", "value": None}

        frame = pd.DataFrame([row], columns=numeric + categorical)
        return frame, trace


    @staticmethod
    def _thresholds(bundle, variant_name: str) -> Tuple[float, float]:
        spec = bundle.variants[variant_name]
        thresholds = spec["thresholds"]
        return float(thresholds["borderline"]), float(thresholds["indicated"])

    @staticmethod
    def band(
        probability: float, borderline: float, indicated: float
    ) -> Tuple[DecisionStatus, RiskLevel, str]:
        if probability >= indicated:
            return DecisionStatus.INDICATED, RiskLevel.HIGH, "high"
        if probability >= borderline:
            return DecisionStatus.BORDERLINE, RiskLevel.MEDIUM, "medium"
        return DecisionStatus.NOT_INDICATED, RiskLevel.LOW, "low"


    def _predict(
        self, features: Mapping[str, Any], context: PredictionContext
    ) -> ClinicalDecision:
        bundle = self.artifact
        variant_name, tri_known = self.select_variant(features)
        frame, trace = self._model_row(features, variant_name)

        pipeline = bundle.pipelines[variant_name]
        probability = float(pipeline.predict_proba(frame)[0][1])

        borderline, indicated = self._thresholds(bundle, variant_name)
        status, risk, band_name = self.band(probability, borderline, indicated)

        spec = bundle.variants[variant_name]
        importance: Dict[str, float] = dict(spec.get("global_feature_importance", {}))

        evidence = self._evidence(trace, importance, context)
        recommendations = self._recommendations(status, context, trace)

        metrics = spec.get("metrics", {}) or {}
        metadata: Dict[str, Any] = {
            "predictor": self.name,
            "predictor_version": self.version,
            "skipped": False,
            "model": self.model_provenance(),
            "variant": variant_name,
            "variant_reason": (
                "chosen by which tri-state answers the patient actually gave: "
                f"hypertension={_tri_word(tri_known['hypertension'])}, "
                f"heart_disease={_tri_word(tri_known['heart_disease'])}. A "
                "variant that excludes a column was fitted without it, so no "
                "value was assumed for an unanswered question."
            ),
            "probability_positive": probability,
            "confidence_semantics": "probability_of_positive_class",
            "confidence_note": (
                "confidence is P(positive) and is NOT 'how sure the model is'. "
                "A low value on a Not Indicated decision means a confident "
                "negative."
            ),
            "thresholds": {
                "borderline": borderline,
                "indicated": indicated,
                **operating_metrics(spec),
            },
            "threshold_basis": (
                "indicated = smallest validation threshold reaching 0.90 "
                "cumulative precision; borderline = largest validation "
                "threshold holding 0.99 cumulative recall. Both measured on a "
                "held-out split, neither chosen as a round number."
            ),
            "risk_band": band_name,
            "band_meaning": _BAND_MEANING[band_name],
            "features_observed": sorted(
                n for n, t in trace.items() if t["status"] == "observed"
            ),
            "features_imputed": sorted(
                n for n, t in trace.items() if t["status"] == "imputed"
            ),
            "features_not_asserted": sorted(
                n for n, t in trace.items() if t["status"] == "not_asserted"
            ),
            "features_unrecognised_category": sorted(
                n for n, t in trace.items() if t["status"] == "unrecognised"
            ),
            "model_input_columns": list(frame.columns),
            "questionable_features_used": sorted(
                n for n in trace if n in context.questionable
            ),
            "clinically_extreme_features_used": sorted(
                n for n in trace if n in context.clinically_extreme
            ),
            "partial_document": context.partial_document,
            "global_feature_importance": importance,
            "feature_importance_scope": "global_model_level",
            "feature_importance_caveat": (
                "Mean impurity decrease over the whole training set. It ranks "
                "features FOR THE MODEL and orders the evidence below. It is "
                "NOT a per-patient explanation and must never be presented as "
                "the reason THIS prediction came out as it did."
            ),
            "evidence_ordering": "global_feature_importance_descending",
            "model_performance_reference": {
                "measured_on": "held-out test split, see the metrics artifact",
                "variant": variant_name,
                "roc_auc": metrics.get("roc_auc"),
                "pr_auc_average_precision": metrics.get("pr_auc_average_precision"),
                "positive_class": metrics.get("positive_class"),
                **performance_figures(spec),
                "artifact": "ml/artifacts/diabetes_rf_v1.metrics.json",
            },
        }

        return ClinicalDecision(
            condition=self.condition,
            status=status,
            risk=risk,
            confidence=probability,
            source=self.source_label,
            source_kind=DecisionSourceKind.MACHINE_LEARNING,
            evidence=evidence,
            recommendations=recommendations,
            metadata=metadata,
        )


    def _evidence(
        self,
        trace: Dict[str, Any],
        importance: Dict[str, float],
        context: PredictionContext,
    ) -> List[EvidenceItem]:
        order = sorted(
            trace,
            key=lambda name: (-importance.get(name, 0.0), name),
        )
        items: List[EvidenceItem] = []
        for name in order:
            entry = trace[name]
            status = entry["status"]
            note = {
                "observed": NOTE_MODEL_INPUT,
                "imputed": NOTE_IMPUTED,
                "not_asserted": NOTE_NOT_ASSERTED,
                "unrecognised": NOTE_UNRECOGNISED_CATEGORY,
            }[status]
            if status == "observed" and name in context.questionable:
                note = NOTE_QUESTIONABLE
            elif status == "observed" and name in context.clinically_extreme:
                note = NOTE_EXTREME_HIGH
            items.append(
                EvidenceItem(
                    feature=name,
                    value=entry["value"],
                    unit=context.unit_for(name) if status == "observed" else None,
                    threshold=None,
                    comparator=None,
                    note=note,
                    source_stage="model_input" if status != "not_asserted" else "not_available",
                )
            )
        return items


    def _recommendations(
        self,
        status: DecisionStatus,
        context: PredictionContext,
        trace: Dict[str, Any],
    ):
        if status is DecisionStatus.INDICATED:
            codes: Tuple[str, ...] = (
                DISCUSS_WITH_CLINICIAN,
                SEEK_PROMPT_MEDICAL_ADVICE,
                CONFIRM_WITH_REPEAT_TESTING,
                GENERAL_LIMIT_ADDED_SUGAR,
                GENERAL_PHYSICAL_ACTIVITY,
            )
        elif status is DecisionStatus.BORDERLINE:
            codes = (
                DISCUSS_WITH_CLINICIAN,
                CONFIRM_WITH_REPEAT_TESTING,
                MONITOR_OVER_TIME,
                GENERAL_LIMIT_ADDED_SUGAR,
                GENERAL_BALANCED_DIET,
            )
        else:
            codes = (NOTHING_FLAGGED_EDUCATIONAL, MONITOR_OVER_TIME)

        if any(name in context.questionable for name in trace):
            codes += (INPUT_QUALITY_CAVEAT,)
        return resolve_recommendations(codes + (NOT_A_DIAGNOSIS,))


_BAND_MEANING = {
    "low": (
        "Below the sensitivity-derived cut-off. On the held-out test split "
        "0.10% of patients in this band were positive."
    ),
    "medium": (
        "Between the two cut-offs: NOT RULED OUT rather than elevated. On the "
        "held-out test split 7.9% of patients in this band were positive, "
        "against a cohort prevalence of 8.8%."
    ),
    "high": (
        "At or above the precision-derived cut-off. On the held-out test split "
        "91.1% of patients in this band were positive."
    ),
}


def _as_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        try:
            number = float(str(value).strip())
        except (TypeError, ValueError):
            return None
    return number if math.isfinite(number) else None


def _tri_word(value: Optional[bool]) -> str:
    return "not recorded" if value is None else str(value).lower()


def _known_levels(bundle, categorical: List[str]) -> Dict[str, Tuple[str, ...]]:
    dataset = bundle.get("dataset", {}) or {}
    return {
        "gender": tuple(dataset.get("gender_levels", ())),
        "smoking_history": tuple(dataset.get("smoking_history_levels", ())),
    }


__all__ = [
    "ABSENT_CATEGORY",
    "DIABETES_NOTE_FRAGMENTS",
    "NOTE_IMPUTED",
    "NOTE_MODEL_INPUT",
    "NOTE_NOT_ASSERTED",
    "NOTE_UNRECOGNISED_CATEGORY",
    "TRI_STATE",
    "VARIANT_BY_AVAILABILITY",
    "DiabetesPredictor",
    "normalise_category",
]
