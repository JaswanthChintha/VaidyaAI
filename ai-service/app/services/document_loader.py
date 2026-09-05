"""File intake: type sniffing, validation, and rasterisation to page images.

Responsibilities
  * detect the real file type from CONTENT (magic bytes), not the extension
  * enforce max file size and max page count
  * render PDF pages to PNG via PyMuPDF (pure-Python wheel; no Poppler)
  * normalise standalone images (EXIF orientation, downscale, RGB, PNG)

PRIVACY: nothing in this module logs image bytes or decoded text.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import List, Optional

import pymupdf  # PyMuPDF (the `fitz` alias is deprecated as of 1.28)
from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import Settings
from app.core.errors import (
    BadRequestError,
    ErrorCode,
    PayloadTooLargeError,
    UnprocessableDocumentError,
    UnsupportedMediaTypeError,
)
from app.core.logging import get_logger, safe_meta

logger = get_logger(__name__)

PDF_MIME = "application/pdf"
PNG_MIME = "image/png"
JPEG_MIME = "image/jpeg"

SUPPORTED_MIME_TYPES = {PDF_MIME, PNG_MIME, JPEG_MIME}


@dataclass
class PageImage:
    """A single page rendered to PNG bytes, ready for the vision model."""

    page_number: int
    image_bytes: bytes
    mime_type: str = PNG_MIME


@dataclass
class LoadedDocument:
    filename: Optional[str]
    mime_type: str
    size_bytes: int
    page_count: int
    pages: List[PageImage]
    warnings: List[str]


def sniff_mime_type(data: bytes) -> Optional[str]:
    """Identify the file type from magic bytes. Returns None if unrecognised.

    Extensions and client-supplied Content-Type headers are attacker- or
    mistake-controlled, so they are never trusted for this decision.
    """
    if len(data) < 4:
        return None

    # PDF: "%PDF-" must appear near the start. Some producers emit junk bytes
    # before the header, and readers tolerate it, so scan a small window.
    if data[:5] == b"%PDF-" or b"%PDF-" in data[:1024]:
        return PDF_MIME

    # PNG signature
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return PNG_MIME

    # JPEG: SOI marker, and JFIF/Exif/raw variants all start FF D8 FF
    if data[:3] == b"\xff\xd8\xff":
        return JPEG_MIME

    return None


def _validate_size(data: bytes, settings: Settings) -> None:
    if len(data) == 0:
        raise BadRequestError(
            "The uploaded file is empty.", code=ErrorCode.EMPTY_FILE
        )
    if len(data) > settings.max_file_size_bytes:
        limit_mb = settings.max_file_size_bytes / (1024 * 1024)
        raise PayloadTooLargeError(
            f"File exceeds the maximum allowed size of {limit_mb:.1f} MB."
        )


def _normalise_image(data: bytes, settings: Settings) -> bytes:
    """Decode, orient, downscale and re-encode a standalone image as PNG.

    Light preprocessing only. The vision model handles contrast and noise far
    better than a fixed threshold/denoise pipeline would, and aggressive
    binarisation destroys faint print on lab scans. What genuinely helps:
      * honouring EXIF orientation (phone photos are frequently rotated)
      * flattening transparency onto white (alpha reads as black otherwise)
      * capping resolution so payloads stay reasonable
    """
    try:
        with Image.open(io.BytesIO(data)) as img:
            img = ImageOps.exif_transpose(img)

            if img.mode in ("RGBA", "LA", "P"):
                img = img.convert("RGBA")
                background = Image.new("RGBA", img.size, (255, 255, 255, 255))
                img = Image.alpha_composite(background, img).convert("RGB")
            elif img.mode != "RGB":
                img = img.convert("RGB")

            max_edge = settings.max_image_edge_pixels
            longest = max(img.size)
            if longest > max_edge:
                scale = max_edge / float(longest)
                new_size = (
                    max(1, int(img.width * scale)),
                    max(1, int(img.height * scale)),
                )
                img = img.resize(new_size, Image.LANCZOS)

            buf = io.BytesIO()
            img.save(buf, format="PNG", optimize=True)
            return buf.getvalue()
    except UnidentifiedImageError as exc:
        raise UnprocessableDocumentError(
            "The uploaded image could not be decoded; it may be corrupt or "
            "truncated."
        ) from exc
    except (OSError, ValueError, MemoryError) as exc:
        # Pillow raises OSError for truncated files and decompression issues.
        raise UnprocessableDocumentError(
            "The uploaded image could not be processed; it may be corrupt or "
            "truncated."
        ) from exc


def _render_pdf(data: bytes, settings: Settings) -> tuple[List[PageImage], List[str]]:
    warnings: List[str] = []
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:  # PyMuPDF raises bare Exception subclasses
        raise UnprocessableDocumentError(
            "The PDF could not be opened; it may be corrupt or not a valid PDF."
        ) from exc

    try:
        if doc.needs_pass:
            raise UnprocessableDocumentError(
                "The PDF is password protected and cannot be read.",
                code=ErrorCode.ENCRYPTED_PDF,
            )

        # MuPDF silently repairs damaged/truncated PDFs and renders what it can
        # recover. That is the behaviour we want -- a slightly damaged scan
        # should still be read -- but the caller must know the input was not
        # intact, since recovered pages may be missing content.
        if getattr(doc, "is_repaired", False):
            warnings.append(
                "The PDF was damaged or truncated and was recovered "
                "automatically; some content may be missing."
            )

        total = doc.page_count
        if total == 0:
            raise UnprocessableDocumentError(
                "The PDF contains no pages.",
                code=ErrorCode.NO_RENDERABLE_PAGES,
            )
        if total > settings.max_page_count:
            raise BadRequestError(
                f"The document has {total} pages, which exceeds the maximum of "
                f"{settings.max_page_count}.",
                code=ErrorCode.TOO_MANY_PAGES,
            )

        # Cap the render DPI so a page with an enormous MediaBox cannot blow
        # up memory. PyMuPDF renders at 72dpi * zoom.
        zoom = settings.pdf_render_dpi / 72.0
        matrix = pymupdf.Matrix(zoom, zoom)

        pages: List[PageImage] = []
        for index in range(total):
            page_number = index + 1
            try:
                page = doc.load_page(index)
                pixmap = page.get_pixmap(matrix=matrix, alpha=False)
                png = pixmap.tobytes("png")
            except Exception:
                # One bad page must not sink the whole document.
                warnings.append(
                    f"Page {page_number} could not be rendered and was skipped."
                )
                logger.warning(
                    "pdf_page_render_failed %s",
                    safe_meta(page_number=page_number),
                )
                continue

            # A rendered page can still exceed the edge cap at high DPI.
            if max(pixmap.width, pixmap.height) > settings.max_image_edge_pixels:
                png = _normalise_image(png, settings)

            pages.append(PageImage(page_number=page_number, image_bytes=png))

        if not pages:
            raise UnprocessableDocumentError(
                "No pages of the PDF could be rendered.",
                code=ErrorCode.NO_RENDERABLE_PAGES,
            )

        return pages, warnings
    finally:
        doc.close()


def load_document(
    data: bytes,
    settings: Settings,
    filename: Optional[str] = None,
    declared_mime: Optional[str] = None,
) -> LoadedDocument:
    """Validate an uploaded file and rasterise it into page images.

    `declared_mime` (the client's Content-Type) is accepted for reporting but
    is NOT trusted for the type decision -- content sniffing wins.
    """
    _validate_size(data, settings)

    mime = sniff_mime_type(data)
    if mime is None or mime not in SUPPORTED_MIME_TYPES:
        raise UnsupportedMediaTypeError(
            "Unsupported file type. Upload a PDF, JPEG or PNG. The file's "
            "actual content did not match any supported format."
        )

    warnings: List[str] = []
    if declared_mime:
        declared = declared_mime.split(";")[0].strip().lower()
        if declared in SUPPORTED_MIME_TYPES and declared != mime:
            warnings.append(
                f"Declared content type '{declared}' did not match the detected "
                f"type '{mime}'; the detected type was used."
            )

    if mime == PDF_MIME:
        pages, render_warnings = _render_pdf(data, settings)
        warnings.extend(render_warnings)
    else:
        # A single image is one page. Enforce the page cap for consistency.
        if settings.max_page_count < 1:
            raise BadRequestError(
                "Page limit configuration rejects all documents.",
                code=ErrorCode.TOO_MANY_PAGES,
            )
        pages = [
            PageImage(page_number=1, image_bytes=_normalise_image(data, settings))
        ]

    logger.info(
        "document_loaded %s",
        safe_meta(mime_type=mime, size_bytes=len(data), page_count=len(pages)),
    )

    return LoadedDocument(
        filename=filename,
        mime_type=mime,
        size_bytes=len(data),
        page_count=len(pages),
        pages=pages,
        warnings=warnings,
    )
