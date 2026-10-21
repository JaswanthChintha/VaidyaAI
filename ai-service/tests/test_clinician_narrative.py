from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.services.clinician_narrative import (
    _code_fingerprint,
    _facts_block,
    _model_notes,
    CLOSING_LINE,
    NARRATIVE_CODE_FINGERPRINT,
    NARRATIVE_VERSION,
    OUTCOME_FACTS_MISSING,
    OUTCOME_GENERATED,
    OUTCOME_NO_MODEL,
    OUTCOME_WITHHELD_BY_SAFETY,
    collect_facts,
    write_clinician_summary,
)

@pytest.fixture()
def offline_settings():
    from app.config import Settings

    return Settings(_env_file=None)


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
    return {
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
                    "position": "above_reference_interval",
                    "printed_flag": "high",
                },
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

    def __init__(self, reply):
        self._reply = reply
        self.prompts = []

    def generate_text(self, prompt):
        self.prompts.append(prompt)
        reply = self._reply
        return reply(len(self.prompts)) if callable(reply) else reply


def _faithful() -> str:
    return (
        "An HbA1c of 8.4 % and a glucose of "
        "186 mg/dl were reported. Diabetes was flagged because HbA1c 8.4 % is at or above "
        "the ADA diabetes-range threshold of 6.5 % and glucose 186 mg/dl is "
        "at or above the impaired-glucose-tolerance boundary of 140 mg/dl. "
        "Kidney Disease was flagged by the statistical model alone, and no "
        "measured value crossed a cut-off for it. Glucose 186 mg/dl is above "
        "the printed reference interval."
    )


def test_no_model_means_no_generation_and_no_network(offline_settings):
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
    llm = FakeLLM(_faithful().replace("186 mg/dl", "a raised glucose"))
    result = write_clinician_summary(_summary(), llm=llm, settings=offline_settings)
    assert result.outcome == OUTCOME_FACTS_MISSING
    assert result.text is None
    assert any("186" in gap for gap in result.missing_facts)


def test_a_narrative_that_drops_a_flagged_topic_is_thrown_away(offline_settings):
    llm = FakeLLM((_faithful()
        .replace("Diabetes was flagged", "It was flagged")
        .replace("ADA diabetes-range", "ADA reference")
    ))
    result = write_clinician_summary(_summary(), llm=llm, settings=offline_settings)
    assert result.outcome == OUTCOME_FACTS_MISSING
    assert "flagged:Diabetes" in result.missing_facts


def test_the_model_note_and_closing_line_are_APPENDED_not_copied(offline_settings):
    llm = FakeLLM(_faithful())
    result = write_clinician_summary(_summary(), llm=llm, settings=offline_settings)

    assert result.outcome == OUTCOME_GENERATED, result.missing_facts
    assert MODEL_NOTE not in llm.prompts[0]
    assert "do not write any closing disclaimer" in llm.prompts[0].lower()
    assert result.text.rstrip().endswith(CLOSING_LINE)
    assert MODEL_NOTE not in result.text


def test_the_model_only_distinction_must_survive(offline_settings):
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
    unsafe = "This patient has diabetes and should start metformin immediately."
    llm = FakeLLM(unsafe)
    result = write_clinician_summary(_summary(), llm=llm, settings=offline_settings)
    assert result.outcome == OUTCOME_WITHHELD_BY_SAFETY
    assert result.text is None
    assert "metformin" not in result.model_dump_json()


def test_the_refused_text_is_never_stored_anywhere(offline_settings):
    llm = FakeLLM(_faithful().replace("186 mg/dl", "CANARY-dropped-value"))
    result = write_clinician_summary(_summary(), llm=llm, settings=offline_settings)
    assert "CANARY" not in result.model_dump_json()


def test_the_prompt_carries_the_facts_and_forbids_inventing_numbers(offline_settings):
    llm = FakeLLM(_faithful())
    write_clinician_summary(_summary(), llm=llm, settings=offline_settings)
    prompt = llm.prompts[0]
    assert "HbA1c 8.4 %" in prompt
    assert "Glucose 186 mg/dl" in prompt
    assert "Diabetes" in prompt
    assert "Never introduce a number that is not below" in prompt
    assert "6.5" in prompt
    assert "Heart Disease" not in prompt
    assert "COULD NOT BE ASSESSED" not in prompt
    assert "NOT SUPPLIED" not in prompt


def test_the_prompt_forbids_naming_the_software(offline_settings):
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


def test_a_note_from_a_model_that_flagged_NOTHING_is_not_required(offline_settings):
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
    facts = collect_facts(_summary())
    joined = " ".join(facts.values)
    assert "Module 2" not in joined
    assert "male" not in joined
    assert "HbA1c 8.4 %" in joined


def test_the_laboratory_printed_name_is_preferred(offline_settings):
    facts = collect_facts(_summary())
    joined = " ".join(facts.values)
    assert "HbA1c 8.4 %" in joined
    assert "Glycated haemoglobin" not in joined


def _summary_with_unassessed(count: int = 17) -> dict:
    summary = _summary()
    summary["data_quality"] = {"unmapped_count": count}
    return summary


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


def test_the_reason_is_the_value_and_the_threshold_it_crossed(offline_settings):
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
    facts = collect_facts(_summary())
    assert any("Glucose 186 mg/dl" in entry for entry in facts.out_of_range)
    assert any("above the printed reference interval" in e for e in facts.out_of_range)


def test_the_prompt_states_only_findings_and_their_reasons(offline_settings):
    llm = FakeLLM(_faithful())
    write_clinician_summary(_summary(), llm=llm, settings=offline_settings)
    prompt = llm.prompts[0]

    assert "FLAGGED -- Diabetes:" in prompt
    assert "OUT OF RANGE:" not in prompt
    assert "Do NOT list the parameters" in prompt
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
    llm = FakeLLM((_faithful()
        .replace("Diabetes was flagged", "It was flagged")
        .replace("ADA diabetes-range", "ADA reference")
    ))
    result = write_clinician_summary(_summary(), llm=llm, settings=offline_settings)
    assert result.outcome == OUTCOME_FACTS_MISSING
    assert "flagged:Diabetes" in result.missing_facts


def test_a_narrative_that_drops_THE_REASON_is_thrown_away(offline_settings):
    llm = FakeLLM(_faithful().replace("8.4 %", "a crossed threshold"))
    result = write_clinician_summary(_summary(), llm=llm, settings=offline_settings)
    assert result.outcome == OUTCOME_FACTS_MISSING
    assert any("8.4" in gap for gap in result.missing_facts)


def test_the_laboratorys_printed_name_is_used_for_the_reason_too(offline_settings):
    joined = " ".join(collect_facts(_summary()).triggering["Diabetes"])
    assert "HbA1c" in joined
    assert "NGSP" not in joined


def _borderline_summary() -> dict:
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
    assert "Diabetes" not in qualified


def test_the_model_is_told_BORDERLINE_and_not_FLAGGED():
    from app.services.clinician_narrative import _facts_block

    block = _facts_block(collect_facts(_borderline_summary()))
    assert "BORDERLINE -- Obesity:" in block
    assert "FLAGGED -- Obesity" not in block
    assert "FLAGGED -- Diabetes:" in block


def test_a_narrative_that_calls_a_borderline_finding_flagged_is_a_gap():
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
    from app.services.clinician_narrative import _missing

    facts = collect_facts(_borderline_summary())
    assert "status:Obesity" not in _missing(phrasing, facts)


def test_the_word_must_be_NEAR_the_condition_not_loose_in_the_document():
    from app.services.clinician_narrative import _missing

    facts = collect_facts(_borderline_summary())
    text = (
        "The glucose result was borderline in an earlier report. "
        "This tool flagged Obesity because Body mass index was 25.25 kg/m2."
    )
    assert "status:Obesity" in _missing(text, facts)


def test_an_all_indicated_summary_reports_no_status_gap():
    from app.services.clinician_narrative import _missing

    facts = collect_facts(_summary())
    assert not [g for g in _missing(_faithful(), facts) if g.startswith("status:")]


def test_an_out_of_range_value_is_neither_required_nor_permitted(offline_settings):
    facts = collect_facts(_summary())

    assert any("186" in value for value in facts.required_values)

    triggering = [v for values in facts.triggering.values() for v in values]
    for required in facts.required_values:
        assert any(required in trigger for trigger in triggering), required


_COUNTED = "two major cardiovascular risk factors were counted"


def _heart_summary() -> dict:

    def line(feature, name, value, unit, threshold):
        return {
            "feature": feature,
            "display_name": name,
            "value": value,
            "unit": unit,
            "comparator": ">=",
            "threshold": threshold,
            "classification": _COUNTED,
        }

    return {
        "patient": {"age": 20, "gender": "male"},
        "laboratory": {"rows": []},
        "abnormal_findings": ["Heart Disease", "Diabetes"],
        "assessments": [
            {
                "condition": "Heart Disease",
                "status": "Borderline",
                "bases": [{"rule": {"triggering_values": [
                    line("cholesterol", "Total Cholesterol", 268, "mg/dl", 240),
                    line("hba1c", "HbA1c", 8.4, "%", 6.5),
                    line("bmi", "Body mass index", 25.25, "kg/m2", 30),
                    line("age", "Age in whole years", 20, "years", 45),
                ]}}],
            },
            {
                "condition": "Diabetes",
                "bases": [{"rule": {"triggering_values": [
                    {"feature": "hba1c", "display_name": "HbA1c", "value": 8.4, "unit": "%",
                     "comparator": ">=", "threshold": 6.5, "classification": "ADA diabetes range"},
                    {"feature": "blood_glucose", "display_name": "Glucose", "value": 186, "unit": "mg/dl",
                     "comparator": ">=", "threshold": 126, "classification": "ADA fasting threshold"},
                ]}}],
            },
        ],
    }


def test_a_criterion_that_was_not_met_is_not_given_as_a_reason():
    reasons = collect_facts(_heart_summary()).triggering["Heart Disease"]
    joined = " | ".join(reasons)
    assert "268" in joined and "8.4" in joined
    assert "25.25" not in joined
    assert "Age in whole years" not in joined


def test_unmet_values_are_not_required_facts_either():
    facts = collect_facts(_heart_summary())
    assert "25.25" not in facts.required_values
    assert "20" not in facts.required_values


def test_one_conclusion_is_said_once():
    reasons = collect_facts(_heart_summary()).triggering["Heart Disease"]
    assert sum(_COUNTED in r for r in reasons) == 1
    assert reasons[-1] == f"together, {_COUNTED}"
    assert reasons[0] == "Total Cholesterol 268 mg/dl (>= 240)"


def test_values_with_different_labels_keep_their_own():
    reasons = collect_facts(_heart_summary()).triggering["Diabetes"]
    assert reasons == (
        "HbA1c 8.4 % (>= 6.5, ADA diabetes range)",
        "Glucose 186 mg/dl (>= 126, ADA fasting threshold)",
    )


def test_a_below_threshold_comparator_still_counts_as_crossed():
    summary = {
        "laboratory": {"rows": []},
        "abnormal_findings": ["Anemia"],
        "assessments": [{"condition": "Anemia", "bases": [{"rule": {"triggering_values": [
            {"feature": "hemoglobin", "display_name": "Haemoglobin", "value": 12.5, "unit": "g/dl",
             "comparator": "<", "threshold": 13, "classification": "mild anaemia band"},
        ]}}]}],
    }
    assert collect_facts(summary).triggering["Anemia"] == (
        "Haemoglobin 12.5 g/dl (< 13, mild anaemia band)",
    )


def test_the_subject_is_not_handed_to_the_model(offline_settings):
    llm = FakeLLM(_faithful())
    write_clinician_summary(_summary(), llm=llm, settings=offline_settings)
    prompt = llm.prompts[0]
    assert "SUBJECT:" not in prompt
    assert "58-year-old" not in prompt
    assert "Do not state the patient's age or sex" in prompt


def test_an_age_the_model_was_not_given_is_refused(offline_settings):
    llm = FakeLLM("This 58-year-old male. " + _faithful())
    result = write_clinician_summary(_summary(), llm=llm, settings=offline_settings)
    assert result.outcome == OUTCOME_WITHHELD_BY_SAFETY
    assert result.text is None


def test_nothing_flagged_is_stated_not_left_empty():
    summary = {"patient": {"age": 34, "gender": "female"}, "laboratory": {"rows": []},
               "abnormal_findings": [], "assessments": []}
    block = _facts_block(collect_facts(summary))
    assert block.strip()
    assert "NOTHING FLAGGED" in block
    assert "34" not in block


def test_the_fingerprint_is_short_hex_and_stable():
    assert re.fullmatch(r"[0-9a-f]{16}", NARRATIVE_CODE_FINGERPRINT)
    assert _code_fingerprint() == NARRATIVE_CODE_FINGERPRINT


def test_the_fingerprint_changes_when_the_note_code_changes(monkeypatch):
    real = Path.read_bytes

    def edited(self):
        data = real(self)
        return data + b"\n# edited\n" if self.name == "clinician_narrative.py" else data

    monkeypatch.setattr(Path, "read_bytes", edited)
    assert _code_fingerprint() != NARRATIVE_CODE_FINGERPRINT


def test_line_endings_alone_do_not_change_the_fingerprint(monkeypatch):
    real = Path.read_bytes
    lf = lambda self: real(self).replace(b"\r\n", b"\n")
    monkeypatch.setattr(Path, "read_bytes", lf)
    as_lf = _code_fingerprint()
    monkeypatch.setattr(Path, "read_bytes", lambda self: lf(self).replace(b"\n", b"\r\n"))
    assert _code_fingerprint() == as_lf == NARRATIVE_CODE_FINGERPRINT


def test_the_fingerprint_endpoint_answers_in_the_envelope(client):
    response = client.get("/api/v1/explain/clinician-summary/fingerprint")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"] == {
        "fingerprint": NARRATIVE_CODE_FINGERPRINT,
        "narrative_version": NARRATIVE_VERSION,
    }


def test_the_fingerprint_endpoint_requires_the_service_key(authed_client):
    assert authed_client.get("/api/v1/explain/clinician-summary/fingerprint").status_code == 401
