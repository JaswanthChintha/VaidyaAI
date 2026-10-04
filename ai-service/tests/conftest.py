"""Shared fixtures.

Two hard rules for this suite:

1. It MUST pass with no GEMINI_API_KEY and no network access. The autouse
   `_isolate_env` fixture strips any real key from the environment so a
   developer's own key can never make a test pass that would otherwise fail,
   and so no test can accidentally reach the network. The opt-in live test
   (tests/test_live_gemini.py) restores the key deliberately.

2. NO REAL MEDICAL DATA. The lab report fixtures below are synthesised here
   with PyMuPDF from invented values for a fictional laboratory.

3. AUTH. The service FAILS CLOSED -- importing `app.main` with no
   `AI_SERVICE_API_KEY` and no escape hatch raises. The suite therefore sets
   `ALLOW_UNAUTHENTICATED=true` before any app module is imported, so the
   pre-existing tests exercise the endpoints without a key. Tests that verify
   authentication build their own clients with an explicit key (see the
   `authed_client_factory` fixture) and `tests/test_auth.py` asserts the
   fail-closed startup behaviour in a real subprocess.
"""

from __future__ import annotations

import io
import os
import re
from typing import Any, Dict, List, Optional

# MUST run before any `app.*` import: `app.main` enforces the auth
# configuration at import time and would otherwise refuse to load.
os.environ.setdefault("ALLOW_UNAUTHENTICATED", "true")
os.environ.pop("AI_SERVICE_API_KEY", None)

# AND THE .env FILE IS NOT READ (2026-10-03). Popping the variables above kept a
# real key out of the ENVIRONMENT, but `Settings` reads `ai-service/.env`
# directly, so any test building settings the ordinary way picked the real
# `AI_SERVICE_API_KEY` up from the file and got 401 instead of 200 -- about
# thirty failures, and for weeks the suite was run with `.env` moved aside by
# hand (MEMORY.md section 0, item 7). Turned off here, once, before any app
# module can construct or cache a `Settings`.
from app import config as _config  # noqa: E402

_config.Settings.model_config["env_file"] = None
_config.get_settings.cache_clear()

import pymupdf
import pytest
from fastapi.testclient import TestClient

# --------------------------------------------------------------------------
# Environment isolation
# --------------------------------------------------------------------------

_LIVE_KEY_ENV = "_VAIDYAAI_REAL_GEMINI_KEY"


@pytest.fixture(autouse=True, scope="session")
def _isolate_env() -> Any:
    """Remove real credentials and settings overrides for the whole session."""
    saved: Dict[str, Optional[str]] = {}
    for name in (
        "GEMINI_API_KEY",
        "GEMINI_MODEL",
        "MAX_FILE_SIZE_BYTES",
        "MAX_PAGE_COUNT",
        "LOW_CONFIDENCE_THRESHOLD",
        "PDF_RENDER_DPI",
        "MAX_IMAGE_EDGE_PIXELS",
        "AI_SERVICE_API_KEY",
        "CORS_ALLOW_ORIGINS",
    ):
        saved[name] = os.environ.pop(name, None)

    # See rule 3 in the module docstring.
    os.environ["ALLOW_UNAUTHENTICATED"] = "true"

    # Stash the real key so only the explicitly opt-in live test can use it.
    if saved.get("GEMINI_API_KEY"):
        os.environ[_LIVE_KEY_ENV] = saved["GEMINI_API_KEY"]  # type: ignore[index]

    yield

    for name, value in saved.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value
    os.environ.pop(_LIVE_KEY_ENV, None)


@pytest.fixture()
def settings(_isolate_env: Any):
    from app.config import Settings

    # Constructed directly (not via the cached get_settings) so each test gets
    # a clean instance. `_env_file=None` keeps a developer's .env out of tests.
    return Settings(_env_file=None)


# --------------------------------------------------------------------------
# Synthetic lab report fixtures -- generated, never real patient data
# --------------------------------------------------------------------------

SYNTHETIC_ROWS: List[tuple] = [
    ("HbA1c", "6.8", "%", "4.0 - 5.6", "H"),
    ("Fasting Blood Glucose", "112", "mg/dL", "70 - 99", "H"),
    ("Haemoglobin", "14.2", "g/dL", "13.0 - 17.0", ""),
    ("Creatinine", "1.0", "mg/dL", "0.7 - 1.3", ""),
    ("Total Cholesterol", "190", "mg/dL", "< 200", ""),
    ("Vitamin D (25-OH)", "35", "ng/mL", "30 - 100", ""),
    ("Urine Ketones", "Negative", "", "Negative", ""),
]


def _draw_report_page(page: "pymupdf.Page", page_number: int, total: int) -> None:
    """Render a simple, realistic-looking lab table onto a page."""
    text_y = 60.0

    def line(text: str, size: float = 10.0, bold: bool = False, dy: float = 16.0):
        nonlocal text_y
        page.insert_text(
            (50, text_y),
            text,
            fontsize=size,
            fontname="hebo" if bold else "helv",
        )
        text_y += dy

    if page_number == 1:
        line("NORTHFIELD DIAGNOSTIC LABORATORY", size=14, bold=True, dy=22)
        line("123 Example Road, Springfield", size=9, dy=20)
        line("Patient Name: Jordan Sample", size=10)
        line("Patient ID: SYN-0001    Age: 45 / M", size=10)
        line("Report Date: 12/03/2024", size=10, dy=26)
        line("BIOCHEMISTRY REPORT", size=12, bold=True, dy=24)
    else:
        line("NORTHFIELD DIAGNOSTIC LABORATORY", size=12, bold=True, dy=20)
        line(f"Continued - page {page_number} of {total}", size=9, dy=24)

    # Table header
    cols = [50, 230, 310, 380, 500]
    headers = ["TEST", "RESULT", "UNIT", "FLAG", "REFERENCE RANGE"]
    for x, head in zip(cols, headers):
        page.insert_text((x, text_y), head, fontsize=9, fontname="hebo")
    text_y += 6
    page.draw_line(pymupdf.Point(50, text_y), pymupdf.Point(560, text_y))
    text_y += 16

    for name, value, unit, ref, flag in SYNTHETIC_ROWS:
        for x, cell in zip(cols, [name, value, unit, flag, ref]):
            page.insert_text((x, text_y), cell, fontsize=9)
        text_y += 18

    text_y += 16
    page.insert_text(
        (50, text_y),
        "This is a synthetic report generated for automated testing.",
        fontsize=8,
    )


def make_synthetic_pdf(page_count: int = 1) -> bytes:
    """Build a synthetic lab report PDF in memory."""
    doc = pymupdf.open()
    try:
        for index in range(page_count):
            page = doc.new_page(width=595, height=842)  # A4
            _draw_report_page(page, index + 1, page_count)
        return doc.tobytes()
    finally:
        doc.close()


def make_synthetic_png(width: int = 900, height: int = 1200) -> bytes:
    """Build a synthetic lab report as a PNG image."""
    doc = pymupdf.open()
    try:
        page = doc.new_page(width=595, height=842)
        _draw_report_page(page, 1, 1)
        zoom = width / 595.0
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
        return pixmap.tobytes("png")
    finally:
        doc.close()


def make_synthetic_jpeg() -> bytes:
    from PIL import Image

    png = make_synthetic_png()
    with Image.open(io.BytesIO(png)) as img:
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=88)
        return buf.getvalue()


@pytest.fixture()
def synthetic_pdf() -> bytes:
    return make_synthetic_pdf(1)


@pytest.fixture()
def synthetic_pdf_2pages() -> bytes:
    return make_synthetic_pdf(2)


@pytest.fixture()
def synthetic_png() -> bytes:
    return make_synthetic_png()


@pytest.fixture()
def synthetic_jpeg() -> bytes:
    return make_synthetic_jpeg()


# --------------------------------------------------------------------------
# Gemini test doubles
# --------------------------------------------------------------------------

WELL_FORMED_PAGE_PAYLOAD: Dict[str, Any] = {
    "raw_text": "NORTHFIELD DIAGNOSTIC LABORATORY\nHbA1c 6.8 % H 4.0 - 5.6\n"
    "Urine Ketones Negative Negative",
    "parameters": [
        {
            "test_name": "HbA1c",
            "value_raw": "6.8",
            "value_numeric": 6.8,
            "unit": "%",
            "reference_range_raw": "4.0 - 5.6",
            "reference_low": 4.0,
            "reference_high": 5.6,
            "flag": "high",
            "confidence": 0.94,
        },
        {
            "test_name": "Urine Ketones",
            "value_raw": "Negative",
            "value_numeric": None,
            "unit": None,
            "reference_range_raw": "Negative",
            "reference_low": None,
            "reference_high": None,
            "flag": None,
            "confidence": 0.9,
        },
    ],
    "lab_name": "Northfield Diagnostic Laboratory",
    "report_date": "12/03/2024",
    "patient_name_present": True,
    "page_confidence": 0.92,
    "warnings": [],
}


class FakeGeminiClient:
    """Stands in for GeminiClient. Records calls; never touches the network."""

    def __init__(
        self,
        payloads: Optional[List[Any]] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._payloads = payloads
        self._payload = payload if payload is not None else WELL_FORMED_PAGE_PAYLOAD
        self.calls: List[Dict[str, Any]] = []

    def extract_page(
        self, image_bytes: bytes, mime_type: str, prompt: str
    ) -> Dict[str, Any]:
        self.calls.append(
            {
                "size": len(image_bytes),
                "mime_type": mime_type,
                "prompt": prompt,
            }
        )
        if self._payloads is not None:
            # BY PAGE NUMBER, NOT CALL ORDER (2026-10-03). Pages are now read
            # concurrently, so page 2's call can arrive before page 1's;
            # indexing by arrival would hand pages each other's payloads at
            # random. The prompt states the page ("This is page 2 of 3"); a
            # single-page prompt does not, and is page 1. A prompt that names
            # no page at all falls back to arrival order, as before.
            match = re.search(r"This is page (\d+) of", prompt)
            if match:
                position = int(match.group(1)) - 1
            elif "This document has a single page" in prompt:
                position = 0
            else:
                position = len(self.calls) - 1
            index = min(position, len(self._payloads) - 1)
            item = self._payloads[index]
            if isinstance(item, Exception):
                raise item
            return item
        return dict(self._payload)


@pytest.fixture()
def client_factory(_isolate_env: Any):
    """Build a TestClient whose extraction service uses a fake Gemini client."""
    from app.api.routes_ocr import get_extraction_service
    from app.config import Settings, get_settings
    from app.main import app
    from app.services.extractor import ExtractionService

    created: List[TestClient] = []

    def _factory(
        fake: Optional[FakeGeminiClient] = None,
        **settings_overrides: Any,
    ) -> TestClient:
        fake = fake or FakeGeminiClient()
        test_settings = Settings(_env_file=None, **settings_overrides)

        app.dependency_overrides[get_settings] = lambda: test_settings
        app.dependency_overrides[get_extraction_service] = (
            lambda: ExtractionService(test_settings, fake)  # type: ignore[arg-type]
        )
        tc = TestClient(app, raise_server_exceptions=False)
        created.append(tc)
        return tc

    yield _factory

    from app.main import app as _app

    _app.dependency_overrides.clear()
    for tc in created:
        tc.close()


@pytest.fixture()
def client(client_factory: Any) -> TestClient:
    return client_factory()


# --------------------------------------------------------------------------
# Authenticated clients -- for the tests that exercise auth itself
# --------------------------------------------------------------------------

#: 32+ chars, so it satisfies `min_service_key_length`. Not a real credential.
TEST_SERVICE_KEY = "test-service-key-0123456789abcdefghij"


@pytest.fixture()
def authed_client_factory(client_factory: Any) -> Any:
    """A client whose settings REQUIRE the service key (no escape hatch)."""

    def _factory(fake: Optional[FakeGeminiClient] = None, **overrides: Any):
        overrides.setdefault("ai_service_api_key", TEST_SERVICE_KEY)
        overrides.setdefault("allow_unauthenticated", False)
        return client_factory(fake, **overrides)

    return _factory


@pytest.fixture()
def authed_client(authed_client_factory: Any) -> TestClient:
    return authed_client_factory()
