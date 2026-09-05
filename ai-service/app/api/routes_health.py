"""GET /api/v1/health -- liveness and configuration readiness."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.config import Settings, get_settings
from app.prompts.extraction_prompt import PROMPT_VERSION

router = APIRouter(prefix="/api/v1", tags=["health"])


@router.get("/health", summary="Service health and readiness")
async def health(settings: Settings = Depends(get_settings)) -> dict:
    # Reports WHETHER a key is configured, never the key itself.
    return {
        "success": True,
        "data": {
            "status": "ok",
            "service": settings.app_name,
            "module": "4 - OCR and Medical Text Extraction",
            "environment": settings.environment,
            "model": settings.gemini_model,
            "model_configured": settings.has_api_key,
            "prompt_version": PROMPT_VERSION,
            "limits": {
                "max_file_size_bytes": settings.max_file_size_bytes,
                "max_page_count": settings.max_page_count,
                "supported_types": ["application/pdf", "image/jpeg", "image/png"],
            },
        },
    }
