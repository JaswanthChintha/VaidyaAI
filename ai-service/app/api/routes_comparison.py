from __future__ import annotations

from typing import Dict

from fastapi import APIRouter, Depends

from app.core.auth import require_service_key
from app.data.trend_polarity import policy_document
from app.schemas.comparison import (
    ReportComparisonRequest,
    ReportComparisonResponse,
)
from app.services.report_comparator import comparator_document, compare_reports
from app.services.trend_analyzer import analyzer_document

router = APIRouter(
    prefix="/api/v1/comparison",
    tags=["comparison"],
    dependencies=[Depends(require_service_key)],
)


@router.post(
    "/reports",
    response_model=ReportComparisonResponse,
    response_model_exclude_none=False,
    summary="Compare two or more reports parameter by parameter",
)
async def compare(request: ReportComparisonRequest) -> ReportComparisonResponse:
    return ReportComparisonResponse(success=True, data=compare_reports(request))


@router.get(
    "/policy",
    summary="The comparison policy, and the trend tables it delegates to",
)
async def policy() -> Dict[str, object]:
    return {
        "success": True,
        "data": {
            "comparator": comparator_document(),
            "analyzer": analyzer_document(),
            "polarity": policy_document(),
        },
    }
