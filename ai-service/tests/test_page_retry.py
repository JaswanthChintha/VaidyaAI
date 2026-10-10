"""A page the whole model chain could not read gets ONE more try (2026-10-10).

Test 3's page 2 -- glucose, creatinine, SGPT -- was skipped as
MODEL_UNAVAILABLE: every model's own retries ran within seconds, inside one
provider outage, and the report read "Healthy (partial assessment)". Now a
page that failed in a way a later moment can fix is read once more after
`page_retry_delay_seconds`; anything else, and a second failure, is final.
"""

from __future__ import annotations

from typing import Dict, List

import pytest

from app.config import Settings
from app.core.errors import ErrorCode, ModelError
from app.services import extractor as extractor_module
from app.services.document_loader import LoadedDocument, PageImage
from app.services.extractor import PAGE_RETRY_CODES, ExtractionService


def _document(pages: int) -> LoadedDocument:
    return LoadedDocument(
        filename="r.pdf",
        mime_type="application/pdf",
        size_bytes=1,
        page_count=pages,
        pages=[PageImage(page_number=n, image_bytes=b"x" * n) for n in range(1, pages + 1)],
        warnings=[],
    )


def _payload(page: int) -> dict:
    return {
        "raw_text": f"page {page} text",
        "parameters": [{"test_name": f"TEST {page}", "value_raw": str(page)}],
    }


def _error(code: ErrorCode) -> ModelError:
    return ModelError("model said no", code=code, status_code=503)


class _ScriptedClient:
    """Each page answers from its own script, one entry per call; a page with
    no script left answers normally. Calls are counted per page."""

    def __init__(self, scripts: Dict[int, List[object]]):
        self.scripts = {page: list(items) for page, items in scripts.items()}
        self.calls: Dict[int, int] = {}

    def extract_page(self, image_bytes, mime_type, prompt):
        page = len(image_bytes)
        self.calls[page] = self.calls.get(page, 0) + 1
        script = self.scripts.get(page) or []
        item = script.pop(0) if script else _payload(page)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture()
def sleeps(monkeypatch):
    recorded: List[float] = []
    monkeypatch.setattr(extractor_module.time, "sleep", lambda s: recorded.append(s))
    return recorded


def _service(client, **overrides) -> ExtractionService:
    return ExtractionService(Settings(_env_file=None, **overrides), client)


def _skipped(result) -> List[str]:
    return [w for w in result.warnings if "could not be processed" in w or "did not match" in w]


def test_a_page_unavailable_once_is_read_on_the_second_try(sleeps):
    client = _ScriptedClient({2: [_error(ErrorCode.MODEL_UNAVAILABLE)]})
    result = _service(client).extract(_document(2))

    assert client.calls == {1: 1, 2: 2}
    assert [p.test_name for p in result.extracted_parameters] == ["TEST 1", "TEST 2"]
    assert [p.page_number for p in result.extracted_parameters] == [1, 2]
    assert _skipped(result) == []
    assert result.pages[1].raw_text == "page 2 text"
    # The pause happens, once, at the configured length (20 s by default).
    assert sleeps == [20.0]


def test_a_page_that_fails_twice_is_skipped_and_said_so(sleeps):
    down = _error(ErrorCode.MODEL_UNAVAILABLE)
    client = _ScriptedClient({2: [down, down]})
    result = _service(client).extract(_document(2))

    assert client.calls == {1: 1, 2: 2}  # one retry, never a third read
    assert [p.test_name for p in result.extracted_parameters] == ["TEST 1"]
    assert _skipped(result) == [
        "Page 2 could not be processed by the extraction model (MODEL_UNAVAILABLE); it was skipped."
    ]
    assert result.pages[1].raw_text is None


@pytest.mark.parametrize(
    "code",
    [ErrorCode.MODEL_RESPONSE_MALFORMED, ErrorCode.MODEL_RESPONSE_EMPTY],
)
def test_a_garbled_answer_is_also_worth_one_more_try(sleeps, code):
    client = _ScriptedClient({1: [_error(code)]})
    result = _service(client).extract(_document(1))
    assert client.calls == {1: 2}
    assert _skipped(result) == []


def test_an_answer_that_did_not_fit_the_schema_is_read_again(sleeps):
    client = _ScriptedClient({2: [{"parameters": "not a list"}]})
    result = _service(client).extract(_document(2))
    assert client.calls == {1: 1, 2: 2}
    assert [p.test_name for p in result.extracted_parameters] == ["TEST 1", "TEST 2"]
    assert _skipped(result) == []


@pytest.mark.parametrize(
    "code",
    [
        # The free tier's cap is daily: twenty seconds later it is still spent.
        ErrorCode.MODEL_RATE_LIMITED,
        # Another full attempt chain would run past the backend's deadline.
        ErrorCode.MODEL_TIMEOUT,
        # Answers, not accidents: the same page gets the same answer.
        ErrorCode.MODEL_RESPONSE_BLOCKED,
        ErrorCode.MODEL_RESPONSE_TRUNCATED,
    ],
)
def test_failures_a_later_moment_cannot_fix_are_not_retried(sleeps, code):
    client = _ScriptedClient({2: [_error(code)]})
    result = _service(client).extract(_document(2))
    assert client.calls == {1: 1, 2: 1}
    assert sleeps == []
    assert len(_skipped(result)) == 1
    assert code not in PAGE_RETRY_CODES


def test_nothing_failed_nothing_waits(sleeps):
    client = _ScriptedClient({})
    result = _service(client).extract(_document(3))
    assert client.calls == {1: 1, 2: 1, 3: 1}
    assert sleeps == []
    assert len(result.extracted_parameters) == 3


def test_only_the_failed_pages_are_read_again(sleeps):
    down = _error(ErrorCode.MODEL_UNAVAILABLE)
    client = _ScriptedClient({1: [down], 3: [down]})
    result = _service(client).extract(_document(3))
    assert client.calls == {1: 2, 2: 1, 3: 2}
    assert sleeps == [20.0]  # one pause for all of them, not one each
    assert [p.page_number for p in result.extracted_parameters] == [1, 2, 3]


def test_every_page_failing_twice_still_fails_the_request_as_before(sleeps):
    down = _error(ErrorCode.MODEL_UNAVAILABLE)
    client = _ScriptedClient({1: [down, down]})
    with pytest.raises(ModelError):
        _service(client).extract(_document(1))
    assert client.calls == {1: 2}


def test_a_zero_pause_does_not_sleep(sleeps):
    client = _ScriptedClient({1: [_error(ErrorCode.MODEL_UNAVAILABLE)]})
    _service(client, page_retry_delay_seconds=0).extract(_document(1))
    assert client.calls == {1: 2}
    assert sleeps == []
