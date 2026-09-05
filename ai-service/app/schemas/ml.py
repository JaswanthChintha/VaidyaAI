"""The Module 9/10 (ML Prediction Engine) request/response contract.

Like Module 8, this module emits `ClinicalDecision[]` -- the shared type in
`app/schemas/decisions.py`, which is NOT redefined, subclassed or wrapped here.

==========================================================================
THE REQUEST SHAPE IS INHERITED FROM MODULE 8 ON PURPOSE
==========================================================================

`MLPredictionRequest` SUBCLASSES `RuleEvaluationRequest` and adds nothing.

That is the whole trick. The rule engine and the ML engine consume the same
Module 6 output, and a caller relaying a response verbatim must get the same
answer from both. Re-implementing the unwrap logic here would let the two
tolerances drift -- and the failure mode of a drift is not an error, it is an
HTTP 200 carrying `decisions: []`, which is exactly the silent-success bug
recorded in MEMORY.md section 6f. Inheriting makes drift impossible.

So every shape `POST /api/v1/rules/evaluate` accepts, `POST /api/v1/ml/predict`
accepts identically, with the same 422s:

    {"validated":  <Module 6 data>}          canonical
    {"engineered": <Module 5 data>}          validated in-process first
    {"success":.., "data": {...}}            either module's envelope, relayed
    a BARE data object at the top level      classified by `valid` vs `features`

and ambiguity is a 422, never a guess:

    an envelope AND a bare object together
    an object carrying both `valid` and `features`

`validated` beats `engineered` when both are named, for the same documented
reason: validated input is strictly better information.

Note that `ValidatedFeaturesInput` HAS NO `rejected` FIELD. The ML layer
inherits that property too: a value Module 6 rejected as physiologically
impossible cannot reach a model, because there is no attribute to read it from.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.decisions import ClinicalDecision, RiskLevel
from app.schemas.features import StageWarning, UpstreamExtraction
from app.schemas.rules import RuleEvaluationRequest
from app.schemas.validation import FeatureValidationSummary

#: The stage identifier Module 9 stamps on its own warnings.
STAGE_ML = "ml"
ML_MODULE = 9


class MLPredictionRequest(RuleEvaluationRequest):
    """Byte-for-byte the same accepted shapes as Module 8. See the docstring."""

    model_config = ConfigDict(extra="ignore")


class PredictorRunSummary(BaseModel):
    """What one registered predictor did on this request.

    Present for EVERY registered predictor, including the ones that skipped, so
    "the kidney model was never registered" is distinguishable from "the kidney
    model ran and found nothing" -- the same reasoning that makes the three
    fusion conditions `always_assessed` in `app/data/conditions.py`.
    """

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
    """The `data` object of a successful ML-prediction response."""

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
