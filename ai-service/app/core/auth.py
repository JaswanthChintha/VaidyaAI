"""Service-to-service authentication.

This service processes protected health information. The ONLY legitimate caller
is the Node `backend/`, so the protection is a shared secret rather than a user
session:

    env var  AI_SERVICE_API_KEY   the shared secret, held by both services
    header   X-Service-Key        how the caller presents it

Applied to `POST /api/v1/ocr/extract`, `POST /api/v1/features/engineer` and
`GET /api/v1/features/catalog`. `GET /api/v1/health` is deliberately left
unauthenticated so the backend can health-check the service before it holds a
key; the health payload therefore carries no secret and no PHI.

DESIGN RULES (each of these is load-bearing, not style):

* FAIL CLOSED. An unset `AI_SERVICE_API_KEY` never means "open". The service
  refuses to start. The one escape hatch, `ALLOW_UNAUTHENTICATED=true`, has to
  be set deliberately and logs a loud warning on EVERY startup.
* CONSTANT TIME. The comparison runs over SHA-256 digests of both sides, so it
  is fixed-length: neither the value nor the LENGTH of the configured key can
  be recovered by timing.
* INDISTINGUISHABLE FAILURES. A missing header, a wrong key, an empty key and a
  whitespace-only key all produce the identical 401 body (one error code, one
  fixed message) and all run the same amount of work.
* NEVER LOG THE SECRET. Not the configured one, not the presented one, not a
  prefix, not a hash. The rejection log line records only the request path and
  the correlation id.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Optional

from fastapi import Depends, Request

from app.config import Settings, get_settings
from app.core.errors import UnauthorizedError
from app.core.logging import get_logger, safe_meta

logger = get_logger(__name__)

#: The header the backend must send.
SERVICE_KEY_HEADER = "X-Service-Key"

#: Fixed rejection message. Says nothing about which check failed.
UNAUTHORIZED_MESSAGE = (
    "Service authentication failed. Send the shared secret in the "
    f"{SERVICE_KEY_HEADER} header."
)

#: Raised at startup when the configuration would leave the service open.
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
    """Constant-time shared-secret comparison.

    Both sides are hashed first so the comparison is over two fixed-length
    32-byte digests. `hmac.compare_digest` on the raw strings would short-
    circuit on a length mismatch and leak the configured key's length.

    A missing header is compared as the empty string so that the missing-header
    path does exactly the same work as the wrong-key path.
    """
    candidate = (presented or "").strip()
    reference = (expected or "").strip()
    # An unusable configured secret must never match anything, including "".
    # (Startup enforcement should have prevented this; belt and braces.)
    if not reference:
        return False
    return hmac.compare_digest(_digest(candidate), _digest(reference))


def enforce_service_auth_configuration(settings: Settings) -> None:
    """Fail closed at startup. Raises `RuntimeError` rather than run open.

    Called at import time from `app.main`, so `uvicorn app.main:app` aborts
    with a clear message instead of silently serving PHI to anyone.
    """
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
        # Loud, unmissable, and repeated on every single startup.
        logger.warning("\n%s", UNAUTHENTICATED_BANNER)
        return

    raise RuntimeError(
        STARTUP_ERROR_MESSAGE.format(min_length=settings.min_service_key_length)
    )


async def require_service_key(
    request: Request, settings: Settings = Depends(get_settings)
) -> None:
    """FastAPI dependency guarding every PHI-bearing endpoint."""
    if settings.allow_unauthenticated and not settings.has_service_key:
        return

    presented = request.headers.get(SERVICE_KEY_HEADER)
    expected = settings.ai_service_api_key.get_secret_value()

    if keys_match(presented, expected):
        return

    # Path only. Never the presented key, never a prefix, never a hash of it,
    # and never which of the four failure shapes occurred.
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
