from __future__ import annotations

import math

from typing import Any, Dict, List, Mapping, Optional, Tuple

from app.data import conditions as C
from app.data.recommendation_catalog import (
    CONFIRM_WITH_REPEAT_TESTING,
    DISCUSS_WITH_CLINICIAN,
    GENERAL_BALANCED_DIET,
    GENERAL_DIETARY_FAT_QUALITY,
    GENERAL_PHYSICAL_ACTIVITY,
    GENERAL_SMOKING_CESSATION_SUPPORT,
    INPUT_QUALITY_CAVEAT,
    MONITOR_OVER_TIME,
    NOTHING_FLAGGED_EDUCATIONAL,
    NOT_A_DIAGNOSIS,
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
from app.schemas.decisions import (
    ClinicalDecision,
    DecisionSourceKind,
    DecisionStatus,
    EvidenceItem,
    RiskLevel,
)
from app.schemas.fusion import BASIS_MODEL_PROBABILITY, BASIS_NOT_ASSESSED

HEART_MODEL_FILE = "heart_rf_v2.joblib"
HEART_METRICS_FILE = "heart_rf_v2.metrics.json"

ASSESSMENT_KIND_KEY = "assessment_kind"
ASSESSMENT_KIND_LIKELIHOOD = "disease_likelihood"

ASSESSMENT_BASIS_KEY = "assessment_basis"


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
NOTE_CHOLESTEROL_BANDED = (
    "this value was grouped into a normal / above normal / well above normal "
    "band before the model used it"
)
NOTE_QUESTIONABLE = "this value was marked less reliable when the report was read"
NOTE_EXTREME_HIGH = (
    "this value is far above the usual range and was flagged for priority"
)

HEART_NOTE_FRAGMENTS: Tuple[str, ...] = (
    NOTE_MODEL_INPUT,
    NOTE_IMPUTED,
    NOTE_NOT_ASSERTED,
    NOTE_UNRECOGNISED_CATEGORY,
    NOTE_CHOLESTEROL_BANDED,
    NOTE_QUESTIONABLE,
    NOTE_EXTREME_HIGH,
)

ABSENT_CATEGORY = "__absent__"


CHOLESTEROL_BAND_CUTOFFS: Tuple[float, float] = (200.0, 240.0)

CHOLESTEROL_BAND_LABELS: Dict[int, str] = {
    1: "normal (< 200 mg/dL)",
    2: "above normal (200-239 mg/dL)",
    3: "well above normal (>= 240 mg/dL)",
}


def cholesterol_band(mg_dl: Any) -> Optional[int]:
    value = _as_float(mg_dl)
    if value is None:
        return None
    borderline, high = CHOLESTEROL_BAND_CUTOFFS
    if value >= high:
        return 3
    if value >= borderline:
        return 2
    return 1


SMOKING_TO_CURRENT: Dict[str, int] = {
    "never": 0,
    "former": 0,
    "not_current": 0,
    "current": 1,
}

SMOKING_UNKNOWN_REASON: Dict[str, str] = {
    "ever": (
        "'ever smoked' covers current and former smokers alike, so it does not "
        "determine the dataset's current-smoker flag"
    ),
    "no_info": "the patient was never asked",
}

TRI_STATE_SMOKING = "smoking_history"

VARIANT_BY_AVAILABILITY: Dict[bool, str] = {
    True: "with_smoking",
    False: "without_smoking",
}


def normalise_category(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    return text.replace(" ", "_").replace("-", "_")


def smoking_current(value: Any) -> Optional[int]:
    token = normalise_category(value)
    if token is None:
        return None
    return SMOKING_TO_CURRENT.get(token)


class HeartPredictor(Predictor):

    name = "heart_rf"
    condition = C.HEART_DISEASE
    source_label = "Random Forest"
    version = "1.0.0"

    required_features: Tuple[str, ...] = ("age", "bmi", "cholesterol")
    optional_features: Tuple[str, ...] = ("gender", "smoking_history")

    def __init__(self, artifact_filename: str = HEART_MODEL_FILE) -> None:
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
            "blood_pressure_excluded": True,
            "blood_pressure_exclusion_reason": (
                "VaidyaAI collects no blood pressure, so training on it would "
                "median-impute the model's strongest input for every patient. "
                "Measured cost of the exclusion: about 0.10 ROC-AUC."
            ),
        }


    def select_variant(
        self, features: Mapping[str, Any]
    ) -> Tuple[str, Optional[int], Optional[str]]:
        token = normalise_category(features.get(TRI_STATE_SMOKING))
        current = SMOKING_TO_CURRENT.get(token) if token is not None else None
        return VARIANT_BY_AVAILABILITY[current is not None], current, token


    def _model_row(
        self, features: Mapping[str, Any], variant_name: str
    ) -> Tuple[Any, Dict[str, Any]]:
        import numpy as np
        import pandas as pd

        bundle = self.artifact
        if bundle is None:
            raise PredictorError("heart model artifact is not loaded")
        spec = bundle.variants.get(variant_name)
        if spec is None:
            raise PredictorError(
                f"the heart artifact has no variant {variant_name!r}; it has "
                f"{sorted(bundle.variants)}"
            )

        numeric: List[str] = list(spec["numeric_features"])
        categorical: List[str] = list(spec["categorical_features"])
        trace: Dict[str, Any] = {}
        row: Dict[str, Any] = {}

        for column in numeric:
            if column == "cholesterol_band":
                raw = features.get("cholesterol")
                band = cholesterol_band(raw)
                if band is None:
                    row[column] = np.nan
                    trace["cholesterol"] = {
                        "status": "imputed",
                        "value": None,
                        "model_column": column,
                    }
                else:
                    row[column] = float(band)
                    trace["cholesterol"] = {
                        "status": "banded",
                        "value": _as_float(raw),
                        "model_column": column,
                        "band": band,
                        "band_label": CHOLESTEROL_BAND_LABELS[band],
                    }
                continue
            if column == "smoking_current":
                current = smoking_current(features.get(TRI_STATE_SMOKING))
                row[column] = float(current)
                trace[TRI_STATE_SMOKING] = {
                    "status": "observed",
                    "value": normalise_category(features.get(TRI_STATE_SMOKING)),
                    "model_column": column,
                }
                continue
            number = _as_float(features.get(column))
            if number is None:
                row[column] = np.nan
                trace[column] = {
                    "status": "imputed",
                    "value": None,
                    "model_column": column,
                }
            else:
                row[column] = number
                trace[column] = {
                    "status": "observed",
                    "value": number,
                    "model_column": column,
                }

        known_levels = _known_levels(bundle)
        for column in categorical:
            token = normalise_category(features.get(column))
            if token is None:
                row[column] = ABSENT_CATEGORY
                trace[column] = {
                    "status": "not_asserted",
                    "value": None,
                    "model_column": column,
                }
            elif token in known_levels.get(column, ()):
                row[column] = token
                trace[column] = {
                    "status": "observed",
                    "value": token,
                    "model_column": column,
                }
            else:
                row[column] = token
                trace[column] = {
                    "status": "unrecognised",
                    "value": token,
                    "model_column": column,
                }

        if "smoking_current" not in numeric:
            trace[TRI_STATE_SMOKING] = {
                "status": "not_asserted",
                "value": normalise_category(features.get(TRI_STATE_SMOKING)),
                "model_column": None,
            }

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
        variant_name, current, smoking_token = self.select_variant(features)
        frame, trace = self._model_row(features, variant_name)

        pipeline = bundle.pipelines[variant_name]
        probability = float(pipeline.predict_proba(frame)[0][1])

        borderline, indicated = self._thresholds(bundle, variant_name)
        status, risk, band_name = self.band(probability, borderline, indicated)

        achieved = operating_metrics(bundle.variants[variant_name])
        achieved_performance = performance_figures(bundle.variants[variant_name])

        spec = bundle.variants[variant_name]
        importance = _canonical_importance(
            dict(spec.get("global_feature_importance", {}))
        )

        evidence = self._evidence(trace, importance, context)
        recommendations = self._recommendations(status, context, trace, current)

        metrics = spec.get("metrics", {}) or {}
        metadata: Dict[str, Any] = {
            "predictor": self.name,
            "predictor_version": self.version,
            "skipped": False,
            "model": self.model_provenance(),
            ASSESSMENT_KIND_KEY: ASSESSMENT_KIND_LIKELIHOOD,
            ASSESSMENT_BASIS_KEY: BASIS_MODEL_PROBABILITY,
            "assessment_kind_note": (
                "This decision estimates the LIKELIHOOD of cardiovascular "
                "disease. Module 8's RULE_HEART_DISEASE_RISK_FACTORS emits the "
                "same condition string from a COUNT OF RISK FACTORS. Both are "
                "legitimate and they are not the same quantity. A decision "
                "carrying no assessment_kind key should be read as a "
                "risk-factor burden, not as a probability."
            ),
            "variant": variant_name,
            "variant_reason": (
                (
                    "chosen by whether the patient's smoking history determines "
                    f"CURRENT smoking: smoking_history={smoking_token or 'not recorded'}"
                    + (
                        ""
                        if current is not None
                        else " (does not determine current smoking, so the "
                        "variant fitted WITHOUT a smoking column was used -- no "
                        "value was assumed)"
                    )
                )
                if len(bundle.pipelines) > 1
                else (
                    "this artifact ships a single pipeline, so no variant "
                    "selection took place; smoking history was not an input to "
                    "it"
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
            "threshold_basis": spec.get(
                "threshold_basis",
                "indicated = smallest out-of-fold threshold whose cumulative "
                "precision reaches 1.5x the cohort base rate; borderline = "
                "largest out-of-fold threshold holding 0.95 cumulative recall. "
                "Neither is a round number; both are read off the measured "
                "precision-recall curve.",
            ),
            "risk_band": band_name,
            "band_meaning": _band_meaning(spec, band_name),
            **(
                {
                    "cholesterol_band_mapping": {
                        "cutoffs_mg_dl": list(CHOLESTEROL_BAND_CUTOFFS),
                        "basis": (
                            "NCEP ATP III total cholesterol: <200 desirable, "
                            "200-239 borderline high, >=240 high. This "
                            "artifact's cholesterol column is an ORDINAL BAND "
                            "(1/2/3), not mg/dL."
                        ),
                        "band": trace.get("cholesterol", {}).get("band"),
                    }
                }
                if "cholesterol_band" in spec.get("numeric_features", ())
                else {}
            ),
            "features_observed": sorted(
                n for n, t in trace.items() if t["status"] in ("observed", "banded")
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
                "artifact": "ml/artifacts/heart_rf_v2.metrics.json",
                "honest_read": (
                    "A COARSE screening signal, not a precise one. At the "
                    "cut-off used here, roughly two out of every three people "
                    "it flags do NOT have heart disease -- a high score is a "
                    "reason to discuss testing with a clinician, never a "
                    "finding. It learned from what "
                    "people said a doctor had told them, so it misses "
                    "people not yet identified. Blood pressure, the strongest "
                    "known predictor, is still not collected by VaidyaAI."
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
        metadata = {
            ASSESSMENT_KIND_KEY: ASSESSMENT_KIND_LIKELIHOOD,
            ASSESSMENT_BASIS_KEY: BASIS_NOT_ASSESSED,
            "assessment_kind_note": (
                "This predictor estimates the LIKELIHOOD of cardiovascular "
                "disease and did not run. Module 8's "
                "RULE_HEART_DISEASE_RISK_FACTORS emits the same condition "
                "string from a COUNT OF RISK FACTORS. A decision carrying no "
                "assessment_kind key should be read as a risk-factor burden, "
                "not as a probability."
            ),
        }
        metadata.update(extra_metadata or {})
        return super().insufficient_decision(
            report, context, extra_metadata=metadata
        )


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
                "banded": NOTE_CHOLESTEROL_BANDED,
                "imputed": NOTE_IMPUTED,
                "not_asserted": NOTE_NOT_ASSERTED,
                "unrecognised": NOTE_UNRECOGNISED_CATEGORY,
            }[status]
            if status in ("observed", "banded") and name in context.questionable:
                note = NOTE_QUESTIONABLE
            elif status in ("observed", "banded") and name in context.clinically_extreme:
                note = NOTE_EXTREME_HIGH
            items.append(
                EvidenceItem(
                    feature=name,
                    value=entry["value"],
                    unit=(
                        context.unit_for(name)
                        if status in ("observed", "banded")
                        else None
                    ),
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
        current_smoker: Optional[int],
    ):
        if status is DecisionStatus.INDICATED:
            codes: Tuple[str, ...] = (
                DISCUSS_WITH_CLINICIAN,
                CONFIRM_WITH_REPEAT_TESTING,
                GENERAL_PHYSICAL_ACTIVITY,
                GENERAL_DIETARY_FAT_QUALITY,
                GENERAL_BALANCED_DIET,
            )
        elif status is DecisionStatus.BORDERLINE:
            codes = (
                DISCUSS_WITH_CLINICIAN,
                MONITOR_OVER_TIME,
                GENERAL_PHYSICAL_ACTIVITY,
                GENERAL_BALANCED_DIET,
            )
        else:
            codes = (NOTHING_FLAGGED_EDUCATIONAL, MONITOR_OVER_TIME)

        if current_smoker == 1 and status is not DecisionStatus.NOT_INDICATED:
            codes += (GENERAL_SMOKING_CESSATION_SUPPORT,)

        if any(name in context.questionable for name in trace):
            codes += (INPUT_QUALITY_CAVEAT,)
        return resolve_recommendations(codes + (NOT_A_DIAGNOSIS,))


def _band_meaning(spec, band_name: str) -> str:
    recorded = spec.get("band_meaning") if hasattr(spec, "get") else None
    if isinstance(recorded, dict):
        text = recorded.get(band_name)
        if isinstance(text, str) and text:
            return text
    return _BAND_MEANING.get(
        band_name, "this artifact records no meaning for this band"
    )


_BAND_MEANING = {
    "low": (
        "Below the sensitivity-derived cut-off. On the held-out test split "
        "21.1% of patients in this band were positive, against a cohort "
        "prevalence of 50.0%. This band holds only 12% of the cohort: this "
        "model rarely rules heart disease out."
    ),
    "medium": (
        "Between the two cut-offs: NOT RULED OUT rather than elevated. On the "
        "held-out test split 48.5% of patients in this band were positive, "
        "which is the cohort base rate."
    ),
    "high": (
        "At or above the precision-derived cut-off. On the held-out test split "
        "74.7% of patients in this band were positive, against a cohort "
        "prevalence of 50.0%."
    ),
}

_COLUMN_TO_FEATURE: Dict[str, str] = {
    "cholesterol_band": "cholesterol",
    "smoking_current": "smoking_history",
}


def _canonical_importance(importance: Dict[str, float]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for column, value in importance.items():
        name = _COLUMN_TO_FEATURE.get(column, column)
        out[name] = out.get(name, 0.0) + float(value)
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


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


def _known_levels(bundle) -> Dict[str, Tuple[str, ...]]:
    dataset = bundle.get("dataset", {}) or {}
    return {"gender": tuple(dataset.get("gender_levels", ()))}


__all__ = [
    "ABSENT_CATEGORY",
    "ASSESSMENT_BASIS_KEY",
    "ASSESSMENT_KIND_KEY",
    "ASSESSMENT_KIND_LIKELIHOOD",
    "CHOLESTEROL_BAND_CUTOFFS",
    "CHOLESTEROL_BAND_LABELS",
    "HEART_METRICS_FILE",
    "HEART_MODEL_FILE",
    "HEART_NOTE_FRAGMENTS",
    "SMOKING_TO_CURRENT",
    "TRI_STATE_SMOKING",
    "VARIANT_BY_AVAILABILITY",
    "HeartPredictor",
    "cholesterol_band",
    "normalise_category",
    "smoking_current",
]
