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
    data = run_decision_fusion(request.validated, engineered=request.engineered)
    return DecisionFusionResponse(success=True, data=data)


@router.get(
    "/policy",
    summary="How decisions are collected, grouped and fused",
)
async def policy() -> dict:
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
