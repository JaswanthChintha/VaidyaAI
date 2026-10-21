from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request

from app.core.auth import require_service_key
from app.core.logging import get_logger
from app.schemas.report import (
    ClinicalReportRequest,
    ClinicalReportResponse,
    OVERALL_STATUS_POLICY,
    PRIORITIZATION_POLICY,
    EXPLAINABILITY_POLICY,
    OVERALL_STATUS_LABELS,
    PRIORITY_BANDS,
    AVAILABILITY_VALUES,
)
from app.services.report_builder import (
    REPORT_POLICY,
    REPORT_VERSION,
    extract_rejected_features,
    generate_report,
)

logger = get_logger(__name__)

router = APIRouter(
    prefix="/api/v1/report",
    tags=["clinical-report"],
    dependencies=[Depends(require_service_key)],
)


async def _raw_body(request: Request) -> Any:
    try:
        return await request.json()
    except Exception:
        return None


@router.post(
    "/generate",
    response_model=ClinicalReportResponse,
    response_model_exclude_none=False,
    summary="Generate the structured Clinical Report for one analysis",
)
async def generate(
    payload: ClinicalReportRequest, request: Request
) -> ClinicalReportResponse:
    rejected = payload.rejected_features or extract_rejected_features(
        await _raw_body(request)
    )
    report = generate_report(
        payload.validated,
        engineered=payload.engineered,
        rejected=rejected,
    )
    return ClinicalReportResponse(success=True, data=report)


@router.get(
    "/policy",
    summary="How the clinical report, overall status, priority and evidence are built",
)
async def policy() -> dict:
    return {
        "success": True,
        "data": {
            "clinical_report": {
                "module": 17,
                "version": REPORT_VERSION,
                "policy": REPORT_POLICY,
                "sections": [
                    "patient",
                    "laboratory_values",
                    "conditions",
                    "overall",
                    "overall_risk",
                    "critical_conditions",
                    "normal_findings",
                    "explainability",
                    "recommendations",
                    "metadata",
                    "validation_warnings",
                ],
            },
            "overall_health_status": {
                "module": 18,
                "policy": OVERALL_STATUS_POLICY,
                "labels": list(OVERALL_STATUS_LABELS),
                "fourth_case": (
                    "when nothing could be assessed the status is 'Not "
                    "Assessed' and never 'Healthy': an absence of findings in "
                    "a report that could not be read is not a finding of good "
                    "health"
                ),
            },
            "risk_prioritization": {
                "module": 19,
                "policy": PRIORITIZATION_POLICY,
                "bands": list(PRIORITY_BANDS),
                "prioritised_by": ["condition"],
            },
            "evidence_and_explainability": {
                "module": 20,
                "policy": EXPLAINABILITY_POLICY,
                "chain": ["Input", "Evidence", "Decision"],
                "availability_values": list(AVAILABILITY_VALUES),
                "ml_feature_importance_scope": "global_model_level",
                "ml_feature_importance_is_per_patient": False,
            },
        },
    }
