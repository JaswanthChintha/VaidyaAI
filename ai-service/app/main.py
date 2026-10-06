"""VaidyaAI AI service -- Modules 4 through 26 of the analysis pipeline.

A standalone FastAPI service. Each stage feeds the next:

* Module 4  OCR/Extraction   -- transcribes a report (PDF/JPEG/PNG) with a
                                Gemini vision model into structured parameters.
                                Does NOT normalise test names.
* Module 5  Feature Eng.     -- maps those parameters (plus optional Module 2
                                profile context) onto canonical, unit-normalised
                                features with full provenance.
* Module 6  Validation       -- decides which values are believable. Separates
                                valid / questionable / rejected.
* Module 7  Repository       -- the single access point for validated features;
                                holds snapshots over time for Modules 28-30.
* Module 8  Clinical Rules   -- deterministic, threshold-based decisions.
* Module 14 Decision Object  -- the shared ClinicalDecision every component emits.
* Module 9/13 ML Registry    -- plugin-style condition-specific predictors.
* Module 10 Diabetes Model   -- Random Forest over real Kaggle data.
* Module 11 Heart Model      -- Random Forest over the real Cardiovascular set.
* Module 12 Kidney Model     -- Random Forest over the official UCI CKD set,
                                with the spec's information-sufficiency SKIP:
                                it refuses to predict rather than guess.
* Module 15 Decision Engine  -- collects decisions, groups by (condition, source).
* Module 16 Fusion Engine    -- merges rule + ML decisions for one condition:
                                highest risk, strongest available confidence,
                                unioned evidence, de-duplicated recommendations
                                and sources. This is the hybrid AI layer.

* Module 17-20 Reporting     -- the clinical report, overall status (incl. the
                                spec's unwritten 4th case: NOTHING assessed is
                                not "Healthy"), risk prioritisation, evidence.
* Module 21/22 RAG + KB      -- a curated, import-time-safety-scanned corpus,
                                chunked and indexed; retrieval is driven by the
                                patient's findings and returns NOTHING rather
                                than a poor match.
* Module 24 Safety Validator -- the gate between an LLM and a patient. Fails
                                CLOSED: unanalysable input is rejected, never
                                approved. See `app/safety/`.
* Module 23/25/26 Explanation-- patient-friendly prose, terminology, and
                                educational guidance. Every generation goes
                                through Module 24; Module 26 serves reviewed
                                catalogue text and calls no model at all.

* Module 28 Trends        -- classifies each feature's trajectory across a
                                patient's reports as improving/worsening/stable,
                                against a per-feature declared polarity. Fewer
                                than two usable readings is INSUFFICIENT_DATA,
                                never "stable". Deterministic; calls no model.

* Module 31 Population    -- how a value compares with an age- and sex-matched
                                group, from survey-weighted NHANES tables built
                                from real published microdata. Reports a BAND
                                between published cut-points, never an
                                interpolated percentile, and refuses rather than
                                substituting an unmatched cohort.

* Module 29 Comparison    -- baseline vs latest: improved / worsened /
                                unchanged / newly abnormal. Reuses Module 28's
                                polarity and stability tables rather than
                                carrying a second copy that could disagree.
                                "Newly abnormal" needs the abnormality of BOTH
                                reports to be KNOWN; otherwise it is explicitly
                                not determinable, never "unchanged".

* Module 30 Progress      -- a 0-100 Health Progress Score over Module 29's
                                finished categories. It recomputes nothing:
                                no polarity lookup, no stability threshold, no
                                arithmetic on a patient value beyond a weighted
                                mean of table lookups. Fewer than three
                                contributing parameters yields NO score rather
                                than a confident-looking number.

* Module 32 Doctor Summary-- the clinician-facing structured document. It
                                ASSEMBLES already-validated structures and
                                generates no prose: it imports no model client
                                and has no free-text entry point, so the safety
                                property Module 26 established holds on the
                                higher-stakes clinical surface too.

The service still deliberately does NOT serve a dashboard (27 lives in the Node
backend, which holds the durable report) or touch a database. The Module 7 repository is in-memory and
process-local; `backend/` holds the durable copy.

Every /api/v1 route except health requires the `X-Service-Key` header. The
service refuses to start if no key is configured -- see app/core/auth.py.
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import (
    routes_features,
    routes_health,
    routes_ml,
    routes_ocr,
    routes_decisions,
    routes_report,
    routes_knowledge,
    routes_safety,
    routes_explain,
    routes_repository,
    routes_rules,
    routes_validation,
    routes_timeline,
    routes_population,
    routes_comparison,
    routes_progress,
    routes_doctor_summary,
)
from app.config import get_settings
from app.core.auth import enforce_service_auth_configuration
from app.core.errors import ErrorCode, ServiceError, error_envelope
from app.core.logging import configure_logging, get_logger, safe_meta
from app.core.request_context import (
    REQUEST_ID_HEADER,
    get_request_id,
    reset_request_id,
    resolve_request_id,
    set_request_id,
)

settings = get_settings()
configure_logging(settings.log_level)
logger = get_logger(__name__)

# FAIL CLOSED, at import time, so `uvicorn app.main:app` refuses to start
# rather than serving PHI to anyone who can reach the port. See app/core/auth.py.
enforce_service_auth_configuration(settings)

def _preload() -> None:
    """Load the ML models and the knowledge index now, not on first use.

    Each is loaded lazily and cached, so this only moves the cost from the
    first patient's analysis to service startup -- where Render is still
    showing its "waking up" page and nobody is waiting on a 30 s stage timeout.
    A failure here is logged and NOT raised: the same failure would surface,
    with its proper reason, on the first request anyway.
    """
    started = time.monotonic()
    try:
        from app.ml.registry import default_registry
        from app.rag.retriever import get_index

        models = {p.name: p.is_available() for p in default_registry()}
        chunks = len(get_index().chunks)
        logger.info(
            "preload_complete %s",
            safe_meta(models=models, knowledge_chunks=chunks,
                      seconds=round(time.monotonic() - started, 1)),
        )
    except Exception as exc:  # noqa: BLE001 - startup must not die on this
        logger.error("preload_failed %s", safe_meta(error_type=type(exc).__name__))


@asynccontextmanager
async def _lifespan(_: FastAPI):
    # Read at startup, not import, so a test can switch it.
    if get_settings().preload_on_startup:
        _preload()
    yield


app = FastAPI(
    lifespan=_lifespan,
    title="VaidyaAI AI Service",
    description=(
        "Modules 4-26 of VaidyaAI. Converts an uploaded laboratory report "
        "into validated canonical features, then applies deterministic clinical "
        "rules and condition-specific ML predictors, then FUSES the two into "
        "hybrid clinical decisions, then explains them in grounded, "
        "safety-validated language. AI-assisted health "
        "education and decision support -- NOT a diagnostic system."
    ),
    version="1.0.0",
)


@app.middleware("http")
async def _correlation_id_middleware(request: Request, call_next):
    """Bind a correlation id for the request and echo it on the response.

    The backend sends an opaque report id in `X-Request-Id` so one pipeline run
    (Module 4 then Module 5) can be traced across both services. A missing or
    unusable value is replaced by a generated id -- see
    `app.core.request_context` for why the value is charset-restricted.
    """
    request_id = resolve_request_id(request.headers.get(REQUEST_ID_HEADER))
    token = set_request_id(request_id)
    try:
        response = await call_next(request)
    finally:
        reset_request_id(token)
    response.headers[REQUEST_ID_HEADER] = request_id
    return response


# CORS is irrelevant to the server-side Node backend (no browser, no origin),
# so `CORS_ALLOW_ORIGINS` defaults to empty -- no browser origin is allowed.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(routes_health.router)
app.include_router(routes_ocr.router)
app.include_router(routes_features.router)
app.include_router(routes_validation.router)
app.include_router(routes_rules.router)
app.include_router(routes_ml.router)
app.include_router(routes_decisions.router)
app.include_router(routes_report.router)
app.include_router(routes_safety.router)
app.include_router(routes_knowledge.router)
app.include_router(routes_repository.router)
app.include_router(routes_explain.router)
app.include_router(routes_timeline.router)
app.include_router(routes_population.router)
app.include_router(routes_comparison.router)
app.include_router(routes_progress.router)
app.include_router(routes_doctor_summary.router)


# --------------------------------------------------------------------------
# Exception handlers -- every failure leaves as the same JSON envelope.
# --------------------------------------------------------------------------


@app.exception_handler(ServiceError)
async def _service_error_handler(_: Request, exc: ServiceError) -> JSONResponse:
    logger.warning("service_error %s", safe_meta(code=exc.code, status=exc.status_code))
    return JSONResponse(status_code=exc.status_code, content=exc.to_dict())


@app.exception_handler(RequestValidationError)
async def _validation_handler(
    _: Request, exc: RequestValidationError
) -> JSONResponse:
    # Missing/!multipart uploads land here. Report the shape problem without
    # echoing the submitted body, which could contain report content.
    missing_file = any(
        "file" in [str(p) for p in err.get("loc", ())] for err in exc.errors()
    )
    code = ErrorCode.NO_FILE if missing_file else "INVALID_REQUEST"
    message = (
        "No file was provided in the 'file' field of a multipart/form-data "
        "request."
        if missing_file
        else "The request was not valid."
    )
    return JSONResponse(status_code=422, content=error_envelope(code, message))


@app.exception_handler(StarletteHTTPException)
async def _http_error_handler(
    _: Request, exc: StarletteHTTPException
) -> JSONResponse:
    code = {
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        413: ErrorCode.FILE_TOO_LARGE,
        415: ErrorCode.UNSUPPORTED_FILE_TYPE,
    }.get(exc.status_code, "HTTP_ERROR")
    detail = exc.detail if isinstance(exc.detail, str) else "Request failed."
    return JSONResponse(
        status_code=exc.status_code, content=error_envelope(code, detail)
    )


@app.exception_handler(Exception)
async def _unhandled_handler(_: Request, exc: Exception) -> JSONResponse:
    # Log the TYPE only. An exception's message may embed document content,
    # which must never reach the logs (medical data).
    logger.error("unhandled_error %s", safe_meta(error_type=type(exc).__name__))
    return JSONResponse(
        status_code=500,
        content=error_envelope(
            ErrorCode.INTERNAL_ERROR,
            "An unexpected error occurred while processing the document.",
        ),
    )


@app.get("/", include_in_schema=False)
async def root() -> dict:
    return {
        "success": True,
        "data": {
            "service": settings.app_name,
            "modules": "4-26 (extraction, features, validation, repository, "
            "rules, ML prediction, fusion, reporting, RAG, safety, explanation)",
            "health": "/api/v1/health",
            "extract": "POST /api/v1/ocr/extract",
            "engineer_features": "POST /api/v1/features/engineer",
            "feature_catalog": "GET /api/v1/features/catalog",
            "validate_features": "POST /api/v1/features/validate",
            "validation_rules": "GET /api/v1/features/validation-rules",
            "load_repository": "POST /api/v1/repository/load",
            "evaluate_rules": "POST /api/v1/rules/evaluate",
            "clinical_rules": "GET /api/v1/rules/clinical-rules",
            "predict": "POST /api/v1/ml/predict",
            "predictors": "GET /api/v1/ml/predictors",
            "fuse_decisions": "POST /api/v1/decisions/fuse",
            "fusion_policy": "GET /api/v1/decisions/policy",
            "docs": "/docs",
        },
    }
