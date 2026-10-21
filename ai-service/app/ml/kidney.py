from __future__ import annotations

import math

from typing import Any, Dict, List, Mapping, Optional, Tuple

from app.data import conditions as C
from app.data.recommendation_catalog import (
    CONFIRM_WITH_REPEAT_TESTING,
    DISCUSS_WITH_CLINICIAN,
    GENERAL_HYDRATION,
    INPUT_QUALITY_CAVEAT,
    MONITOR_OVER_TIME,
    NOTHING_FLAGGED_EDUCATIONAL,
    NOT_A_DIAGNOSIS,
    SEEK_PROMPT_MEDICAL_ADVICE,
    recommendations as resolve_recommendations,
)
from app.ml.artifacts import load_failure_reason, load_model
from app.ml.operating_metrics import (
    operating_metrics,
    performance_figures,
)
from app.ml.base import (
    PredictionContext,
    Predictor,
    PredictorError,
)
from app.ml.heart import (
    ASSESSMENT_BASIS_KEY,
    ASSESSMENT_KIND_KEY,
    ASSESSMENT_KIND_LIKELIHOOD,
)
from app.schemas.decisions import (
    ClinicalDecision,
    DecisionSourceKind,
    DecisionStatus,
    EvidenceItem,
    RiskLevel,
)
from app.schemas.fusion import BASIS_MODEL_PROBABILITY, BASIS_NOT_ASSESSED

KIDNEY_MODEL_FILE = "kidney_rf_v1.joblib"
KIDNEY_METRICS_FILE = "kidney_rf_v1.metrics.json"


NOTE_MODEL_INPUT = "this value was given to the model"
NOTE_IMPUTED = (
    "this value was not available, so the model used the median of its "
    "training data in its place"
)
NOTE_NOT_ASSERTED = (
    "this was not recorded, and the model used for this report was built "
    "without it rather than assuming an answer"
)
NOTE_QUESTIONABLE = "this value was marked less reliable when the report was read"
NOTE_EXTREME_HIGH = (
    "this value is far above the usual range and was flagged for priority"
)
NOTE_EXTREME_LOW = (
    "this value is far below the usual range and was flagged for priority"
)

KIDNEY_NOTE_FRAGMENTS: Tuple[str, ...] = (
    NOTE_MODEL_INPUT,
    NOTE_IMPUTED,
    NOTE_NOT_ASSERTED,
    NOTE_QUESTIONABLE,
    NOTE_EXTREME_HIGH,
    NOTE_EXTREME_LOW,
)

TRI_STATE_HYPERTENSION = "hypertension"

VARIANT_BY_AVAILABILITY: Dict[bool, str] = {
    True: "with_hypertension",
    False: "without_hypertension",
}

HYPERTENSION_LEVELS: Dict[bool, str] = {True: "yes", False: "no"}

_EXTREME_LOW_FEATURES = ("hemoglobin",)


class KidneyPredictor(Predictor):

    name = "kidney_rf"
    condition = C.KIDNEY_DISEASE
    source_label = "Random Forest"
    version = "1.0.0"

    required_features: Tuple[str, ...] = ("creatinine", "hemoglobin")
    optional_features: Tuple[str, ...] = ("blood_glucose", "age", "hypertension")

    def __init__(self, artifact_filename: str = KIDNEY_MODEL_FILE) -> None:
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
            "malformed_label_rows_dropped": dataset.get(
                "malformed_label_rows_dropped"
            ),
            "synthetic_rows": dataset.get("synthetic_rows"),
            "resampling": dataset.get("resampling"),
            "kidney_parameters_unavailable_to_vaidyaai": dataset.get(
                "columns_available_but_unused"
            ),
        }


    @staticmethod
    def _tri_state(value: Any) -> Optional[bool]:
        if isinstance(value, bool):
            return value
        return None

    def select_variant(
        self, features: Mapping[str, Any]
    ) -> Tuple[str, Optional[bool]]:
        known = self._tri_state(features.get(TRI_STATE_HYPERTENSION))
        return VARIANT_BY_AVAILABILITY[known is not None], known


    def _model_row(
        self, features: Mapping[str, Any], variant_name: str
    ) -> Tuple[Any, Dict[str, Any]]:
        import numpy as np
        import pandas as pd

        bundle = self.artifact
        if bundle is None:
            raise PredictorError("kidney model artifact is not loaded")
        spec = bundle.variants.get(variant_name)
        if spec is None:
            raise PredictorError(
                f"the kidney artifact has no variant {variant_name!r}; it has "
                f"{sorted(bundle.variants)}"
            )

        numeric: List[str] = list(spec["numeric_features"])
        categorical: List[str] = list(spec["categorical_features"])
        trace: Dict[str, Any] = {}
        row: Dict[str, Any] = {}

        for column in numeric:
            number = _as_float(features.get(column))
            if number is None:
                row[column] = np.nan
                trace[column] = {"status": "imputed", "value": None}
            else:
                row[column] = number
                trace[column] = {"status": "observed", "value": number}

        for column in categorical:
            known = self._tri_state(features.get(column))
            if known is None:
                raise PredictorError(
                    f"variant {variant_name!r} requires {column!r} but the "
                    "patient did not supply it; select_variant() should have "
                    "chosen the variant fitted without it"
                )
            row[column] = HYPERTENSION_LEVELS[known]
            trace[column] = {"status": "observed", "value": known}

        if TRI_STATE_HYPERTENSION not in categorical:
            trace[TRI_STATE_HYPERTENSION] = {"status": "not_asserted", "value": None}

        frame = pd.DataFrame([row], columns=numeric + categorical)
        return frame, trace


    @staticmethod
    def _thresholds(bundle, variant_name: str) -> Tuple[float, float]:
        thresholds = bundle.variants[variant_name]["thresholds"]
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
        variant_name, known_hypertension = self.select_variant(features)
        frame, trace = self._model_row(features, variant_name)

        pipeline = bundle.pipelines[variant_name]
        probability = float(pipeline.predict_proba(frame)[0][1])

        borderline, indicated = self._thresholds(bundle, variant_name)
        status, risk, band_name = self.band(probability, borderline, indicated)

        achieved = operating_metrics(bundle.variants[variant_name])
        achieved_performance = performance_figures(bundle.variants[variant_name])

        spec = bundle.variants[variant_name]
        importance: Dict[str, float] = dict(spec.get("global_feature_importance", {}))

        evidence = self._evidence(trace, importance, context)
        recommendations = self._recommendations(status, context, trace)

        metrics = spec.get("metrics", {}) or {}
        sufficiency = bundle.get("sufficiency_evidence", {}) or {}
        metadata: Dict[str, Any] = {
            "predictor": self.name,
            "predictor_version": self.version,
            "skipped": False,
            "model": self.model_provenance(),
            ASSESSMENT_KIND_KEY: ASSESSMENT_KIND_LIKELIHOOD,
            ASSESSMENT_BASIS_KEY: BASIS_MODEL_PROBABILITY,
            "assessment_kind_note": (
                "This decision estimates the LIKELIHOOD of chronic kidney "
                "disease. Module 8's creatinine rule assesses the same "
                "condition string from a threshold on one analyte. A decision "
                "carrying no assessment_kind key should not be read as a "
                "probability."
            ),
            "variant": variant_name,
            "variant_reason": (
                "chosen by whether the patient actually answered the "
                f"hypertension question: hypertension="
                f"{_tri_word(known_hypertension)}"
                + (
                    ""
                    if known_hypertension is not None
                    else ". The variant fitted WITHOUT a hypertension column "
                    "was used, so an unanswered question was never encoded as "
                    "'no'."
                )
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
                **achieved,
            },
            "threshold_basis": (
                "indicated = most precise out-of-fold threshold still holding "
                "0.98 cumulative recall; borderline = largest out-of-fold "
                "threshold still holding 0.99 cumulative recall. Both are read "
                "off the measured precision-recall curve, neither is a round "
                "number, and both are stated as sensitivity guarantees because "
                "a missed case is the dangerous failure here."
            ),
            "risk_band": band_name,
            "band_meaning": _BAND_MEANING[band_name],
            "sufficiency_rule": {
                "required_features": list(self.required_features),
                "optional_features": list(self.optional_features),
                "basis": (
                    "creatinine + hemoglobin alone reach 0.986 cross-validated "
                    "ROC-AUC against the full model's 0.996, so the other "
                    "three inputs are a refinement rather than load-bearing. "
                    "Creatinine is required on clinical rather than "
                    "statistical grounds: it is the analyte that defines renal "
                    "function, and without it this model leans on haemoglobin, "
                    "which is a correlate in this cohort and would not be one "
                    "in a screening population."
                ),
                "measured": sufficiency.get("imputed_at_prediction_time", {}).get(
                    "blanked"
                ),
            },
            "features_observed": sorted(
                n for n, t in trace.items() if t["status"] == "observed"
            ),
            "features_imputed": sorted(
                n for n, t in trace.items() if t["status"] == "imputed"
            ),
            "features_not_asserted": sorted(
                n for n, t in trace.items() if t["status"] == "not_asserted"
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
                **achieved_performance,
                "measured_on": "held-out test split, see the metrics artifact",
                "variant": variant_name,
                "roc_auc": metrics.get("roc_auc"),
                "pr_auc_average_precision": metrics.get("pr_auc_average_precision"),
                "accuracy": metrics.get("accuracy"),
                "majority_class_baseline_accuracy": metrics.get(
                    "majority_class_baseline_accuracy"
                ),
                "positive_class": metrics.get("positive_class"),
                "artifact": "ml/artifacts/kidney_rf_v1.metrics.json",
                "honest_read": (
                    "This came from a pattern model, not from a measurement. "
                    "It was developed on one small dataset in which the two "
                    "groups separated unusually cleanly, so its accuracy there "
                    "flatters it and nothing shows it holds in a screening "
                    "population where kidney disease is far less common. It is "
                    "a reason to consider further assessment, never a finding "
                    "in itself."
                ),
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


    def insufficient_decision(self, report, context=None, *, extra_metadata=None):
        metadata: Dict[str, Any] = {
            ASSESSMENT_KIND_KEY: ASSESSMENT_KIND_LIKELIHOOD,
            ASSESSMENT_BASIS_KEY: BASIS_NOT_ASSESSED,
            "sufficiency_rule": {
                "required_features": list(self.required_features),
                "optional_features": list(self.optional_features),
                "basis": (
                    "Serum creatinine defines renal function and haemoglobin "
                    "carries the largest measured share of this model's "
                    "discrimination. Without both, a probability would rest on "
                    "median values taken from the training cohort rather than "
                    "on this patient. Module 8's creatinine rule still "
                    "assesses this condition."
                ),
            },
        }
        metadata.update(extra_metadata or {})
        return super().insufficient_decision(report, context, extra_metadata=metadata)


    def _evidence(
        self,
        trace: Dict[str, Any],
        importance: Dict[str, float],
        context: PredictionContext,
    ) -> List[EvidenceItem]:
        order = sorted(trace, key=lambda name: (-importance.get(name, 0.0), name))
        items: List[EvidenceItem] = []
        for name in order:
            entry = trace[name]
            status = entry["status"]
            note = {
                "observed": NOTE_MODEL_INPUT,
                "imputed": NOTE_IMPUTED,
                "not_asserted": NOTE_NOT_ASSERTED,
            }[status]
            if status == "observed" and name in context.questionable:
                note = NOTE_QUESTIONABLE
            elif status == "observed" and name in context.clinically_extreme:
                note = (
                    NOTE_EXTREME_LOW
                    if name in _EXTREME_LOW_FEATURES
                    else NOTE_EXTREME_HIGH
                )
            items.append(
                EvidenceItem(
                    feature=name,
                    value=entry["value"],
                    unit=context.unit_for(name) if status == "observed" else None,
                    threshold=None,
                    comparator=None,
                    note=note,
                    source_stage=(
                        "not_available" if status == "not_asserted" else "model_input"
                    ),
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
                GENERAL_HYDRATION,
            )
        elif status is DecisionStatus.BORDERLINE:
            codes = (
                DISCUSS_WITH_CLINICIAN,
                CONFIRM_WITH_REPEAT_TESTING,
                MONITOR_OVER_TIME,
                GENERAL_HYDRATION,
            )
        else:
            codes = (NOTHING_FLAGGED_EDUCATIONAL, MONITOR_OVER_TIME)

        if any(name in context.questionable for name in trace):
            codes += (INPUT_QUALITY_CAVEAT,)
        return resolve_recommendations(codes + (NOT_A_DIAGNOSIS,))


_BAND_MEANING = {
    "low": (
        "Below the sensitivity-derived cut-off. On the held-out test split "
        "2.9% of patients in this band were positive, against a cohort "
        "prevalence of 63.0%."
    ),
    "medium": (
        "Between the two cut-offs: NOT RULED OUT rather than elevated. It held "
        "one patient of 100 on the held-out split, because this cohort's "
        "scores are strongly bimodal. A near-empty band here is a property of "
        "the test cohort, not evidence that borderline patients do not exist."
    ),
    "high": (
        "At or above the precision-derived cut-off. On the held-out test split "
        "96.9% of patients in this band were positive, against a cohort "
        "prevalence of 63.0%."
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


__all__ = [
    "HYPERTENSION_LEVELS",
    "KIDNEY_METRICS_FILE",
    "KIDNEY_MODEL_FILE",
    "KIDNEY_NOTE_FRAGMENTS",
    "TRI_STATE_HYPERTENSION",
    "VARIANT_BY_AVAILABILITY",
    "KidneyPredictor",
]
