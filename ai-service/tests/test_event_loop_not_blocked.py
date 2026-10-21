from __future__ import annotations

import asyncio
import time

import httpx

import app.api.routes_ocr as routes_ocr
from app.config import Settings, get_settings
from app.main import app

SLOW_SECONDS = 1.5

PROBE_COUNT = 4
PROBE_INTERVAL = 0.3

MARGIN_SECONDS = 0.15


class _StubDocument:
    pages: list = []
    is_repaired = False
    filename = "stub.pdf"
    mime_type = "application/pdf"
    page_count = 1


class _StubExtractionService:

    def extract(self, document):
        from app.schemas.extraction import ExtractionData

        return ExtractionData(
            source={
                "filename": "stub.pdf",
                "mime_type": "application/pdf",
                "page_count": 1,
            },
            extracted_parameters=[],
            extraction_confidence=0.0,
        )


def _run_overlap_probe(monkeypatch):
    observed = {}
    started = {}

    def slow_load_document(data, settings, filename=None, declared_mime=None):
        from app.core.request_context import get_request_id

        observed["request_id"] = get_request_id()
        time.sleep(SLOW_SECONDS)
        return _StubDocument()

    monkeypatch.setattr(routes_ocr, "load_document", slow_load_document)

    test_settings = Settings(_env_file=None)
    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[routes_ocr.get_extraction_service] = (
        lambda: _StubExtractionService()
    )

    headers = {"X-Request-Id": "event-loop-probe-id"}

    async def drive():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            started["t0"] = time.perf_counter()

            async def extraction():
                files = {"file": ("r.pdf", b"%PDF-1.4 stub", "application/pdf")}
                response = await client.post(
                    "/api/v1/ocr/extract",
                    files=files,
                    headers=headers,
                    timeout=60,
                )
                assert response.status_code == 200, response.text
                return time.perf_counter() - started["t0"]

            async def probe_health():
                results = []
                for _ in range(PROBE_COUNT):
                    await asyncio.sleep(PROBE_INTERVAL)
                    response = await client.get("/api/v1/health", timeout=60)
                    results.append(
                        (response.status_code, time.perf_counter() - started["t0"])
                    )
                return results

            return await asyncio.gather(extraction(), probe_health())

    try:
        finished_at, probes = asyncio.run(drive())
    finally:
        app.dependency_overrides.pop(routes_ocr.get_extraction_service, None)
        app.dependency_overrides.pop(get_settings, None)

    return finished_at, probes, observed.get("request_id")


def test_health_is_served_while_an_extraction_is_in_flight(monkeypatch):
    finished_at, probes, _ = _run_overlap_probe(monkeypatch)

    assert all(status == 200 for status, _ in probes)

    served_during = [
        completed_at
        for _, completed_at in probes
        if completed_at < finished_at - MARGIN_SECONDS
    ]

    assert len(served_during) == PROBE_COUNT, (
        f"only {len(served_during)} of {PROBE_COUNT} /health probes completed "
        f"while a {SLOW_SECONDS}s extraction was in flight (it finished at "
        f"{finished_at:.2f}s; probes completed at "
        f"{[round(t, 2) for _, t in probes]}). The event loop is being blocked "
        "by a synchronous call in an async endpoint -- see app/api/routes_ocr.py "
        "and this module's docstring."
    )


def test_request_id_survives_the_worker_thread(monkeypatch):
    _, _, request_id = _run_overlap_probe(monkeypatch)

    assert request_id == "event-loop-probe-id", (
        "the request-id ContextVar did not reach the worker thread "
        f"(saw {request_id!r})"
    )
