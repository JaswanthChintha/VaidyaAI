from __future__ import annotations

from typing import Dict

from fastapi import APIRouter, Depends

from app.core.auth import require_service_key
from app.data.progress_scoring import scoring_document
from app.data.trend_polarity import policy_document
from app.schemas.progress import (
    HealthProgressRequest,
    HealthProgressResponse,
)
from app.services.progress_analyzer import analyse_progress, progress_document
from app.services.report_comparator import comparator_document
from app.services.trend_analyzer import analyzer_document

router = APIRouter(
    prefix="/api/v1/progress",
    tags=["progress"],
    dependencies=[Depends(require_service_key)],
)


@router.post(
    "/score",
    response_model=HealthProgressResponse,
    response_model_exclude_none=False,
    summary="Compute the health progress score between two reports",
)
async def score(request: HealthProgressRequest) -> HealthProgressResponse:
    return HealthProgressResponse(success=True, data=analyse_progress(request))


@router.get(
    "/policy",
    summary="The scoring table, and the clinical tables it delegates to",
)
async def policy() -> Dict[str, object]:
    return {
        "success": True,
        "data": {
            "progress": progress_document(),
            "scoring": scoring_document(),
            "comparator": comparator_document(),
            "analyzer": analyzer_document(),
            "polarity": policy_document(),
        },
    }
