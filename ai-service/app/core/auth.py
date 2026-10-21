from __future__ import annotations

import hashlib
import hmac
from typing import Optional

from fastapi import Depends, Request

from app.config import Settings, get_settings
from app.core.errors import UnauthorizedError
from app.core.logging import get_logger, safe_meta

logger = get_logger(__name__)

SERVICE_KEY_HEADER = "X-Service-Key"

UNAUTHORIZED_MESSAGE = (
    "Service authentication failed. Send the shared secret in the "
    f"{SERVICE_KEY_HEADER} header."
)

STARTUP_ERROR_MESSAGE = (
    "REFUSING TO START: AI_SERVICE_API_KEY is not configured.\n"
    "This service processes protected health information and must not accept "
    "unauthenticated traffic.\n"
    "  * Production / any shared environment: set AI_SERVICE_API_KEY to a "
    "random secret of at least {min_length} characters, and set the same value "
    "in the Node backend's AI_SERVICE_API_KEY.\n"
    "  * Local development ONLY, if you truly want an open service: set "
    "ALLOW_UNAUTHENTICATED=true. This is logged loudly on every startup.\n"
    "An unset key is NEVER treated as 'no authentication required'."
)

SHORT_KEY_ERROR_MESSAGE = (
    "REFUSING TO START: AI_SERVICE_API_KEY is shorter than {min_length} "
    "characters. The shared secret is machine-generated material, not a "
    "human password; a short value is a configuration mistake."
)

UNAUTHENTICATED_BANNER = (
    "=" * 78 + "\n"
    "  SECURITY WARNING: ALLOW_UNAUTHENTICATED=true\n"
    "  This service is accepting UNAUTHENTICATED requests. Any caller who can\n"
    "  reach this port can submit medical documents and read extractions.\n"
    "  This is a LOCAL DEVELOPMENT setting only. Never set it in a shared or\n"
    "  production environment. Set AI_SERVICE_API_KEY instead.\n"
    + "=" * 78
)


def _digest(value: str) -> bytes:
    return hashlib.sha256(value.encode("utf-8")).digest()


def keys_match(presented: Optional[str], expected: str) -> bool:
    candidate = (presented or "").strip()
    reference = (expected or "").strip()
    if not reference:
        return False
    return hmac.compare_digest(_digest(candidate), _digest(reference))


def enforce_service_auth_configuration(settings: Settings) -> None:
    if settings.has_service_key:
        key = settings.ai_service_api_key.get_secret_value().strip()
        if len(key) < settings.min_service_key_length:
            raise RuntimeError(
                SHORT_KEY_ERROR_MESSAGE.format(
                    min_length=settings.min_service_key_length
                )
            )
        return

    if settings.allow_unauthenticated:
        logger.warning("\n%s", UNAUTHENTICATED_BANNER)
        return

    raise RuntimeError(
        STARTUP_ERROR_MESSAGE.format(min_length=settings.min_service_key_length)
    )


async def require_service_key(
    request: Request, settings: Settings = Depends(get_settings)
) -> None:
    if settings.allow_unauthenticated and not settings.has_service_key:
        return

    presented = request.headers.get(SERVICE_KEY_HEADER)
    expected = settings.ai_service_api_key.get_secret_value()

    if keys_match(presented, expected):
        return

    logger.warning(
        "service_auth_rejected %s",
        safe_meta(path=request.url.path, method=request.method),
    )
    raise UnauthorizedError(UNAUTHORIZED_MESSAGE)


__all__ = [
    "SERVICE_KEY_HEADER",
    "STARTUP_ERROR_MESSAGE",
    "UNAUTHENTICATED_BANNER",
    "UNAUTHORIZED_MESSAGE",
    "enforce_service_auth_configuration",
    "keys_match",
    "require_service_key",
]
