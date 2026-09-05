"""Configuration for the VaidyaAI AI service (Modules 4 and 5).

All settings are read from environment variables or a local `.env` file.

SECURITY NOTE: `gemini_api_key` and `ai_service_api_key` hold secrets. Both are
typed as `SecretStr` so that they are redacted from `repr()`/logs by default.
Never log their values, never include them in error responses, and never put
them in the health payload.
"""

from functools import lru_cache
from typing import List

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Service ---
    app_name: str = "vaidyaai-ocr-service"
    environment: str = "development"
    log_level: str = "INFO"

    # --- Gemini ---
    # The user selected `gemini-3.6-flash`. Overridable so the model can be
    # swapped without a code change.
    gemini_api_key: SecretStr = Field(default=SecretStr(""))
    gemini_model: str = "gemini-3.6-flash"
    gemini_timeout_seconds: float = 120.0
    gemini_max_retries: int = 3
    gemini_retry_base_delay_seconds: float = 1.0
    gemini_temperature: float = 0.0
    gemini_max_output_tokens: int = 32768

    # --- File intake limits ---
    max_file_size_bytes: int = 15 * 1024 * 1024  # 15 MB
    max_page_count: int = 10
    # DPI used when rasterising PDF pages before sending them to the model.
    pdf_render_dpi: int = 200
    # Hard cap on the longest edge of any image sent to the model, in pixels.
    # Keeps request payloads sane for large scans.
    max_image_edge_pixels: int = 2200

    # --- Confidence ---
    # Extraction confidence at or below this value raises a warning.
    low_confidence_threshold: float = 0.6

    # --- Service-to-service authentication -------------------------------
    # The ONLY legitimate caller of this service is the Node backend. The
    # shared secret arrives in the `X-Service-Key` header.
    #
    # FAIL CLOSED: an unset key does NOT mean "open". The service refuses to
    # start unless either `AI_SERVICE_API_KEY` is set, or the deliberate local
    # development escape hatch `ALLOW_UNAUTHENTICATED=true` is set (which logs
    # a loud warning on every startup). See `app/core/auth.py`.
    ai_service_api_key: SecretStr = Field(default=SecretStr(""))
    allow_unauthenticated: bool = False
    # Minimum length for the shared secret. Machine-generated material; a short
    # value is a configuration mistake, not a choice.
    min_service_key_length: int = 32

    # --- CORS ---
    # The backend is a SERVER-SIDE caller; server-to-server requests are not
    # subject to the browser same-origin policy, so CORS is irrelevant to it and
    # defaults to allowing NO browser origin. Only widen this if a browser must
    # call the service directly -- which it must not, since it would then hold
    # the service key.
    cors_allow_origins: List[str] = Field(default_factory=list)

    @field_validator("allow_unauthenticated", mode="before")
    @classmethod
    def _hatch_must_be_deliberate(cls, v: object) -> object:
        """Only an explicit truthy value opens the service.

        `ALLOW_UNAUTHENTICATED=` (exported but blank) is a very common shell
        accident. Without this it raised an opaque pydantic parse error instead
        of the clear "REFUSING TO START" refusal -- still closed, but for the
        wrong reason and with an unhelpful message. Blank means NOT SET.
        """
        if isinstance(v, str) and not v.strip():
            return False
        return v

    @field_validator("cors_allow_origins", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @property
    def has_api_key(self) -> bool:
        return bool(self.gemini_api_key.get_secret_value().strip())

    @property
    def has_service_key(self) -> bool:
        """Whether a usable service-to-service shared secret is configured.

        Whitespace-only is NOT usable -- it must never be treated as "set".
        """
        return bool(self.ai_service_api_key.get_secret_value().strip())

    @property
    def worst_case_extraction_seconds(self) -> float:
        """Upper bound on how long POST /api/v1/ocr/extract can take.

        Every Gemini call is bounded by `gemini_timeout_seconds`, is attempted
        at most `gemini_max_retries` times, and is made once per page. Backoff
        between attempts is `base * 2**(n-1)` plus up to 25% jitter.

        The backend MUST set its HTTP client timeout above this value, or above
        whatever lower value it configures here.
        """
        attempts = max(1, self.gemini_max_retries)
        base = self.gemini_retry_base_delay_seconds
        backoff = sum(base * (2 ** n) * 1.25 for n in range(attempts - 1))
        per_page = attempts * self.gemini_timeout_seconds + backoff
        return per_page * max(1, self.max_page_count)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
