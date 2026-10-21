from __future__ import annotations

import io

import pymupdf
import pytest
from PIL import Image

from app.core.errors import (
    BadRequestError,
    ErrorCode,
    PayloadTooLargeError,
    UnprocessableDocumentError,
    UnsupportedMediaTypeError,
)
from app.services.document_loader import (
    JPEG_MIME,
    PDF_MIME,
    PNG_MIME,
    load_document,
    sniff_mime_type,
)
from tests.conftest import make_synthetic_pdf, make_synthetic_png


def test_sniff_detects_pdf(synthetic_pdf):
    assert sniff_mime_type(synthetic_pdf) == PDF_MIME


def test_sniff_detects_png(synthetic_png):
    assert sniff_mime_type(synthetic_png) == PNG_MIME


def test_sniff_detects_jpeg(synthetic_jpeg):
    assert sniff_mime_type(synthetic_jpeg) == JPEG_MIME


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"ab",
        b"not a document at all, just text",
        b"GIF89a" + b"\x00" * 64,
        b"PK\x03\x04" + b"\x00" * 64,
        b"MZ\x90\x00" + b"\x00" * 64,
        b"\x7fELF" + b"\x00" * 64,
    ],
)
def test_sniff_rejects_unsupported_and_hostile_payloads(payload):
    assert sniff_mime_type(payload) not in {PDF_MIME, PNG_MIME, JPEG_MIME}


def test_extension_is_never_trusted_over_content(settings):
    png = make_synthetic_png()
    doc = load_document(png, settings, filename="report.pdf", declared_mime=PDF_MIME)
    assert doc.mime_type == PNG_MIME
    assert any("did not match" in w for w in doc.warnings)


def test_empty_file_is_rejected(settings):
    with pytest.raises(BadRequestError) as exc:
        load_document(b"", settings)
    assert exc.value.code == ErrorCode.EMPTY_FILE


def test_oversized_file_is_rejected(settings, synthetic_pdf):
    settings.max_file_size_bytes = 100
    with pytest.raises(PayloadTooLargeError) as exc:
        load_document(synthetic_pdf, settings)
    assert exc.value.code == ErrorCode.FILE_TOO_LARGE
    assert exc.value.status_code == 413


def test_unsupported_type_is_rejected(settings):
    with pytest.raises(UnsupportedMediaTypeError) as exc:
        load_document(b"GIF89a" + b"\x00" * 128, settings)
    assert exc.value.code == ErrorCode.UNSUPPORTED_FILE_TYPE
    assert exc.value.status_code == 415


def test_too_many_pages_is_rejected(settings):
    settings.max_page_count = 2
    pdf = make_synthetic_pdf(5)
    with pytest.raises(BadRequestError) as exc:
        load_document(pdf, settings)
    assert exc.value.code == ErrorCode.TOO_MANY_PAGES


def test_page_count_at_the_limit_is_accepted(settings):
    settings.max_page_count = 3
    doc = load_document(make_synthetic_pdf(3), settings)
    assert doc.page_count == 3


def test_single_page_pdf_renders_to_one_png(settings, synthetic_pdf):
    doc = load_document(synthetic_pdf, settings, filename="report.pdf")
    assert doc.mime_type == PDF_MIME
    assert doc.page_count == 1
    assert len(doc.pages) == 1
    page = doc.pages[0]
    assert page.page_number == 1
    assert page.mime_type == PNG_MIME
    assert page.image_bytes[:8] == b"\x89PNG\r\n\x1a\n"


def test_multipage_pdf_renders_each_page_in_order(settings, synthetic_pdf_2pages):
    doc = load_document(synthetic_pdf_2pages, settings)
    assert doc.page_count == 2
    assert [p.page_number for p in doc.pages] == [1, 2]
    assert doc.pages[0].image_bytes != doc.pages[1].image_bytes


def test_rendered_page_respects_the_edge_cap(settings, synthetic_pdf):
    settings.pdf_render_dpi = 400
    settings.max_image_edge_pixels = 700
    doc = load_document(synthetic_pdf, settings)
    with Image.open(io.BytesIO(doc.pages[0].image_bytes)) as img:
        assert max(img.size) <= 700


def test_rendered_page_carries_actual_content(settings, synthetic_pdf):
    doc = load_document(synthetic_pdf, settings)
    with Image.open(io.BytesIO(doc.pages[0].image_bytes)) as img:
        extrema = img.convert("L").getextrema()
    assert extrema[0] < extrema[1], "rendered page appears blank"


def test_corrupt_pdf_is_rejected_cleanly(settings):
    corrupt = b"%PDF-1.4\n" + b"\xde\xad\xbe\xef" * 500
    with pytest.raises(UnprocessableDocumentError) as exc:
        load_document(corrupt, settings)
    assert exc.value.status_code == 422
    assert exc.value.code in {
        ErrorCode.CORRUPT_FILE,
        ErrorCode.NO_RENDERABLE_PAGES,
    }


def test_recoverable_truncated_pdf_is_read_but_warned_about(settings, synthetic_pdf):
    truncated = synthetic_pdf[: len(synthetic_pdf) // 3]
    doc = load_document(truncated, settings)
    assert doc.page_count >= 1
    assert any("recovered" in w.lower() for w in doc.warnings)


def test_intact_pdf_carries_no_recovery_warning(settings, synthetic_pdf):
    doc = load_document(synthetic_pdf, settings)
    assert not any("recovered" in w.lower() for w in doc.warnings)


def test_severely_truncated_pdf_is_rejected_cleanly(settings, synthetic_pdf_2pages):
    truncated = synthetic_pdf_2pages[: len(synthetic_pdf_2pages) // 3]
    with pytest.raises((UnprocessableDocumentError, BadRequestError)) as exc:
        load_document(truncated, settings)
    assert exc.value.status_code in (400, 422)


def test_truncated_png_is_rejected_cleanly(settings, synthetic_png):
    truncated = synthetic_png[:120]
    with pytest.raises(UnprocessableDocumentError) as exc:
        load_document(truncated, settings)
    assert exc.value.status_code == 422


def test_png_header_with_garbage_body_is_rejected(settings):
    fake = b"\x89PNG\r\n\x1a\n" + b"\x00\xff" * 400
    with pytest.raises(UnprocessableDocumentError):
        load_document(fake, settings)


def test_encrypted_pdf_is_reported_as_such(settings):
    doc = pymupdf.open()
    doc.new_page(width=595, height=842)
    encrypted = doc.tobytes(
        encryption=pymupdf.PDF_ENCRYPT_AES_256,
        owner_pw="owner-pw",
        user_pw="user-pw",
    )
    doc.close()
    with pytest.raises(UnprocessableDocumentError) as exc:
        load_document(encrypted, settings)
    assert exc.value.code == ErrorCode.ENCRYPTED_PDF


def test_pdf_with_zero_pages_is_rejected(settings):
    empty = (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\n"
        b"trailer<</Root 1 0 R>>\n"
        b"%%EOF\n"
    )
    with pytest.raises(UnprocessableDocumentError) as exc:
        load_document(empty, settings)
    assert exc.value.code in {
        ErrorCode.NO_RENDERABLE_PAGES,
        ErrorCode.CORRUPT_FILE,
    }


def test_png_intake_produces_one_page(settings, synthetic_png):
    doc = load_document(synthetic_png, settings, filename="scan.png")
    assert doc.mime_type == PNG_MIME
    assert doc.page_count == 1
    assert doc.pages[0].page_number == 1


def test_jpeg_intake_is_converted_to_png(settings, synthetic_jpeg):
    doc = load_document(synthetic_jpeg, settings, filename="scan.jpg")
    assert doc.mime_type == JPEG_MIME
    assert doc.pages[0].mime_type == PNG_MIME
    assert doc.pages[0].image_bytes[:8] == b"\x89PNG\r\n\x1a\n"


def test_transparency_is_flattened_onto_white(settings):
    img = Image.new("RGBA", (200, 120), (0, 0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    doc = load_document(buf.getvalue(), settings)
    with Image.open(io.BytesIO(doc.pages[0].image_bytes)) as out:
        assert out.mode == "RGB"
        assert out.getpixel((5, 5)) == (255, 255, 255)


def test_large_image_is_downscaled(settings):
    settings.max_image_edge_pixels = 400
    img = Image.new("RGB", (1600, 900), (255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    doc = load_document(buf.getvalue(), settings)
    with Image.open(io.BytesIO(doc.pages[0].image_bytes)) as out:
        assert max(out.size) <= 400


def test_grayscale_image_is_converted_to_rgb(settings):
    img = Image.new("L", (300, 200), 128)
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    doc = load_document(buf.getvalue(), settings)
    with Image.open(io.BytesIO(doc.pages[0].image_bytes)) as out:
        assert out.mode == "RGB"


def test_source_metadata_is_recorded(settings, synthetic_pdf):
    doc = load_document(synthetic_pdf, settings, filename="my-report.pdf")
    assert doc.filename == "my-report.pdf"
    assert doc.size_bytes == len(synthetic_pdf)
