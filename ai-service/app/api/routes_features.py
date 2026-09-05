"""POST /api/v1/features/engineer -- the Module 5 endpoint.

Thin HTTP wrapper. All logic lives in
`app.services.feature_engineer.engineer_features`, which is importable
directly by Module 7 and the ML layer.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.auth import require_service_key

from app.schemas.features import (
    FeatureEngineeringRequest,
    FeatureEngineeringResponse,
    catalog_document,
)
from app.services.feature_engineer import DUPLICATE_POLICY, engineer_features

# PHI-bearing endpoints: every route on this router requires the shared
# service secret in the X-Service-Key header. See app/core/auth.py.
router = APIRouter(
    prefix="/api/v1/features",
    tags=["features"],
    dependencies=[Depends(require_service_key)],
)


@router.post(
    "/engineer",
    response_model=FeatureEngineeringResponse,
    response_model_exclude_none=False,
    summary="Convert extracted lab parameters into canonical medical features",
)
async def engineer(request: FeatureEngineeringRequest) -> FeatureEngineeringResponse:
    # The whole extraction is passed, not just the rows: Module 4's warnings,
    # source, report metadata, confidence and per-page readability must survive
    # this boundary or the final report cannot tell a damaged scan from a clean
    # one.
    data = engineer_features(
        request.extraction.extracted_parameters,
        request.profile,
        extraction=request.extraction,
    )
    return FeatureEngineeringResponse(success=True, data=data)


@router.get(
    "/catalog",
    summary="The canonical feature space, units and duplicate policy",
)
async def catalog() -> dict:
    """Machine-readable contract for Module 6 / 7 and for clinical review."""
    document = catalog_document()
    document["duplicate_policy"] = DUPLICATE_POLICY
    return {"success": True, "data": document}
