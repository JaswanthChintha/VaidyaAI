from __future__ import annotations

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import (
    routes_chat,
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

enforce_service_auth_configuration(settings)

def _preload() -> None:
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
    except Exception as exc:
        logger.error("preload_failed %s", safe_meta(error_type=type(exc).__name__))


@asynccontextmanager
async def _lifespan(_: FastAPI):
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
    request_id = resolve_request_id(request.headers.get(REQUEST_ID_HEADER))
    token = set_request_id(request_id)
    try:
        response = await call_next(request)
    finally:
        reset_request_id(token)
    response.headers[REQUEST_ID_HEADER] = request_id
    return response


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
app.include_router(routes_chat.router)
app.include_router(routes_timeline.router)
app.include_router(routes_population.router)
app.include_router(routes_comparison.router)
app.include_router(routes_progress.router)
app.include_router(routes_doctor_summary.router)


@app.exception_handler(ServiceError)
async def _service_error_handler(_: Request, exc: ServiceError) -> JSONResponse:
    logger.warning("service_error %s", safe_meta(code=exc.code, status=exc.status_code))
    return JSONResponse(status_code=exc.status_code, content=exc.to_dict())


@app.exception_handler(RequestValidationError)
async def _validation_handler(
    _: Request, exc: RequestValidationError
) -> JSONResponse:
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
