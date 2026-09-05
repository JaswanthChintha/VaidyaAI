"""The canonical condition vocabulary (app/data/conditions.py).

Module 16 fuses by grouping on `ClinicalDecision.condition`, which is a STRING
match. These tests pin the exact strings Modules 10-12 will have to emit, so a
future spelling drift breaks a test here rather than silently disabling fusion.
"""

from __future__ import annotations

import pytest

from app.data import conditions as C
from app.data.clinical_rules import COMPOSITE_RULES, THRESHOLD_RULES


def test_the_three_fusion_condition_strings_are_exact():
    # Modules 10, 11 and 12 MUST emit these byte-for-byte.
    assert C.DIABETES == "Diabetes"
    assert C.HEART_DISEASE == "Heart Disease"
    assert C.KIDNEY_DISEASE == "Kidney Disease"
    assert C.FUSION_CONDITIONS == ("Diabetes", "Heart Disease", "Kidney Disease")


def test_every_fusion_condition_is_always_assessed():
    # Otherwise Module 16 cannot tell "the rule engine did not assess this"
    # from "the rule engine found nothing".
    for name in C.FUSION_CONDITIONS:
        assert C.CONDITIONS[name].always_assessed is True


def test_no_two_conditions_differ_only_by_case():
    lowered = [name.lower() for name in C.CONDITIONS]
    assert len(set(lowered)) == len(lowered)


def test_condition_names_have_no_stray_whitespace():
    for name in C.CONDITIONS:
        assert name == name.strip()
        assert name


def test_every_rule_uses_a_canonical_condition():
    for rule in THRESHOLD_RULES:
        assert C.is_canonical_condition(rule.condition), rule.id
    for rule in COMPOSITE_RULES:
        assert C.is_canonical_condition(rule.condition), rule.id


def test_condition_rank_orders_fusion_conditions_first():
    ranks = [C.condition_rank(n) for n in C.FUSION_CONDITIONS]
    assert ranks == sorted(ranks)
    assert max(ranks) < C.condition_rank(C.ANEMIA)


def test_unknown_condition_sorts_last_and_is_not_canonical():
    assert not C.is_canonical_condition("Diabetes Mellitus")
    assert C.condition_rank("Diabetes Mellitus") == len(C.CONDITION_ORDER)


def test_self_check_rejects_a_case_only_duplicate(monkeypatch):
    """The import-time guard is real, not decorative."""
    original = dict(C.CONDITIONS)
    try:
        C.CONDITIONS["diabetes"] = C.ConditionDefinition("diabetes", "clash")
        with pytest.raises(ValueError):
            C._self_check()
    finally:
        C.CONDITIONS.clear()
        C.CONDITIONS.update(original)


def test_conditions_document_is_serialisable_and_complete():
    document = C.conditions_document()
    assert document["fusion_conditions"] == list(C.FUSION_CONDITIONS)
    assert set(document["conditions"]) == set(C.CONDITIONS)
