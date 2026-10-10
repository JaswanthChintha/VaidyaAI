"""Pages are read at the same time, and assembled in page order (2026-10-03).

Before: one model round trip after another -- Test 3's two pages took ~17 s
and ~19 s in sequence. The calls are independent; only the assembly depends
on order, and that must not change: the first page's lab name, date, sex and
age still win, and a later page that disagrees is still warned about.
"""

from __future__ import annotations

import threading
import time

from app.config import Settings
from app.core.errors import ErrorCode, ModelError
from app.services.document_loader import LoadedDocument, PageImage
from app.services import extractor as extractor_module
from app.services.extractor import ExtractionService


def _document(pages: int) -> LoadedDocument:
    return LoadedDocument(
        filename="r.pdf",
        mime_type="application/pdf",
        size_bytes=1,
        page_count=pages,
        pages=[PageImage(page_number=n, image_bytes=b"x" * n) for n in range(1, pages + 1)],
        warnings=[],
    )


def _payload(page: int, **extra):
    return {
        "raw_text": f"page {page} text",
        "parameters": [{"test_name": f"TEST {page}", "value_raw": str(page)}],
        **extra,
    }


class _SlowClient:
    """Page 1 is the SLOWEST, so a sequential reader would finish it first and
    a concurrent one finishes it last -- the order of the output is then the
    assembler's doing, not the timing's."""

    def __init__(self, delays, payloads=None, fail_pages=()):
        self.delays = delays
        self.payloads = payloads or {}
        self.fail_pages = set(fail_pages)
        self.active = 0
        self.peak = 0
        self.lock = threading.Lock()

    def extract_page(self, image_bytes, mime_type, prompt):
        page = len(image_bytes)
        with self.lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
        try:
            time.sleep(self.delays[page])
            if page in self.fail_pages:
                raise ModelError("down", code=ErrorCode.MODEL_UNAVAILABLE, status_code=503)
            return self.payloads.get(page) or _payload(page)
        finally:
            with self.lock:
                self.active -= 1


def _service(client, **overrides):
    # No real pause before the one page retry (2026-10-10): what is under test
    # here is concurrency and order, not the wait.
    overrides.setdefault("page_retry_delay_seconds", 0)
    return ExtractionService(Settings(_env_file=None, **overrides), client)


def test_pages_are_read_at_the_same_time():
    client = _SlowClient({1: 0.4, 2: 0.4, 3: 0.4})
    started = time.perf_counter()
    _service(client).extract(_document(3))
    elapsed = time.perf_counter() - started
    assert client.peak == 3
    # Three 0.4 s pages in sequence would take 1.2 s.
    assert elapsed < 1.0


def test_no_more_than_the_limit_at_once():
    pages = extractor_module.MAX_CONCURRENT_PAGES + 2
    client = _SlowClient({n: 0.05 for n in range(1, pages + 1)})
    _service(client).extract(_document(pages))
    assert client.peak == extractor_module.MAX_CONCURRENT_PAGES


def test_results_are_assembled_in_page_order_whatever_finishes_first():
    client = _SlowClient({1: 0.3, 2: 0.0, 3: 0.1})
    data = _service(client).extract(_document(3))
    assert [p.test_name for p in data.extracted_parameters] == ["TEST 1", "TEST 2", "TEST 3"]
    assert [p.page_number for p in data.extracted_parameters] == [1, 2, 3]
    assert data.raw_text.startswith("page 1 text")


def test_the_first_page_still_wins_document_metadata():
    client = _SlowClient(
        {1: 0.3, 2: 0.0},
        payloads={
            1: _payload(1, lab_name="First Lab", patient_sex="Female"),
            2: _payload(2, lab_name="Second Lab", patient_sex="Male"),
        },
    )
    data = _service(client).extract(_document(2))
    assert data.report_metadata.lab_name == "First Lab"
    assert data.report_metadata.patient_sex == "Female"
    assert any("Multiple laboratory names" in w for w in data.warnings)
    assert any("Different patient sexes" in w for w in data.warnings)


def test_one_failed_page_degrades_the_result_instead_of_failing_it():
    client = _SlowClient({1: 0.0, 2: 0.0, 3: 0.0}, fail_pages={2})
    data = _service(client).extract(_document(3))
    assert [p.page_number for p in data.extracted_parameters] == [1, 3]
    assert any(w.startswith("Page 2 could not be processed") for w in data.warnings)


def test_a_single_page_is_read_without_a_thread():
    seen = []

    class _Client:
        def extract_page(self, image_bytes, mime_type, prompt):
            seen.append(threading.current_thread() is threading.main_thread())
            return _payload(1)

    _service(_Client()).extract(_document(1))
    assert seen == [True]


def test_the_seed_is_sent_with_every_page():
    from types import SimpleNamespace

    from app.services.gemini_client import GeminiClient

    configs = []

    class _Models:
        def generate_content(self, model, contents, config):
            configs.append(config)
            candidate = SimpleNamespace(finish_reason=SimpleNamespace(name="STOP"), content=None)
            return SimpleNamespace(candidates=[candidate], text='{"raw_text": "", "parameters": []}')

    settings = Settings(_env_file=None, gemini_api_key="x")
    client = GeminiClient(settings, client=SimpleNamespace(models=_Models()))
    client.extract_page(b"img", "image/png", "prompt")
    assert configs[0].seed == settings.gemini_seed is not None
    assert configs[0].temperature == 0.0
