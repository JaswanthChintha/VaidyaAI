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

router = APIRouter(
    prefix="/api/v1/ocr",
    tags=["ocr"],
    dependencies=[Depends(require_service_key)],
)

_CHUNK = 1024 * 1024


async def _read_capped(upload: UploadFile, settings: Settings) -> bytes:
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

    filename = (file.filename or "").replace("\\", "/").split("/")[-1] or None

    document = await run_in_threadpool(
        load_document,
        data,
        settings,
        filename=filename,
        declared_mime=file.content_type,
    )
    result = await run_in_threadpool(service.extract, document)
    return ExtractionResponse(success=True, data=result)
