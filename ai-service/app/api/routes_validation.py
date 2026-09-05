"""POST /api/v1/features/validate -- the Module 6 endpoint.

Thin HTTP wrapper. All logic lives in
`app.services.validator.validate_features`, which is importable directly by
Module 7, Module 8 and the ML layer, exactly as `engineer_features` is.

The router lives in its own file and carries its own prefix so it can be
mounted alongside `routes_features` without either module owning the other.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.auth import require_service_key
from app.data.validation_rules import rules_document
from app.schemas.validation import (
    FeatureValidationRequest,
    FeatureValidationResponse,
)
from app.services.validator import VALIDATION_POLICY, validate_features

# PHI-bearing endpoints: every route on this router requires the shared
# service secret in the X-Service-Key header. See app/core/auth.py.
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
    # The WHOLE Module 5 object is passed, not just `features`: its warnings,
    # upstream extraction context, unmapped rows and missing-feature list must
    # survive this boundary or the final report cannot tell a damaged scan from
    # a clean one, and an unread test becomes indistinguishable from an absent
    # one.
    data = validate_features(request.engineered)
    return FeatureValidationResponse(success=True, data=data)


@router.get(
    "/validation-rules",
    summary="The per-feature validation rule table and its clinical basis",
)
async def validation_rules() -> dict:
    """Machine-readable rule table, for clinical review and for Module 20."""
    document = rules_document()
    document["policy"] = VALIDATION_POLICY
    return {"success": True, "data": document}
