"""Module 14 -- the Clinical Decision Object.

This schema is BINDING and SHARED. Every analytical component in VaidyaAI emits
`ClinicalDecision` objects and nothing else:

    Module 8  Clinical Rule Engine      -> ClinicalDecision[]
    Module 10 Diabetes Predictor        -> ClinicalDecision[]
    Module 11 Heart Disease Predictor   -> ClinicalDecision[]
    Module 12 Kidney Disease Predictor  -> ClinicalDecision[]
    (future predictors)                 -> ClinicalDecision[]

Module 15 (Decision Engine) collects them, Module 16 (Fusion Engine) merges
decisions about the same condition, Module 19 prioritises by risk, and Module 20
renders `evidence` to explain each finding to the user.

The whole point of standardising here is that Module 16 can fuse a deterministic
rule decision with a Random Forest decision WITHOUT knowing anything about how
either was produced.

Design rules encoded in this module
-----------------------------------

* `RiskLevel` is ORDERED (`LOW < MEDIUM < HIGH`) and the ordering is a property
  of the type. Module 16 keeps the highest applicable risk when fusing, so no
  caller should re-implement that comparison and risk getting it wrong.

* `confidence is None` means "this component does not produce a probability"
  (a deterministic rule). `confidence == 0.0` means "a model ran and was
  maximally unconfident". These are NOT the same thing, and collapsing them
  would corrupt Module 16's "strongest available confidence" fusion. `None` is
  therefore never defaulted to 0.0 anywhere.

* `evidence` is STRUCTURED, never prose. Module 16 must merge evidence from
  several sources without duplicating it, and Module 20 must render each item.
  Free text cannot be de-duplicated or rendered reliably.

* SAFETY (spec sections 14 and 24). VaidyaAI is explicitly NOT a diagnostic
  system. Recommendation text is drawn from a fixed, reviewable catalogue
  (`app/data/recommendation_catalog.py`) rather than composed ad hoc, so an
  unsafe recommendation cannot be introduced by a caller passing a string. A
  decision can never assert a diagnosis, prescribe a medication, give a dosage,
  or claim certainty. Module 24 adds a further safety validator later, but this
  type does not rely on a downstream filter to make its output safe.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictStr,
    field_validator,
    model_validator,
)

# ---------------------------------------------------------------------------
# Ordered risk
# ---------------------------------------------------------------------------


@enum.unique
class RiskLevel(str, enum.Enum):
    """Risk bands, ordered LOW < MEDIUM < HIGH.

    Spec Module 16: "Risk levels are ordered: Low < Medium < High. The highest
    applicable risk level is retained." The comparison operators below exist so
    that fusion is a `max()` and never a hand-written if/elif ladder.

    `UNKNOWN` is deliberately NOT a risk level. A component that cannot assess
    risk must not emit a decision at all -- see Module 12's information
    sufficiency requirement, where an under-informed predictor skips rather than
    guessing. Emitting "unknown risk" would let an absence masquerade as a
    finding.
    """

    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"

    @property
    def rank(self) -> int:
        return _RISK_RANK[self]

    def __lt__(self, other: object) -> bool:  # type: ignore[override]
        if not isinstance(other, RiskLevel):
            return NotImplemented
        return self.rank < other.rank

    def __le__(self, other: object) -> bool:  # type: ignore[override]
        if not isinstance(other, RiskLevel):
            return NotImplemented
        return self.rank <= other.rank

    def __gt__(self, other: object) -> bool:  # type: ignore[override]
        if not isinstance(other, RiskLevel):
            return NotImplemented
        return self.rank > other.rank

    def __ge__(self, other: object) -> bool:  # type: ignore[override]
        if not isinstance(other, RiskLevel):
            return NotImplemented
        return self.rank >= other.rank

    @classmethod
    def highest(cls, levels: "list[RiskLevel]") -> Optional["RiskLevel"]:
        """The highest risk in `levels`, or None for an empty list.

        Module 16 fuses with this. Returning None rather than defaulting to LOW
        matters: "no decisions" must not silently become "low risk".
        """
        if not levels:
            return None
        return max(levels, key=lambda level: level.rank)


_RISK_RANK: Dict[RiskLevel, int] = {
    RiskLevel.LOW: 0,
    RiskLevel.MEDIUM: 1,
    RiskLevel.HIGH: 2,
}


@enum.unique
class DecisionStatus(str, enum.Enum):
    """What the component concluded about the condition.

    Deliberately NOT diagnostic vocabulary. `INDICATED` means "the configured
    thresholds or the model flagged this", not "the patient has this disease".
    The distinction is the difference between a decision-support tool and an
    unlicensed diagnostic device.

    * NOT_INDICATED    -- assessed, nothing flagged
    * BORDERLINE       -- assessed, near a threshold
    * INDICATED        -- assessed, flagged for discussion with a professional
    * INSUFFICIENT_DATA-- could not assess (Module 12 skips this way)
    """

    NOT_INDICATED = "Not Indicated"
    BORDERLINE = "Borderline"
    INDICATED = "Indicated"
    INSUFFICIENT_DATA = "Insufficient Data"


@enum.unique
class DecisionSourceKind(str, enum.Enum):
    """Which family of analysis produced a decision.

    Module 16 reports the contributing sources, and a fused decision backed by
    both a rule and a model is stronger evidence than either alone -- so the
    KIND must be machine-readable, not just the free-text `source` label.
    """

    CLINICAL_RULE = "clinical_rule"
    MACHINE_LEARNING = "machine_learning"
    FUSION = "fusion"


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------


class EvidenceItem(BaseModel):
    """One structured reason a decision was reached.

    Spec Module 20: the system must show WHICH value drove a finding, not just
    that a finding exists. Every field here exists so Module 20 can render a
    line like "Creatinine = 1.9 mg/dL (reference 0.7-1.3), above the configured
    threshold of 1.3" without re-deriving anything.
    """

    model_config = ConfigDict(extra="forbid")

    feature: StrictStr = Field(
        description="Canonical feature name, e.g. 'hba1c'. Matches Module 5's key."
    )
    value: Any = Field(
        default=None,
        description=(
            "The value that drove the decision, in canonical units. May be a "
            "float, a bool (tri-state features), or a string (categorical)."
        ),
    )
    unit: Optional[StrictStr] = Field(
        default=None, description="Canonical unit, or None for categorical/boolean."
    )
    threshold: Optional[Any] = Field(
        default=None,
        description=(
            "The configured threshold this value was compared against, when the "
            "producer is rule-based. None for ML decisions, where no single "
            "threshold applies."
        ),
    )
    comparator: Optional[StrictStr] = Field(
        default=None,
        description="How value related to threshold, e.g. '>=', '<', 'in'.",
    )
    reference_low: Optional[StrictFloat] = Field(
        default=None,
        description=(
            "Lower reference bound printed on the report, IN THE SAME "
            "CANONICAL UNIT as `value` and `unit`. Module 5 converts the "
            "interval with the value; a bound it could not convert is absent, "
            "never carried through in the printed unit."
        ),
    )
    reference_high: Optional[StrictFloat] = Field(
        default=None,
        description=(
            "Upper reference bound, in the same canonical unit as `value`. "
            "Same conversion and same refusal rule as `reference_low`."
        ),
    )
    note: Optional[StrictStr] = Field(
        default=None,
        description=(
            "Short factual clarification, e.g. 'unit was assumed' or 'value was "
            "censored at the detection limit'. NOT interpretation or advice."
        ),
    )
    source_stage: Optional[StrictStr] = Field(
        default=None,
        description="Pipeline stage the value came from, e.g. 'lab_report'.",
    )

    def dedup_key(self) -> tuple:
        """Identity used by Module 16 to merge evidence from several sources.

        Two components citing the same feature/value/threshold are citing the
        same evidence, and the user should see it once.
        """
        return (self.feature, str(self.value), self.unit, str(self.threshold))


class Recommendation(BaseModel):
    """A safe, educational recommendation drawn from a reviewable catalogue.

    SAFETY: `code` refers to an entry in `app/data/recommendation_catalog.py`.
    Producing recommendations by code rather than by free string is what makes
    the safety property structural: to add a new recommendation you must edit a
    reviewed catalogue file, so no code path can emit unvetted medical advice.

    Spec Module 26 calls for "pre-approved educational guidance rather than
    unrestricted AI-generated medical treatment advice". This is that mechanism.
    """

    model_config = ConfigDict(extra="forbid")

    code: StrictStr = Field(description="Catalogue key, e.g. 'DISCUSS_WITH_CLINICIAN'.")
    text: StrictStr = Field(description="The catalogue's approved wording.")
    category: Optional[StrictStr] = Field(
        default=None,
        description="e.g. 'consultation', 'monitoring', 'lifestyle', 'retest'.",
    )

    def dedup_key(self) -> str:
        """Module 16 consolidates recommendations and removes duplicates."""
        return self.code


# ---------------------------------------------------------------------------
# The decision
# ---------------------------------------------------------------------------


class ClinicalDecision(BaseModel):
    """The standardised output of every analytical component (spec Module 14).

    Example (spec's own illustration, Module 10):

        ClinicalDecision(
            condition="Diabetes",
            status=DecisionStatus.INDICATED,
            risk=RiskLevel.HIGH,
            confidence=0.87,
            source="Random Forest",
            source_kind=DecisionSourceKind.MACHINE_LEARNING,
            evidence=[...HbA1c, Blood Glucose, BMI...],
            recommendations=[...],
        )
    """

    model_config = ConfigDict(extra="forbid")

    condition: StrictStr = Field(
        description=(
            "The condition assessed, e.g. 'Diabetes'. Module 16 groups by this "
            "value, so producers MUST use a consistent spelling -- see "
            "app/data/conditions.py for the canonical list."
        )
    )
    status: DecisionStatus
    risk: Optional[RiskLevel] = Field(
        default=None,
        description=(
            "None ONLY when status is INSUFFICIENT_DATA. A component that could "
            "not assess must not imply a risk level."
        ),
    )
    confidence: Optional[StrictFloat] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "Model probability in [0,1]. None means 'this component produces no "
            "probability' (deterministic rules) -- NOT zero confidence. Module 16 "
            "must not conflate the two."
        ),
    )
    source: StrictStr = Field(
        description="Human-readable producer, e.g. 'Clinical Rule Engine'."
    )
    source_kind: DecisionSourceKind
    evidence: List[EvidenceItem] = Field(default_factory=list)
    recommendations: List[Recommendation] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Reproducibility context: rule id and version, model name and "
            "version, thresholds applied, feature vector completeness. Must "
            "never contain PHI or raw report text."
        ),
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of decision creation.",
    )

    # -- invariants ---------------------------------------------------------

    @field_validator("condition", "source")
    @classmethod
    def _non_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped

    @field_validator("condition")
    @classmethod
    def _canonical_condition(cls, value: str) -> str:
        """Reject a condition string that is not in the canonical vocabulary.

        `app/data/conditions.py` states that "NO producer may invent a condition
        string", because Module 16 fuses by EXACT STRING MATCH. Until this
        validator existed nothing enforced it, so
        `ClinicalDecision(condition="diabetes mellitus", ...)` constructed
        happily and then silently failed to fuse with the rule engine's
        "Diabetes" -- two dashboard cards, no error, no test failure. The
        product would just have been quietly worse.

        Enforcing it HERE rather than in each producer is what makes the
        guarantee structural: a producer cannot opt out, and a future Module 21+
        component written by someone who never read `conditions.py` fails at
        construction instead of at the user's screen.

        CIRCULAR IMPORT: none. The import below reaches
        `app.data.conditions` DIRECTLY, and that module imports nothing from
        `app` at all (only `dataclasses` and `typing`); `app/data/__init__.py`
        is docstring-only. The one module that could have closed a loop --
        `app.data.recommendation_catalog`, which imports `Recommendation` from
        THIS file -- is a different module and is never pulled in by
        `conditions`. `tests/test_decision_vocabulary.py` proves both import
        orders work in a fresh interpreter, so a future edit that adds a real
        cycle fails loudly rather than at some importer's whim.

        The import is nonetheless kept FUNCTION-LOCAL rather than moved to the
        top of this file: `decisions.py` is the most widely imported module in
        the service, and a module-level `app.data` import would make every one
        of its importers transitively depend on the data package's import
        order. Local keeps this schema a leaf. The cost is one dict lookup of
        an already-cached module per construction.
        """
        from app.data.conditions import CONDITION_ORDER, is_canonical_condition

        if not is_canonical_condition(value):
            raise ValueError(
                f"{value!r} is not a canonical condition. Module 16 fuses by "
                "exact string match, so a non-canonical spelling would silently "
                "never fuse. Import a constant from app/data/conditions.py; the "
                f"permitted values are {list(CONDITION_ORDER)}"
            )
        return value

    @model_validator(mode="after")
    def _check_risk_and_status_agree(self) -> "ClinicalDecision":
        """Keep `status` and `risk` from contradicting each other.

        Two mistakes this prevents:

        1. INSUFFICIENT_DATA carrying a risk level. Module 12's kidney predictor
           skips when it lacks inputs; if that skip carried `risk=LOW` the
           dashboard would show a reassuring "low risk" for a condition that was
           never actually assessed. That is the most dangerous failure mode this
           type can have.
        2. An assessable status carrying no risk, which would leave Module 16
           and Module 19 with nothing to prioritise on.
        """
        if self.status is DecisionStatus.INSUFFICIENT_DATA:
            if self.risk is not None:
                raise ValueError(
                    "risk must be None when status is INSUFFICIENT_DATA: a "
                    "condition that could not be assessed has no risk level"
                )
            if self.confidence is not None:
                # THE SAME INVARIANT, ONE FIELD OVER (integration audit D6).
                # An abstention has no probability: no model ran, so there is
                # nothing for a number to be the probability OF. `0.0` would be
                # a lie about a model that never executed and `0.99` would be a
                # lie in the dangerous direction -- Module 16 fuses on
                # "strongest available confidence", and Module 19 and every
                # renderer downstream read that number as the system's strength
                # of belief. Module 15's within-source merge happens to zero it
                # today; that is a behaviour, not a guarantee, and this is the
                # type-level guarantee.
                raise ValueError(
                    "confidence must be None when status is INSUFFICIENT_DATA: "
                    "no model ran, so there is no probability to report"
                )
        elif self.risk is None:
            raise ValueError(f"risk is required when status is {self.status.value}")
        return self

    @model_validator(mode="after")
    def _ml_decisions_carry_confidence(self) -> "ClinicalDecision":
        """An ML decision that actually ran must report its probability.

        Without this, a predictor could silently omit confidence and Module 16
        would treat it as "no probability available" -- indistinguishable from a
        deterministic rule, losing the information that a model was involved.
        """
        if (
            self.source_kind is DecisionSourceKind.MACHINE_LEARNING
            and self.status is not DecisionStatus.INSUFFICIENT_DATA
            and self.confidence is None
        ):
            raise ValueError(
                "machine_learning decisions must report confidence unless "
                "status is INSUFFICIENT_DATA"
            )
        return self

    # -- helpers ------------------------------------------------------------

    @property
    def was_assessed(self) -> bool:
        """False when the component skipped for lack of information."""
        return self.status is not DecisionStatus.INSUFFICIENT_DATA

    @property
    def is_flagged(self) -> bool:
        """True when this decision should surface as a finding to the user."""
        return self.status in (DecisionStatus.INDICATED, DecisionStatus.BORDERLINE)

    def evidence_features(self) -> List[str]:
        """Canonical feature names cited, in order, without duplicates."""
        seen: Dict[str, None] = {}
        for item in self.evidence:
            seen.setdefault(item.feature, None)
        return list(seen)


__all__ = [
    "ClinicalDecision",
    "DecisionSourceKind",
    "DecisionStatus",
    "EvidenceItem",
    "Recommendation",
    "RiskLevel",
]
