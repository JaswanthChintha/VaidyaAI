from __future__ import annotations

import json
import threading
import time
from typing import Any, Dict, List, Optional

import httpx

from app.config import Settings
from app.core.errors import (
    ErrorCode,
    ModelError,
    ModelNotConfiguredError,
    ModelRateLimitedError,
    ModelTimeoutError,
)
from app.core.logging import get_logger, safe_meta

logger = get_logger(__name__)

_COOLDOWN: Dict[str, float] = {}
_COOLDOWN_LOCK = threading.Lock()

_ACCOUNT_KEY = "*account*"


def _in_cooldown(key: str) -> bool:
    with _COOLDOWN_LOCK:
        until = _COOLDOWN.get(key)
        if until is None:
            return False
        if time.monotonic() >= until:
            del _COOLDOWN[key]
            return False
        return True


def reset_cooldowns() -> None:
    with _COOLDOWN_LOCK:
        _COOLDOWN.clear()


def _is_account_exhausted(body: str) -> bool:
    lowered = (body or "").lower()
    if "provider returned error" in lowered or "provider_name" in lowered:
        return False
    markers = (
        "free-model-per-day",
        "free_model_daily",
        "daily request limit",
        "daily limit",
        "add credits",
        "rate-limited by your account",
    )
    return any(m in lowered for m in markers)


class OpenRouterTextClient:

    def __init__(self, settings: Settings, http_client: Optional[Any] = None) -> None:
        self._settings = settings
        self._http = http_client


    def _model_chain(self) -> List[str]:
        if _in_cooldown(_ACCOUNT_KEY):
            return []
        return [m for m in self._settings.openrouter_model_list if not _in_cooldown(m)]

    def _mark_exhausted(self, key: str, *, account: bool = False) -> None:
        with _COOLDOWN_LOCK:
            _COOLDOWN[key] = (
                time.monotonic() + self._settings.openrouter_model_cooldown_seconds
            )
        logger.warning(
            "openrouter_exhausted %s",
            safe_meta(
                provider="openrouter",
                scope="account" if account else "model",
                model=None if account else key,
                cooldown_seconds=self._settings.openrouter_model_cooldown_seconds,
            ),
        )


    def generate_text(
        self,
        prompt: str,
        *,
        system_instruction: str,
        temperature: float,
        max_output_tokens: int,
    ) -> str:
        if not self._settings.openrouter_available:
            raise ModelNotConfiguredError(
                "The secondary text provider is not configured."
            )

        chain = self._model_chain()
        if not chain:
            raise ModelRateLimitedError(
                "The secondary text provider is rate limited. Please retry "
                "shortly."
            )

        rate_limited: Optional[ModelError] = None
        for model in chain:
            try:
                return self._generate_with(model, prompt, system_instruction,
                                           temperature, max_output_tokens)
            except ModelRateLimitedError as exc:
                rate_limited = exc
                if _in_cooldown(_ACCOUNT_KEY):
                    break
                continue

        raise rate_limited or ModelError(
            "The secondary text provider request failed."
        )

    def _generate_with(
        self,
        model: str,
        prompt: str,
        system_instruction: str,
        temperature: float,
        max_output_tokens: int,
    ) -> str:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_output_tokens,
        }
        if self._settings.openrouter_disable_reasoning:
            payload["reasoning"] = {"enabled": False}
        headers = {
            "Authorization": "Bearer "
            + self._settings.openrouter_api_key.get_secret_value(),
            "Content-Type": "application/json",
        }
        url = self._settings.openrouter_base_url.rstrip("/") + "/chat/completions"
        started = time.monotonic()

        try:
            response = self._post(url, payload, headers)
        except Exception as exc:
            raise self._to_service_error(exc, model) from exc

        status = getattr(response, "status_code", None)
        body = self._body_text(response)

        if status == 429:
            account = _is_account_exhausted(body)
            self._mark_exhausted(_ACCOUNT_KEY if account else model, account=account)
            raise ModelRateLimitedError(
                "The secondary text provider is rate limited. Please retry "
                "shortly."
            )
        if status in (401, 403):
            raise ModelNotConfiguredError(
                "The secondary text provider rejected the service credentials."
            )
        if status in (500, 502, 503, 504):
            raise ModelError(
                "The secondary text provider is temporarily unavailable.",
                code=ErrorCode.MODEL_UNAVAILABLE,
                status_code=503,
            )
        if status != 200:
            raise ModelError(
                "The secondary text provider rejected the request.",
                code=ErrorCode.MODEL_REQUEST_FAILED,
                status_code=502,
            )

        text = self._extract_text(body)
        logger.info(
            "openrouter_text_generated %s",
            safe_meta(
                provider="openrouter",
                model=model,
                chars=len(text),
                duration_ms=int((time.monotonic() - started) * 1000),
                fell_back=True,
            ),
        )
        return text


    def _post(self, url: str, payload: dict, headers: dict) -> Any:
        if self._http is not None:
            return self._http.post(url, json=payload, headers=headers)
        timeout = self._settings.openrouter_timeout_seconds
        with httpx.Client(timeout=timeout) as client:
            return client.post(url, json=payload, headers=headers)

    @staticmethod
    def _body_text(response: Any) -> str:
        text = getattr(response, "text", None)
        if isinstance(text, str):
            return text
        return ""

    @staticmethod
    def _extract_text(body: str) -> str:
        try:
            payload = json.loads(body or "")
        except Exception:
            raise ModelError(
                "The secondary text provider returned an unreadable response.",
                code=ErrorCode.MODEL_REQUEST_FAILED,
                status_code=502,
            )
        choices = payload.get("choices") if isinstance(payload, dict) else None
        message = (
            choices[0].get("message")
            if isinstance(choices, list) and choices and isinstance(choices[0], dict)
            else None
        )
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise ModelError(
                "The secondary text provider returned an empty response.",
                code=ErrorCode.MODEL_RESPONSE_EMPTY,
                status_code=502,
            )
        return content


    @staticmethod
    def _to_service_error(exc: BaseException, model: str) -> ModelError:
        names = {type(exc).__name__} | {b.__name__ for b in type(exc).__mro__}
        if isinstance(exc, TimeoutError) or names & {
            "ConnectTimeout",
            "ReadTimeout",
            "WriteTimeout",
            "PoolTimeout",
            "TimeoutException",
            "TimeoutError",
        }:
            return ModelTimeoutError(
                "The secondary text provider did not respond in time."
            )
        return ModelError("The secondary text provider request failed.")


def build_openrouter_client(
    settings: Settings, http_client: Optional[Any] = None
) -> OpenRouterTextClient:
    return OpenRouterTextClient(settings, http_client)


__all__ = [
    "OpenRouterTextClient",
    "build_openrouter_client",
    "reset_cooldowns",
]
