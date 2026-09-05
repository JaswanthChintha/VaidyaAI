"""The Module 29 (Smart Report Comparison) endpoints.

Thin HTTP wrappers. All logic lives in `app.services.report_comparator`, whose
`compare_reports()` is importable directly by Modules 27/30/32 exactly as
`analyse_trends()` is. **The in-process API is the primary interface**; this
router exists so the Node backend -- which owns the durable report history and
already drives the pipeline over HTTP -- can ask for a comparison without a
second integration style.

WHERE THE HISTORY COMES FROM. This service holds no database. The backend
assembles the reports from Mongo (`Report.chronoDate` is indexed on
`{user, chronoDate}`) and POSTs the snapshots in, in Module 28's
`TimelineReportInput` shape -- the same shape, deliberately, so there is one
way to hand this service a report's features.

DETERMINISTIC AND MODEL-FREE. `compare_reports` calls no LLM, reads no clock
except for `generated_at`, and performs no I/O. Same request in, same
comparison out. The comparison summary is assembled from a fixed template
table that is safety-scanned at import time; this project's standing property
is that interpretation text has no free-text entry point.

WHAT TO BRANCH ON. Never `change_class` alone and never `transition` alone:
`outcome` says whether a change was classified at all, and
`transition_outcome` says whether the reference-interval crossing could be
established. A parameter present in only one of the two reports is
`ONLY_IN_BASELINE` / `ONLY_IN_COMPARISON`, NOT `unchanged`, and its table cell
is `null` rather than `0`.

AUTH: every route here handles medical values and is therefore PHI-bearing, so
the router carries the same service-key dependency as `routes_timeline.py`.
`tests/test_auth.py` walks the route tree recursively and fails if any
`/api/v1` route lacks it.
"""

from __future__ import annotations

from typing import Dict

from fastapi import APIRouter, Depends

from app.core.auth import require_service_key
from app.data.trend_polarity import policy_document
from app.schemas.comparison import (
    ReportComparisonRequest,
    ReportComparisonResponse,
)
from app.services.report_comparator import comparator_document, compare_reports
from app.services.trend_analyzer import analyzer_document

router = APIRouter(
    prefix="/api/v1/comparison",
    tags=["comparison"],
    dependencies=[Depends(require_service_key)],
)


@router.post(
    "/reports",
    response_model=ReportComparisonResponse,
    response_model_exclude_none=False,
    summary="Compare two or more reports parameter by parameter",
)
async def compare(request: ReportComparisonRequest) -> ReportComparisonResponse:
    """Newly abnormal / improved / worsened / unchanged -- or a stated refusal.

    Send two or more reports. Name the pair with `baseline_ref` and
    `comparison_ref`, or name neither and the earliest and latest by
    `chrono_date` are compared. `pair` in the response always says which two
    were used and how they were chosen; when more than two reports are sent,
    `series` carries the intermediate readings for rendering, and they take no
    part in the classification.

    `newly_abnormal` is a STATE TRANSITION and requires knowing the reading's
    position relative to the reference interval printed on BOTH reports. When
    the earlier report printed neither an interval nor a marker, the answer is
    `NOT_DETERMINABLE_BASELINE` -- not `newly_abnormal`, and not `unchanged`.

    `unchanged` is earned from the declared stability band in
    `app/data/trend_polarity.py`, never assigned because nothing else matched.
    """
    return ReportComparisonResponse(success=True, data=compare_reports(request))


@router.get(
    "/policy",
    summary="The comparison policy, and the trend tables it delegates to",
)
async def policy() -> Dict[str, object]:
    """The reviewable rules behind every classification. No patient data.

    The polarity and stability tables returned here are the SAME ones Module 28
    returns from `GET /api/v1/timeline/policy` -- one table, one lookup. If
    these two endpoints ever disagree, something has been duplicated that
    should not have been.
    """
    return {
        "success": True,
        "data": {
            "comparator": comparator_document(),
            "analyzer": analyzer_document(),
            "polarity": policy_document(),
        },
    }
