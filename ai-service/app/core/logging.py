from __future__ import annotations

import logging
import sys
from typing import Any, Dict

_CONFIGURED = False

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
    for noisy in ("httpx", "httpcore", "google_genai", "google.genai", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    _CONFIGURED = True


_RESERVED_RECORD_KEYS = frozenset(
    logging.LogRecord("", 0, "", 0, "", None, None).__dict__
) | {"message", "asctime"}


class _SafeLogger(logging.Logger):

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
    previous = logging.getLoggerClass()
    logging.setLoggerClass(_SafeLogger)
    try:
        return logging.getLogger(name)
    finally:
        logging.setLoggerClass(previous)


def safe_meta(**kwargs: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
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
            out[key] = value[:120]
        else:
            out[key] = type(value).__name__
    return out
