"""The Modules 23, 25 and 26 endpoints.

    POST /api/v1/explain/feature    Module 23 -- explain one parameter
    POST /api/v1/explain/report     Module 23 -- explain a Module 17 report
    POST /api/v1/explain/term       Module 25 -- explain a medical term
    GET  /api/v1/explain/terms      Module 25 -- what it will answer
    POST /api/v1/explain/guidance   Module 26 -- educational lifestyle guidance
    POST /api/v1/explain/glossary   describe tests this platform does NOT assess
    POST /api/v1/explain/clinician-summary
                                    write Module 32's handover note as prose
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


class GlossaryResponse(BaseModel):
    """The same `{success, data}` envelope every other endpoint here returns.

    THIS WRAPPER WAS MISSING AND THE FEATURE WAS DEAD ON EVERY CALL. The route
    returned a bare `GlossaryData`, so the backend's `unwrapEnvelope` -- which
    requires `success === true` and an object `data` -- rejected a perfectly
    good 200 as `AI_SERVICE_MALFORMED_RESPONSE`. The descriptions were
    generated, safety-validated, cached, and thrown away at the transport
    boundary; the ai-service log said "generated: 3" while the analysis
    recorded the stage as failed.

    Nothing caught it because the module's 14 tests never went through HTTP.
    The endpoint tests added alongside this do, and assert the envelope
    itself rather than only the payload inside it.
    """

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
    """What each named test measures -- and nothing about any patient.

    Returns an empty set rather than erroring when no model is configured: an
    unconfigured key is a service state, and the caller renders the values
    without descriptions exactly as it does when a description is refused.
    """
    if llm is None:
        return GlossaryResponse(data=GlossaryData())
    return GlossaryResponse(
        data=describe_parameters(
            request.test_names, llm, max_calls=GLOSSARY_MAX_PER_REQUEST
        )
    )


class LabPolarityRequest(BaseModel):
    """Series to classify: a test NAME, two values, and the lab's own interval.

    THE VALUES ARE HERE AND THEY NEVER REACH THE MODEL. Module 35's prompt is
    built from `test_name` alone -- the arithmetic that uses `first_value` and
    `last_value` is Module 28's classifier, running in this service. This is
    the same split Module 27b makes and for the same reason: the model supplies
    a property of the TEST, the pipeline supplies everything about the person.

    `reference_low` / `reference_high` are the interval the PATIENT'S OWN
    LABORATORY printed. They are accepted rather than generated because an
    invented reference range is the most damaging hallucination available to
    this feature, and §6v records one reaching a patient already.
    """

    model_config = ConfigDict(extra="forbid")

    series: List[LabSeriesInput] = Field(default_factory=list, max_length=64)


class LabPolarityResponse(BaseModel):
    """The `{success, data}` envelope -- see `GlossaryResponse` for why.

    That wrapper was missing once and the feature was dead on every call while
    the log said it had worked. This one has an endpoint test that asserts the
    envelope, not only the payload inside it.
    """

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
    """improving / worsening / stable for an unassessed test.

    Returns an empty set rather than erroring when no model is configured. The
    caller then renders the readings and the movement word exactly as it does
    when a polarity is refused -- an unconfigured key is a service state, not a
    finding about the patient.
    """
    if llm is None:
        return LabPolarityResponse(data=LabPolarityData())
    return LabPolarityResponse(
        data=classify_lab_series(
            request.series, llm, max_calls=LAB_POLARITY_MAX_PER_REQUEST
        )
    )


class LabNameMatchRequest(BaseModel):
    """Test names to group. THERE IS NOWHERE IN THIS SHAPE TO PUT A VALUE.

    Module 35's request carries the readings and keeps them from the prompt by
    construction. This one has no field for them at all, which is the stronger
    version of the same guarantee: a caller cannot leak a patient value through
    an endpoint that does not accept one.
    """

    model_config = ConfigDict(extra="forbid")

    names: List[str] = Field(default_factory=list, max_length=64)


class LabNameMatchResponse(BaseModel):
    """The `{success, data}` envelope -- see `GlossaryResponse` for why."""

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
    """Which of these printed names are one test.

    Returns an empty set rather than erroring when no model is configured. The
    caller then groups by word set exactly as it did before this existed -- an
    unjoined name is the status quo, not a finding about anyone.
    """
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
    """The `{success, data}` envelope, for the reason §6w records at length.

    A route that returns a bare payload is rejected by the backend's
    `unwrapEnvelope` as malformed, and the feature is then dead on every call
    with nothing saying so. This route is also listed in
    `tests/test_explain_endpoint.py::ROUTES`, which is the test that would
    have caught that one on its first run.
    """

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
    """Rewrite an existing Module 32 summary for the reader it is addressed to.

    NO MODEL IS NOT AN ERROR. With no key configured this answers 200 with
    `outcome: model_unavailable` and no text, because the caller's fallback --
    the composed passage it renders today -- is the normal path here, not a
    failure path. Erroring would turn a configuration state into a broken page.
    """
    return ClinicianSummaryResponse(
        data=write_clinician_summary(request.summary, llm=llm)
    )


class ClinicianFingerprintData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fingerprint: str
    narrative_version: str


class ClinicianFingerprintResponse(BaseModel):
    """Same `{success, data}` envelope as every route the backend reads."""

    model_config = ConfigDict(extra="forbid")

    success: bool = True
    data: ClinicianFingerprintData


@router.get(
    "/clinician-summary/fingerprint",
    response_model=ClinicianFingerprintResponse,
    summary="Fingerprint of the code that writes the clinician note",
)
def clinician_summary_fingerprint_endpoint() -> ClinicianFingerprintResponse:
    """Which version of the note-writing code is running (2026-10-03).

    No patient data in or out, and no model call. The backend compares this
    with the fingerprint saved beside a cached note and re-writes the note
    when they differ -- see `NARRATIVE_CODE_FINGERPRINT`.
    """
    return ClinicianFingerprintResponse(
        data=ClinicianFingerprintData(
            fingerprint=NARRATIVE_CODE_FINGERPRINT,
            narrative_version=NARRATIVE_VERSION,
        )
    )


class SummaryProseRequest(BaseModel):
    """The sentences the page has ALREADY composed, in the order it shows them.

    NOT A REPORT, AND THAT IS THE ENTIRE CONTRACT. This endpoint rewrites
    finished patient-facing text and derives no finding of its own; handing it
    a payload to summarise instead would make it the one thing
    `Dashboard.jsx`'s `InShort` comment exists to refuse.
    """

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
    """The `{success, data}` envelope. See `ClinicianSummaryResponse`."""

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
    """Make composed sentences read better, or say why they were not changed.

    NO MODEL IS NOT AN ERROR, for the same reason the clinician summary says:
    the caller's fallback is the composed text it already has, which is what
    the page shows today. A 200 carrying `outcome: model_unavailable` keeps a
    configuration state out of the page's error path.
    """
    return SummaryProseResponse(
        data=rewrite_summary(request.sentences, names=request.names, llm=llm)
    )


class FindingContextRequest(BaseModel):
    """Tests already marked out of range, by NAME and DIRECTION only.

    THE SHAPE IS THE SAFETY ARGUMENT. There is deliberately no field for a
    value, a reference range, an age or a sex: this endpoint answers what a
    raised or lowered result is GENERALLY associated with, and a payload that
    could carry the reader's own numbers would make that answer about them.
    `extra="forbid"` so a caller cannot smuggle one in.
    """

    model_config = ConfigDict(extra="forbid")

    findings: List[Dict[str, str]] = Field(
        default_factory=list,
        description='[{"test_name": "...", "direction": "raised"|"lowered"}]. '
        "A direction this service does not know is skipped, never guessed at.",
    )


class FindingContextResponse(BaseModel):
    """The `{success, data}` envelope. See `ClinicianSummaryResponse`."""

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
    """General context for findings something else already made.

    NO MODEL IS NOT AN ERROR: 200 with no entries, and the caller renders
    nothing. Every refusal is per-entry and carries no text.
    """
    return FindingContextResponse(data=describe_findings(request.findings, llm=llm))


__all__ = ["get_explanation_llm", "router"]
