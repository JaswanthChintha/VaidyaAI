"""The Module 28 (Health Timeline and Trend Analysis) endpoints.

Thin HTTP wrappers. All logic lives in `app.services.trend_analyzer`, whose
`analyse_trends()` is importable directly by Modules 29/30/32 exactly as
`engineer_features`, `validate_features` and `evaluate_rules` are. **The
in-process API is the primary interface**; this router exists so the Node
backend -- which owns the durable report history and already drives the
pipeline over HTTP -- can ask for a timeline without a second integration
style.

WHERE THE HISTORY COMES FROM. This service holds no database. Module 7's
repository is in-memory and process-local, so it cannot be the source of a
patient's history across restarts or workers. The backend assembles the
history from Mongo (`Report.chronoDate` is indexed on `{user, chronoDate}`
precisely for this module) and POSTs the snapshots in. That keeps ownership
scoping in the one place that has an authenticated user, and keeps this
service a pure function of its request.

DETERMINISTIC AND MODEL-FREE. `analyse_trends` calls no LLM, reads no clock
except for `generated_at`, and performs no I/O. Same request in, same trends
out. That is deliberate: a trend is a claim about a patient's direction of
travel, and this project's standing property is that interpretation text has
no free-text entry point.

AUTH: every route here handles medical values over time and is therefore
PHI-bearing, so the router carries the same service-key dependency as
`routes_repository.py`. `tests/test_auth.py` walks the route tree recursively
and fails if any `/api/v1` route lacks it.
"""

from __future__ import annotations

from typing import Dict

from fastapi import APIRouter, Depends

from app.core.auth import require_service_key
from app.data.trend_polarity import policy_document
from app.schemas.timeline import (
    TimelineTrendsRequest,
    TimelineTrendsResponse,
)
from app.services.trend_analyzer import analyse_trends, analyzer_document

router = APIRouter(
    prefix="/api/v1/timeline",
    tags=["timeline"],
    dependencies=[Depends(require_service_key)],
)


@router.post(
    "/trends",
    response_model=TimelineTrendsResponse,
    response_model_exclude_none=False,
    summary="Classify each feature's trajectory across a patient's reports",
)
async def trends(request: TimelineTrendsRequest) -> TimelineTrendsResponse:
    """Improving / worsening / stable per feature -- or an explicit refusal.

    `outcome` is the field to branch on, never `trend`. A feature with fewer
    than two usable readings returns `INSUFFICIENT_DATA` with `trend: null`;
    it is NEVER reported as `stable`, because "we could not tell" and "it did
    not move" are different facts and collapsing them fabricates a finding.

    Missing readings are GAPS, carried in `gaps[]` with the reason they are
    missing. Nothing is interpolated and nothing is imputed.
    """
    return TimelineTrendsResponse(success=True, data=analyse_trends(request))


@router.get(
    "/policy",
    summary="The trend policy: per-feature polarity and stability bands",
)
async def policy() -> Dict[str, object]:
    """The reviewable rule tables behind every classification. No patient data.

    Exposed because a trend direction is only meaningful if the reader can see
    what this service considers "better" for that feature, and on what basis.
    A feature whose clinical polarity is undeclared reports direction only.
    """
    return {
        "success": True,
        "data": {"analyzer": analyzer_document(), "polarity": policy_document()},
    }
