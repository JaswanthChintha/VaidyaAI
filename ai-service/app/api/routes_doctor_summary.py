from __future__ import annotations

from typing import Dict

from fastapi import APIRouter, Depends

from app.core.auth import require_service_key
from app.schemas.doctor_summary import (
    DoctorSummaryRequest,
    DoctorSummaryResponse,
)
from app.services.doctor_summary import (
    build_doctor_summary,
    doctor_summary_document,
)

router = APIRouter(
    prefix="/api/v1/doctor-summary",
    tags=["doctor-summary"],
    dependencies=[Depends(require_service_key)],
)


@router.post(
    "/generate",
    response_model=DoctorSummaryResponse,
    response_model_exclude_none=False,
    summary="Assemble a structured summary a patient can hand to a clinician",
)
async def generate(request: DoctorSummaryRequest) -> DoctorSummaryResponse:
    return DoctorSummaryResponse(success=True, data=build_doctor_summary(request))


@router.get(
    "/policy",
    summary="What this document does and does not contain",
)
async def policy() -> Dict[str, object]:
    return {"success": True, "data": doctor_summary_document()}
