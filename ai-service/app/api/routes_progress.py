"""The Module 30 (Health Progress Analysis) endpoints.

Thin HTTP wrappers. All logic lives in `app.services.progress_analyzer`, whose
`analyse_progress()` is importable directly by Modules 27/32 exactly as
`analyse_trends()` and `compare_reports()` are. **The in-process API is the
primary interface**; this router exists so the Node backend -- which owns the
durable report history and already drives the pipeline over HTTP -- can ask
for a progress score without a second integration style.

WHERE THE HISTORY COMES FROM. This service holds no database. The backend
assembles the reports from Mongo (`Report.chronoDate` is indexed on
`{user, chronoDate}`) and POSTs the snapshots in, in Module 28's
`TimelineReportInput` shape -- the same shape Modules 28 and 29 take, so there
is one way to hand this service a report's features.

WHAT THE SCORE IS. One number, 0 to 100, HIGHER IS BETTER, describing how the
measured laboratory parameters moved between two reports. It is not a risk
score, not a measure of health, and not a diagnosis; the response carries
`what_this_is` and `what_this_is_not` saying so in the flat, non-clinical
register `app/population/policy.py` uses, and `scale` says which way the
number points.

WHAT TO BRANCH ON. `outcome`, never `score`. `score` is non-null for exactly
one outcome, `SCORE_COMPUTED`; the other three carry `score: null` and say
why. In particular a request where no parameter could be assessed returns
`NOTHING_ASSESSED` with a null score -- never 50, and never a sentence that
reads like steady progress. `coverage` says how many parameters the number was
built from, which ones, and which were excluded with the reason.

NO SECOND CLINICAL TABLE. Module 30 computes nothing clinical. It calls Module
29, which delegates the improved / worsened / unchanged decision to Module 28,
which reads the single polarity and stability table in
`app/data/trend_polarity.py`. `GET /policy` returns the scoring table
alongside those, so a reviewer can see there is only one of each.

DETERMINISTIC AND MODEL-FREE. `analyse_progress` calls no LLM, reads no clock
except for `generated_at`, and performs no I/O. Same request in, same score
out. The summary text is assembled from a fixed template table that is
safety-scanned at import time; this project's standing property is that
interpretation text has no free-text entry point.

AUTH: every route here handles medical values and is therefore PHI-bearing, so
the router carries the same service-key dependency as `routes_comparison.py`.
`tests/test_auth.py` walks the route tree recursively and fails if any
`/api/v1` route lacks it.
"""

from __future__ import annotations

from typing import Dict

from fastapi import APIRouter, Depends

from app.core.auth import require_service_key
from app.data.progress_scoring import scoring_document
from app.data.trend_polarity import policy_document
from app.schemas.progress import (
    HealthProgressRequest,
    HealthProgressResponse,
)
from app.services.progress_analyzer import analyse_progress, progress_document
from app.services.report_comparator import comparator_document
from app.services.trend_analyzer import analyzer_document

router = APIRouter(
    prefix="/api/v1/progress",
    tags=["progress"],
    dependencies=[Depends(require_service_key)],
)


@router.post(
    "/score",
    response_model=HealthProgressResponse,
    response_model_exclude_none=False,
    summary="Compute the health progress score between two reports",
)
async def score(request: HealthProgressRequest) -> HealthProgressResponse:
    """One number for longitudinal progress -- or a stated refusal.

    Send two or more reports. Name the pair with `baseline_ref` and
    `comparison_ref`, or name neither and the earliest and latest by
    `chrono_date` are used; `pair` always says which two and how they were
    chosen. Pair selection is Module 29's, unchanged.

    THE SCALE runs 0 to 100 and HIGHER IS BETTER. It is a weighted mean of
    five equally spaced ordinal positions, one per parameter, and every
    parameter carries the same weight. `scale` carries the direction, the
    bands and the rounding rule on every response, including the refusals.

    ABSENCE IS NEVER A VALUE. A parameter that could not be classified, or
    whose clinical direction is undeclared, contributes NOTHING -- it is
    listed in `coverage.excluded` with a reason code and lowers the
    contributing count. It is never scored as neutral, because "we could not
    tell" and "it did not move" are different facts.

    NO SCORE BELOW THE DECLARED FLOOR. Under
    `coverage.minimum_required` contributing parameters, the outcome is
    `INSUFFICIENT_COVERAGE`, the contributions found are still returned, and
    `score` is null. The floor exists so that no single parameter can hold a
    majority of the number; its stated basis is in `GET /policy`.
    """
    return HealthProgressResponse(success=True, data=analyse_progress(request))


@router.get(
    "/policy",
    summary="The scoring table, and the clinical tables it delegates to",
)
async def policy() -> Dict[str, object]:
    """The reviewable rules behind every score. No patient data.

    Every point value, every weight and every band is here with its stated
    basis, including the sentence explaining why the weights are equal and why
    the five points are equally spaced.

    The polarity and stability tables returned here are the SAME ones Modules
    28 and 29 return from their own `/policy` endpoints -- one table, one
    lookup. If these three endpoints ever disagree, something has been
    duplicated that should not have been.
    """
    return {
        "success": True,
        "data": {
            "progress": progress_document(),
            "scoring": scoring_document(),
            "comparator": comparator_document(),
            "analyzer": analyzer_document(),
            "polarity": policy_document(),
        },
    }
