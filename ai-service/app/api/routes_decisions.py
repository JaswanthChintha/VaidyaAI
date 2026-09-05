"""POST /api/v1/decisions/fuse -- the Module 15/16 endpoint.

Thin HTTP wrapper. All logic lives in
`app.services.decision_engine.collect_decisions` and
`app.services.fusion_engine.fuse_decisions`, both of which are importable
directly by Module 17, exactly as `evaluate_rules` and `predict_all` are.

The router lives in its own file and carries its own prefix so it can be
mounted alongside the other routers without either module owning the other.

AUTH: this endpoint receives medical feature values and returns fused clinical
decisions about them, so it is PHI-bearing and carries the same service-key
dependency as `routes_rules.py` and `routes_ml.py`. `tests/test_auth.py` walks
the route tree recursively and fails if any `/api/v1` route lacks it.

INPUT TOLERANCE is inherited, not re-implemented: `DecisionFusionRequest`
subclasses `RuleEvaluationRequest`, so every shape `/rules/evaluate` and
`/ml/predict` accept is accepted identically here, and every ambiguity is the
same 422. Nothing is guessed -- a wrong guess here would not raise, it would
return `fused: []` with HTTP 200.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.auth import require_service_key
from app.schemas.fusion import DecisionFusionRequest, DecisionFusionResponse
from app.services.decision_engine import (
    DECISION_ENGINE_POLICY,
    DECISION_ENGINE_VERSION,
    STATUS_FUSION_RULE,
    CONFIDENCE_RULE,
)
from app.services.fusion_engine import (
    FUSION_ENGINE_VERSION,
    FUSION_POLICY,
    run_decision_fusion,
)

router = APIRouter(
    prefix="/api/v1/decisions",
    tags=["decision-fusion"],
    dependencies=[Depends(require_service_key)],
)


@router.post(
    "/fuse",
    response_model=DecisionFusionResponse,
    response_model_exclude_none=False,
    summary="Collect every clinical decision and fuse them by condition",
)
async def fuse(request: DecisionFusionRequest) -> DecisionFusionResponse:
    # `validated` is preferred; `engineered` is accepted so the engines are
    # usable before Module 6 has been run (each validates in-process, so
    # neither the rules nor a model ever sees an unvalidated value).
    data = run_decision_fusion(request.validated, engineered=request.engineered)
    return DecisionFusionResponse(success=True, data=data)


@router.get(
    "/policy",
    summary="How decisions are collected, grouped and fused",
)
async def policy() -> dict:
    """The fusion rules, in machine-readable form.

    Exposed for the same reason the rule table and the model metrics are: a
    documented rule nobody can retrieve from the running service is not an
    accountability mechanism. Shape and policy only -- no PHI, no values.
    """
    return {
        "success": True,
        "data": {
            "decision_engine": {
                "module": 15,
                "version": DECISION_ENGINE_VERSION,
                "policy": DECISION_ENGINE_POLICY,
                "grouped_by": ["condition", "source"],
            },
            "fusion_engine": {
                "module": 16,
                "version": FUSION_ENGINE_VERSION,
                "policy": FUSION_POLICY,
                "fused_by": ["condition"],
                "risk_rule": (
                    "risk levels are ordered Low < Medium < High and the "
                    "highest applicable risk is retained; an empty set yields "
                    "no risk at all rather than Low"
                ),
                "status_rule": STATUS_FUSION_RULE,
                "confidence_rule": CONFIDENCE_RULE,
            },
        },
    }
