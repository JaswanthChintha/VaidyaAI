"""POST /api/v1/rules/evaluate -- the Module 8 endpoint.

Thin HTTP wrapper. All logic lives in
`app.services.rule_engine.evaluate_rules`, which is importable directly by
Module 15 (Decision Engine), exactly as `engineer_features` and
`validate_features` are.

The router lives in its own file and carries its own prefix so it can be
mounted alongside the other routers without either module owning the other.

AUTH: this endpoint receives medical feature values and returns clinical
decisions about them, so it is PHI-bearing and carries the same service-key
dependency as `routes_validation.py`. `tests/test_auth.py` walks the route tree
recursively and fails if any `/api/v1` route lacks it.
"""

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
    # `validated` is preferred; `engineered` is accepted so the engine is usable
    # before Module 6 has been run (it is then validated in-process, so the
    # rules still only ever see validated values).
    data = evaluate_rules(request.validated, engineered=request.engineered)
    return RuleEvaluationResponse(success=True, data=data)


@router.get(
    "/clinical-rules",
    summary="The clinical rule table, its thresholds and their clinical basis",
)
async def clinical_rules() -> dict:
    """Machine-readable rule table, for clinical review and for Module 20."""
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
