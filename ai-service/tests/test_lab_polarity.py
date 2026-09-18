"""Module 35 -- improving / worsening / stable for an unassessed test.

EVERY FIXTURE NAME HERE IS INVENTED, for the reason `labSeries.test.js` states:
the feature must work for ANY test a laboratory can print, there is no list of
known tests in the module, and there must be none in its tests either, or the
suite would pass by recognising the fixtures instead of the rule working.

The two things this file is really about:

  1. THE PROMPT NEVER SEES A PATIENT VALUE. Asserted by inspecting the prompt
     the module actually builds, not by reading the code that builds it.
  2. A NUMBER FROM THE MODEL IS GATED, NEVER CLAMPED. A clamped hallucination
     is still a hallucination wearing a plausible value.
"""

from __future__ import annotations

import json
from typing import Any, List, Optional

import pytest

from app.data.trend_polarity import reference_change_value
from app.services.lab_polarity import (
    CV_PERMITTED,
    LabSeriesInput,
    classify_lab_series,
    reset_cache,
)


class RecordingClient:
    """A Module 23 text client that records every prompt it is given."""

    def __init__(self, payload: Any, *, raw: Optional[str] = None) -> None:
        self.payload = payload
        self.raw = raw
        self.prompts: List[str] = []

    def generate_text(self, prompt: str, system_instruction: str | None = None) -> str:
        self.prompts.append(prompt)
        if self.raw is not None:
            return self.raw
        return json.dumps(self.payload)


def answer(polarity: str = "higher_is_worse", cva: Any = 4.0, cvi: Any = 20.0) -> dict:
    return {
        "polarity": polarity,
        "analytical_cv_pct": cva,
        "within_subject_cv_pct": cvi,
    }


@pytest.fixture(autouse=True)
def _clean_cache():
    reset_cache()
    yield
    reset_cache()


def series(first: float, last: float, **kw: Any) -> LabSeriesInput:
    return LabSeriesInput(test_name="Zorblex", first_value=first, last_value=last, **kw)


# --------------------------------------------------------------------------
# The prompt
# --------------------------------------------------------------------------


def test_the_prompt_contains_the_test_name_and_no_patient_value():
    """THE SAFETY PROPERTY OF THE WHOLE MODULE, asserted on the real prompt.

    12.1 and 38.9 are this patient's readings. Neither may appear, nor the
    change between them, nor the laboratory's interval.
    """
    client = RecordingClient(answer())
    classify_lab_series(
        [series(12.1, 38.9, reference_low=0.0, reference_high=6.0, unit="mg/L")],
        client,
    )

    assert len(client.prompts) == 1
    prompt = client.prompts[0]
    assert "Zorblex" in prompt
    for leaked in ["12.1", "38.9", "26.8", "6.0", "mg/L"]:
        assert leaked not in prompt


def test_the_prompt_forbids_a_reference_range():
    client = RecordingClient(answer())
    classify_lab_series([series(1.0, 2.0)], client)
    assert "Do NOT give a reference range" in client.prompts[0]


# --------------------------------------------------------------------------
# Classification -- Module 28's own classifier, not a second one
# --------------------------------------------------------------------------


def test_a_rise_in_a_higher_is_worse_test_is_worsening():
    client = RecordingClient(answer("higher_is_worse", 4.0, 20.0))
    out = classify_lab_series([series(12.1, 38.9)], client)

    verdict = out.verdicts[0]
    assert verdict.outcome == "TREND_CLASSIFIED"
    assert verdict.trend == "worsening"


def test_a_rise_in_a_higher_is_better_test_is_improving():
    client = RecordingClient(answer("higher_is_better", 4.0, 20.0))
    out = classify_lab_series([series(12.1, 38.9)], client)
    assert out.verdicts[0].trend == "improving"


def test_a_move_smaller_than_the_reference_change_value_is_stable():
    """`stable` is EARNED, and this is the whole reason the RCV is obtained.

    CVa 4 and CVi 20 give an RCV of 57 %. A rise from 12.1 to 12.3 is 1.7 % --
    smaller than two draws from an unchanged person differ anyway -- so calling
    it worsening would state something nobody measured.
    """
    client = RecordingClient(answer("higher_is_worse", 4.0, 20.0))
    out = classify_lab_series([series(12.1, 12.3)], client)

    verdict = out.verdicts[0]
    assert verdict.trend == "stable"
    assert verdict.significant_change_pct == round(reference_change_value(4.0, 20.0))


def test_the_rcv_is_this_services_own_arithmetic():
    """The model supplies CVa and CVi; the formula is the project's.

    Recomputed here from the published formula rather than compared against a
    number typed into this test, which is the discipline the hand-written
    STABILITY table applies to its own rows.
    """
    client = RecordingClient(answer("higher_is_worse", 2.5, 5.7))
    out = classify_lab_series([series(100.0, 200.0)], client)

    # sqrt(2) * 1.96 * sqrt(2.5^2 + 5.7^2) -> 17 %, which is the value the
    # hand-written table records for cholesterol from the same two inputs.
    assert out.verdicts[0].significant_change_pct == 17


def test_best_within_range_uses_the_LABORATORYS_interval():
    """The model says the SHAPE; the report says where the bounds are.

    Moving from below the interval to inside it is an improvement, and nothing
    in that sentence came from the model except "both extremes are bad".
    """
    client = RecordingClient(answer("best_within_range", 2.0, 4.0))
    out = classify_lab_series(
        [series(10.0, 30.0, reference_low=22.0, reference_high=45.0)], client
    )
    assert out.verdicts[0].trend == "improving"


def test_best_within_range_refuses_when_the_report_printed_no_interval():
    """Shape known, position unknown. `_classify` would call every move
    equidistant from an interval that does not exist."""
    client = RecordingClient(answer("best_within_range", 2.0, 4.0))
    out = classify_lab_series([series(10.0, 30.0)], client)

    verdict = out.verdicts[0]
    assert verdict.outcome == "CLINICAL_DIRECTION_UNKNOWN"
    assert verdict.trend is None
    assert verdict.reason_key == "no_reference_interval"


# --------------------------------------------------------------------------
# Refusals -- every one of these must classify NOTHING
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_cv",
    [
        CV_PERMITTED[1] + 1,   # implausibly large
        CV_PERMITTED[0] - 0.01,  # implausibly small
        -5.0,
        "twelve",
        None,
        True,  # a bool is not a CV, and bool is a subclass of int
    ],
)
def test_an_implausible_variation_figure_refuses_the_whole_entry(bad_cv):
    """REFUSED, NOT CLAMPED.

    A model that returns CVa = 300 has not made a small error about a real
    quantity; it has produced something that is not a CV. Substituting a
    plausible number would hide that behind a value nobody measured.
    """
    client = RecordingClient(answer("higher_is_worse", bad_cv, 20.0))
    out = classify_lab_series([series(12.1, 38.9)], client)

    verdict = out.verdicts[0]
    assert verdict.outcome == "CLINICAL_DIRECTION_UNKNOWN"
    assert verdict.trend is None
    assert out.withheld == 1


def test_an_unknown_polarity_classifies_nothing():
    client = RecordingClient(answer("unknown", 0, 0))
    out = classify_lab_series([series(12.1, 38.9)], client)

    assert out.verdicts[0].trend is None
    assert out.verdicts[0].outcome == "CLINICAL_DIRECTION_UNKNOWN"


def test_an_unparsable_answer_classifies_nothing():
    client = RecordingClient(None, raw="I am not JSON at all.")
    out = classify_lab_series([series(12.1, 38.9)], client)
    assert out.verdicts[0].trend is None


def test_a_polarity_word_the_module_does_not_know_classifies_nothing():
    client = RecordingClient(answer("definitely_worse_probably", 4.0, 20.0))
    out = classify_lab_series([series(12.1, 38.9)], client)
    assert out.verdicts[0].trend is None


def test_a_json_object_inside_a_fence_is_still_read():
    """A model asked for JSON returns a fenced object often enough that
    refusing one would refuse mostly-correct answers."""
    client = RecordingClient(
        None, raw='```json\n{"polarity":"higher_is_worse",'
        '"analytical_cv_pct":4.0,"within_subject_cv_pct":20.0}\n```'
    )
    out = classify_lab_series([series(12.1, 38.9)], client)
    assert out.verdicts[0].trend == "worsening"


# --------------------------------------------------------------------------
# The cache and the ceiling
# --------------------------------------------------------------------------


def test_one_model_call_serves_every_patient_with_that_test():
    """The prompt IS the test name, so the answer cannot be patient-specific."""
    client = RecordingClient(answer())
    out = classify_lab_series([series(1.0, 100.0), series(2.0, 200.0)], client)

    assert len(client.prompts) == 1
    assert out.generated == 1
    assert out.cached == 1
    assert [v.trend for v in out.verdicts] == ["worsening", "worsening"]


def test_a_refusal_is_never_cached():
    """A refusal is a moment, not a fact about the test.

    A spent quota refuses everything, and pinning that would make an outage
    look like a property of the test for as long as the process lives.
    """
    refusing = RecordingClient(None, raw="not json")
    classify_lab_series([series(1.0, 2.0)], refusing)

    working = RecordingClient(answer())
    out = classify_lab_series([series(12.1, 38.9)], working)

    assert len(working.prompts) == 1, "the refusal was cached"
    assert out.verdicts[0].trend == "worsening"


def test_the_ceiling_counts_calls_and_is_reported_not_silent():
    client = RecordingClient(answer())
    out = classify_lab_series(
        [
            LabSeriesInput(test_name=f"Zorblex {n}", first_value=1.0, last_value=100.0)
            for n in range(5)
        ],
        client,
        max_calls=2,
    )

    assert out.generated == 2
    # NOT AN ABSENCE. The count that answers "did this truncate" is the one the
    # producer keeps about what it did NOT do -- §6at, sixth time.
    assert out.skipped_over_limit == 3
    assert len(out.verdicts) == 2


def test_nothing_to_do_answers_with_an_empty_set_rather_than_throwing():
    client = RecordingClient(answer())
    out = classify_lab_series([], client)
    assert out.verdicts == []
    assert out.requested == 0
    assert client.prompts == []


def test_a_listed_test_uses_the_table_and_never_calls_the_model():
    """THE FIX FOR A THRESHOLD THAT MOVED BETWEEN PAGE LOADS.

    EOSINOPHILS was refused on one request and called `stable` on the next,
    with the data unchanged, because the model returned a different CVi. A
    listed test now costs no call at all, so the same readings always get the
    same verdict -- and the figures are somewhere a reviewer can find them.
    """
    client = RecordingClient(answer(polarity="higher_is_worse", cva=99.0, cvi=99.0))
    out = classify_lab_series(
        [
            LabSeriesInput(
                test_name="C-REACTIVE PROTEIN(CRP)",
                first_value=12.1,
                last_value=38.9,
                unit="mg/L",
            )
        ],
        client,
    )

    # THE MODEL WAS NOT ASKED. Its answer above would have given a wildly
    # different threshold, and the verdict must not contain it.
    assert client.prompts == []
    verdict = out.verdicts[0]
    assert verdict.variation_source == "table"
    assert verdict.significant_change_pct == 118
    assert verdict.trend == "worsening"


def test_a_table_threshold_is_NOT_reported_as_verified():
    """The table is reviewable; that is not the same as reviewed.

    Every row is `verified=False`, so the sentence a reader gets must say the
    figure has not been checked -- and must name the source so it can be.
    """
    client = RecordingClient(answer())
    out = classify_lab_series(
        [LabSeriesInput(test_name="ESR", first_value=35.0, last_value=45.0, unit="mm/hr")],
        client,
    )

    verdict = out.verdicts[0]
    assert verdict.variation_verified is False
    assert "NOT YET CHECKED" in verdict.basis
    assert "biologicalvariation.eu" in verdict.basis


def test_an_unlisted_test_still_asks_the_model_and_says_so():
    """The fall-through is the previous behaviour, and it is labelled.

    A model-supplied figure has no source to check, and the sentence says that
    rather than naming one that does not exist.
    """
    client = RecordingClient(answer(polarity="higher_is_worse", cva=4.0, cvi=20.0))
    out = classify_lab_series(
        [LabSeriesInput(test_name="Frimbulator Factor", first_value=1.0, last_value=100.0)],
        client,
    )

    assert len(client.prompts) == 1
    verdict = out.verdicts[0]
    assert verdict.variation_source == "model"
    assert verdict.variation_verified is False
    assert verdict.variation_reference is None
    assert "NOT from a reviewable source" in verdict.basis


def test_a_series_that_did_not_move_is_stable_not_refused():
    """0 -> 0 is an ordinary shape on a differential count, and it was broken.

    FOUND LIVE ON BASOPHILS, which is 0 % on both of this account's reports.
    Module 35 sets `min_absolute_change` to 0.0 because it has no canonical
    unit to set a floor in, so a zero move cleared the absolute test, fell
    through to `_is_significant`'s undefined-percentage branch for a zero
    first value, and came back SIGNIFICANT. `_classify` was then asked to
    direct a change that had not happened, and refused -- correctly, since both
    readings sit inside the printed interval. The panel showed "no change" and
    no trend word while every parameter beside it showed one, and the reader
    asked why that row was different.

    A MOVE OF ZERO IS NOT A SIGNIFICANT MOVE. No band permits it.
    """
    client = RecordingClient(answer(polarity="best_within_range", cva=10.0, cvi=20.2))
    out = classify_lab_series(
        [
            LabSeriesInput(
                test_name="Zorblex",
                first_value=0.0,
                last_value=0.0,
                unit="%",
                reference_low=0.0,
                reference_high=2.0,
            )
        ],
        client,
    )

    verdict = out.verdicts[0]
    assert verdict.outcome == "TREND_CLASSIFIED"
    assert verdict.trend == "stable"


def test_a_real_move_from_zero_is_still_judged_on_its_size():
    """The guard above must not swallow the branch it sits in front of.

    `_is_significant` returns True from a zero first value BECAUSE the
    percentage is undefined there, and that is right for 0 -> 3: the reader's
    value went from nothing to something and only the absolute floor can speak.
    A guard that refused every series starting at zero would delete that.
    """
    client = RecordingClient(answer(polarity="higher_is_worse", cva=4.0, cvi=20.0))
    out = classify_lab_series(
        [
            LabSeriesInput(
                test_name="Zorblex",
                first_value=0.0,
                last_value=3.0,
                unit="%",
            )
        ],
        client,
    )

    verdict = out.verdicts[0]
    assert verdict.outcome == "TREND_CLASSIFIED"
    assert verdict.trend == "worsening"


def test_a_move_inside_the_printed_range_that_clears_the_noise_gets_no_direction():
    """The other half of the rule, so "stable" cannot creep on to it.

    MCH went 26.2 -> 29.2 pg against a printed 26-33 with a 6 % noise band:
    an 11.5 % move is real, and both readings are inside the laboratory's own
    interval, so there is no better or worse to state. Calling that "stable"
    would deny a change the same arithmetic just found.
    """
    client = RecordingClient(answer(polarity="best_within_range", cva=1.0, cvi=2.0))
    out = classify_lab_series(
        [
            LabSeriesInput(
                test_name="Zorblex",
                first_value=26.2,
                last_value=29.2,
                unit="pg",
                reference_low=26.0,
                reference_high=33.0,
            )
        ],
        client,
    )

    verdict = out.verdicts[0]
    assert verdict.outcome == "CHANGE_WITHIN_REFERENCE_INTERVAL"
    assert verdict.trend is None
