"""POST /api/v1/ml/predict -- the Module 9/10 endpoint.

Thin HTTP wrapper. All logic lives in `app.ml.engine.predict_all`, which is
importable directly by Module 15 (Decision Engine), exactly as
`engineer_features`, `validate_features` and `evaluate_rules` are.

The router lives in its own file and carries its own prefix so it can be
mounted alongside the other routers without either module owning the other.

AUTH: these endpoints receive medical feature values and return clinical
decisions about them, so they are PHI-bearing and carry the same service-key
dependency as `routes_rules.py`. `tests/test_auth.py` walks the route tree
recursively and fails if any `/api/v1` route lacks it.

NOTHING HERE TRAINS. The model artifact is built by `python ml/train_diabetes.py`
and is loaded lazily and cached on first prediction.
"""

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
    # `validated` is preferred; `engineered` is accepted so the engine is usable
    # before Module 6 has been run (it is then validated in-process, so a model
    # still only ever sees validated values).
    data = predict_all(request.validated, engineered=request.engineered)
    return MLPredictionResponse(success=True, data=data)


@router.get(
    "/predictors",
    summary="The registered predictors, their required features and status",
)
async def predictors() -> dict:
    """Registry introspection (spec Module 13).

    Shape only -- no PHI, no values. `available: false` on a predictor means
    its model artifact could not be loaded, which is the one way a deployment
    mistake becomes visible before every report comes back unassessed.
    """
    document = default_registry().describe()
    document["engine_version"] = ML_ENGINE_VERSION
    document["policy"] = ML_ENGINE_POLICY
    return {"success": True, "data": document}


@router.get(
    "/models",
    summary="Model provenance and the recorded evaluation metrics",
)
async def models() -> dict:
    """The evaluation artifact written beside the model, verbatim.

    Exposed so the numbers behind a prediction are auditable from the running
    service rather than only from the repository -- spec section 11 asks for
    the metrics, and a metric nobody can retrieve is not an accountability
    mechanism.
    """
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
