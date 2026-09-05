"""Module 9 -- the Machine Learning Prediction Engine.

    Module 6 (validated features)
            |
            v
      +-----------------+
      | PredictorRegistry |     <- Module 13
      +-----------------+
            |
            +-- DiabetesPredictor   (Module 10, built)
            +-- HeartPredictor      (Module 11, not built)
            +-- KidneyPredictor     (Module 12, not built)
            |
            v
      ClinicalDecision[]  ->  Module 15 -> Module 16

Nothing here trains a model. Training lives in `ml/train_diabetes.py` and is
run by hand; this package only ever LOADS a persisted artifact.

The public surface deliberately mirrors the rest of the service: a
framework-independent `predict_all()` that Module 15 can call in-process,
exactly as it calls `engineer_features()`, `validate_features()` and
`evaluate_rules()`.
"""

from __future__ import annotations

from app.ml.base import (
    ML_MODULE,
    STAGE_ML,
    Predictor,
    PredictorError,
    SufficiencyReport,
)
from app.ml.engine import ML_ENGINE_POLICY, ML_ENGINE_VERSION, predict_all
from app.ml.registry import (
    DuplicatePredictorError,
    PredictorRegistry,
    UnknownPredictorError,
    build_default_registry,
    default_registry,
)

__all__ = [
    "ML_ENGINE_POLICY",
    "ML_ENGINE_VERSION",
    "ML_MODULE",
    "STAGE_ML",
    "DuplicatePredictorError",
    "Predictor",
    "PredictorError",
    "PredictorRegistry",
    "SufficiencyReport",
    "UnknownPredictorError",
    "build_default_registry",
    "default_registry",
    "predict_all",
]
