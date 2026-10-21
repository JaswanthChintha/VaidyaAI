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
from app.services.finding_context import (
    FindingContextData,
    describe_findings,
)
from app.services.summary_prose import (
    SummaryProse,
    rewrite_summary,
)
from app.services.clinician_narrative import (
    NARRATIVE_CODE_FINGERPRINT,
    NARRATIVE_VERSION,
    ClinicianNarrative,
    write_clinician_summary,
)
from app.services.parameter_glossary import (
    MAX_PER_REQUEST as GLOSSARY_MAX_PER_REQUEST,
    GlossaryData,
    describe_parameters,
)
from app.services.lab_polarity import (
    MAX_PER_REQUEST as LAB_POLARITY_MAX_PER_REQUEST,
    LabPolarityData,
    LabSeriesInput,
    classify_lab_series,
)
from app.services.lab_name_match import (
    NameMatchData,
    match_names,
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
    if not settings.has_api_key:
        return None
    from app.services.gemini_text import build_text_client

    return build_text_client(settings)


class FeatureExplanationRequest(BaseModel):

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
    return {"success": True, "data": terminology_policy_document()}


@router.post(
    "/guidance",
    response_model=GuidanceResponse,
    response_model_exclude_none=False,
    summary="Module 26 -- pre-approved educational lifestyle guidance",
)
async def guidance(payload: GuidanceRequest) -> GuidanceResponse:
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

    model_config = ConfigDict(extra="forbid")

    test_names: List[str] = Field(default_factory=list, max_length=64)


class GlossaryResponse(BaseModel):

    model_config = ConfigDict(extra="forbid")

    success: bool = True
    data: GlossaryData


@router.post(
    "/glossary",
    response_model=GlossaryResponse,
    response_model_exclude_none=False,
    summary="Describe laboratory tests this platform does not assess",
)
def glossary_endpoint(
    request: GlossaryRequest,
    llm: Any = Depends(get_explanation_llm),
) -> GlossaryResponse:
    if llm is None:
        return GlossaryResponse(data=GlossaryData())
    return GlossaryResponse(
        data=describe_parameters(
            request.test_names, llm, max_calls=GLOSSARY_MAX_PER_REQUEST
        )
    )


class LabPolarityRequest(BaseModel):

    model_config = ConfigDict(extra="forbid")

    series: List[LabSeriesInput] = Field(default_factory=list, max_length=64)


class LabPolarityResponse(BaseModel):

    model_config = ConfigDict(extra="forbid")

    success: bool = True
    data: LabPolarityData


@router.post(
    "/lab-polarity",
    response_model=LabPolarityResponse,
    response_model_exclude_none=False,
    summary="Classify trends for laboratory tests this platform does not assess",
)
def lab_polarity_endpoint(
    request: LabPolarityRequest,
    llm: Any = Depends(get_explanation_llm),
) -> LabPolarityResponse:
    if llm is None:
        return LabPolarityResponse(data=LabPolarityData())
    return LabPolarityResponse(
        data=classify_lab_series(
            request.series, llm, max_calls=LAB_POLARITY_MAX_PER_REQUEST
        )
    )


class LabNameMatchRequest(BaseModel):

    model_config = ConfigDict(extra="forbid")

    names: List[str] = Field(default_factory=list, max_length=64)


class LabNameMatchResponse(BaseModel):

    model_config = ConfigDict(extra="forbid")

    success: bool = True
    data: NameMatchData


@router.post(
    "/lab-name-match",
    response_model=LabNameMatchResponse,
    response_model_exclude_none=False,
    summary="Group printed laboratory test names that are the same test",
)
def lab_name_match_endpoint(
    request: LabNameMatchRequest,
    llm: Any = Depends(get_explanation_llm),
) -> LabNameMatchResponse:
    if llm is None:
        return LabNameMatchResponse(data=NameMatchData())
    return LabNameMatchResponse(data=match_names(request.names, llm))


class ClinicianSummaryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: Dict[str, Any] = Field(
        description="A Module 32 DoctorSummary, as returned by "
        "POST /api/v1/report/doctor-summary. Posted verbatim: this endpoint "
        "REWRITES a document that already exists and derives no finding of "
        "its own."
    )


class ClinicianSummaryResponse(BaseModel):

    model_config = ConfigDict(extra="forbid")

    success: bool = True
    data: ClinicianNarrative


@router.post(
    "/clinician-summary",
    response_model=ClinicianSummaryResponse,
    response_model_exclude_none=False,
    summary="Write the clinician handover note as prose",
)
def clinician_summary_endpoint(
    request: ClinicianSummaryRequest,
    llm: Any = Depends(get_explanation_llm),
) -> ClinicianSummaryResponse:
    return ClinicianSummaryResponse(
        data=write_clinician_summary(request.summary, llm=llm)
    )


class ClinicianFingerprintData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fingerprint: str
    narrative_version: str


class ClinicianFingerprintResponse(BaseModel):

    model_config = ConfigDict(extra="forbid")

    success: bool = True
    data: ClinicianFingerprintData


@router.get(
    "/clinician-summary/fingerprint",
    response_model=ClinicianFingerprintResponse,
    summary="Fingerprint of the code that writes the clinician note",
)
def clinician_summary_fingerprint_endpoint() -> ClinicianFingerprintResponse:
    return ClinicianFingerprintResponse(
        data=ClinicianFingerprintData(
            fingerprint=NARRATIVE_CODE_FINGERPRINT,
            narrative_version=NARRATIVE_VERSION,
        )
    )


class SummaryProseRequest(BaseModel):

    model_config = ConfigDict(extra="forbid")

    sentences: List[str] = Field(
        min_length=1,
        description="Composed summary sentences, verbatim and in order.",
    )
    names: List[str] = Field(
        default_factory=list,
        description="Condition and test names that must survive the rewrite. "
        "Supplied by the caller because it knows which tokens are names; this "
        "service must not guess at them.",
    )


class SummaryProseResponse(BaseModel):

    model_config = ConfigDict(extra="forbid")

    success: bool = True
    data: SummaryProse


@router.post(
    "/summary-prose",
    response_model=SummaryProseResponse,
    response_model_exclude_none=False,
    summary="Rewrite already-composed summary sentences for flow",
)
def summary_prose_endpoint(
    request: SummaryProseRequest,
    llm: Any = Depends(get_explanation_llm),
) -> SummaryProseResponse:
    return SummaryProseResponse(
        data=rewrite_summary(request.sentences, names=request.names, llm=llm)
    )


class FindingContextRequest(BaseModel):

    model_config = ConfigDict(extra="forbid")

    findings: List[Dict[str, str]] = Field(
        default_factory=list,
        description='[{"test_name": "...", "direction": "raised"|"lowered"}]. '
        "A direction this service does not know is skipped, never guessed at.",
    )


class FindingContextResponse(BaseModel):

    model_config = ConfigDict(extra="forbid")

    success: bool = True
    data: FindingContextData


@router.post(
    "/finding-context",
    response_model=FindingContextResponse,
    response_model_exclude_none=False,
    summary="What a raised or lowered test is generally associated with",
)
def finding_context_endpoint(
    request: FindingContextRequest,
    llm: Any = Depends(get_explanation_llm),
) -> FindingContextResponse:
    return FindingContextResponse(data=describe_findings(request.findings, llm=llm))


__all__ = ["get_explanation_llm", "router"]
