from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.auth import require_service_key
from app.safety.fallback import FALLBACK_NOTICE, safe_fallback
from app.safety.policy import (
    MODIFICATION_POLICY,
    SAFETY_LAYER_VERSION,
    SAFETY_POLICY,
    rule_document,
)
from app.safety.schemas import (
    SafetyValidationData,
    SafetyValidationRequest,
    SafetyValidationResponse,
)
from app.safety.validator import (
    APPROVE,
    APPROVE_WITH_MODIFICATION,
    MAX_TEXT_LENGTH,
    REJECT,
    REDACTION_NOTICE,
    validate_text,
)

router = APIRouter(
    prefix="/api/v1/safety",
    tags=["medical-safety"],
    dependencies=[Depends(require_service_key)],
)


@router.post(
    "/validate",
    response_model=SafetyValidationResponse,
    response_model_exclude_none=False,
    summary="Validate patient-facing text before it is shown (spec section 14)",
)
async def validate(request: SafetyValidationRequest) -> SafetyValidationResponse:
    verdict = validate_text(request.text, request.to_context())
    fallback = safe_fallback(verdict) if verdict.verdict == REJECT else None
    return SafetyValidationResponse(
        success=True,
        data=SafetyValidationData(verdict=verdict, fallback=fallback),
    )


@router.get(
    "/policy",
    summary="What the safety layer enforces, what it may modify, and what it cannot guarantee",
)
async def policy() -> dict:
    return {
        "success": True,
        "data": {
            "medical_safety": {
                "module": 24,
                "version": SAFETY_LAYER_VERSION,
                "policy": SAFETY_POLICY,
                "verdicts": [APPROVE, APPROVE_WITH_MODIFICATION, REJECT],
                "modification": MODIFICATION_POLICY,
                "max_text_length": MAX_TEXT_LENGTH,
                "redaction_notice": REDACTION_NOTICE,
                "fallback_notice": FALLBACK_NOTICE,
            }
        },
    }


@router.get(
    "/rules",
    summary="Every safety rule, its code, its severity, and whether it is a blocklist rule",
)
async def rules() -> dict:
    return {"success": True, "data": {"module": 24, **rule_document()}}
