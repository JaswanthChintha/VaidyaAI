from __future__ import annotations

import re
import uuid
from contextvars import ContextVar
from typing import Optional

REQUEST_ID_HEADER = "X-Request-Id"

_ALLOWED_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")

_request_id: ContextVar[Optional[str]] = ContextVar("vaidyaai_request_id", default=None)


def new_request_id() -> str:
    return uuid.uuid4().hex


def sanitize_request_id(value: object) -> Optional[str]:
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not candidate:
        return None
    if not _ALLOWED_REQUEST_ID.match(candidate):
        return None
    return candidate


def resolve_request_id(header_value: object) -> str:
    return sanitize_request_id(header_value) or new_request_id()


def set_request_id(value: Optional[str]):
    return _request_id.set(value)


def reset_request_id(token) -> None:
    _request_id.reset(token)


def get_request_id() -> Optional[str]:
    return _request_id.get()


__all__ = [
    "REQUEST_ID_HEADER",
    "get_request_id",
    "new_request_id",
    "reset_request_id",
    "resolve_request_id",
    "sanitize_request_id",
    "set_request_id",
]
