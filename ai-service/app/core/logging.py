"""Logging setup for the OCR service.

PRIVACY / SAFETY RULE (medical data):
    This service handles protected health information. The following must
    NEVER be written to logs, at any level:
      * raw file bytes or any part of an uploaded document
      * OCR'd / transcribed report text (`raw_text`, page text)
      * extracted parameter names, values, units, or reference ranges
      * patient names or any other identifier read off the report
      * the Gemini API key

    Only non-identifying operational metadata may be logged: request ids,
    mime types, byte sizes, page counts, durations, error codes, and counts.

`safe_meta()` below is the sanctioned way to build a log payload; it accepts
only scalar metadata and truncates anything unexpectedly long.
"""

from __future__ import annotations

import logging
import sys
from typing import Any, Dict

_CONFIGURED = False

# Keys that must never appear in a log record, however they arrive.
_FORBIDDEN_KEYS = {
    "raw_text",
    "text",
    "content",
    "pages",
    "extracted_parameters",
    "parameters",
    "patient_name",
    "api_key",
    "gemini_api_key",
    "file_bytes",
    "data",
    "prompt",
    "response_text",
}


def configure_logging(level: str = "INFO") -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(getattr(logging, str(level).upper(), logging.INFO))
    # The SDK's HTTP layer can be chatty and may echo request bodies at DEBUG.
    # Pin it to WARNING so document bytes can never leak through it.
    for noisy in ("httpx", "httpcore", "google_genai", "google.genai", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    _CONFIGURED = True


# Attribute names CPython's `Logger.makeRecord` refuses to let `extra=`
# overwrite. Derived from a real LogRecord rather than hand-listed, so it
# cannot fall out of date with the interpreter, plus the two names makeRecord
# rejects explicitly even though they are not instance attributes.
_RESERVED_RECORD_KEYS = frozenset(
    logging.LogRecord("", 0, "", 0, "", None, None).__dict__
) | {"message", "asctime"}


class _SafeLogger(logging.Logger):
    """A logger whose `extra=` payload can never take down a request.

    Stock `Logger.makeRecord` RAISES `KeyError` when an `extra` key collides
    with a LogRecord attribute -- and `module` is one of them. That raise
    happens in `_log`, BEFORE any handler runs, so logging's usual
    swallow-errors-during-emit protection does not apply and the exception
    propagates into the caller. A single observability line then becomes a
    500, and worst of all it does so from inside `except` blocks written to
    make a failure degrade gracefully.

    This is not hypothetical: `module=` is the tag every module in this
    service stamps on its log payloads, so ANY caller reaching for `extra=`
    hits it on their first line. Module 32 did, and every one of its four log
    calls raised -- taking out both its happy path and all three of its
    degradation paths.

    Colliding keys are RE-KEYED (`module` -> `meta_module`), never dropped:
    losing the tag silently would trade a loud failure for a quiet one, which
    is the trade this project refuses everywhere else.
    """

    def makeRecord(self, name, level, fn, lno, msg, args, exc_info,
                   func=None, extra=None, sinfo=None):
        if extra:
            collisions = _RESERVED_RECORD_KEYS.intersection(extra)
            if collisions:
                extra = {
                    (f"meta_{k}" if k in collisions else k): v
                    for k, v in extra.items()
                }
        return super().makeRecord(
            name, level, fn, lno, msg, args, exc_info, func, extra, sinfo
        )


def get_logger(name: str) -> logging.Logger:
    """Return this service's logger for `name`.

    Every module obtains its logger here -- there is no direct
    `logging.getLogger` call anywhere in `app/` -- so installing the class at
    this single point is a total guarantee, and unlike a module-level
    `setLoggerClass()` it does not depend on import ordering.
    """
    previous = logging.getLoggerClass()
    logging.setLoggerClass(_SafeLogger)
    try:
        return logging.getLogger(name)
    finally:
        logging.setLoggerClass(previous)


def safe_meta(**kwargs: Any) -> Dict[str, Any]:
    """Filter a would-be log payload down to safe, non-PHI scalars.

    The active correlation id (if any) is stamped on automatically, so every
    log line written through this helper is traceable back to the backend's
    request. The id is charset-restricted at the edge -- see
    `app.core.request_context` -- so it cannot carry PHI or inject into a log
    line.
    """
    out: Dict[str, Any] = {}
    # Imported lazily: request_context must stay importable without logging.
    from app.core.request_context import get_request_id

    request_id = get_request_id()
    if request_id and "request_id" not in kwargs:
        out["request_id"] = request_id

    for key, value in kwargs.items():
        if key.lower() in _FORBIDDEN_KEYS:
            continue
        if value is None or isinstance(value, (bool, int, float)):
            out[key] = value
        elif isinstance(value, str):
            # Cap length: metadata is short. Anything long is suspicious.
            out[key] = value[:120]
        else:
            out[key] = type(value).__name__
    return out
