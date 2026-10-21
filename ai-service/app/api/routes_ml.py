from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.auth import require_service_key
from app.ml.artifacts import load_metrics
from app.ml.engine import ML_ENGINE_POLICY, ML_ENGINE_VERSION, predict_all
from app.ml.registry import default_registry
from app.schemas.ml import MLPredictionRequest, MLPredictionResponse

router = APIRouter(
    prefix="/api/v1/ml",
    tags=["ml-predictions"],
    dependencies=[Depends(require_service_key)],
)


@router.post(
    "/predict",
    response_model=MLPredictionResponse,
    response_model_exclude_none=False,
    summary="Run every registered ML predictor over a validated feature set",
)
async def predict(request: MLPredictionRequest) -> MLPredictionResponse:
    data = predict_all(request.validated, engineered=request.engineered)
    return MLPredictionResponse(success=True, data=data)


@router.get(
    "/predictors",
    summary="The registered predictors, their required features and status",
)
async def predictors() -> dict:
    document = default_registry().describe()
    document["engine_version"] = ML_ENGINE_VERSION
    document["policy"] = ML_ENGINE_POLICY
    return {"success": True, "data": document}


@router.get(
    "/models",
    summary="Model provenance and the recorded evaluation metrics",
)
async def models() -> dict:
    metrics = load_metrics()
    return {
        "success": True,
        "data": {
            "available": metrics is not None,
            "metrics": metrics,
            "note": (
                "Measured on a held-out test split by ml/train_diabetes.py. "
                "The dataset is 8.8% positive after de-duplication, so "
                "accuracy is reported next to the majority-class baseline and "
                "PR-AUC is the more informative headline number."
            ),
        },
    }
