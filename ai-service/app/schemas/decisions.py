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


@enum.unique
class RiskLevel(str, enum.Enum):

    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"

    @property
    def rank(self) -> int:
        return _RISK_RANK[self]

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, RiskLevel):
            return NotImplemented
        return self.rank < other.rank

    def __le__(self, other: object) -> bool:
        if not isinstance(other, RiskLevel):
            return NotImplemented
        return self.rank <= other.rank

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, RiskLevel):
            return NotImplemented
        return self.rank > other.rank

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, RiskLevel):
            return NotImplemented
        return self.rank >= other.rank

    @classmethod
    def highest(cls, levels: "list[RiskLevel]") -> Optional["RiskLevel"]:
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

    NOT_INDICATED = "Not Indicated"
    BORDERLINE = "Borderline"
    INDICATED = "Indicated"
    INSUFFICIENT_DATA = "Insufficient Data"


@enum.unique
class DecisionSourceKind(str, enum.Enum):

    CLINICAL_RULE = "clinical_rule"
    MACHINE_LEARNING = "machine_learning"
    FUSION = "fusion"


class EvidenceItem(BaseModel):

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
        return (self.feature, str(self.value), self.unit, str(self.threshold))


class Recommendation(BaseModel):

    model_config = ConfigDict(extra="forbid")

    code: StrictStr = Field(description="Catalogue key, e.g. 'DISCUSS_WITH_CLINICIAN'.")
    text: StrictStr = Field(description="The catalogue's approved wording.")
    category: Optional[StrictStr] = Field(
        default=None,
        description="e.g. 'consultation', 'monitoring', 'lifestyle', 'retest'.",
    )

    def dedup_key(self) -> str:
        return self.code


class ClinicalDecision(BaseModel):

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
        if self.status is DecisionStatus.INSUFFICIENT_DATA:
            if self.risk is not None:
                raise ValueError(
                    "risk must be None when status is INSUFFICIENT_DATA: a "
                    "condition that could not be assessed has no risk level"
                )
            if self.confidence is not None:
                raise ValueError(
                    "confidence must be None when status is INSUFFICIENT_DATA: "
                    "no model ran, so there is no probability to report"
                )
        elif self.risk is None:
            raise ValueError(f"risk is required when status is {self.status.value}")
        return self

    @model_validator(mode="after")
    def _ml_decisions_carry_confidence(self) -> "ClinicalDecision":
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


    @property
    def was_assessed(self) -> bool:
        return self.status is not DecisionStatus.INSUFFICIENT_DATA

    @property
    def is_flagged(self) -> bool:
        return self.status in (DecisionStatus.INDICATED, DecisionStatus.BORDERLINE)

    def evidence_features(self) -> List[str]:
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
