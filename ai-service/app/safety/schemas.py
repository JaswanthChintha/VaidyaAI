"""Module 24 -- the HTTP contract, pydantic v2 enforced.

Kept beside the validator rather than in `app/schemas/` because everything in
this package has to be importable without FastAPI and because Module 24 owns
its own vocabulary. The core objects (`SafetyVerdict`, `SafetyViolation`,
`SafeFallback`) are already pydantic models, so the response models here just
wrap them in the service's `{success, data}` envelope.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

from app.safety.fallback import SafeFallback
from app.safety.validator import SafetyContext, SafetyVerdict


class SafetyValidationRequest(BaseModel):
    """One piece of text to validate, plus the policy that applies to it.

    `extra="forbid"`: a caller who misspells `grounding_sources` would
    otherwise silently get a validation with NO numeric grounding and a clean
    verdict. In this module a typo must be a 422, not a weaker check.
    """

    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., description="The text to validate. Never logged.")
    grounding_sources: Tuple[str, ...] = Field(
        default=(),
        description=(
            "Retrieved knowledge (Modules 21/22) the generation was supposed "
            "to be grounded in. Every number in `text` must appear here or in "
            "`permitted_numbers`."
        ),
    )
    permitted_numbers: Tuple[float, ...] = Field(
        default=(),
        description=(
            "Numbers the explanation may legitimately state -- the patient's "
            "own validated values and the reference bounds behind them."
        ),
    )
    require_grounding: bool = Field(
        default=False,
        description="Refuse the text outright if no grounding was supplied.",
    )
    require_referral: bool = Field(
        default=True,
        description=(
            "Require the mandated 'qualified healthcare professional' framing. "
            "Turn off only for fragment-level checks."
        ),
    )
    check_numeric_grounding: bool = Field(default=True)
    purpose: str = Field(default="llm_explanation", max_length=64)

    def to_context(self) -> SafetyContext:
        return SafetyContext(
            grounding_sources=self.grounding_sources,
            permitted_numbers=self.permitted_numbers,
            require_grounding=self.require_grounding,
            require_referral=self.require_referral,
            check_numeric_grounding=self.check_numeric_grounding,
            purpose=self.purpose,
        )


class SafetyValidationData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: SafetyVerdict
    #: Populated exactly when the verdict is a rejection, so a caller that
    #: renders the response has something honest to show without a second call.
    fallback: Optional[SafeFallback] = None


class SafetyValidationResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    success: bool = True
    data: SafetyValidationData


__all__ = [
    "SafetyValidationData",
    "SafetyValidationRequest",
    "SafetyValidationResponse",
]
