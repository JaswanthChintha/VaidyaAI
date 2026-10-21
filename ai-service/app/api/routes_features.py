from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.auth import require_service_key

from app.schemas.features import (
    FeatureEngineeringRequest,
    FeatureEngineeringResponse,
    catalog_document,
)
from app.services.feature_engineer import DUPLICATE_POLICY, engineer_features

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
    document = catalog_document()
    document["duplicate_policy"] = DUPLICATE_POLICY
    return {"success": True, "data": document}
