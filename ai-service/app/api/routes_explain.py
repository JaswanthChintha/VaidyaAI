"""The Modules 23, 25 and 26 endpoints.

    POST /api/v1/explain/feature    Module 23 -- explain one parameter
    POST /api/v1/explain/report     Module 23 -- explain a Module 17 report
    POST /api/v1/explain/term       Module 25 -- explain a medical term
    GET  /api/v1/explain/terms      Module 25 -- what it will answer
    POST /api/v1/explain/guidance   Module 26 -- educational lifestyle guidance
    POST /api/v1/explain/glossary   describe tests this platform does NOT assess
    GET  /api/v1/explain/policy     what all three do and refuse to do

Thin HTTP wrapper, like `routes_report.py` and `routes_safety.py`. All logic
lives in `app.services.explanation`, `app.services.terminology` and
`app.services.lifestyle`, whose `explain_feature`, `explain_report`,
`explain_term` and `lifestyle_guidance` are importable and callable
in-process -- which is how the Node backend and Modules 27/32 will use them.

AUTH: every route carries the service-key dependency, exactly as
`routes_report.py` does. `/explain/feature` receives a patient's laboratory
value and returns prose about it, so it is plainly PHI-bearing; the
introspection routes carry it too, for the reason `routes_safety.py` gives --
an unauthenticated reader of the policy is an unauthenticated reader of exactly
what would have to be evaded. `tests/test_auth.py` walks the route tree
recursively and fails if any `/api/v1` route lacks it.

LOGGING: nothing here logs a value, a term, a prompt or a generated sentence.
The service modules log outcomes, codes and counts through `safe_meta`.

THE LLM IS A DEPENDENCY, NOT AN IMPORT. `get_explanation_llm` is overridable
with `app.dependency_overrides`, which is how the offline test suite runs the
generation paths with no key and no network -- the same pattern
`routes_ocr.get_extraction_service` uses for Module 4.
"""

from __future__ import annotations

import functools

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from fastapi.concurrency import run_in_threadpool

from app.config import Settings, get_settings
from app.core.auth import require_service_key
from app.core.logging import get_logger
from app.services.explanation import (
    DEFAULT_MAX_EXPLANATIONS,
    PatientExplanation,
    ReportExplanationSet,
    explain_feature,
    explain_report,
    explanation_policy_document,
)
from app.services.lifestyle import (
    LifestyleGuidance,
    guidance_policy_document,
    lifestyle_guidance,
)
from app.services.parameter_glossary import (
    MAX_PER_REQUEST as GLOSSARY_MAX_PER_REQUEST,
    GlossaryData,
    describe_parameters,
)
from app.services.terminology import (
    MAX_TERM_CHARS,
    TerminologyAnswer,
    explain_term,
    terminology_policy_document,
)

logger = get_logger(__name__)

router = APIRouter(
    prefix="/api/v1/explain",
    tags=["patient-explanation"],
    dependencies=[Depends(require_service_key)],
)


def get_explanation_llm(settings: Settings = Depends(get_settings)) -> Any:
    """The text client, or None when no key is configured.

    Returning None rather than raising is deliberate: an unconfigured model is
    a service state, not a request error, and the service modules answer it
    with the structured fallback instead of a 5xx. Overridden in tests.
    """
    if not settings.has_api_key:
        return None
    from app.services.gemini_text import build_text_client

    return build_text_client(settings)


# --------------------------------------------------------------------------
# Requests
# --------------------------------------------------------------------------


class FeatureExplanationRequest(BaseModel):
    """One canonical parameter and the finding already reached about it.

    STRICT (`extra="forbid"`): a caller that misspells a field gets a 422
    rather than an explanation built from a silently missing value.
    """

    model_config = ConfigDict(extra="forbid")

    feature: str = Field(
        max_length=64,
        description=(
            "CANONICAL feature name from app/data/feature_catalog.py, matched "
            "exactly. Free text is not accepted here -- see "
            "POST /api/v1/explain/term for the term-lookup path and why it "
            "refuses rather than guesses."
        ),
    )
    value: Optional[Any] = Field(
        default=None, description="The patient's VALIDATED value."
    )
    unit: Optional[str] = Field(default=None, max_length=32)
    interpretation: Optional[str] = Field(
        default=None,
        max_length=240,
        description=(
            "The interpretation the analysis already reached, as a short "
            "label. Structured output from Modules 8/16 -- not patient text."
        ),
    )
    conditions: List[str] = Field(default_factory=list, max_length=8)
    reference_low: Optional[float] = None
    reference_high: Optional[float] = None
    status: Optional[str] = Field(default=None, max_length=32)
    additional_permitted_numbers: List[float] = Field(
        default_factory=list,
        max_length=16,
        description=(
            "Extra numbers the explanation may state -- rule-table thresholds "
            "the caller already holds. EVERY number here becomes citable, so "
            "pass only values you can vouch for."
        ),
    )


class ReportExplanationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report: Dict[str, Any] = Field(
        description="A Module 17 clinical report, as returned by "
        "POST /api/v1/report/generate."
    )
    features: Optional[List[str]] = Field(
        default=None,
        max_length=16,
        description="Restrict to these canonical features. None means all "
        "usable laboratory values, up to `max_explanations`.",
    )
    max_explanations: int = Field(
        default=DEFAULT_MAX_EXPLANATIONS,
        ge=0,
        le=DEFAULT_MAX_EXPLANATIONS,
        description=(
            "Each explanation is a model call. Capped rather than unbounded so "
            "one request cannot become a dozen round trips."
        ),
    )


class TermExplanationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    term: str = Field(
        max_length=MAX_TERM_CHARS,
        description=(
            "A medical term. Mapped EXACTLY onto a canonical feature or a "
            "curated document; an unmapped term is refused and nothing is "
            "searched for."
        ),
    )
    simplify: bool = Field(
        default=False,
        description=(
            "Ask the LLM to rewrite the curated entry in plainer language, "
            "gated by Module 24. Off by default: the curated text was written "
            "for patients and reviewed."
        ),
    )


class GuidanceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conditions: List[str] = Field(default_factory=list, max_length=16)
    features: List[str] = Field(default_factory=list, max_length=16)
    codes: List[str] = Field(
        default_factory=list,
        max_length=32,
        description="Recommendation codes the caller already holds.",
    )


# --------------------------------------------------------------------------
# Responses
# --------------------------------------------------------------------------


class FeatureExplanationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    success: bool = True
    data: PatientExplanation


class ReportExplanationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    success: bool = True
    data: ReportExplanationSet


class TermExplanationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    success: bool = True
    data: TerminologyAnswer


class GuidanceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    success: bool = True
    data: LifestyleGuidance


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------


@router.post(
    "/feature",
    response_model=FeatureExplanationResponse,
    response_model_exclude_none=False,
    summary="Module 23 -- explain one parameter in patient-friendly language",
)
async def feature_explanation(
    payload: FeatureExplanationRequest,
    llm: Any = Depends(get_explanation_llm),
    settings: Settings = Depends(get_settings),
) -> FeatureExplanationResponse:
    """Structured findings + retrieved knowledge -> LLM -> Module 24 -> here.

    `data.explanation` is populated only when the safety layer approved the
    generated text; otherwise it is null and `data.fallback` carries the
    structured, catalogue-sourced response with `data.outcome` saying why.
    """
    # OFF THE EVENT LOOP. `explain_feature` calls Gemini through the blocking
    # google-genai client; on this project's own live run the explanation stage
    # took 40s even after per-feature calls were parallelised. Run directly in
    # this `async def` it would hold the loop for that whole time and stall
    # every other request, including `/health`. `run_in_threadpool` awaits it
    # on a worker thread instead; `anyio.to_thread.run_sync` copies the
    # contextvars context, so the request-id logging still works.
    result = await run_in_threadpool(
        functools.partial(
            explain_feature,
            payload.feature,
            value=payload.value,
            unit=payload.unit,
            interpretation=payload.interpretation,
            conditions=tuple(payload.conditions),
            reference_low=payload.reference_low,
            reference_high=payload.reference_high,
            status=payload.status,
            additional_permitted_numbers=tuple(payload.additional_permitted_numbers),
            llm=llm,
            settings=settings,
        )
    )
    return FeatureExplanationResponse(success=True, data=result)


@router.post(
    "/report",
    response_model=ReportExplanationResponse,
    response_model_exclude_none=False,
    summary="Module 23 -- attach explanations to a Module 17 clinical report",
)
async def report_explanation(
    payload: ReportExplanationRequest,
    llm: Any = Depends(get_explanation_llm),
    settings: Settings = Depends(get_settings),
) -> ReportExplanationResponse:
    # OFF THE EVENT LOOP. `explain_report` calls Gemini through the blocking
    # google-genai client; on this project's own live run the explanation stage
    # took 40s even after per-feature calls were parallelised. Run directly in
    # this `async def` it would hold the loop for that whole time and stall
    # every other request, including `/health`. `run_in_threadpool` awaits it
    # on a worker thread instead; `anyio.to_thread.run_sync` copies the
    # contextvars context, so the request-id logging still works.
    result = await run_in_threadpool(
        functools.partial(
            explain_report,
            payload.report,
            llm=llm,
            settings=settings,
            max_explanations=payload.max_explanations,
            features=payload.features,
        )
    )
    return ReportExplanationResponse(success=True, data=result)


@router.post(
    "/term",
    response_model=TermExplanationResponse,
    response_model_exclude_none=False,
    summary="Module 25 -- explain a medical term, or say it is not covered",
)
async def term_explanation(
    payload: TermExplanationRequest,
    llm: Any = Depends(get_explanation_llm),
    settings: Settings = Depends(get_settings),
) -> TermExplanationResponse:
    """Refuses an unmapped term instead of retrieving on it.

    `data.covered` is false and `data.outcome` is `term_not_covered` when the
    term is outside the curated vocabulary. This is the correct answer, not a
    failure: the retriever cannot distinguish a term the corpus covers from one
    it does not, so a nearest match would be an explanation of the wrong test.
    """
    result = await run_in_threadpool(
        functools.partial(
            explain_term,
            payload.term,
            simplify=payload.simplify,
            llm=llm,
            settings=settings,
        )
    )
    return TermExplanationResponse(success=True, data=result)


@router.get(
    "/terms",
    summary="Module 25 -- every term this service will explain",
)
async def terms() -> dict:
    """The covered vocabulary, and the gaps, published rather than implied."""
    return {"success": True, "data": terminology_policy_document()}


@router.post(
    "/guidance",
    response_model=GuidanceResponse,
    response_model_exclude_none=False,
    summary="Module 26 -- pre-approved educational lifestyle guidance",
)
async def guidance(payload: GuidanceRequest) -> GuidanceResponse:
    """Catalogue text only. This route reaches no language model.

    It deliberately takes no LLM dependency at all, so the absence of
    generation is visible in the signature rather than asserted in a comment.
    """
    result = lifestyle_guidance(
        conditions=tuple(payload.conditions),
        features=tuple(payload.features),
        codes=tuple(payload.codes),
    )
    return GuidanceResponse(success=True, data=result)


@router.get(
    "/policy",
    summary="What Modules 23, 25 and 26 do, and what they refuse to do",
)
async def policy() -> dict:
    """The explanation policies, in machine-readable form.

    Published for the same reason the rule table, the model metrics, the fusion
    policy and the safety rules are: a documented rule nobody can retrieve from
    the running service is not an accountability mechanism. That includes the
    prompt's own prohibition list and Module 25's known coverage gaps.
    """
    return {
        "success": True,
        "data": {
            "patient_explanation": explanation_policy_document(),
            "terminology": terminology_policy_document(),
            "lifestyle_guidance": guidance_policy_document(),
            "architecture": [
                "structured findings + retrieved knowledge",
                "LLM",
                "Module 24 safety validation",
                "approved educational response",
            ],
            "never": "LLM output shown directly to a patient",
        },
    }


class GlossaryRequest(BaseModel):
    """Test NAMES only. There is deliberately nowhere to put a patient value.

    The shape is the safety property: a caller cannot send a result even by
    accident, so the model can never be asked what someone's number means.
    """

    model_config = ConfigDict(extra="forbid")

    test_names: List[str] = Field(default_factory=list, max_length=64)


@router.post(
    "/glossary",
    response_model=GlossaryData,
    summary="Describe laboratory tests this platform does not assess",
)
def glossary_endpoint(
    request: GlossaryRequest,
    llm: Any = Depends(get_explanation_llm),
) -> GlossaryData:
    """What each named test measures -- and nothing about any patient.

    Returns an empty set rather than erroring when no model is configured: an
    unconfigured key is a service state, and the caller renders the values
    without descriptions exactly as it does when a description is refused.
    """
    if llm is None:
        return GlossaryData()
    return describe_parameters(
        request.test_names, llm, max_calls=GLOSSARY_MAX_PER_REQUEST
    )


__all__ = ["get_explanation_llm", "router"]
