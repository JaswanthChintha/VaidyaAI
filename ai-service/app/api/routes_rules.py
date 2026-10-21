from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.auth import require_service_key
from app.data.clinical_rules import rules_document
from app.data.conditions import conditions_document
from app.data.recommendation_catalog import catalog_document
from app.schemas.rules import RuleEvaluationRequest, RuleEvaluationResponse
from app.services.rule_engine import RULE_ENGINE_POLICY, evaluate_rules

router = APIRouter(
    prefix="/api/v1/rules",
    tags=["clinical-rules"],
    dependencies=[Depends(require_service_key)],
)


@router.post(
    "/evaluate",
    response_model=RuleEvaluationResponse,
    response_model_exclude_none=False,
    summary="Apply the deterministic clinical rule table to validated features",
)
async def evaluate(request: RuleEvaluationRequest) -> RuleEvaluationResponse:
    data = evaluate_rules(request.validated, engineered=request.engineered)
    return RuleEvaluationResponse(success=True, data=data)


@router.get(
    "/clinical-rules",
    summary="The clinical rule table, its thresholds and their clinical basis",
)
async def clinical_rules() -> dict:
    document = rules_document()
    document["policy"] = RULE_ENGINE_POLICY
    return {"success": True, "data": document}


@router.get(
    "/conditions",
    summary="The canonical condition vocabulary Modules 10-12 must match",
)
async def conditions() -> dict:
    return {"success": True, "data": conditions_document()}


@router.get(
    "/recommendations",
    summary="The reviewable recommendation catalogue and its safety rules",
)
async def recommendation_catalog() -> dict:
    return {"success": True, "data": catalog_document()}
