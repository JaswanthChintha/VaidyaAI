from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.decisions import ClinicalDecision, RiskLevel
from app.schemas.features import FeatureProvenance, StageWarning, UpstreamExtraction
from app.schemas.validation import (
    STATUS_VALID,
    EngineeredFeaturesInput,
    FeatureValidationSummary,
)

STAGE_RULES = "rules"
RULES_MODULE = 8


class IncomingValidatedFeature(BaseModel):

    model_config = ConfigDict(extra="ignore")

    name: Optional[str] = None
    value: Any = None
    unit: Optional[str] = None
    canonical_unit: bool = True
    source: Optional[str] = None
    provenance: Optional[FeatureProvenance] = None
    status: str = STATUS_VALID
    questionable: bool = False
    clinically_extreme: bool = False
    extreme_direction: Optional[str] = None


class ValidatedFeaturesInput(BaseModel):

    model_config = ConfigDict(extra="ignore")

    valid: Dict[str, IncomingValidatedFeature] = Field(
        default_factory=dict, description="THE USABLE FEATURE SET. The only input."
    )
    questionable: Dict[str, IncomingValidatedFeature] = Field(
        default_factory=dict, description="A subset view of `valid`."
    )
    clinically_extreme: List[str] = Field(
        default_factory=list,
        description="VALID and fully trusted, but alarming. A prioritisation "
        "signal, never a reason to distrust the value.",
    )
    missing_features: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    upstream_warnings: List[StageWarning] = Field(default_factory=list)
    all_warnings: List[StageWarning] = Field(default_factory=list)
    upstream: UpstreamExtraction = Field(default_factory=UpstreamExtraction)
    summary: FeatureValidationSummary = Field(
        default_factory=FeatureValidationSummary
    )

    @field_validator("warnings", mode="before")
    @classmethod
    def _warnings_list(cls, v: object) -> object:
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return v


AMBIGUOUS_REQUEST_MESSAGE = (
    "Ambiguous request: send Module 6's validated features under 'validated' "
    "(or Module 5's engineered features under 'engineered'), or relay exactly "
    "one response envelope -- but not several at once."
)

AMBIGUOUS_OBJECT_MESSAGE = (
    "Ambiguous request: the posted object carries both 'valid' (Module 6) and "
    "'features' (Module 5). Send one or the other, or name it explicitly with "
    "'validated' / 'engineered'."
)


class RuleEvaluationRequest(BaseModel):

    model_config = ConfigDict(extra="ignore")

    validated: Optional[ValidatedFeaturesInput] = None
    engineered: Optional[EngineeredFeaturesInput] = None

    @model_validator(mode="before")
    @classmethod
    def _unwrap(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        if "validated" in value or "engineered" in value:
            return value

        envelope = value.get("data")
        has_envelope = isinstance(envelope, dict)
        bare_validated = "valid" in value
        bare_engineered = "features" in value

        if has_envelope and (bare_validated or bare_engineered):
            raise ValueError(AMBIGUOUS_REQUEST_MESSAGE)
        if bare_validated and bare_engineered:
            raise ValueError(AMBIGUOUS_OBJECT_MESSAGE)

        if has_envelope:
            inner_validated = "valid" in envelope
            inner_engineered = "features" in envelope
            if inner_validated and inner_engineered:
                raise ValueError(AMBIGUOUS_OBJECT_MESSAGE)
            if inner_validated:
                return {"validated": envelope}
            if inner_engineered:
                return {"engineered": envelope}
            return {"validated": envelope}
        if bare_validated:
            return {"validated": value}
        if bare_engineered:
            return {"engineered": value}
        return value


class RuleEvaluationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_count: int = 0
    flagged_count: int = Field(
        default=0, description="INDICATED or BORDERLINE -- decisions the report "
        "should surface."
    )
    indicated_count: int = 0
    borderline_count: int = 0
    not_indicated_count: int = 0
    insufficient_data_count: int = 0
    highest_risk: Optional[RiskLevel] = Field(
        default=None,
        description="RiskLevel.highest() over every decision carrying a risk. "
        "None when nothing was assessable -- deliberately NOT defaulted to Low, "
        "which would make 'nothing assessed' look reassuring.",
    )
    conditions_assessed: List[str] = Field(default_factory=list)
    conditions_flagged: List[str] = Field(default_factory=list)
    rules_evaluated: int = 0
    rules_fired: int = 0
    features_used: List[str] = Field(default_factory=list)
    questionable_features_used: List[str] = Field(default_factory=list)
    clinically_extreme_features_used: List[str] = Field(default_factory=list)
    partial_document: bool = False
    input_kind: str = Field(
        default="none",
        description="validated | engineered | none -- which form of input the "
        "engine was given.",
    )


class RuleEvaluationData(BaseModel):

    model_config = ConfigDict(extra="forbid")

    decisions: List[ClinicalDecision] = Field(
        default_factory=list,
        description="The Module 14 objects. Ordered by canonical condition, "
        "then by rule table order, so output is stable across runs.",
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="Warnings raised by MODULE 8 ITSELF. Upstream warnings are "
        "NOT merged in here -- see `upstream_warnings` / `all_warnings`.",
    )
    upstream_warnings: List[StageWarning] = Field(
        default_factory=list,
        description="Every warning from Modules 4, 5 and 6, carried forward with "
        "its original stage. Module 8 never edits, filters or drops these.",
    )
    all_warnings: List[StageWarning] = Field(
        default_factory=list,
        description="Every warning from every stage, upstream first, each tagged "
        "with the stage that raised it. Module 8's own carry stage='rules'.",
    )
    upstream: UpstreamExtraction = Field(
        default_factory=UpstreamExtraction,
        description="Module 4 context carried forward unchanged.",
    )
    upstream_summary: FeatureValidationSummary = Field(
        default_factory=FeatureValidationSummary,
        description="Module 6's own summary, preserved verbatim.",
    )
    summary: RuleEvaluationSummary = Field(default_factory=RuleEvaluationSummary)
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Reproducibility context for the RUN: engine and rule-table "
        "versions, which rules were evaluated. Never PHI, never a value, never "
        "report text.",
    )


class RuleEvaluationResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    success: bool = True
    data: RuleEvaluationData


__all__ = [
    "AMBIGUOUS_OBJECT_MESSAGE",
    "AMBIGUOUS_REQUEST_MESSAGE",
    "RULES_MODULE",
    "STAGE_RULES",
    "IncomingValidatedFeature",
    "RuleEvaluationData",
    "RuleEvaluationRequest",
    "RuleEvaluationResponse",
    "RuleEvaluationSummary",
    "ValidatedFeaturesInput",
]
