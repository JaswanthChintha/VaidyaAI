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


def test_the_prompt_contains_the_test_name_and_no_patient_value():
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
    client = RecordingClient(answer("higher_is_worse", 4.0, 20.0))
    out = classify_lab_series([series(12.1, 12.3)], client)

    verdict = out.verdicts[0]
    assert verdict.trend == "stable"
    assert verdict.significant_change_pct == round(reference_change_value(4.0, 20.0))


def test_the_rcv_is_this_services_own_arithmetic():
    client = RecordingClient(answer("higher_is_worse", 2.5, 5.7))
    out = classify_lab_series([series(100.0, 200.0)], client)

    assert out.verdicts[0].significant_change_pct == 17


def test_best_within_range_uses_the_LABORATORYS_interval():
    client = RecordingClient(answer("best_within_range", 2.0, 4.0))
    out = classify_lab_series(
        [series(10.0, 30.0, reference_low=22.0, reference_high=45.0)], client
    )
    assert out.verdicts[0].trend == "improving"


def test_best_within_range_refuses_when_the_report_printed_no_interval():
    client = RecordingClient(answer("best_within_range", 2.0, 4.0))
    out = classify_lab_series([series(10.0, 30.0)], client)

    verdict = out.verdicts[0]
    assert verdict.outcome == "CLINICAL_DIRECTION_UNKNOWN"
    assert verdict.trend is None
    assert verdict.reason_key == "no_reference_interval"


@pytest.mark.parametrize(
    "bad_cv",
    [
        CV_PERMITTED[1] + 1,
        CV_PERMITTED[0] - 0.01,
        -5.0,
        "twelve",
        None,
        True,
    ],
)
def test_an_implausible_variation_figure_refuses_the_whole_entry(bad_cv):
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
    client = RecordingClient(
        None, raw='```json\n{"polarity":"higher_is_worse",'
        '"analytical_cv_pct":4.0,"within_subject_cv_pct":20.0}\n```'
    )
    out = classify_lab_series([series(12.1, 38.9)], client)
    assert out.verdicts[0].trend == "worsening"


def test_one_model_call_serves_every_patient_with_that_test():
    client = RecordingClient(answer())
    out = classify_lab_series([series(1.0, 100.0), series(2.0, 200.0)], client)

    assert len(client.prompts) == 1
    assert out.generated == 1
    assert out.cached == 1
    assert [v.trend for v in out.verdicts] == ["worsening", "worsening"]


def test_a_refusal_is_never_cached():
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
    assert out.skipped_over_limit == 3
    assert len(out.verdicts) == 2


def test_nothing_to_do_answers_with_an_empty_set_rather_than_throwing():
    client = RecordingClient(answer())
    out = classify_lab_series([], client)
    assert out.verdicts == []
    assert out.requested == 0
    assert client.prompts == []


def test_a_listed_test_uses_the_table_and_never_calls_the_model():
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

    assert client.prompts == []
    verdict = out.verdicts[0]
    assert verdict.variation_source == "table"
    assert verdict.significant_change_pct == 97
    assert verdict.trend == "worsening"


def test_a_table_threshold_is_NOT_reported_as_verified():
    client = RecordingClient(answer())
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

    verdict = out.verdicts[0]
    assert verdict.variation_verified is False
    assert "NOT YET CHECKED" in verdict.basis
    assert "biologicalvariation.eu" in verdict.basis


def test_the_ESR_basis_names_NO_source_rather_than_a_wrong_one():
    client = RecordingClient(answer())
    out = classify_lab_series(
        [LabSeriesInput(test_name="ESR", first_value=35.0, last_value=45.0, unit="mm/hr")],
        client,
    )

    verdict = out.verdicts[0]
    assert verdict.variation_source == "table"
    assert verdict.variation_verified is False
    assert "NO SOURCE" in verdict.basis
    assert "biologicalvariation.eu/meta_by_analyte" not in verdict.basis


def test_an_unlisted_test_still_asks_the_model_and_says_so():
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
