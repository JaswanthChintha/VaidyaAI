"""The event loop must stay free while a slow extraction runs.

WHY THIS FILE EXISTS, AND WHY IT LOOKS UNLIKE EVERY OTHER TEST HERE.

Module 4's two heavy calls are synchronous: `load_document` is pymupdf
(CPU-bound, per page) and `ExtractionService.extract` is the google-genai
client, which is BLOCKING network I/O measured at 45s-190s for one real
report. Both are invoked from an `async def` endpoint. Called directly they
run ON the event loop, and for as long as they run the process serves nothing
else -- not `/health`, not the Node backend's readiness probe, and not the
Module 6/8/28-32 endpoints that touch no model and answer in milliseconds.

That was measured on a live run, not theorised: during one extraction
`/api/v1/health` degraded from under 10ms to 2.5s, then 4.7s, then a 30s
timeout. With one worker and this module's documented worst case, a single
pathological upload could make the whole service unavailable for about an
hour. The fix is `run_in_threadpool` in `app/api/routes_ocr.py`.

NO OTHER TEST IN THIS SUITE CAN CATCH A REGRESSION HERE. Every other test
drives the app through `fastapi.testclient.TestClient`, which is synchronous
and issues one request at a time -- it cannot observe that a second request
was starved, because it never has a second request in flight. So this file
runs the real ASGI app on a real event loop with two requests overlapping.

IT ALSO MEASURES THE RIGHT THING, WHICH IS SUBTLER THAN IT LOOKS. Timing each
probe individually proves nothing: when the loop is blocked, `asyncio.sleep`
cannot resume either, so the probe's own clock starts only after the block has
already ended and every probe looks fast in both worlds. What separates the
two cases is WHEN a probe completes on one absolute clock -- whether it can
finish while the extraction is still in flight. That is what is asserted.

This test was confirmed to FAIL against the pre-fix code path (0 of 4 probes
served during the extraction, all completing after it) and to pass after it
(4 of 4 served, at roughly 0.4s, 0.8s, 1.3s and 1.7s into a 3s extraction).
`test_request_id_survives_the_worker_thread` covers the other half: the
correlation id lives in a `ContextVar`, and `run_in_threadpool` must carry it
into the worker or every log line from an extraction loses its request id.
"""

from __future__ import annotations

import asyncio
import time

import httpx

import app.api.routes_ocr as routes_ocr
from app.config import Settings, get_settings
from app.main import app

#: How long the stand-in blocking call sleeps. Long enough that several probes
#: fit inside it, short enough not to slow the suite down.
SLOW_SECONDS = 1.5

#: Probe cadence. Four probes at 0.3s spacing all land inside SLOW_SECONDS.
PROBE_COUNT = 4
PROBE_INTERVAL = 0.3

#: A completion within this margin of the extraction's own finish is not
#: evidence of concurrency -- it could just be the pile-up resolving.
MARGIN_SECONDS = 0.15


class _StubDocument:
    pages: list = []
    is_repaired = False
    filename = "stub.pdf"
    mime_type = "application/pdf"
    page_count = 1


class _StubExtractionService:
    """Returns an empty, valid Module 4 payload. No model, no network."""

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
    """Race a slow extraction against repeated /health calls.

    Returns `(extraction_finished_at, [(status, completed_at), ...],
    request_id_seen_inside_the_worker)`, all offsets from one absolute start.
    """
    observed = {}
    started = {}

    def slow_load_document(data, settings, filename=None, declared_mime=None):
        # Stands in for pymupdf: blocks whichever thread calls it, exactly as
        # the real one does. If this runs on the event loop, nothing else in
        # the process can make progress while it sleeps.
        from app.core.request_context import get_request_id

        observed["request_id"] = get_request_id()
        time.sleep(SLOW_SECONDS)
        return _StubDocument()

    monkeypatch.setattr(routes_ocr, "load_document", slow_load_document)

    # Same override pattern the rest of the suite uses (see conftest's
    # `client_factory`): settings built with no env file, which leaves the
    # service unauthenticated for the test, and a stub extraction service so
    # no model and no network are involved.
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
    """A slow extraction must not starve every other endpoint.

    The assertion is deliberately about WHEN each probe completed relative to
    the extraction, not how long each probe itself took -- see the module
    docstring for why the latter cannot distinguish the two cases.
    """
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
    """The correlation id must cross into the thread the work runs on.

    `run_in_threadpool` goes through `anyio.to_thread.run_sync`, which copies
    the caller's `contextvars` context. If that ever stops holding, extraction
    log lines silently lose their request id and a pipeline run can no longer
    be traced across the two services -- a quiet failure, so it is asserted.
    """
    _, _, request_id = _run_overlap_probe(monkeypatch)

    assert request_id == "event-loop-probe-id", (
        "the request-id ContextVar did not reach the worker thread "
        f"(saw {request_id!r})"
    )
