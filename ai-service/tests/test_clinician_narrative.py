"""Module 32's written handover note.

Almost every test here is about the narrative being THROWN AWAY. That is the
point of the design: the composed passage is what a caller renders whenever
this refuses, so the worst case is today's behaviour and a partial or
unqualified narrative can never reach a reader.
"""

from __future__ import annotations

import pytest

from app.services.clinician_narrative import (
    CLOSING_LINE,
    OUTCOME_FACTS_MISSING,
    OUTCOME_GENERATED,
    OUTCOME_NO_MODEL,
    OUTCOME_WITHHELD_BY_SAFETY,
    collect_facts,
    write_clinician_summary,
)

@pytest.fixture()
def offline_settings():
    """Settings with no API key -- the state the whole suite runs in."""
    from app.config import Settings

    return Settings(_env_file=None)


MODEL_NOTE = (
    "A COARSE screening signal, not a precise one. At the cut-off used here, "
    "roughly two out of every three people it flags do NOT have heart disease."
)


def _summary() -> dict:
    """The shape Module 32 produces, reduced to what the narrative reads."""
    return {
        # THE PRODUCER'S SHAPE, read off a live Module 32 response: the
        # unsupplied answers are `null` on the tri-state keys, and there is no
        # `not_supplied` list anywhere on the payload.
        "patient": {
            "age": 58,
            "gender": "male",
            "bmi": 26.42,
            "hypertension": None,
            "heart_disease": "no",
            "smoking_history": "never",
            "provided_fields": ["age", "gender", "bmi"],
        },
        "laboratory": {
            "rows": [
                # THE PRODUCER'S SHAPE, read off a live Module 32 response:
                # the name and the source live under `provenance`, and there
                # is no top-level `source` on these rows at all.
                {
                    "display_name": "Glycated haemoglobin, NGSP %",
                    "value": 8.4,
                    "unit": "%",
                    "usable": True,
                    "provenance": {
                        "source": "lab_report",
                        "original_test_name": {"text": "HbA1c"},
                    },
                    "reference_low": None,
                    "reference_high": None,
                },
                {
                    "display_name": "Blood glucose",
                    "value": 186,
                    "unit": "mg/dl",
                    "usable": True,
                    "provenance": {
                        "source": "lab_report",
                        "original_test_name": {"text": "Glucose"},
                    },
                    "reference_low": None,
                    "reference_high": None,
                },
                # A PROFILE ANSWER, carrying the catalog's internal note as its
                # display name. On the first live run this opened the document
                # with "Self-described gender as stored by Module 2 as male".
                {
                    "display_name": "Self-described gender as stored by Module 2.",
                    "feature": "gender",
                    "value": "male",
                    "usable": True,
                    "provenance": {"source": "patient_profile"},
                },
            ]
        },
        "abnormal_findings": ["Diabetes", "Kidney Disease"],
        "normal_findings": ["Anemia"],
        "unassessed_conditions": ["Heart Disease"],
        "assessments": [
            {
                "condition": "Kidney Disease",
                "bases": [
                    {
                        "status": "Indicated",
                        "assessed": True,
                        "source_kind": "machine_learning",
                        "ml": {"limitations": {"author_note": {"text": MODEL_NOTE}}},
                    }
                ],
            }
        ],
    }


class FakeLLM:
    """Returns whatever it was given, and records the prompts it saw."""

    def __init__(self, reply):
        self._reply = reply
        self.prompts = []

    def generate_text(self, prompt):
        self.prompts.append(prompt)
        reply = self._reply
        return reply(len(self.prompts)) if callable(reply) else reply


def _faithful() -> str:
    """What the MODEL returns -- the body only.

    It does not contain the limitation note or the closing line: the model is
    told not to write them and they are appended after approval, so it cannot
    paraphrase or drop them.
    """
    return (
        "This 58-year-old male was assessed from a single laboratory report. "
        "No value was available for hypertension. "
        "The source report printed no reference intervals. "
        "HbA1c was 8.4 % and glucose was 186 mg/dl. "
        "Diabetes was flagged. Kidney Disease was flagged by the model alone, "
        "with no measured value crossing a cut-off for it. Anemia was assessed "
        "and not flagged, and Heart Disease could not be assessed at all."
    )


# --------------------------------------------------------------------------
# The four gates
# --------------------------------------------------------------------------


def test_no_model_means_no_generation_and_no_network(offline_settings):
    """The caller's fallback is the NORMAL path, not an error path."""
    result = write_clinician_summary(_summary(), llm=None, settings=offline_settings)
    assert result.outcome == OUTCOME_NO_MODEL
    assert result.text is None
    assert result.notice
    assert result.llm_calls_made == 0
    assert result.safety.validated is False


def test_a_faithful_narrative_is_returned(offline_settings):
    llm = FakeLLM(_faithful())
    result = write_clinician_summary(_summary(), llm=llm, settings=offline_settings)
    assert result.outcome == OUTCOME_GENERATED, result.missing_facts
    assert result.text
    assert result.notice is None
    assert result.safety.validated is True


def test_a_narrative_that_drops_a_value_is_thrown_away(offline_settings):
    # The number is the one thing a clinician reads this document for.
    llm = FakeLLM(_faithful().replace("186 mg/dl", "a raised glucose"))
    result = write_clinician_summary(_summary(), llm=llm, settings=offline_settings)
    assert result.outcome == OUTCOME_FACTS_MISSING
    assert result.text is None
    assert any("186" in gap for gap in result.missing_facts)


def test_a_narrative_that_drops_AN_ABSENCE_is_thrown_away(offline_settings):
    # The sentence a summariser drops first. "Heart Disease could not be
    # assessed" missing turns an open question into silence, and silence on
    # this page reads as nothing to report.
    llm = FakeLLM(
        _faithful().replace(", and Heart Disease could not be assessed at all", "")
    )
    result = write_clinician_summary(_summary(), llm=llm, settings=offline_settings)
    assert result.outcome == OUTCOME_FACTS_MISSING
    assert "unassessed:Heart Disease" in result.missing_facts


def test_a_narrative_that_drops_a_flagged_topic_is_thrown_away(offline_settings):
    llm = FakeLLM(_faithful().replace("Diabetes was flagged. ", ""))
    result = write_clinician_summary(_summary(), llm=llm, settings=offline_settings)
    assert result.outcome == OUTCOME_FACTS_MISSING
    assert "flagged:Diabetes" in result.missing_facts


def test_the_model_note_and_closing_line_are_APPENDED_not_copied(offline_settings):
    """The model never handles the safety-critical sentences.

    The first version told it to copy them and verified the copy. That was
    unsatisfiable: the kidney note is judged UNHEDGED_INTERPRETIVE_CLAIM by
    this safety context -- it passes Module 32 own transcription check, which
    applies different controls -- so a narrative REQUIRED to contain it could
    never be approved, and every live attempt was refused by the safety note
    itself.
    """
    llm = FakeLLM(_faithful())
    result = write_clinician_summary(_summary(), llm=llm, settings=offline_settings)

    assert result.outcome == OUTCOME_GENERATED, result.missing_facts
    # The model was told not to write them...
    assert MODEL_NOTE not in llm.prompts[0]
    assert "do not write any closing disclaimer" in llm.prompts[0].lower()
    # ...and they are in the finished text anyway, verbatim, because we put
    # them there.
    assert MODEL_NOTE in result.text
    assert result.text.rstrip().endswith(CLOSING_LINE)


def test_the_model_only_distinction_must_survive(offline_settings):
    """MEMORY.md 6w first kept thing.

    A clinician told "Kidney Disease flagged", with no mention that no measured
    value crossed anything, is being told something the analysis did not find.
    """
    body = _faithful().replace(
        "Kidney Disease was flagged by the model alone, with no measured value "
        "crossing a cut-off for it.",
        "Kidney Disease was flagged.",
    )
    llm = FakeLLM(body)
    result = write_clinician_summary(_summary(), llm=llm, settings=offline_settings)
    assert result.outcome == OUTCOME_FACTS_MISSING
    assert "model_only_distinction" in result.missing_facts


def test_an_unsafe_narrative_never_reaches_the_caller(offline_settings):
    """Module 24, on the same footing as every other generated text."""
    unsafe = "This patient has diabetes and should start metformin immediately."
    llm = FakeLLM(unsafe)
    result = write_clinician_summary(_summary(), llm=llm, settings=offline_settings)
    assert result.outcome == OUTCOME_WITHHELD_BY_SAFETY
    assert result.text is None
    # And not a word of it is carried on the object.
    assert "metformin" not in result.model_dump_json()


def test_the_refused_text_is_never_stored_anywhere(offline_settings):
    llm = FakeLLM(_faithful().replace("186 mg/dl", "CANARY-dropped-value"))
    result = write_clinician_summary(_summary(), llm=llm, settings=offline_settings)
    assert "CANARY" not in result.model_dump_json()


# --------------------------------------------------------------------------
# The prompt
# --------------------------------------------------------------------------


def test_the_prompt_carries_the_facts_and_forbids_inventing_numbers(offline_settings):
    llm = FakeLLM(_faithful())
    write_clinician_summary(_summary(), llm=llm, settings=offline_settings)
    prompt = llm.prompts[0]
    # NAMED values. Bare numbers produced "the reported values are 8.4 %,
    # 186 mg/dl, 14.8 g/dl..." on the first live run -- a list of quantities
    # of nothing, worse than the passage it was meant to improve on.
    assert "HbA1c 8.4 %" in prompt
    assert "Glucose 186 mg/dl" in prompt
    assert "Diabetes" in prompt and "Heart Disease" in prompt
    assert "Never introduce a number that is not below" in prompt


def test_the_prompt_forbids_naming_the_software(offline_settings):
    """The whole reason the user asked for this."""
    llm = FakeLLM(_faithful())
    write_clinician_summary(_summary(), llm=llm, settings=offline_settings)
    assert "Do not name or describe the software" in llm.prompts[0]


def test_a_safety_refusal_is_retried_with_the_codes_quoted_back(offline_settings):
    def reply(attempt):
        if attempt == 1:
            return f"This patient has diabetes. {MODEL_NOTE} {CLOSING_LINE}"
        return _faithful()

    llm = FakeLLM(reply)
    result = write_clinician_summary(_summary(), llm=llm, settings=offline_settings)
    assert result.outcome == OUTCOME_GENERATED
    assert len(llm.prompts) == 2
    assert "refused by a safety check" in llm.prompts[1]


# --------------------------------------------------------------------------
# Facts
# --------------------------------------------------------------------------


def test_a_note_from_a_model_that_flagged_NOTHING_is_not_required(offline_settings):
    """MEMORY.md 6w: a note qualifies an OUTPUT.

    A model that returned Not Indicated produced no output this document
    reports, and requiring its caveat would put a warning under a finding that
    model disagreed with.
    """
    summary = _summary()
    summary["assessments"].append(
        {
            "condition": "Heart Disease",
            "bases": [
                {
                    "status": "Not Indicated",
                    "assessed": True,
                    "ml": {"limitations": {"author_note": {"text": "UNRELATED NOTE"}}},
                }
            ],
        }
    )
    facts = collect_facts(summary)
    assert "UNRELATED NOTE" not in facts.model_notes


def test_a_narrative_that_drops_A_MISSING_PROFILE_ANSWER_is_thrown_away(
    offline_settings,
):
    """MEMORY.md 6w third kept thing: EVERY absence.

    Lost on a live run that passed every other gate. The prose read well,
    carried every value and every finding, and quietly stopped mentioning that
    three profile answers were never supplied.
    """
    llm = FakeLLM(_faithful().replace("No value was available for hypertension. ", ""))
    result = write_clinician_summary(_summary(), llm=llm, settings=offline_settings)
    assert result.outcome == OUTCOME_FACTS_MISSING
    assert "not_supplied:hypertension" in result.missing_facts


def test_a_narrative_that_drops_THE_NO_INTERVALS_SENTENCE_is_thrown_away(
    offline_settings,
):
    """The one sentence that stops eight bare numbers reading as in range.

    Also lost on that live run.
    """
    llm = FakeLLM(
        _faithful().replace("The source report printed no reference intervals. ", "")
    )
    result = write_clinician_summary(_summary(), llm=llm, settings=offline_settings)
    assert result.outcome == OUTCOME_FACTS_MISSING
    assert "no_intervals_sentence" in result.missing_facts


def test_the_no_intervals_fact_is_carried(offline_settings):
    facts = collect_facts(_summary())
    assert facts.no_intervals is True


def test_an_unsupplied_answer_is_derived_from_the_payload_shape(offline_settings):
    """There is no `not_supplied` list; the nulls are the signal.

    Reading one produced an empty tuple on every real report, so the absence
    check it fed could never fire -- the live narrative dropped the sentence
    and the gate reported nothing missing.
    """
    facts = collect_facts(_summary())
    assert facts.not_supplied == ("hypertension",)


def test_a_profile_answer_is_not_a_reported_value(offline_settings):
    """And its display name never reaches the document.

    `feature_catalog` stores an internal note as the display name for
    `gender` -- "Self-described gender as stored by Module 2." -- which is
    MEMORY.md 6y, still open at source. The first live narrative opened with
    it, because the row filter looked for a top-level `source` that these rows
    do not carry.
    """
    facts = collect_facts(_summary())
    joined = " ".join(facts.values)
    assert "Module 2" not in joined
    assert "male" not in joined
    assert "HbA1c 8.4 %" in joined


def test_the_laboratory_printed_name_is_preferred(offline_settings):
    """A clinician matches the row against the paper in front of them."""
    facts = collect_facts(_summary())
    joined = " ".join(facts.values)
    assert "HbA1c 8.4 %" in joined
    assert "Glycated haemoglobin" not in joined
