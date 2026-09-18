"""Module 32's written handover note.

Almost every test here is about the narrative being THROWN AWAY. That is the
point of the design: the composed passage is what a caller renders whenever
this refuses, so the worst case is today's behaviour and a partial or
unqualified narrative can never reach a reader.
"""

from __future__ import annotations

import pytest

from app.services.clinician_narrative import (
    _model_notes,
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
                    # OUT OF RANGE ON THE LABORATORY'S OWN INTERVAL, which is
                    # a different fact from crossing one of this tool's
                    # cut-offs. Both belong in the note.
                    "position": "above_reference_interval",
                    "printed_flag": "high",
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
                # THE REASON, AS THE RULE ENGINE STATES IT. The note is built
                # from these: the parameter, its value, the comparator, the
                # threshold and the rule's own classification. "What was
                # flagged and why" is not prose -- it is already on the
                # payload.
                "condition": "Diabetes",
                "bases": [
                    {
                        "status": "Indicated",
                        "assessed": True,
                        "source_kind": "clinical_rule",
                        "rule": {
                            "triggering_values": [
                                {
                                    "display_name": "Glycated haemoglobin, NGSP %",
                                    "value": 8.4,
                                    "unit": "%",
                                    "comparator": ">=",
                                    "threshold": 6.5,
                                    "classification": "at or above the ADA diabetes-range HbA1c threshold of 6.5 %",
                                },
                                {
                                    "display_name": "Blood glucose",
                                    "value": 186,
                                    "unit": "mg/dl",
                                    "comparator": ">=",
                                    "threshold": 140,
                                    "classification": "at or above the impaired-glucose-tolerance boundary",
                                },
                            ]
                        },
                    }
                ],
            },
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
        "This 58-year-old male had an HbA1c of 8.4 % and a glucose of "
        "186 mg/dl. Diabetes was flagged because HbA1c 8.4 % is at or above "
        "the ADA diabetes-range threshold of 6.5 % and glucose 186 mg/dl is "
        "at or above the impaired-glucose-tolerance boundary of 140 mg/dl. "
        "Kidney Disease was flagged by the statistical model alone, and no "
        "measured value crossed a cut-off for it. Glucose 186 mg/dl is above "
        "the printed reference interval."
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


def test_a_narrative_that_drops_a_flagged_topic_is_thrown_away(offline_settings):
    llm = FakeLLM((_faithful()
        .replace("Diabetes was flagged", "It was flagged")
        # ALSO the incidental mention inside the threshold wording --
        # the check is a substring match, so "ADA diabetes-range" alone
        # would satisfy it and the test would pass for the wrong reason.
        .replace("ADA diabetes-range", "ADA reference")
    ))
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
    # ...and the CLOSING LINE is appended anyway, because we put it there.
    assert result.text.rstrip().endswith(CLOSING_LINE)
    # THE MODEL NOTE IS NO LONGER IN THE DOCUMENT AT ALL -- it moved to the
    # page. See `test_the_document_carries_no_model_or_metric_talk`.
    assert MODEL_NOTE not in result.text


def test_the_model_only_distinction_must_survive(offline_settings):
    """MEMORY.md 6w first kept thing.

    A clinician told "Kidney Disease flagged", with no mention that no measured
    value crossed anything, is being told something the analysis did not find.
    """
    body = _faithful().replace(
        "Kidney Disease was flagged by the statistical model alone, and no "
        "measured value crossed a cut-off for it.",
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
    assert "Diabetes" in prompt
    assert "Never introduce a number that is not below" in prompt
    # AND THE THRESHOLD IT CROSSED, which is the "why" the note is made of.
    assert "6.5" in prompt
    # "Heart Disease" is an unassessed topic and is deliberately NOT here any
    # more: the note states what was flagged and why, and nothing about what
    # was assessed, not assessed or not supplied.
    assert "Heart Disease" not in prompt
    assert "COULD NOT BE ASSESSED" not in prompt
    assert "NOT SUPPLIED" not in prompt


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


# --------------------------------------------------------------------------
# A PURE CLINICAL SUMMARY -- THE READER'S INSTRUCTION, GIVEN THREE TIMES
#
# A clinician reading a handover note is not reading a model card, and a
# clinical summary does not editorialise about the tool that produced it.
#
# NEITHER REQUIREMENT IS DISCARDED, BOTH ARE MOVED OFF THE PROSE:
#   * the parameters this platform does not assess are LISTED on the page with
#     their values, which answers the completeness problem better than a
#     sentence counting them ever did;
#   * the model metrics render beside the page's data-quality furniture, which
#     is what keeps 6w's rule -- a model-derived flag never reaches a reader
#     with no indication of what produced it.
# --------------------------------------------------------------------------


def test_the_document_carries_no_model_or_metric_talk(offline_settings):
    llm = FakeLLM(_faithful())
    result = write_clinician_summary(_summary(), llm=llm, settings=offline_settings)
    assert result.outcome == OUTCOME_GENERATED, result.missing_facts

    lowered = result.text.lower()
    for banned in (
        "roc-auc",
        "operating threshold",
        "random forest",
        "dataset",
        "held-out",
        "metrics artifact",
    ):
        assert banned not in lowered, banned


# --- the metrics themselves, which the PAGE renders -----------------------


def _ml_case(condition, limits):
    return {
        "condition": condition,
        "bases": [
            {
                "status": "Indicated",
                "assessed": True,
                "ml": {"model_name": "Random Forest", "limitations": limits},
            }
        ],
    }


# --------------------------------------------------------------------------
# WHAT THE NOTE CONTAINS, AND IT CONTAINS NOTHING ELSE
#
# The owner's spec, given after reading three drafts of it:
#
#   "the summary should contain what diseases are flagged and why that's it
#    no other information like these were assessed and these were not
#    assessed ... and mention those parameters which are not in range"
#
# Everything below is that sentence, turned into checks.
# --------------------------------------------------------------------------


def test_the_reason_is_the_value_and_the_threshold_it_crossed(offline_settings):
    """THE "WHY" IS NOT PROSE -- it is already on the payload, as the rule's
    own triggering values. The note is built from them."""
    facts = collect_facts(_summary())
    reasons = facts.triggering["Diabetes"]
    joined = " ".join(reasons)
    assert "HbA1c 8.4 %" in joined
    assert ">= 6.5" in joined
    assert "ADA diabetes-range" in joined
    assert "Glucose 186 mg/dl" in joined


def test_a_parameter_out_of_the_laboratorys_own_interval_is_carried(
    offline_settings,
):
    """SEPARATE FROM CROSSING ONE OF THIS TOOL'S CUT-OFFS, and both are wanted.

    A parameter can be marked high by the laboratory without crossing any
    threshold this tool holds, and it is still out of range.
    """
    facts = collect_facts(_summary())
    assert any("Glucose 186 mg/dl" in entry for entry in facts.out_of_range)
    assert any("above the printed reference interval" in e for e in facts.out_of_range)


def test_the_prompt_states_only_findings_reasons_and_out_of_range(offline_settings):
    llm = FakeLLM(_faithful())
    write_clinician_summary(_summary(), llm=llm, settings=offline_settings)
    prompt = llm.prompts[0]

    assert "FLAGGED -- Diabetes:" in prompt
    assert "OUT OF RANGE:" in prompt
    # None of the coverage vocabulary reaches the model at all.
    for banned in (
        "NOT SUPPLIED",
        "COULD NOT BE ASSESSED",
        "ASSESSED AND NOT FLAGGED",
        "MEASURED VALUES AVAILABLE",
        "NOT ASSESSED",
    ):
        assert banned not in prompt, banned


def test_the_note_says_nothing_about_coverage(offline_settings):
    llm = FakeLLM(_faithful())
    result = write_clinician_summary(_summary(), llm=llm, settings=offline_settings)
    assert result.outcome == OUTCOME_GENERATED, result.missing_facts

    lowered = result.text.lower()
    for banned in (
        "not assessed",
        "could not be assessed",
        "was assessed",
        "were assessed",
        "not supplied",
        "set aside",
        "not found normal",
        "does not assess",
    ):
        assert banned not in lowered, banned


def test_the_note_carries_no_model_or_metric_talk(offline_settings):
    llm = FakeLLM(_faithful())
    result = write_clinician_summary(_summary(), llm=llm, settings=offline_settings)
    lowered = result.text.lower()
    for banned in ("roc-auc", "precision", "operating threshold", "random forest",
                   "dataset", "held-out", "metrics artifact"):
        assert banned not in lowered, banned


def test_a_narrative_that_drops_A_FLAGGED_CONDITION_is_thrown_away(offline_settings):
    """The findings ARE the document now, so losing one is fatal."""
    llm = FakeLLM((_faithful()
        .replace("Diabetes was flagged", "It was flagged")
        # ALSO the incidental mention inside the threshold wording --
        # the check is a substring match, so "ADA diabetes-range" alone
        # would satisfy it and the test would pass for the wrong reason.
        .replace("ADA diabetes-range", "ADA reference")
    ))
    result = write_clinician_summary(_summary(), llm=llm, settings=offline_settings)
    assert result.outcome == OUTCOME_FACTS_MISSING
    assert "flagged:Diabetes" in result.missing_facts


def test_a_narrative_that_drops_THE_REASON_is_thrown_away(offline_settings):
    """A finding without its value is the half a clinician cannot act on."""
    llm = FakeLLM(_faithful().replace("8.4 %", "a crossed threshold"))
    result = write_clinician_summary(_summary(), llm=llm, settings=offline_settings)
    assert result.outcome == OUTCOME_FACTS_MISSING
    assert any("8.4" in gap for gap in result.missing_facts)


def test_the_laboratorys_printed_name_is_used_for_the_reason_too(offline_settings):
    """A clinician matches the row against the paper in front of them.

    The rule's triggering values carry the catalog's display name -- "Glycated
    haemoglobin, NGSP %" -- and the laboratory printed "HbA1c". The join puts
    the printed name back.
    """
    joined = " ".join(collect_facts(_summary()).triggering["Diabetes"])
    assert "HbA1c" in joined
    assert "NGSP" not in joined


# --------------------------------------------------------------------------
# A BORDERLINE FINDING IS NOT A FLAGGED ONE
# --------------------------------------------------------------------------
#
# READ OFF THE REAL CLINICIAN PAGE, 2026-09-18:
#
#     This tool flagged Obesity because Body mass index was 25.25 kg/m2
#     (>= 25, inside the WHO overweight band of 25.0-29.9).
#
# The sentence contradicts its own parenthetical -- 25.25 is overweight and
# obesity begins at 30.0. Module 8 had it right (BORDERLINE, LOW risk, and it
# says "overweight band" itself) and the composed document renders
# `Obesity (borderline)`. Only the WRITTEN narrative lost it, because
# `_facts_block` handed the model the word FLAGGED for every condition in
# `abnormal_findings` whatever its status.


def _borderline_summary() -> dict:
    """`_summary()` plus a BORDERLINE Obesity, as the producer returns it.

    The top-level `status` key is what `_qualified` reads, and the live
    payload carries it on every assessment -- checked against a real Module 32
    response rather than assumed.
    """
    summary = _summary()
    summary["abnormal_findings"] = ["Diabetes", "Kidney Disease", "Obesity"]
    summary["assessments"].append(
        {
            "condition": "Obesity",
            "status": "Borderline",
            "assessed": True,
            "bases": [
                {
                    "status": "Borderline",
                    "assessed": True,
                    "source_kind": "clinical_rule",
                    "rule": {
                        "triggering_values": [
                            {
                                "display_name": "Body mass index",
                                "value": 25.25,
                                "unit": "kg/m2",
                                "comparator": ">=",
                                "threshold": 25,
                                "classification": (
                                    "inside the WHO overweight band of 25.0-29.9"
                                ),
                            }
                        ]
                    },
                }
            ],
        }
    )
    return summary


def test_a_borderline_status_is_collected_and_an_indicated_one_is_not():
    from app.services.clinician_narrative import _qualified

    qualified = _qualified(_borderline_summary())
    assert qualified == {"Obesity": "Borderline"}
    # Diabetes and Kidney Disease are `Indicated`; naming them would make the
    # narrative hedge findings that were not hedged.
    assert "Diabetes" not in qualified


def test_the_model_is_told_BORDERLINE_and_not_FLAGGED():
    from app.services.clinician_narrative import _facts_block

    block = _facts_block(collect_facts(_borderline_summary()))
    assert "BORDERLINE -- Obesity:" in block
    assert "FLAGGED -- Obesity" not in block
    # The Indicated findings keep the word they had.
    assert "FLAGGED -- Diabetes:" in block


def test_a_narrative_that_calls_a_borderline_finding_flagged_is_a_gap():
    """THE CONTROL. A prompt instruction alone would not be one.

    A gap is fed back and the narrative regenerated; a second failure refuses
    it and the page renders the composed document, which has always said
    `Obesity (borderline)`. **The fallback is already correct**, which is what
    makes refusing safe.
    """
    from app.services.clinician_narrative import _missing

    facts = collect_facts(_borderline_summary())
    text = (
        "This tool flagged Obesity because Body mass index was 25.25 kg/m2 "
        "(>= 25, inside the WHO overweight band of 25.0-29.9)."
    )
    assert "status:Obesity" in _missing(text, facts)


@pytest.mark.parametrize(
    "phrasing",
    [
        "This tool recorded Obesity as borderline at 25.25 kg/m2.",
        "Borderline Obesity was recorded, at 25.25 kg/m2.",
        "Obesity (borderline) was recorded at 25.25 kg/m2.",
    ],
)
def test_the_gap_accepts_any_phrasing_that_carries_the_word(phrasing):
    """THE SUBSTANCE, NOT ONE PHRASING.

    The sibling `model_only_distinction` check records an earlier version that
    refused a live narrative for saying the right thing a different way. **A
    gate that always refuses is a feature that never ships.**
    """
    from app.services.clinician_narrative import _missing

    facts = collect_facts(_borderline_summary())
    assert "status:Obesity" not in _missing(phrasing, facts)


def test_the_word_must_be_NEAR_the_condition_not_loose_in_the_document():
    # Otherwise a borderline remark about something else satisfies it.
    from app.services.clinician_narrative import _missing

    facts = collect_facts(_borderline_summary())
    text = (
        "The glucose result was borderline in an earlier report. "
        "This tool flagged Obesity because Body mass index was 25.25 kg/m2."
    )
    assert "status:Obesity" in _missing(text, facts)


def test_an_all_indicated_summary_reports_no_status_gap():
    """The ANSWERING branch: this must not start refusing ordinary narratives."""
    from app.services.clinician_narrative import _missing

    facts = collect_facts(_summary())
    assert not [g for g in _missing(_faithful(), facts) if g.startswith("status:")]
