"""Opt-in live test of Module 23 against the real Gemini API.

SKIPPED BY DEFAULT. It runs only when BOTH are true:
    RUN_LIVE_TESTS=1
    GEMINI_API_KEY=<a real key>

Run it with:
    RUN_LIVE_TESTS=1 pytest tests/test_live_explanation.py -v -s

It costs a small number of API tokens and requires network access. It uses an
INVENTED value for a fictional reader -- no real medical data -- and it asserts
the thing that actually matters: that real, unrehearsed model output clears
Module 24. A mocked test can only ever prove the wiring; this proves the prompt
is narrow enough that the gate is not doing all the work.

The test is deliberately intolerant. If the live model routinely fails the
safety layer, that is a finding about the prompt, not a flaky test to retry.
"""

from __future__ import annotations

import os

import pytest

from tests.conftest import _LIVE_KEY_ENV


def _live_key():
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
        gemini_timeout_seconds=60.0,
        gemini_max_retries=2,
    )


@pytest.mark.live
@live_only
def test_a_real_explanation_passes_the_safety_layer(live_settings):
    from app.services.explanation import explain_feature

    result = explain_feature(
        "hba1c",
        value=6.8,
        unit="%",
        interpretation="above the reference interval used by this platform",
        conditions=("Diabetes",),
        reference_low=4.0,
        reference_high=5.6,
        status="valid",
        settings=live_settings,
    )

    print("\n--- live outcome:", result.outcome)
    print("--- attempts:", result.safety.attempts)
    print("--- violation codes:", result.safety.violation_codes)
    print("--- sources:", [s.doc_id for s in result.sources])
    print("--- explanation:\n", result.explanation)

    assert result.outcome == "generated", (
        f"live generation was not approved: {result.safety.violation_codes}"
    )
    assert result.explanation
    assert result.safety.verdict in ("approve", "approve_with_modification")
    assert result.sources


@pytest.mark.live
@live_only
def test_a_real_explanation_is_approved_on_the_first_attempt(live_settings):
    """A prompt that only works after a safety retry is not a good prompt."""
    from app.services.explanation import explain_feature

    result = explain_feature(
        "creatinine",
        value=1.1,
        unit="mg/dl",
        interpretation="within the reference interval",
        conditions=("Kidney Disease",),
        reference_low=0.7,
        reference_high=1.3,
        status="valid",
        settings=live_settings,
    )
    print("\n--- creatinine outcome:", result.outcome, result.safety.violation_codes)
    print("--- explanation:\n", result.explanation)
    assert result.outcome == "generated"
    assert result.safety.attempts == 1


@pytest.mark.live
@live_only
def test_a_real_explanation_states_no_ungrounded_number(live_settings):
    """The control that a mock cannot exercise honestly."""
    from app.services.explanation import explain_feature

    result = explain_feature(
        "cholesterol",
        value=215.0,
        unit="mg/dl",
        interpretation="above the desirable range",
        conditions=("High Cholesterol",),
        status="valid",
        settings=live_settings,
    )
    print("\n--- cholesterol outcome:", result.outcome, result.safety.violation_codes)
    assert "UNGROUNDED_NUMERIC_CLAIM" not in result.safety.violation_codes


@pytest.mark.live
@live_only
def test_the_live_terminology_simplification_is_approved(live_settings):
    from app.services.terminology import explain_term

    answer = explain_term("eGFR", simplify=True, settings=live_settings)
    print("\n--- terminology outcome:", answer.outcome, answer.source_kind)
    print("--- explanation:\n", answer.explanation)
    assert answer.explanation
    # Either the model was approved, or the curated text was served. Both are
    # correct; what must never happen is an empty answer for a covered term.
    assert answer.outcome in ("generated", "served_from_knowledge_base")
