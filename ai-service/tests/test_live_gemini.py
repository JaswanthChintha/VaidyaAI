"""Opt-in live test against the real Gemini API.

SKIPPED BY DEFAULT. It runs only when BOTH are true:
    RUN_LIVE_TESTS=1
    GEMINI_API_KEY=<a real key>

Run it with:
    RUN_LIVE_TESTS=1 pytest tests/test_live_gemini.py -v -s

It costs a small number of API tokens and requires network access. It uses the
same synthetic fixture as the rest of the suite -- no real medical data.
"""

from __future__ import annotations

import os

import pytest

from tests.conftest import _LIVE_KEY_ENV, make_synthetic_pdf


def _live_key() -> str | None:
    """The real key, from the environment or the conftest stash."""
    return os.environ.get("GEMINI_API_KEY") or os.environ.get(_LIVE_KEY_ENV)


live_only = pytest.mark.skipif(
    os.environ.get("RUN_LIVE_TESTS") != "1" or not _live_key(),
    reason="live test: set RUN_LIVE_TESTS=1 and GEMINI_API_KEY to enable",
)


@pytest.fixture()
def live_settings():
    from app.config import Settings

    key = _live_key()
    assert key, "guarded by the skipif above"
    return Settings(
        _env_file=None,
        gemini_api_key=key,
        gemini_model=os.environ.get("GEMINI_MODEL", "gemini-3.6-flash"),
    )


@pytest.mark.live
@live_only
def test_configured_model_id_exists_in_the_live_model_list(live_settings):
    """Guards against the configured GEMINI_MODEL silently not existing."""
    from google import genai

    client = genai.Client(api_key=live_settings.gemini_api_key.get_secret_value())
    available = {m.name.split("/")[-1] for m in client.models.list()}
    assert live_settings.gemini_model in available, (
        f"Configured GEMINI_MODEL '{live_settings.gemini_model}' is not in the "
        f"live model list."
    )


@pytest.mark.live
@live_only
def test_real_extraction_of_the_synthetic_report(live_settings):
    """End-to-end against the real API, using the synthetic lab report."""
    from app.services.document_loader import load_document
    from app.services.extractor import ExtractionService
    from app.services.gemini_client import GeminiClient

    pdf = make_synthetic_pdf(1)
    document = load_document(pdf, live_settings, filename="synthetic.pdf")
    service = ExtractionService(live_settings, GeminiClient(live_settings))

    data = service.extract(document)

    print(f"\n--- LIVE RESULT ({live_settings.gemini_model}) ---")
    print(f"pages={data.source.page_count} "
          f"params={len(data.extracted_parameters)} "
          f"confidence={data.extraction_confidence}")
    for p in data.extracted_parameters:
        print(
            f"  {p.test_name!r} raw={p.value_raw!r} num={p.value_numeric} "
            f"unit={p.unit!r} ref={p.reference_range_raw!r} flag={p.flag}"
        )
    print(f"warnings={data.warnings}")

    # The fixture has 7 rows; allow slack for how the model groups them.
    assert len(data.extracted_parameters) >= 5
    assert data.raw_text.strip()

    names = " ".join(p.test_name.lower() for p in data.extracted_parameters)
    assert "hba1c" in names
    assert "creatinine" in names

    by_name = {p.test_name.lower(): p for p in data.extracted_parameters}

    hba1c = next(p for k, p in by_name.items() if "hba1c" in k)
    assert hba1c.value_numeric == pytest.approx(6.8, abs=0.01)
    assert hba1c.unit and "%" in hba1c.unit

    # The contract's null rule, verified against the real model.
    ketones = next((p for k, p in by_name.items() if "keton" in k), None)
    if ketones is not None:
        assert ketones.value_numeric is None
        assert "negative" in ketones.value_raw.lower()

    # No normalisation: names must not have been canonicalised to snake_case.
    assert not any("_" in p.test_name for p in data.extracted_parameters)
