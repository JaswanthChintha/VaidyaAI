"""POST /api/v1/report/generate -- the Module 17-20 endpoint.

Thin HTTP wrapper. All logic lives in `app.services.report_builder`, whose
`generate_report`, `overall_status`, `prioritise` and `build_explainability`
are importable and callable in-process -- which is how Module 27 (dashboard),
Module 32 (doctor summary) and the Node backend will use them, exactly as
`evaluate_rules`, `predict_all` and `fuse_decisions` are used today.

The router lives in its own file and carries its own prefix so it can be
mounted alongside the other routers without either module owning the other.

AUTH: this endpoint receives medical feature values and returns a clinical
report about them, so it is PHI-bearing and carries the same service-key
dependency as `routes_rules.py`, `routes_ml.py` and `routes_decisions.py`.
`tests/test_auth.py` walks the route tree recursively and fails if any
`/api/v1` route lacks it.

INPUT TOLERANCE is inherited, not re-implemented: `ClinicalReportRequest`
subclasses `DecisionFusionRequest`, which subclasses `RuleEvaluationRequest`,
so every shape `/rules/evaluate`, `/ml/predict` and `/decisions/fuse` accept is
accepted identically here and every ambiguity is the same 422. Nothing is ever
guessed -- a wrong guess here would not raise, it would return HTTP 200
carrying an empty report, which is the worst possible failure mode for this
particular endpoint.

WHY THE RAW BODY IS READ AS WELL
--------------------------------
Module 6's `rejected` map is deliberately NOT parsed by the decision chain's
request models (see `app/schemas/rules.py`: that absence is what makes "a
clinical rule can never read a rejected value" structural rather than
disciplinary). Modules 17 and 20 DO need it, to say "we found this value but
could not trust its unit" instead of the factually wrong "it wasn't there".

So the route reads the already-buffered request body and lifts the map out with
`extract_rejected_features`. The decision chain still receives exactly what it
received before -- a `ValidatedFeaturesInput` with no `rejected` attribute to
read -- and only the report layer sees the refused values.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request

from app.core.auth import require_service_key
from app.core.logging import get_logger
from app.schemas.report import (
    ClinicalReportRequest,
    ClinicalReportResponse,
    OVERALL_STATUS_POLICY,
    PRIORITIZATION_POLICY,
    EXPLAINABILITY_POLICY,
    OVERALL_STATUS_LABELS,
    PRIORITY_BANDS,
    AVAILABILITY_VALUES,
)
from app.services.report_builder import (
    REPORT_POLICY,
    REPORT_VERSION,
    extract_rejected_features,
    generate_report,
)

logger = get_logger(__name__)

router = APIRouter(
    prefix="/api/v1/report",
    tags=["clinical-report"],
    dependencies=[Depends(require_service_key)],
)


async def _raw_body(request: Request) -> Any:
    """The already-buffered JSON body, or None.

    FastAPI has read and cached the body before this handler runs, so this is a
    read of memory rather than a second read of the stream. Any failure is
    swallowed: the rejected-feature join is an ENRICHMENT, and the worst case
    of not finding the map is the behaviour the service has today.
    """
    try:
        return await request.json()
    except Exception:  # noqa: BLE001 -- see the docstring
        return None


@router.post(
    "/generate",
    response_model=ClinicalReportResponse,
    response_model_exclude_none=False,
    summary="Generate the structured Clinical Report for one analysis",
)
async def generate(
    payload: ClinicalReportRequest, request: Request
) -> ClinicalReportResponse:
    # `validated` is preferred; `engineered` is accepted so the report is
    # usable before Module 6 has been run over HTTP -- the builder then runs
    # Module 6 in-process, so the report's laboratory values and its rejected
    # map are the real ones and cannot diverge from what the rules saw.
    rejected = payload.rejected_features or extract_rejected_features(
        await _raw_body(request)
    )
    report = generate_report(
        payload.validated,
        engineered=payload.engineered,
        rejected=rejected,
    )
    return ClinicalReportResponse(success=True, data=report)


@router.get(
    "/policy",
    summary="How the clinical report, overall status, priority and evidence are built",
)
async def policy() -> dict:
    """The report rules, in machine-readable form.

    Exposed for the same reason the rule table, the model metrics and the
    fusion policy are: a documented rule nobody can retrieve from the running
    service is not an accountability mechanism. Shape and policy only -- no
    PHI, no values.
    """
    return {
        "success": True,
        "data": {
            "clinical_report": {
                "module": 17,
                "version": REPORT_VERSION,
                "policy": REPORT_POLICY,
                "sections": [
                    "patient",
                    "laboratory_values",
                    "conditions",
                    "overall",
                    "overall_risk",
                    "critical_conditions",
                    "normal_findings",
                    "explainability",
                    "recommendations",
                    "metadata",
                    "validation_warnings",
                ],
            },
            "overall_health_status": {
                "module": 18,
                "policy": OVERALL_STATUS_POLICY,
                "labels": list(OVERALL_STATUS_LABELS),
                "fourth_case": (
                    "when nothing could be assessed the status is 'Not "
                    "Assessed' and never 'Healthy': an absence of findings in "
                    "a report that could not be read is not a finding of good "
                    "health"
                ),
            },
            "risk_prioritization": {
                "module": 19,
                "policy": PRIORITIZATION_POLICY,
                "bands": list(PRIORITY_BANDS),
                "prioritised_by": ["condition"],
            },
            "evidence_and_explainability": {
                "module": 20,
                "policy": EXPLAINABILITY_POLICY,
                "chain": ["Input", "Evidence", "Decision"],
                "availability_values": list(AVAILABILITY_VALUES),
                "ml_feature_importance_scope": "global_model_level",
                "ml_feature_importance_is_per_patient": False,
            },
        },
    }
