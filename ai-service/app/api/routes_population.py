from __future__ import annotations

from typing import Dict

from fastapi import APIRouter, Depends

from app.core.auth import require_service_key
from app.population.policy import POLICY
from app.schemas.population import (
    PopulationContextRequest,
    PopulationContextResponse,
)
from app.services.population_context import population_context, population_document

router = APIRouter(
    prefix="/api/v1/population",
    tags=["population-context"],
    dependencies=[Depends(require_service_key)],
)


@router.post(
    "/context",
    response_model=PopulationContextResponse,
    response_model_exclude_none=False,
    summary="Place a patient's values in an age- and sex-matched population",
)
async def context(request: PopulationContextRequest) -> PopulationContextResponse:
    return PopulationContextResponse(success=True, data=population_context(request))


@router.get(
    "/policy",
    summary="The population policy, the exclusions, and the shipped tables",
)
async def policy() -> Dict[str, object]:
    return {
        "success": True,
        "data": {"policy": POLICY, "service": population_document()},
    }
