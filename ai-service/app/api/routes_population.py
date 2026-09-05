"""The Module 31 (Population Context and Percentile Analysis) endpoints.

Thin HTTP wrappers. All logic lives in `app.services.population_context`,
whose `population_context()` is importable directly by Modules 27/32 exactly
as `engineer_features`, `evaluate_rules` and `analyse_trends` are. **The
in-process API is the primary interface**; this router exists so the Node
backend -- which already drives the pipeline over HTTP -- can ask for
population context without a second integration style.

DETERMINISTIC AND MODEL-FREE. `population_context` calls no LLM, performs no
I/O beyond the distribution tables loaded once at import, and reads no clock
except for `generated_at`. Same request in, same bands out. A percentile is a
factual claim about a real surveyed population, and this project's standing
property is that such a claim has no free-text entry point.

AUTH: `POST /context` carries medical values and is therefore PHI-bearing, so
the router carries the same service-key dependency as `routes_repository.py`.
`GET /policy` returns only the reviewable rules and the shipped tables'
provenance -- no patient data -- but sits behind the same dependency because
the whole `/api/v1` surface does: `tests/test_auth.py` walks the route tree
recursively and fails if any `/api/v1` route lacks it.
"""

from __future__ import annotations

from typing import Dict

from fastapi import APIRouter, Depends

from app.core.auth import require_service_key
from app.population.policy import POLICY
from app.schemas.population import (
    PopulationContextRequest,
    PopulationContextResponse,
)
from app.services.population_context import population_context, population_document

router = APIRouter(
    prefix="/api/v1/population",
    tags=["population-context"],
    dependencies=[Depends(require_service_key)],
)


@router.post(
    "/context",
    response_model=PopulationContextResponse,
    response_model_exclude_none=False,
    summary="Place a patient's values in an age- and sex-matched population",
)
async def context(request: PopulationContextRequest) -> PopulationContextResponse:
    """`available` is the field to branch on, never `comparison`.

    When `available` is false the entry has NO `comparison` object at all, so
    there is no value, no percentile and no band anywhere in it -- not null,
    not zero, not an empty band. `reason_code` and `message` say why instead.

    A percentile is reported as a BAND between two adjacent published
    cut-points ("between the 75th and the 90th"), never as a single
    interpolated number. Matching is on sex AND age band only; there is no
    all-adults fallback and no nearest-band fallback.
    """
    return PopulationContextResponse(success=True, data=population_context(request))


@router.get(
    "/policy",
    summary="The population policy, the exclusions, and the shipped tables",
)
async def policy() -> Dict[str, object]:
    """The reviewable rules and the evidence behind them. No patient data.

    Exposed because a percentile is only meaningful if the reader can see
    which population it describes -- so this returns the survey, cycle, file,
    sha256 digest and NHANES variable behind every covered parameter, the
    cohort sample sizes, and the canonical features that are deliberately NOT
    covered together with the reason for each.
    """
    return {
        "success": True,
        "data": {"policy": POLICY, "service": population_document()},
    }
