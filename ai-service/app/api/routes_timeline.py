from __future__ import annotations

from typing import Dict

from fastapi import APIRouter, Depends

from app.core.auth import require_service_key
from app.data.trend_polarity import policy_document
from app.schemas.timeline import (
    TimelineTrendsRequest,
    TimelineTrendsResponse,
)
from app.services.trend_analyzer import analyse_trends, analyzer_document

router = APIRouter(
    prefix="/api/v1/timeline",
    tags=["timeline"],
    dependencies=[Depends(require_service_key)],
)


@router.post(
    "/trends",
    response_model=TimelineTrendsResponse,
    response_model_exclude_none=False,
    summary="Classify each feature's trajectory across a patient's reports",
)
async def trends(request: TimelineTrendsRequest) -> TimelineTrendsResponse:
    return TimelineTrendsResponse(success=True, data=analyse_trends(request))


@router.get(
    "/policy",
    summary="The trend policy: per-feature polarity and stability bands",
)
async def policy() -> Dict[str, object]:
    return {
        "success": True,
        "data": {"analyzer": analyzer_document(), "polarity": policy_document()},
    }
