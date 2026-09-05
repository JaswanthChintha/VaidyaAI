"""Error types and the consistent JSON error envelope.

Every failure path in this service surfaces as:

    {"success": false, "error": {"code": "...", "message": "..."}}

with a meaningful HTTP status -- never an unhandled 500 with a stack trace.

SECURITY NOTE: error messages are returned to the caller. They must never
contain report content, extracted medical values, or the API key.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


class ErrorCode:
    """Stable, machine-readable error codes. Module 5 may branch on these."""

    # --- authentication (401) ---
    # Deliberately ONE code for every rejection reason: a missing header, a
    # wrong key, an empty key and a whitespace key must be indistinguishable.
    UNAUTHORIZED = "UNAUTHORIZED"

    # --- intake / validation (4xx) ---
    NO_FILE = "NO_FILE"
    EMPTY_FILE = "EMPTY_FILE"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    UNSUPPORTED_FILE_TYPE = "UNSUPPORTED_FILE_TYPE"
    CORRUPT_FILE = "CORRUPT_FILE"
    TOO_MANY_PAGES = "TOO_MANY_PAGES"
    ENCRYPTED_PDF = "ENCRYPTED_PDF"
    NO_RENDERABLE_PAGES = "NO_RENDERABLE_PAGES"

    # --- upstream model (5xx / 429) ---
    MODEL_NOT_CONFIGURED = "MODEL_NOT_CONFIGURED"
    MODEL_TIMEOUT = "MODEL_TIMEOUT"
    MODEL_RATE_LIMITED = "MODEL_RATE_LIMITED"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    MODEL_REQUEST_FAILED = "MODEL_REQUEST_FAILED"
    MODEL_RESPONSE_MALFORMED = "MODEL_RESPONSE_MALFORMED"
    MODEL_RESPONSE_TRUNCATED = "MODEL_RESPONSE_TRUNCATED"
    MODEL_RESPONSE_BLOCKED = "MODEL_RESPONSE_BLOCKED"
    MODEL_RESPONSE_EMPTY = "MODEL_RESPONSE_EMPTY"

    # --- catch-all ---
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ServiceError(Exception):
    """Base class for every error this service deliberately raises."""

    status_code: int = 500
    code: str = ErrorCode.INTERNAL_ERROR

    def __init__(
        self,
        message: str,
        *,
        code: Optional[str] = None,
        status_code: Optional[int] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code

    def to_dict(self) -> Dict[str, Any]:
        return error_envelope(self.code, self.message)


class UnauthorizedError(ServiceError):
    """Service-to-service authentication failed.

    The message is a FIXED string. It must never say which check failed, and
    must never echo the presented key.
    """

    status_code = 401
    code = ErrorCode.UNAUTHORIZED


class BadRequestError(ServiceError):
    status_code = 400


class PayloadTooLargeError(ServiceError):
    status_code = 413
    code = ErrorCode.FILE_TOO_LARGE


class UnsupportedMediaTypeError(ServiceError):
    status_code = 415
    code = ErrorCode.UNSUPPORTED_FILE_TYPE


class UnprocessableDocumentError(ServiceError):
    """The file was accepted but could not be turned into pages."""

    status_code = 422
    code = ErrorCode.CORRUPT_FILE


class ModelError(ServiceError):
    """Anything that went wrong talking to, or parsing the output of, Gemini."""

    status_code = 502
    code = ErrorCode.MODEL_REQUEST_FAILED


class ModelTimeoutError(ModelError):
    status_code = 504
    code = ErrorCode.MODEL_TIMEOUT


class ModelRateLimitedError(ModelError):
    status_code = 429
    code = ErrorCode.MODEL_RATE_LIMITED


class ModelNotConfiguredError(ServiceError):
    status_code = 503
    code = ErrorCode.MODEL_NOT_CONFIGURED


def error_envelope(code: str, message: str) -> Dict[str, Any]:
    return {"success": False, "error": {"code": code, "message": message}}
