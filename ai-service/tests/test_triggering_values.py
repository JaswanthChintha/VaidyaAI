"""A counted-factor rule's UNMET criteria are not "triggering values".

Found by the owner on 2026-10-03 (`02-diabetes-and-lipids-redacted.pdf`): the
clinician note read "recorded Heart Disease as borderline because ... Body mass
index was 25.25 kg/m2 (>= 30 ...) and Age in whole years was 20 years (>= 45
...)". The cardiovascular rule counted two of four factors and was right; but
`report_builder._triggering_values` took every evidence line with a threshold,
including the two the rule had marked "criterion not met".

These tests drive the REAL rule engine on that report's numbers, so they hold
against the rule's own notes rather than a hand-written copy of them.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.data.clinical_rules import HEART_DISEASE_RULE
from app.schemas.decisions import DecisionStatus
from app.services import report_builder as RB
from app.services import rule_engine as RE


def _incoming(value):
    return SimpleNamespace(
        value=value,
        unit=None,
        questionable=False,
        clinically_extreme=False,
        extreme_direction=None,
        source="lab_report",
        provenance=SimpleNamespace(
            reference_low=None,
            reference_high=None,
            source="lab_report",
            original_test_name=None,
            matched_synonym=None,
        ),
    )


def _decision():
    values = {
        "cholesterol": 268,
        "hba1c": 8.4,
        "bmi": 25.25,
        "age": 20,
        "gender": "male",
        "smoking_history": "never",
        "hypertension": False,
        "heart_disease": False,
    }
    views = {name: RE.FeatureView(name, _incoming(v)) for name, v in values.items()}
    return RE._evaluate_composite_rule(HEART_DISEASE_RULE, views, "male", 20.0, False)


def _as_line(item, classification):
    return SimpleNamespace(
        feature=item.feature,
        value=item.value,
        unit=item.unit,
        threshold=item.threshold,
        comparator=item.comparator,
        classification=classification,
    )


def test_the_rule_itself_counts_two_of_four_and_is_borderline():
    decision = _decision()
    assert decision.status is DecisionStatus.BORDERLINE
    assert sorted(decision.metadata["factors_counted"]) == [
        "diabetes_range_hba1c",
        "high_total_cholesterol",
    ]


def test_unmet_factors_stay_on_the_evidence_as_not_met():
    # The evidence still records them -- "evaluated and not met" is true.
    notes = {i.feature: i.note for i in _decision().evidence}
    assert notes["bmi"].startswith(RE.NOTE_FACTOR_NOT_MET)
    assert notes["age"].startswith(RE.NOTE_FACTOR_NOT_MET)


def test_only_counted_factors_become_triggering_values():
    triggering = RB._triggering_values([_decision()], _as_line)
    assert sorted(t.feature for t in triggering) == ["cholesterol", "hba1c"]
