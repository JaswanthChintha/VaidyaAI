from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.decisions import ClinicalDecision, RiskLevel
from app.schemas.features import StageWarning, UpstreamExtraction
from app.schemas.rules import RuleEvaluationRequest
from app.schemas.validation import FeatureValidationSummary

STAGE_ML = "ml"
ML_MODULE = 9


class MLPredictionRequest(RuleEvaluationRequest):

    model_config = ConfigDict(extra="ignore")


class PredictorRunSummary(BaseModel):

    model_config = ConfigDict(extra="forbid")

    name: str
    condition: str
    source: str
    version: str
    available: bool = True
    assessed: bool = Field(
        default=False,
        description="False when the predictor skipped for insufficient "
        "information or an unloadable model.",
    )
    skipped_reason: Optional[str] = None
    required_features: List[str] = Field(default_factory=list)
    required_missing: List[str] = Field(default_factory=list)
    probability_positive: Optional[float] = Field(
        default=None,
        description="P(positive class). None when the predictor skipped.",
    )


class MLPredictionSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_count: int = 0
    flagged_count: int = Field(
        default=0, description="INDICATED or BORDERLINE."
    )
    indicated_count: int = 0
    borderline_count: int = 0
    not_indicated_count: int = 0
    insufficient_data_count: int = 0
    highest_risk: Optional[RiskLevel] = Field(
        default=None,
        description="RiskLevel.highest() over decisions carrying a risk. None "
        "when nothing was assessable -- deliberately NOT defaulted to Low, "
        "which would make 'nothing assessed' look reassuring.",
    )
    predictors_registered: int = 0
    predictors_run: int = Field(
        default=0, description="Predictors that actually reached their model."
    )
    predictors_skipped: int = 0
    conditions_assessed: List[str] = Field(default_factory=list)
    conditions_flagged: List[str] = Field(default_factory=list)
    features_used: List[str] = Field(default_factory=list)
    questionable_features_used: List[str] = Field(default_factory=list)
    partial_document: bool = False
    input_kind: str = Field(
        default="none",
        description="validated | engineered | none.",
    )
    predictor_runs: List[PredictorRunSummary] = Field(default_factory=list)


class MLPredictionData(BaseModel):

    model_config = ConfigDict(extra="forbid")

    decisions: List[ClinicalDecision] = Field(
        default_factory=list,
        description="The Module 14 objects, ordered by canonical condition "
        "then by registration order, so output is stable across runs.",
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="Warnings raised by the ML LAYER ITSELF. Upstream warnings "
        "are NOT merged in here.",
    )
    upstream_warnings: List[StageWarning] = Field(
        default_factory=list,
        description="Every warning from Modules 4, 5 and 6, carried forward "
        "with its original stage. Never edited, filtered or dropped.",
    )
    all_warnings: List[StageWarning] = Field(
        default_factory=list,
        description="Every warning from every stage, upstream first. This "
        "module's own carry stage='ml'.",
    )
    upstream: UpstreamExtraction = Field(default_factory=UpstreamExtraction)
    upstream_summary: FeatureValidationSummary = Field(
        default_factory=FeatureValidationSummary
    )
    summary: MLPredictionSummary = Field(default_factory=MLPredictionSummary)
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Reproducibility context for the RUN: engine version, "
        "registered predictors, model provenance. Never PHI, never raw report "
        "text.",
    )


class MLPredictionResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    success: bool = True
    data: MLPredictionData


__all__ = [
    "ML_MODULE",
    "STAGE_ML",
    "MLPredictionData",
    "MLPredictionRequest",
    "MLPredictionResponse",
    "MLPredictionSummary",
    "PredictorRunSummary",
]
