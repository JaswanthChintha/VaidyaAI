"""The condition-vocabulary validator on `ClinicalDecision`.

From the 2026-08-30 integration audit: `ClinicalDecision(condition="diabetes
mellitus", ...)` used to construct happily. `app/data/conditions.py` states that
no producer may invent a condition string -- because Module 16 groups by exact
string, so a drift silently prevents fusion rather than raising -- but nothing
enforced it. Modules 15 and 16 add new producers, so it is enforced now.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from app.data import conditions as C
from app.schemas.decisions import (
    ClinicalDecision,
    DecisionSourceKind,
    DecisionStatus,
    RiskLevel,
)


def _decision(condition: str) -> ClinicalDecision:
    return ClinicalDecision(
        condition=condition,
        status=DecisionStatus.INDICATED,
        risk=RiskLevel.HIGH,
        source="Clinical Rule Engine",
        source_kind=DecisionSourceKind.CLINICAL_RULE,
    )


# --------------------------------------------------------------------------
# Every canonical condition still constructs
# --------------------------------------------------------------------------


@pytest.mark.parametrize("condition", sorted(C.CONDITIONS))
def test_every_canonical_condition_is_accepted(condition: str) -> None:
    assert _decision(condition).condition == condition


def test_the_vocabulary_is_not_empty() -> None:
    """Guard the parametrisation above: an empty list would vacuously pass."""
    assert len(C.CONDITIONS) >= 13
    assert set(C.FUSION_CONDITIONS) <= set(C.CONDITIONS)


# --------------------------------------------------------------------------
# A non-canonical condition is refused at construction
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "condition",
    [
        "diabetes mellitus",  # the exact string named in the audit
        "Diabetes Mellitus",
        "diabetes",  # case drift alone is enough to break grouping
        "DIABETES",
        "Prediabetes",  # deliberately not a condition; it is Diabetes/Borderline
        "Heart disease",
        "Chronic Kidney Disease",
        "Cancer",
    ],
)
def test_a_non_canonical_condition_is_rejected(condition: str) -> None:
    with pytest.raises(ValueError, match="not a canonical condition"):
        _decision(condition)


def test_the_rejection_names_where_to_look() -> None:
    with pytest.raises(ValueError) as excinfo:
        _decision("diabetes mellitus")
    message = str(excinfo.value)
    assert "app/data/conditions.py" in message
    # The permitted values are listed, so the fix does not require a repo search.
    assert C.DIABETES in message


def test_surrounding_whitespace_is_stripped_before_the_check() -> None:
    """`_non_blank` runs first, so a padded canonical name is still canonical."""
    assert _decision("  Diabetes  ").condition == C.DIABETES


def test_blank_is_still_rejected_as_blank_not_as_non_canonical() -> None:
    with pytest.raises(ValueError, match="must not be blank"):
        _decision("   ")


def test_a_fused_decision_is_held_to_the_same_vocabulary() -> None:
    """Module 16 is a producer too and gets no exemption."""
    with pytest.raises(ValueError, match="not a canonical condition"):
        ClinicalDecision(
            condition="Cardiometabolic Risk",
            status=DecisionStatus.INDICATED,
            risk=RiskLevel.HIGH,
            source="Clinical Rule Engine + Random Forest",
            source_kind=DecisionSourceKind.FUSION,
        )


def test_source_is_not_subject_to_the_condition_vocabulary() -> None:
    """Only `condition` is a fusion key. `source` is free text and stays so."""
    decision = ClinicalDecision(
        condition=C.DIABETES,
        status=DecisionStatus.NOT_INDICATED,
        risk=RiskLevel.LOW,
        source="Some Future Analytical Component",
        source_kind=DecisionSourceKind.CLINICAL_RULE,
    )
    assert decision.source == "Some Future Analytical Component"


# --------------------------------------------------------------------------
# No circular import, in EITHER direction
# --------------------------------------------------------------------------
#
# `app/schemas/decisions.py` now reaches `app/data/conditions.py`, while
# `app/data/recommendation_catalog.py` reaches back into `decisions.py` for
# `Recommendation`. That is not a cycle today -- `conditions.py` imports nothing
# from `app` at all -- but it is one edit away from being one, and a cycle would
# show up as an ImportError only for whichever module happened to be imported
# first. These run in a FRESH interpreter so an already-populated
# `sys.modules` cannot hide the problem.

_ROOT = Path(__file__).resolve().parents[1]

_IMPORT_ORDERS = [
    "import app.schemas.decisions, app.data.conditions",
    "import app.data.conditions, app.schemas.decisions",
    "import app.data.recommendation_catalog, app.schemas.decisions",
    "import app.schemas.decisions, app.data.recommendation_catalog",
    "import app.schemas.fusion",
    "import app.services.fusion_engine",
    "import app.services.decision_engine",
]


@pytest.mark.parametrize("statement", _IMPORT_ORDERS)
def test_import_order_never_deadlocks(statement: str) -> None:
    result = subprocess.run(
        [sys.executable, "-c", statement],
        cwd=str(_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr


def test_the_subprocess_harness_can_actually_fail() -> None:
    """Without this, a broken harness would make every check above vacuous."""
    result = subprocess.run(
        [sys.executable, "-c", "import app.this_module_does_not_exist"],
        cwd=str(_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode != 0
