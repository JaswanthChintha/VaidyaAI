"""Module 23 -- LLM-based patient-friendly explanation.

The suite runs with NO `GEMINI_API_KEY` and NO network. Every generation path
is driven by `FakeTextClient` below, exactly as Module 4's tests drive
extraction through `conftest.FakeGeminiClient`.

The tests that matter most are not the happy path. They are:

* `test_no_path_returns_unvalidated_model_text` and its structural sibling
  `test_explanation_is_only_ever_assigned_from_the_guarded_result` -- one
  behavioural, one reading the source, because a behavioural test only covers
  the paths it thought to call.
* `test_a_hallucinated_number_is_caught` -- the numeric-grounding control,
  which is the part of "grounded in retrieved knowledge" that can be checked
  exactly.
* the Gemini failure-mode block -- four ways the model can fail, none of which
  may produce unvalidated text or a 500.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, List

import pytest

from app.core.errors import (
    ErrorCode,
    ModelError,
    ModelNotConfiguredError,
    ModelRateLimitedError,
    ModelTimeoutError,
)


# --------------------------------------------------------------------------
# The test double
# --------------------------------------------------------------------------


class FakeTextClient:
    """Stands in for `GeminiTextClient`. Records prompts; never uses network.

    `outputs` may hold strings (returned) and exceptions (raised), consumed in
    order; the last entry repeats. That is enough to express "rejected, then
    fixed on the retry" and "fails every time".
    """

    def __init__(self, *outputs: Any) -> None:
        self.outputs: List[Any] = list(outputs) or [_APPROVABLE]
        self.prompts: List[str] = []

    def generate_text(self, prompt: str, **kwargs: Any) -> str:
        self.prompts.append(prompt)
        index = min(len(self.prompts) - 1, len(self.outputs) - 1)
        item = self.outputs[index]
        if isinstance(item, BaseException):
            raise item
        return item


#: A generation the safety layer approves: hedged, no diagnosis, no
#: instruction, names a professional, and states only permitted numbers.
_APPROVABLE = (
    "Your HbA1c result was 6.8 %. HbA1c is a measure of how much glucose has "
    "attached to haemoglobin in your blood over the last few months, which is "
    "why it is used to look at longer-term patterns rather than a single "
    "moment. Compared with the interval printed on your report, 4.0 to 5.6, "
    "your value sits above it. What that may mean for you is a question for a "
    "qualified healthcare professional, who can look at it alongside the rest "
    "of your history."
)

#: Everything the safety layer exists to stop, in one paragraph.
_UNSAFE = (
    "You have diabetes. Start metformin 500 mg twice a day and stop your "
    "current tablets. This result definitely proves it, and your risk score "
    "of 87.5 confirms the diagnosis. You do not need to see a doctor."
)

PLANTED_VALUE = 6.8


@pytest.fixture()
def offline_settings():
    """Settings with no API key -- the state the whole suite runs in."""
    from app.config import Settings

    return Settings(_env_file=None)


def _explain(llm: Any = None, settings: Any = None, **overrides: Any):
    from app.services.explanation import explain_feature

    kwargs = dict(
        value=PLANTED_VALUE,
        unit="%",
        interpretation="above the reference interval used by this platform",
        conditions=("Diabetes",),
        reference_low=4.0,
        reference_high=5.6,
        status="valid",
    )
    kwargs.update(overrides)
    return explain_feature("hba1c", llm=llm, settings=settings, **kwargs)


# --------------------------------------------------------------------------
# The architecture: findings + knowledge -> LLM -> safety -> response
# --------------------------------------------------------------------------


def test_an_approved_generation_is_returned_with_its_sources(offline_settings):
    result = _explain(llm=FakeTextClient(_APPROVABLE), settings=offline_settings)

    assert result.outcome == "generated"
    assert result.explanation == _APPROVABLE
    assert result.fallback is None
    assert result.safety.validated is True
    assert result.safety.verdict in ("approve", "approve_with_modification")


def test_every_generation_passes_through_guarded_generation(
    monkeypatch, offline_settings
):
    """The gate is not optional and not bypassable by any argument."""
    import app.services.explanation as module

    calls: List[dict] = []
    real = module.guarded_generation

    def spy(generate, **kwargs):
        calls.append(kwargs)
        return real(generate, **kwargs)

    monkeypatch.setattr(module, "guarded_generation", spy)

    fake = FakeTextClient(_APPROVABLE)
    result = _explain(llm=fake, settings=offline_settings)

    assert fake.prompts, "the model was never called -- test proves nothing"
    assert len(calls) == 1
    assert result.explanation is not None


def test_the_safety_context_carries_the_retrieved_grounding(
    monkeypatch, offline_settings
):
    """The validator must be told what the model was allowed to cite."""
    import app.services.explanation as module

    seen: List[Any] = []
    real = module.guarded_generation

    def spy(generate, *, context=None, **kwargs):
        seen.append(context)
        return real(generate, context=context, **kwargs)

    monkeypatch.setattr(module, "guarded_generation", spy)
    _explain(llm=FakeTextClient(_APPROVABLE), settings=offline_settings)

    context = seen[0]
    assert context.grounding_sources, "no grounding was handed to the validator"
    assert context.require_grounding is True
    assert context.check_numeric_grounding is True
    assert PLANTED_VALUE in context.permitted_numbers
    assert 4.0 in context.permitted_numbers and 5.6 in context.permitted_numbers


def test_the_prompt_receives_findings_and_retrieved_knowledge(offline_settings):
    fake = FakeTextClient(_APPROVABLE)
    _explain(llm=fake, settings=offline_settings)

    prompt = fake.prompts[0]
    assert "Structured findings" in prompt
    assert "Retrieved knowledge" in prompt
    assert "PERMITTED NUMBERS" in prompt
    # A cited document id appears, so the model is grounded in named sources.
    assert "[lab_hba1c]" in prompt or "[ref_hba1c_bands]" in prompt


def test_the_prompt_never_receives_raw_report_text(offline_settings):
    """Spec Module 23: structured evidence, not unrestricted raw input."""
    fake = FakeTextClient(_APPROVABLE)
    _explain(
        llm=fake,
        settings=offline_settings,
        interpretation="above the reference interval",
    )
    prompt = fake.prompts[0]
    # Nothing resembling a transcript header can be in there, because no raw
    # text is an input to this module at all.
    assert "raw_text" not in prompt
    assert "Patient Name" not in prompt


# --------------------------------------------------------------------------
# The property: no path returns unvalidated model text
# --------------------------------------------------------------------------


def test_no_path_returns_unvalidated_model_text(offline_settings):
    """The planted unsafe paragraph must not survive anywhere in the payload."""
    result = _explain(llm=FakeTextClient(_UNSAFE), settings=offline_settings)

    assert result.explanation is None
    assert result.outcome == "withheld_by_safety"

    serialised = result.model_dump_json()
    for fragment in (
        "You have diabetes",
        "metformin",
        "500 mg",
        "definitely proves",
        "87.5",
        "You do not need to see a doctor",
    ):
        assert fragment not in serialised, (
            f"refused model text leaked into the response: {fragment!r}"
        )


def test_explanation_is_only_ever_assigned_from_the_guarded_result():
    """Read the source. A behavioural test only covers paths it called.

    Every `explanation=` keyword in `app/services/explanation.py` must be
    either `None` or `guarded.approved_text`. A third value would be a second
    way for text to reach a patient.
    """
    source = Path("app/services/explanation.py").read_text(encoding="utf-8")
    assigned = set(re.findall(r"^\s*explanation=([^,\n]+),", source, re.MULTILINE))
    assert assigned == {"None", "guarded.approved_text"}, assigned


def test_terminology_explanations_come_from_validated_sources_only():
    source = Path("app/services/terminology.py").read_text(encoding="utf-8")
    assigned = set(re.findall(r"^\s*explanation=([^,\n]+),", source, re.MULTILINE))
    # `generated.explanation` is a `PatientExplanation`, which by the test
    # above can only hold `guarded.approved_text`; `verdict.approved_text` is
    # Module 24's own output for curated corpus text.
    assert assigned == {
        "None",
        "generated.explanation",
        "verdict.approved_text",
    }, assigned


def test_the_model_is_called_in_exactly_one_place_per_service_module():
    """A second call site is a second chance to skip the gate."""
    for path in ("app/services/explanation.py", "app/services/terminology.py"):
        source = Path(path).read_text(encoding="utf-8")
        assert source.count(".generate_text(") <= 1, path


# --------------------------------------------------------------------------
# Rejection and fallback
# --------------------------------------------------------------------------


def test_a_rejection_falls_back_with_the_structured_findings_intact(
    offline_settings,
):
    result = _explain(llm=FakeTextClient(_UNSAFE), settings=offline_settings)

    fallback = result.fallback
    assert fallback is not None
    assert fallback.generated_explanation_available is False
    assert fallback.use_structured_report is True
    assert fallback.recommendation_codes, "the catalogue guidance vanished"
    assert fallback.recommendations
    assert fallback.notice


def test_the_failure_is_made_visible_and_is_not_silently_substituted(
    offline_settings,
):
    """Never an empty screen, never a quiet swap for something else."""
    result = _explain(llm=FakeTextClient(_UNSAFE), settings=offline_settings)

    assert result.outcome == "withheld_by_safety"
    assert result.explanation is None
    assert result.fallback is not None and result.fallback.notice
    assert result.safety.validated is True
    assert result.safety.violation_codes, "the reason was not reported"
    # The structured provenance survives the refusal, so a reader can still see
    # what the analysis was working from.
    assert result.sources


def test_the_violation_codes_are_reported_but_the_offending_text_is_not(
    offline_settings,
):
    result = _explain(llm=FakeTextClient(_UNSAFE), settings=offline_settings)
    assert "UNSUPPORTED_DIAGNOSIS" in result.safety.violation_codes
    assert "MEDICATION_REFERENCE" in result.safety.violation_codes
    assert "metformin" not in result.model_dump_json()


def test_a_safety_rejection_is_retried_with_a_different_prompt(offline_settings):
    """Never retry a refusal with the same prompt and hope."""
    fake = FakeTextClient(_UNSAFE, _APPROVABLE)
    result = _explain(llm=fake, settings=offline_settings)

    assert len(fake.prompts) == 2
    assert fake.prompts[0] != fake.prompts[1]
    assert "PREVIOUS ATTEMPT WAS REJECTED" in fake.prompts[1]
    assert "UNSUPPORTED_DIAGNOSIS" in fake.prompts[1]
    assert result.outcome == "generated"
    assert result.safety.attempts == 2


def test_two_rejections_end_in_the_fallback_and_no_third_call(offline_settings):
    fake = FakeTextClient(_UNSAFE, _UNSAFE, _APPROVABLE)
    result = _explain(llm=fake, settings=offline_settings)

    assert len(fake.prompts) == 2, "the attempt cap was not honoured"
    assert result.outcome == "withheld_by_safety"
    assert result.explanation is None


# --------------------------------------------------------------------------
# Numeric grounding
# --------------------------------------------------------------------------


def test_a_hallucinated_number_is_caught(offline_settings):
    """A fabricated threshold reads as a clinical fact. It must not survive."""
    hallucinated = (
        "Your HbA1c result was 6.8 %. Anything above 41.7 is considered a "
        "serious problem by every laboratory. A qualified healthcare "
        "professional can discuss it with you."
    )
    result = _explain(
        llm=FakeTextClient(hallucinated, hallucinated), settings=offline_settings
    )

    assert result.outcome == "withheld_by_safety"
    assert "UNGROUNDED_NUMERIC_CLAIM" in result.safety.violation_codes
    assert "41.7" not in result.model_dump_json()


def test_the_patients_own_value_is_permitted(offline_settings):
    result = _explain(llm=FakeTextClient(_APPROVABLE), settings=offline_settings)
    assert result.outcome == "generated"
    assert "6.8" in result.explanation


def test_only_vouched_numbers_become_permitted(offline_settings):
    result = _explain(
        llm=FakeTextClient(_APPROVABLE),
        settings=offline_settings,
        additional_permitted_numbers=(6.5,),
    )
    assert 6.5 in result.permitted_numbers
    assert 6.8 in result.permitted_numbers
    # Nothing else crept in from the interpretation label or anywhere else.
    assert set(result.permitted_numbers) == {6.8, 4.0, 5.6, 6.5}


# --------------------------------------------------------------------------
# Provenance
# --------------------------------------------------------------------------


def test_citations_carry_document_topic_and_basis(offline_settings):
    result = _explain(llm=FakeTextClient(_APPROVABLE), settings=offline_settings)

    assert result.sources
    for source in result.sources:
        assert source.doc_id
        assert source.title
        assert source.topic
        assert source.basis, "a claim a reader cannot trace"
        assert source.last_reviewed
        assert 0.0 <= source.score <= 1.0


def test_provenance_survives_a_refusal(offline_settings):
    result = _explain(llm=FakeTextClient(_UNSAFE), settings=offline_settings)
    assert result.sources and all(s.basis for s in result.sources)


# --------------------------------------------------------------------------
# Refusals decided before generation
# --------------------------------------------------------------------------


def test_no_model_means_no_generation_and_a_visible_notice(offline_settings):
    from app.services.explanation import MODEL_UNAVAILABLE_NOTICE

    result = _explain(llm=None, settings=offline_settings)

    assert result.outcome == "model_unavailable"
    assert result.explanation is None
    assert result.notice == MODEL_UNAVAILABLE_NOTICE
    assert result.fallback is not None
    assert result.safety.validated is False


def test_an_unknown_feature_is_refused_not_retrieved_on(offline_settings):
    from app.services.explanation import explain_feature

    fake = FakeTextClient(_APPROVABLE)
    result = explain_feature("thyroid_stimulating_hormone", llm=fake, settings=offline_settings)

    assert result.outcome == "unknown_subject"
    assert result.explanation is None
    assert fake.prompts == [], "the model was called about an unknown parameter"


def test_no_grounding_means_no_generation(monkeypatch, offline_settings):
    import app.services.explanation as module

    monkeypatch.setattr(module, "retrieve", lambda **kwargs: [])
    fake = FakeTextClient(_APPROVABLE)
    result = _explain(llm=fake, settings=offline_settings)

    assert result.outcome == "not_grounded"
    assert result.explanation is None
    assert result.notice == module.NOT_GROUNDED_NOTICE
    assert fake.prompts == [], "an ungrounded generation was attempted"


def test_a_retrieval_failure_is_treated_as_no_grounding(
    monkeypatch, offline_settings
):
    import app.services.explanation as module

    def boom(**kwargs):
        raise RuntimeError("index unavailable")

    monkeypatch.setattr(module, "retrieve", boom)
    fake = FakeTextClient(_APPROVABLE)
    result = _explain(llm=fake, settings=offline_settings)

    assert result.outcome == "not_grounded"
    assert fake.prompts == []


# --------------------------------------------------------------------------
# Gemini failure modes
# --------------------------------------------------------------------------


FAILURES = [
    ModelTimeoutError("timed out"),
    ModelRateLimitedError("rate limited"),
    ModelError("empty", code=ErrorCode.MODEL_RESPONSE_EMPTY, status_code=502),
    ModelError("malformed", code=ErrorCode.MODEL_RESPONSE_MALFORMED, status_code=502),
    ModelError("blocked", code=ErrorCode.MODEL_RESPONSE_BLOCKED, status_code=502),
    ModelNotConfiguredError("no key"),
    RuntimeError("something nobody predicted"),
]


@pytest.mark.parametrize("failure", FAILURES, ids=lambda f: type(f).__name__ + str(getattr(f, "code", "")))
def test_a_model_failure_never_produces_text_and_never_raises(
    failure, offline_settings
):
    result = _explain(llm=FakeTextClient(failure), settings=offline_settings)

    assert result.explanation is None
    assert result.outcome == "model_unavailable"
    assert result.fallback is not None
    assert result.notice


def test_an_empty_model_response_is_not_an_approval(offline_settings):
    """The one failure that arrives as a value rather than an exception."""
    result = _explain(llm=FakeTextClient(""), settings=offline_settings)
    assert result.explanation is None
    assert result.outcome == "withheld_by_safety"


def test_whitespace_only_output_is_not_an_approval(offline_settings):
    result = _explain(llm=FakeTextClient("   \n\t  "), settings=offline_settings)
    assert result.explanation is None


def test_a_transport_failure_is_not_retried_here(offline_settings):
    """The client already retried with backoff; a second round multiplies it."""
    fake = FakeTextClient(ModelTimeoutError("timed out"), _APPROVABLE)
    result = _explain(llm=fake, settings=offline_settings)

    assert len(fake.prompts) == 1
    assert result.outcome == "model_unavailable"


# --------------------------------------------------------------------------
# The prompt module
# --------------------------------------------------------------------------


def test_the_prompt_module_states_every_required_prohibition():
    from app.prompts.explanation_prompt import PROHIBITIONS

    text = " ".join(PROHIBITIONS).lower()
    assert "never diagnose" in text
    assert "medication" in text
    assert "dosage" in text
    assert "certainty" in text or "definitely" in text
    assert "qualified healthcare professional" in text
    assert "only the supplied values" in text


def test_the_prohibitions_reach_the_actual_prompt():
    """The reviewable list and the sent text cannot drift apart."""
    from app.prompts.explanation_prompt import (
        PROHIBITIONS,
        KnowledgeExtract,
        build_explanation_prompt,
        build_terminology_prompt,
    )

    extract = KnowledgeExtract("d1", "T", "terminology", "basis", "text")
    for prompt in (
        build_explanation_prompt(
            subject="the HbA1c result", findings=("a",), extracts=[extract]
        ),
        build_terminology_prompt(
            term="HbA1c", canonical_feature="hba1c", extracts=[extract]
        ),
    ):
        for rule in PROHIBITIONS:
            assert rule in prompt


def test_a_prompt_with_no_permitted_numbers_forbids_digits_outright():
    from app.prompts.explanation_prompt import KnowledgeExtract, build_explanation_prompt

    prompt = build_explanation_prompt(
        subject="x",
        findings=(),
        extracts=[KnowledgeExtract("d", "t", "topic", "b", "text")],
        permitted_numbers=(),
    )
    assert "NONE. Write no digits" in prompt


def test_the_prompt_version_is_recorded_on_the_result(offline_settings):
    from app.prompts.explanation_prompt import PROMPT_VERSION

    result = _explain(llm=FakeTextClient(_APPROVABLE), settings=offline_settings)
    assert result.prompt_version == PROMPT_VERSION


# --------------------------------------------------------------------------
# Logging
# --------------------------------------------------------------------------


def test_no_phi_reaches_the_logs(caplog, offline_settings):
    """Values, prompts and generated sentences must never be logged."""
    import logging

    caplog.set_level(logging.DEBUG)
    _explain(llm=FakeTextClient(_APPROVABLE), settings=offline_settings)
    _explain(llm=FakeTextClient(_UNSAFE), settings=offline_settings)
    _explain(llm=FakeTextClient(ModelTimeoutError("x")), settings=offline_settings)

    logged = "\n".join(record.getMessage() for record in caplog.records)
    for forbidden in (
        "6.8",
        "metformin",
        "You have diabetes",
        "HbA1c is a measure",
        "Structured findings",
    ):
        assert forbidden not in logged, f"PHI in logs: {forbidden!r}"


def test_the_outcome_is_logged_so_a_refusal_is_operationally_visible(
    caplog, offline_settings
):
    import logging

    caplog.set_level(logging.INFO)
    _explain(llm=FakeTextClient(_UNSAFE), settings=offline_settings)
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "withheld_by_safety" in logged or "fallback" in logged


# --------------------------------------------------------------------------
# Report-level
# --------------------------------------------------------------------------


def _report() -> dict:
    return {
        "laboratory_values": [
            {
                "feature": "hba1c",
                "value": 6.8,
                "unit": "%",
                "status": "valid",
                "usable": True,
                "reference_low": 4.0,
                "reference_high": 5.6,
            },
            {
                "feature": "creatinine",
                "value": 1.0,
                "unit": "mg/dl",
                "status": "rejected",
                "usable": False,
            },
            {
                "feature": "not_a_feature",
                "value": 1,
                "status": "valid",
                "usable": True,
            },
        ],
        "conditions": [
            {"condition": "Diabetes", "evidence_features": ["hba1c"]},
        ],
    }


def test_explain_report_explains_usable_values_and_says_why_it_skipped(
    offline_settings,
):
    from app.services.explanation import explain_report

    result = explain_report(
        _report(), llm=FakeTextClient(_APPROVABLE), settings=offline_settings
    )

    features = [e.feature for e in result.explanations]
    assert features == ["hba1c"]
    assert result.generated_count == 1
    reasons = {row["feature"]: row["reason"] for row in result.skipped}
    assert reasons["creatinine"] == "value_not_usable"
    assert reasons["not_a_feature"] == "not_a_canonical_feature"


def test_explain_report_passes_the_conditions_the_feature_contributed_to(
    offline_settings,
):
    from app.services.explanation import explain_report

    result = explain_report(
        _report(), llm=FakeTextClient(_APPROVABLE), settings=offline_settings
    )
    assert result.explanations[0].conditions == ("Diabetes",)


def test_explain_report_does_not_spend_a_call_on_a_profile_answer(
    offline_settings,
):
    """Age, sex and BMI are context the assessment used, not results.

    They arrive in `laboratory_values` alongside the printed values, so they
    were candidates for explanation -- three model calls spent writing "this
    test measures your age" while a real cholesterol result went unexplained
    for want of budget.
    """
    from app.services.explanation import explain_report

    report = _report()
    report["laboratory_values"].append(
        {
            "feature": "age",
            "value": 58,
            "unit": "years",
            "status": "valid",
            "usable": True,
            "source": "patient_profile",
        }
    )

    fake = FakeTextClient(_APPROVABLE)
    result = explain_report(report, llm=fake, settings=offline_settings)

    assert "age" not in [e.feature for e in result.explanations]
    reasons = {row["feature"]: row["reason"] for row in result.skipped}
    assert reasons["age"] == "not_a_laboratory_value"
    # And no call was made for it.
    assert len(fake.prompts) == len(result.explanations)


def test_a_row_with_no_source_at_all_is_still_explained(offline_settings):
    """A missing `source` is not evidence that a value came from the profile.

    `LaboratoryValue.source` is `Optional[str] = None`, so an older stored
    report or a hand-built row can arrive without one. Requiring the field to
    EQUAL "lab_report" would skip every such row and explain nothing at all.
    """
    from app.services.explanation import explain_report

    report = _report()
    assert "source" not in report["laboratory_values"][0]

    result = explain_report(
        report, llm=FakeTextClient(_APPROVABLE), settings=offline_settings
    )
    assert [e.feature for e in result.explanations] == ["hba1c"]


def test_a_row_past_the_limit_is_not_blamed_on_the_limit_when_it_was_never_eligible(
    offline_settings,
):
    """Eligibility is decided before the budget.

    With the limit checked first, every row past the cap came back as
    `explanation_limit_reached` -- including rows that were never eligible at
    all -- so a caller could not tell "we ran out" from "there was nothing
    here to explain".
    """
    from app.services.explanation import explain_report

    result = explain_report(
        _report(),
        llm=FakeTextClient(_APPROVABLE),
        settings=offline_settings,
        max_explanations=0,
    )

    reasons = {row["feature"]: row["reason"] for row in result.skipped}
    assert reasons["hba1c"] == "explanation_limit_reached"
    # These two are not the budget's fault and must not say they are.
    assert reasons["creatinine"] == "value_not_usable"
    assert reasons["not_a_feature"] == "not_a_canonical_feature"


def test_explain_report_honours_the_call_limit(offline_settings):
    from app.services.explanation import explain_report

    fake = FakeTextClient(_APPROVABLE)
    result = explain_report(
        _report(), llm=fake, settings=offline_settings, max_explanations=0
    )
    assert result.explanations == ()
    assert fake.prompts == []


def test_explain_report_accepts_a_pydantic_report_too(offline_settings):
    """The Node backend sends a dict; Modules 27/32 hold the object."""
    from app.services.explanation import explain_report
    from app.schemas.report import ClinicalReport, LaboratoryValue

    report = ClinicalReport(
        report_version="1.0.0",
        laboratory_values=[
            LaboratoryValue(
                feature="hba1c",
                value=6.8,
                unit="%",
                status="valid",
                usable=True,
                reference_low=4.0,
                reference_high=5.6,
            )
        ],
    )
    result = explain_report(
        report, llm=FakeTextClient(_APPROVABLE), settings=offline_settings
    )
    assert [e.feature for e in result.explanations] == ["hba1c"]


# --------------------------------------------------------------------------
# The published policy
# --------------------------------------------------------------------------


def test_the_policy_states_the_architecture_and_the_prohibitions():
    from app.services.explanation import explanation_policy_document

    document = explanation_policy_document()
    assert document["module"] == 23
    assert document["pipeline"][1] == "LLM"
    assert document["pipeline"][2].startswith("Module 24")
    assert document["prohibitions_in_prompt"]
    assert "guarded_generation" in document["policy"]


def test_the_cap_covers_every_laboratory_feature():
    """THE CHECK THAT SHOULD HAVE EXISTED WHEN THE CAP WAS LAST RAISED.

    `DEFAULT_MAX_EXPLANATIONS` bounds how many per-feature explanations one
    report may generate. It has now silently started dropping results TWICE,
    both times because the feature catalogue grew and nothing connected the
    two numbers:

      * at 6, a report with eight laboratory values lost two;
      * at 10, the complete blood count took `LAB_FEATURES` from 8 to 20 and
        `Test 3.pdf` lost six -- neutrophils, lymphocytes, monocytes,
        eosinophils, basophils and platelet_count, which is the whole
        differential, because they sit last in row order.

    Both times the reader was told a count rather than shown the results. A
    cap is a legitimate bound on model calls; a cap that quietly falls behind
    the catalogue is a feature disappearing from a medical document.

    This does not assert a NUMBER -- it asserts the RELATIONSHIP, so raising
    it stays a deliberate edit and growing the catalogue past it cannot be
    silent.
    """
    from app.data.feature_catalog import LAB_FEATURES
    from app.services.explanation import DEFAULT_MAX_EXPLANATIONS

    assert DEFAULT_MAX_EXPLANATIONS >= len(LAB_FEATURES), (
        f"{len(LAB_FEATURES)} laboratory features and a cap of "
        f"{DEFAULT_MAX_EXPLANATIONS}: a report mapping them all would leave "
        f"{len(LAB_FEATURES) - DEFAULT_MAX_EXPLANATIONS} results with no "
        "explanation, and the reader would be told a count rather than shown "
        "them. Raise the cap in app/services/explanation.py, and read its "
        "note on what each explanation costs in model calls."
    )
