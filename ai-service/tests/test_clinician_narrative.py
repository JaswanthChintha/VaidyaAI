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


#: WHAT THE APPENDED CAVEAT NOW SAYS, and it is composed from the metrics
#: rather than quoted from the payload. The old note was
#: `limitations.author_note.text`, written in plain language for a lay reader
#: -- a paragraph of methodology narrative in a document headed "Summary for a
#: healthcare professional". The reader objected to exactly that, and the
#: metrics were already in the same structure.
MODEL_METRICS = {
    "metrics_available": True,
    "roc_auc": 0.9987129987129988,
    "precision_at_operating_threshold": 0.968421052631579,
    "recall_at_operating_threshold": 0.983957219251337,
    "operating_threshold": 0.3673979778714104,
    "measured_on": "held-out test split",
    "variant": "without_hypertension",
}

MODEL_NOTE = (
    "Kidney Disease: flagged by a Random Forest -- ROC-AUC 0.999, "
    "precision 0.97 / recall 0.98, at an operating threshold of 0.37, "
    "measured on held-out test split, variant: without hypertension. "
    "An estimated probability from comparable records, not a measurement of "
    "this patient and not a diagnosis."
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
                        "ml": {
                            "model_name": "Random Forest",
                            "limitations": dict(MODEL_METRICS),
                        },
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


# --------------------------------------------------------------------------
# THE ASSESSED SUBSET IS NOT "THE REPORTED VALUES"
#
# Found by a reader looking at Test 2's clinician summary, which opened:
#
#   "The reported values are GLYSOLATED HAEMOGLOBIN ( HBA1C) 5.9 %, Random
#    Blood Sugar 134.7 mg/dl, Haemoglobin 10.6 g/dl, and SERUM CREATININE
#    0.99 mg/dl."
#
# The laboratory reported TWENTY-ONE parameters. Seventeen were read, found to
# map to no feature this platform assesses, and set aside -- among them a CRP
# of 12.1 mg/L, an SGPT of 101.9 U/L and an ESR of 35 mm/hr. The model was
# obeying its prompt, which labelled the assessed four "REPORTED VALUES".
# --------------------------------------------------------------------------


def _summary_with_unassessed(count: int = 17) -> dict:
    summary = _summary()
    summary["data_quality"] = {"unmapped_count": count}
    return summary


def test_the_unassessed_count_is_collected(offline_settings):
    facts = collect_facts(_summary_with_unassessed())
    assert facts.unmapped_count == 17


def test_the_prompt_does_not_call_the_assessed_subset_the_reported_values(
    offline_settings,
):
    """THE LABEL IS WHAT THE MODEL REPEATED, so the label is what changed.

    A stronger instruction would not have helped: the model was told these
    were the reported values and it said so.
    """
    llm = FakeLLM(_faithful())
    write_clinician_summary(
        _summary_with_unassessed(), llm=llm, settings=offline_settings
    )
    prompt = llm.prompts[0]
    assert "REPORTED VALUES:" not in prompt
    assert "VALUES THIS TOOL ASSESSED" in prompt
    assert "NOT all the values on the report" in prompt


def test_the_prompt_states_how_many_were_not_assessed(offline_settings):
    llm = FakeLLM(_faithful())
    write_clinician_summary(
        _summary_with_unassessed(), llm=llm, settings=offline_settings
    )
    prompt = llm.prompts[0]
    assert "NOT ASSESSED:" in prompt
    assert "17" in prompt
    # NOT found normal. The distinction is the entire point.
    assert "NOT found normal" in prompt


def test_a_narrative_that_omits_the_unassessed_count_is_thrown_away(
    offline_settings,
):
    """`_faithful()` states every value and every finding and says nothing
    about the seventeen -- which is exactly the document the reader saw."""
    llm = FakeLLM(_faithful())
    result = write_clinician_summary(
        _summary_with_unassessed(), llm=llm, settings=offline_settings
    )
    assert result.outcome == OUTCOME_FACTS_MISSING
    assert "unmapped_count" in result.missing_facts
    assert "unmapped_sentence" in result.missing_facts


def test_a_narrative_that_states_it_is_accepted(offline_settings):
    body = _faithful() + (
        " The laboratory reported 17 further parameters that this platform "
        "does not assess; they remain on the source report for review."
    )
    llm = FakeLLM(body)
    result = write_clinician_summary(
        _summary_with_unassessed(), llm=llm, settings=offline_settings
    )
    assert result.outcome == OUTCOME_GENERATED, result.missing_facts
    assert "17" in result.text


def test_the_count_is_a_permitted_number(offline_settings):
    """INSTRUCTED AND THEREFORE PERMITTED.

    The prompt requires the document to state the count. If the validator's
    numeric grounding does not permit it, the narrative is refused for obeying
    its own instruction -- §6as's defect from the other direction.
    """
    body = _faithful() + (
        " A further 17 parameters were reported and are not assessed here."
    )
    llm = FakeLLM(body)
    result = write_clinician_summary(
        _summary_with_unassessed(), llm=llm, settings=offline_settings
    )
    assert result.outcome == OUTCOME_GENERATED, result.missing_facts


def test_the_substance_is_accepted_in_wording_we_did_not_choose(offline_settings):
    """This file has already refused a faithful narrative by insisting on its
    own phrasing (see the model-only check). The alternation is wide."""
    for phrasing in (
        "17 other parameters were set aside and not evaluated by this tool.",
        "A further 17 results fall outside the scope of this assessment and "
        "were not analysed.",
        "17 reported parameters are not covered here.",
    ):
        llm = FakeLLM(_faithful() + " " + phrasing)
        result = write_clinician_summary(
            _summary_with_unassessed(), llm=llm, settings=offline_settings
        )
        assert result.outcome == OUTCOME_GENERATED, (phrasing, result.missing_facts)


def test_a_report_with_nothing_unassessed_gains_no_sentence(offline_settings):
    """No count, no requirement, no invented caveat. A report whose every
    parameter mapped must not be told that some did not."""
    llm = FakeLLM(_faithful())
    result = write_clinician_summary(_summary(), llm=llm, settings=offline_settings)
    assert result.outcome == OUTCOME_GENERATED, result.missing_facts
    assert "NOT ASSESSED:" not in llm.prompts[0]


# --------------------------------------------------------------------------
# THE MODEL CAVEAT IS FOR A CLINICIAN, SO IT IS THE METRICS
#
# The reader, on Test 3's page: the document should not carry "un-necessary
# things like model, datasets and all". It was carrying
# `limitations.author_note.text` -- "It was developed on one small dataset in
# which the two groups separated unusually cleanly ..." -- which is methodology
# narrative written for a lay reader.
#
# §6w's rule is untouched and is why the caveat still exists at all: a
# model-derived flag may NOT appear without its limitation. Only the register
# changed.
# --------------------------------------------------------------------------


def _ml_basis(condition: str, limits: dict, model: str = "Random Forest") -> dict:
    return {
        "condition": condition,
        "bases": [
            {
                "status": "Indicated",
                "assessed": True,
                "source_kind": "machine_learning",
                "ml": {"model_name": model, "limitations": limits},
            }
        ],
    }


def test_the_caveat_states_the_metrics_not_the_methodology(offline_settings):
    llm = FakeLLM(_faithful())
    result = write_clinician_summary(_summary(), llm=llm, settings=offline_settings)
    assert result.outcome == OUTCOME_GENERATED, result.missing_facts
    text = result.text
    assert "ROC-AUC 0.999" in text
    assert "recall 0.98" in text
    assert "operating threshold of 0.37" in text
    # And NOT the lay paragraph it replaced.
    assert "small dataset" not in text
    assert "flatters" not in text


def test_the_auc_keeps_three_places_so_it_is_not_read_as_perfect(offline_settings):
    """0.9987 at two places is "1.00", which reads as a perfect classifier --
    the single impression this note exists to prevent."""
    llm = FakeLLM(_faithful())
    result = write_clinician_summary(_summary(), llm=llm, settings=offline_settings)
    assert "ROC-AUC 1.00" not in result.text
    assert "ROC-AUC 0.999" in result.text


def test_a_model_with_no_author_note_still_gets_a_caveat(offline_settings):
    """THE COVERAGE THIS CHANGE GAINS.

    `author_note` is NOT_PRESENT for the diabetes model, so a report flagging
    both Diabetes and Kidney Disease carried ONE caveat. Diabetes runs at
    recall 0.70 -- close to a third of true cases not flagged -- which is
    exactly the figure a clinician needs and the old note omitted entirely.
    """
    summary = _summary()
    summary["assessments"] = summary["assessments"] + [
        _ml_basis(
            "Diabetes",
            {
                "metrics_available": True,
                "roc_auc": 0.9733748420857805,
                "precision_at_operating_threshold": 0.9218266253869969,
                "recall_at_operating_threshold": 0.7022405660377359,
                "operating_threshold": 0.7932221243150029,
                "measured_on": "held-out test split",
                "variant": "neither",
                # The shape that produced NO note at all before.
                "author_note": {"text": None, "state": "NOT_PRESENT"},
            },
        )
    ]
    llm = FakeLLM(_faithful())
    result = write_clinician_summary(summary, llm=llm, settings=offline_settings)
    assert result.outcome == OUTCOME_GENERATED, result.missing_facts
    assert "Diabetes: flagged by a Random Forest" in result.text
    assert "recall 0.70" in result.text
    # `variant: neither` is not a variant and must not be printed as one.
    assert "variant: neither" not in result.text


def test_a_model_with_no_metrics_says_so_rather_than_nothing(offline_settings):
    """Silence would read as "no limitation", which is the §6w defect."""
    summary = _summary()
    summary["assessments"] = [
        _ml_basis("Kidney Disease", {"metrics_available": False})
    ]
    llm = FakeLLM(_faithful())
    result = write_clinician_summary(summary, llm=llm, settings=offline_settings)
    assert result.outcome == OUTCOME_GENERATED, result.missing_facts
    assert "No validation metrics are recorded" in result.text
    assert "not diagnostic" in result.text.lower()


def test_the_prompt_asks_for_a_clinician_register(offline_settings):
    llm = FakeLLM(_faithful())
    write_clinician_summary(_summary(), llm=llm, settings=offline_settings)
    prompt = llm.prompts[0].lower()
    assert "the reader is a clinician" in prompt
    assert "no lay glosses" in prompt
    assert "handover note" in prompt


@pytest.mark.parametrize(
    "measured_on,expected",
    [
        # THE REAL PRODUCER STRING. The trailing clause names an internal file.
        ("held-out test split, see the metrics artifact", "held-out test split"),
        ("held-out test split, refer to the artifact", "held-out test split"),
        # A MEANINGFUL CLAUSE IS NOT A POINTER AND MUST SURVIVE. This is the
        # difference between trimming and mangling the producer's own text.
        ("held-out test split, stratified by age", "held-out test split, stratified by age"),
        ("held-out test split", "held-out test split"),
    ],
)
def test_only_the_artifact_pointer_is_trimmed(offline_settings, measured_on, expected):
    summary = _summary()
    limits = dict(MODEL_METRICS)
    limits["measured_on"] = measured_on
    summary["assessments"] = [_ml_basis("Kidney Disease", limits)]

    llm = FakeLLM(_faithful())
    result = write_clinician_summary(summary, llm=llm, settings=offline_settings)
    assert result.outcome == OUTCOME_GENERATED, result.missing_facts
    assert f"measured on {expected}" in result.text
    assert "metrics artifact" not in result.text
