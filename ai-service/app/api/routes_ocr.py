"""POST /api/v1/ocr/extract -- the Module 4 endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.concurrency import run_in_threadpool

from app.config import Settings, get_settings
from app.core.auth import require_service_key
from app.core.errors import BadRequestError, ErrorCode, PayloadTooLargeError
from app.schemas.extraction import ExtractionResponse
from app.services.document_loader import load_document
from app.services.extractor import ExtractionService
from app.services.gemini_client import GeminiClient

# PHI-bearing endpoint: every route on this router requires the shared
# service secret in the X-Service-Key header. See app/core/auth.py.
router = APIRouter(
    prefix="/api/v1/ocr",
    tags=["ocr"],
    dependencies=[Depends(require_service_key)],
)

_CHUNK = 1024 * 1024  # 1 MB


async def _read_capped(upload: UploadFile, settings: Settings) -> bytes:
    """Read the upload, aborting as soon as the size cap is exceeded.

    Streaming with a cap matters: reading first and checking afterwards lets a
    hostile or accidental multi-GB upload exhaust memory before validation.
    """
    limit = settings.max_file_size_bytes
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(_CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            limit_mb = limit / (1024 * 1024)
            raise PayloadTooLargeError(
                f"File exceeds the maximum allowed size of {limit_mb:.1f} MB."
            )
        chunks.append(chunk)
    return b"".join(chunks)


def get_extraction_service(
    settings: Settings = Depends(get_settings),
) -> ExtractionService:
    """Dependency seam -- tests override this to inject a mocked client."""
    return ExtractionService(settings, GeminiClient(settings))


@router.post(
    "/extract",
    response_model=ExtractionResponse,
    response_model_exclude_none=False,
    summary="Extract structured medical information from a lab report",
)
async def extract(
    file: UploadFile = File(..., description="PDF, JPEG or PNG lab report"),
    settings: Settings = Depends(get_settings),
    service: ExtractionService = Depends(get_extraction_service),
) -> ExtractionResponse:
    if file is None or not getattr(file, "filename", None):
        raise BadRequestError(
            "No file was provided in the 'file' field.", code=ErrorCode.NO_FILE
        )

    data = await _read_capped(file, settings)

    # Filename is echoed back to the caller, so strip any path component a
    # client may have sent rather than trusting it.
    filename = (file.filename or "").replace("\\", "/").split("/")[-1] or None

    # BOTH CALLS BELOW ARE SYNCHRONOUS AND SLOW, AND THIS IS AN `async def`.
    #
    # `load_document` is pymupdf (CPU-bound, per page) and `service.extract` is
    # the google-genai client, which is BLOCKING I/O -- a real network round
    # trip to Gemini that has been measured at 45s-190s for one report. Called
    # directly, they run ON the event loop, and while they run this process
    # serves nothing else: not `/health`, not the backend's readiness probe,
    # and not the Module 6/8/28-32 endpoints that need no model and answer in
    # milliseconds. That was measured, not theorised -- during one live
    # extraction `/api/v1/health` degraded from <10ms to 2.5s, then 4.7s, then
    # a 30s timeout. With one worker and this module's documented worst case,
    # a single pathological upload could make the whole service unavailable
    # for roughly an hour.
    #
    # `run_in_threadpool` hands each to a worker thread and awaits it, so the
    # loop stays free to serve every other request. The request-scoped
    # correlation id survives: `run_in_threadpool` goes through
    # `anyio.to_thread.run_sync`, which copies the caller's `contextvars`
    # context into the worker, and `app/core/request_context.py` stores the id
    # in a `ContextVar`. Verified, not assumed.
    #
    # Nothing about the extraction itself changes -- same inputs, same calls,
    # same order, same result. Only the thread they occupy changes.
    document = await run_in_threadpool(
        load_document,
        data,
        settings,
        filename=filename,
        declared_mime=file.content_type,
    )
    result = await run_in_threadpool(service.extract, document)
    return ExtractionResponse(success=True, data=result)
