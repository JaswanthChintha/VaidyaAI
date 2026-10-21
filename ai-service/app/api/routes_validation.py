from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.auth import require_service_key
from app.data.validation_rules import rules_document
from app.schemas.validation import (
    FeatureValidationRequest,
    FeatureValidationResponse,
)
from app.services.validator import VALIDATION_POLICY, validate_features

router = APIRouter(
    prefix="/api/v1/features",
    tags=["validation"],
    dependencies=[Depends(require_service_key)],
)


@router.post(
    "/validate",
    response_model=FeatureValidationResponse,
    response_model_exclude_none=False,
    summary="Validate engineered medical features for plausibility and usability",
)
async def validate(request: FeatureValidationRequest) -> FeatureValidationResponse:
    data = validate_features(request.engineered)
    return FeatureValidationResponse(success=True, data=data)


@router.get(
    "/validation-rules",
    summary="The per-feature validation rule table and its clinical basis",
)
async def validation_rules() -> dict:
    document = rules_document()
    document["policy"] = VALIDATION_POLICY
    return {"success": True, "data": document}
