"""Correlation-id plumbing so one pipeline run can be traced across services.

The Node backend calls Module 4 and then Module 5 for the same stored report.
It sends an opaque report id in `X-Request-Id`; this service echoes it on the
response and stamps it onto every log line, so a failure in either stage can be
matched to the backend's own log.

PRIVACY RULE (medical data):
    A correlation id MUST NOT contain PHI. This module cannot detect PHI, so it
    enforces the next best thing -- a strict allow-list charset and a length
    cap. A value that does not satisfy them is DISCARDED and a fresh id is
    generated, rather than being logged as-is. The charset also makes log
    injection (newlines, control characters, ANSI escapes) impossible.

    Callers must send an opaque identifier (a Mongo ObjectId, a UUID). Never a
    patient name, an email, a filename or a report title.
"""

from __future__ import annotations

import re
import uuid
from contextvars import ContextVar
from typing import Optional

#: Header the backend sends and this service echoes.
REQUEST_ID_HEADER = "X-Request-Id"

#: Hex, letters, digits and a small set of separators. Nothing else.
_ALLOWED_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")

_request_id: ContextVar[Optional[str]] = ContextVar("vaidyaai_request_id", default=None)


def new_request_id() -> str:
    """A fresh, opaque correlation id."""
    return uuid.uuid4().hex


def sanitize_request_id(value: object) -> Optional[str]:
    """Return the caller's id if it is safe to log, else None.

    Returning None (rather than a scrubbed variant) is deliberate: a partially
    scrubbed id would still be a fragment of whatever the caller sent.
    """
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not candidate:
        return None
    if not _ALLOWED_REQUEST_ID.match(candidate):
        return None
    return candidate


def resolve_request_id(header_value: object) -> str:
    """The id to use for this request: the caller's if usable, else a new one."""
    return sanitize_request_id(header_value) or new_request_id()


def set_request_id(value: Optional[str]):
    """Bind the id for the current context. Returns the contextvar token."""
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
