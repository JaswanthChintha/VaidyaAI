from functools import lru_cache
from typing import List, Optional

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "vaidyaai-ocr-service"
    environment: str = "development"
    log_level: str = "INFO"

    gemini_api_key: SecretStr = Field(default=SecretStr(""))
    gemini_model: str = "gemini-3.6-flash"
    gemini_fallback_models: str = "gemini-3.5-flash,gemini-3.5-flash-lite,gemini-3.1-flash-lite"
    gemini_model_cooldown_seconds: float = 1800.0
    gemini_timeout_seconds: float = 120.0
    gemini_max_retries: int = 3
    gemini_retry_base_delay_seconds: float = 1.0
    page_retry_delay_seconds: float = 20.0
    gemini_temperature: float = 0.0
    gemini_max_output_tokens: int = 32768
    gemini_seed: Optional[int] = 20261003

    finding_context_deadline_seconds: float = 150.0
    finding_context_concurrency: int = 2

    openrouter_api_key: SecretStr = Field(default=SecretStr(""))
    openrouter_models: str = (
        "nvidia/nemotron-3.5-lightning:free,"
        "nvidia/nemotron-3-super-120b-a12b:free,"
        "google/gemma-4-31b-it:free"
    )
    openrouter_disable_reasoning: bool = True
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_timeout_seconds: float = 120.0
    openrouter_model_cooldown_seconds: float = 300.0

    max_file_size_bytes: int = 15 * 1024 * 1024
    max_page_count: int = 10
    pdf_render_dpi: int = 200
    max_image_edge_pixels: int = 2200

    low_confidence_threshold: float = 0.6

    preload_on_startup: bool = False

    ai_service_api_key: SecretStr = Field(default=SecretStr(""))
    allow_unauthenticated: bool = False
    min_service_key_length: int = 32

    cors_allow_origins: List[str] = Field(default_factory=list)

    @field_validator("allow_unauthenticated", mode="before")
    @classmethod
    def _hatch_must_be_deliberate(cls, v: object) -> object:
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
    def fallback_model_list(self) -> List[str]:
        seen = {self.gemini_model}
        out: List[str] = []
        for name in self.gemini_fallback_models.split(","):
            name = name.strip()
            if name and name not in seen:
                seen.add(name)
                out.append(name)
        return out

    @property
    def has_api_key(self) -> bool:
        return bool(self.gemini_api_key.get_secret_value().strip())

    @property
    def openrouter_model_list(self) -> List[str]:
        seen = set()
        out: List[str] = []
        for name in self.openrouter_models.split(","):
            name = name.strip()
            if name and name not in seen:
                seen.add(name)
                out.append(name)
        return out

    @property
    def has_openrouter_key(self) -> bool:
        return bool(self.openrouter_api_key.get_secret_value().strip())

    @property
    def openrouter_available(self) -> bool:
        return self.has_openrouter_key and bool(self.openrouter_model_list)

    @property
    def has_service_key(self) -> bool:
        return bool(self.ai_service_api_key.get_secret_value().strip())

    @property
    def worst_case_extraction_seconds(self) -> float:
        attempts = max(1, self.gemini_max_retries)
        base = self.gemini_retry_base_delay_seconds
        backoff = sum(base * (2 ** n) * 1.25 for n in range(attempts - 1))
        per_page = attempts * self.gemini_timeout_seconds + backoff
        per_page_with_retry = 2 * per_page + max(0.0, self.page_retry_delay_seconds)
        return per_page_with_retry * max(1, self.max_page_count)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
