"""The Module 8 (Clinical Rule Engine) request/response contract.

Module 8 consumes Module 6's validated feature set and emits
`ClinicalDecision[]` -- the shared type defined in `app/schemas/decisions.py`,
which is NOT redefined, subclassed or wrapped here.

--------------------------------------------------------------------------
WHAT THE ENGINE IS ALLOWED TO SEE
--------------------------------------------------------------------------

`ValidatedFeaturesInput` below models Module 6's `data` object and DELIBERATELY
HAS NO `rejected` FIELD.

That is not an oversight and it is not laziness. Module 6's `rejected` map holds
suspected extraction errors -- values that are physiologically impossible, of
the wrong type, or in a unit that could not be converted. A clinical rule must
never compare against one. By simply not parsing the field, the rule engine
cannot read a rejected value even by accident, even if a future edit tries to:
there is no attribute to read. The guarantee is structural rather than
disciplinary.

`questionable` IS parsed, and is a subset view of `valid`, so the engine can
carry "this decision rests on a shakier number" into its evidence and metadata
instead of pretending every input is equally solid.

--------------------------------------------------------------------------
ACCEPTED REQUEST SHAPES
--------------------------------------------------------------------------

THE CANONICAL FORM is Module 6's output:

    {"validated": <Module 6's `data` object>}

For the same reason `routes_validation.py` is tolerant -- a caller relaying a
response verbatim must never be silently handed an empty result -- these are
also accepted:

  * `{"engineered": <Module 5's `data` object>}`   raw, pre-validation input.
    The engine runs Module 6 over it in-process first, so rules still only ever
    see validated values. This is what makes the engine usable in tests and by
    Module 15 before validation has been run.
  * `{"success": ..., "data": {...}}`  either module's response envelope,
    relayed unchanged. Which module it came from is decided by whether the
    object carries `valid` (Module 6) or `features` (Module 5).
  * a BARE `data` object posted at the top level, classified the same way.

Anything ambiguous is a 422. Nothing is ever guessed:

  * an envelope AND a bare object in the same body
  * a bare object carrying both `valid` and `features`
  * an envelope carrying both `valid` and `features`

An explicit `validated` key always wins over an explicit `engineered` key,
because validated input is strictly better information. That precedence is
documented, deterministic, and not a guess.
"""

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

#: The stage identifier Module 8 stamps on its own warnings.
STAGE_RULES = "rules"
RULES_MODULE = 8


# --------------------------------------------------------------------------
# Request
# --------------------------------------------------------------------------


class IncomingValidatedFeature(BaseModel):
    """One entry of Module 6's `valid` map.

    Permissive about `value` for the same reason Module 6 is permissive about
    Module 5's: a single odd entry must not turn into an opaque 422 that
    discards every other perfectly good feature in the payload. The rule engine
    skips a value it cannot compare and says so in a warning.
    """

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
    """Module 6's `data` object, MINUS `rejected`.

    See the module docstring: the absence of `rejected` is the mechanism that
    makes "rules never consume rejected features" structural.
    """

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
    """See the module docstring for every accepted shape."""

    model_config = ConfigDict(extra="ignore")

    validated: Optional[ValidatedFeaturesInput] = None
    engineered: Optional[EngineeredFeaturesInput] = None

    @model_validator(mode="before")
    @classmethod
    def _unwrap(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        if "validated" in value or "engineered" in value:
            return value  # Explicit wins; `validated` beats `engineered` later.

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
            # An envelope with neither key carries no features at all. Treat it
            # as an empty validated set rather than guessing which module sent
            # it -- the outcome is identical either way (no rules can fire).
            return {"validated": envelope}
        if bare_validated:
            return {"validated": value}
        if bare_engineered:
            return {"engineered": value}
        return value


# --------------------------------------------------------------------------
# Response
# --------------------------------------------------------------------------


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
    """The `data` object of a successful rule-evaluation response."""

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
