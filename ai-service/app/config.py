"""Configuration for the VaidyaAI AI service (Modules 4 and 5).

All settings are read from environment variables or a local `.env` file.

SECURITY NOTE: `gemini_api_key` and `ai_service_api_key` hold secrets. Both are
typed as `SecretStr` so that they are redacted from `repr()`/logs by default.
Never log their values, never include them in error responses, and never put
them in the health payload.
"""

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

    # --- Service ---
    app_name: str = "vaidyaai-ocr-service"
    environment: str = "development"
    log_level: str = "INFO"

    # --- Gemini ---
    # The user selected `gemini-3.6-flash`. Overridable so the model can be
    # swapped without a code change.
    gemini_api_key: SecretStr = Field(default=SecretStr(""))
    gemini_model: str = "gemini-3.6-flash"
    # Models to fall back to when the primary is OUT OF QUOTA, in order.
    #
    # Google's free tier meters `generate_content` PER MODEL PER DAY (the
    # quota id is literally GenerateRequestsPerDayPerProjectPerModel-FreeTier),
    # so an exhausted model does not mean an exhausted key: a sibling model on
    # the same key still has its own untouched allowance. Without this list a
    # free-tier key stops the whole pipeline after ~20 requests even though
    # several models remain usable.
    #
    # A PLAIN STRING, split by `fallback_model_list`, NOT a `List[str]`.
    # pydantic-settings JSON-decodes complex types in the dotenv source BEFORE
    # any validator runs, so a `List[str]` field blows up on an empty or
    # comma-separated value -- the same trap that `cors_allow_origins` sets.
    gemini_fallback_models: str = "gemini-3.5-flash,gemini-3.5-flash-lite,gemini-3.1-flash-lite"
    # How long an exhausted model is skipped before being tried again. The free
    # tier's cap is DAILY, so a short cooldown just wastes a request rediscovering
    # the same 429; 30 minutes keeps a transient per-minute limit recoverable
    # within one session without re-probing a dead model on every page.
    gemini_model_cooldown_seconds: float = 1800.0
    gemini_timeout_seconds: float = 120.0
    gemini_max_retries: int = 3
    gemini_retry_base_delay_seconds: float = 1.0
    # A PAGE THE WHOLE MODEL CHAIN COULD NOT READ GETS ONE MORE TRY, after this
    # pause (2026-10-10). Test 3's page 2 was skipped as MODEL_UNAVAILABLE:
    # every model's retries ran within seconds of one another, inside one
    # provider outage, and the page -- glucose, creatinine, SGPT -- was lost.
    # See `ExtractionService._retry_failed_pages`.
    page_retry_delay_seconds: float = 20.0
    gemini_temperature: float = 0.0
    gemini_max_output_tokens: int = 32768
    # A fixed sampling seed for EXTRACTION (2026-10-03). Temperature 0 alone
    # did not make re-reading a report repeatable: a re-analysis of Test 3
    # changed HbA1c's flag between runs. The provider treats a seed as best
    # effort, so this narrows the variation rather than removing it. `None`
    # sends no seed.
    gemini_seed: Optional[int] = 20261003

    # --- Module 34: how long a page waits for finding descriptions ---
    #
    # MUST STAY BELOW the backend's `AI_SERVICE_FINDING_CONTEXT_TIMEOUT_MS`
    # (180 s). Past this deadline the request returns what is finished and
    # marks the rest `in_progress`; the unfinished work carries on and lands in
    # the process cache for the next view. Before this existed, seven findings
    # during a Gemini outage took ~5 minutes, the backend gave up at 180 s, and
    # the page showed nothing although every description was later written.
    finding_context_deadline_seconds: float = 150.0
    # How many findings are described at once. 2 shortens a long list without
    # piling onto the free tier's per-minute limit; 1 is strictly sequential.
    finding_context_concurrency: int = 2

    # --- OpenRouter: the SECONDARY PROVIDER for prose, quota-only ---
    #
    # Reached ONLY when every Gemini model in the chain above has answered 429,
    # and ONLY for the text path (`generate_text`). Module 4's extraction stays
    # on Gemini: it needs vision plus a strict response schema, and an
    # extraction that succeeds with a weaker reader puts wrong NUMBERS into a
    # medical pipeline, which is a different class of risk from a missing
    # paragraph.
    #
    # NO KEY MEANS NOTHING CHANGES. With `openrouter_api_key` empty the
    # fallback is never attempted and the service behaves exactly as it did
    # before this existed -- which is the state every pre-existing test runs in.
    openrouter_api_key: SecretStr = Field(default=SecretStr(""))
    # A PLAIN STRING, split by `openrouter_model_list`, for the same
    # pydantic-settings reason as `gemini_fallback_models` above.
    #
    # BOTH WERE PROBED with this codebase's own Module 35 and Module 27b
    # prompts before being written here, and both produced answers that parsed,
    # passed the CV gate and were approved by Module 24. A third candidate
    # (`google/gemma-4-31b-it:free`) was dropped: it answered 429 from its
    # upstream provider on every attempt.
    #
    # RE-PROBED 2026-10-09 with the chatbot's own prompt, live: the DeepSeek
    # free slug now answers 404 ("unavailable for free"), and every free model
    # left is a REASONING model that spends its budget thinking and returns
    # empty content -- unless reasoning is switched off
    # (`openrouter_disable_reasoning` below). With it off, these three answered
    # in 1-3 s; `google/gemma-4-26b-a4b-it:free` answered 429.
    openrouter_models: str = (
        "nvidia/nemotron-3.5-lightning:free,"
        "nvidia/nemotron-3-super-120b-a12b:free,"
        "google/gemma-4-31b-it:free"
    )
    #: Send `reasoning: {enabled: false}`. Measured 2026-10-09: with thinking
    #: on, a 600-token answer budget was spent entirely on reasoning and the
    #: message content came back empty; with it off, answers arrived in 1-3 s.
    openrouter_disable_reasoning: bool = True
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_timeout_seconds: float = 120.0
    # Deliberately SHORTER than the Gemini cooldown. A Gemini 429 is a daily
    # per-model cap, so re-probing soon is waste. An OpenRouter 429 is often
    # the UPSTREAM provider being briefly busy -- observed live on a candidate
    # model while the account's own allowance was untouched -- and that does
    # clear in minutes.
    openrouter_model_cooldown_seconds: float = 300.0

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

    # --- Startup ---
    # Load the ML models and the knowledge index BEFORE the port opens
    # (2026-10-06). On Render's free plan (0.1 CPU) the first analysis spent
    # ~30 s loading the models mid-request, the backend's 30 s stage timeout
    # fired, and the report came out "partial". Off by default so development
    # and the test suite start instantly; render.yaml turns it on.
    preload_on_startup: bool = False

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
    def fallback_model_list(self) -> List[str]:
        """`gemini_fallback_models` as a list, primary removed, order kept.

        Deduplicated because a repeated model would be tried twice and spend
        two requests proving the same quota is gone.
        """
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
        """`openrouter_models` as a list, deduplicated, order kept.

        Same shape as `fallback_model_list`, and deduplicated for the same
        reason -- a repeated model spends a second request proving what the
        first already established.
        """
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
        """Whether the secondary provider is configured at all.

        Whitespace-only is NOT configured. False here means the fallback is
        never attempted and the service behaves exactly as it did before the
        secondary provider existed.
        """
        return bool(self.openrouter_api_key.get_secret_value().strip())

    @property
    def openrouter_available(self) -> bool:
        """A key AND at least one model. Either alone can do nothing.

        Stated as one property so a caller cannot check half of it -- an empty
        `openrouter_models` with a key set would otherwise reach the transport
        and fail there rather than degrading quietly.
        """
        return self.has_openrouter_key and bool(self.openrouter_model_list)

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

        A page that fails is read ONE more time after `page_retry_delay_seconds`
        (2026-10-10), so each page is counted twice, plus that pause.
        """
        attempts = max(1, self.gemini_max_retries)
        base = self.gemini_retry_base_delay_seconds
        backoff = sum(base * (2 ** n) * 1.25 for n in range(attempts - 1))
        per_page = attempts * self.gemini_timeout_seconds + backoff
        per_page_with_retry = 2 * per_page + max(0.0, self.page_retry_delay_seconds)
        return per_page_with_retry * max(1, self.max_page_count)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
