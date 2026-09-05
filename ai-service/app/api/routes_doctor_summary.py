"""The Module 32 (Doctor-Friendly Clinical Summary) endpoints.

Thin HTTP wrappers. All logic lives in `app.services.doctor_summary`, whose
`build_doctor_summary()` is importable directly exactly as `generate_report`,
`analyse_trends` and `compare_reports` are. **The in-process API is the
primary interface**; this router exists so the Node backend -- which owns the
durable report history and already drives the pipeline over HTTP -- can ask
for a clinician summary without a second integration style.

WHAT IT TAKES. An ALREADY-BUILT Module 17 `ClinicalReport`, posted verbatim,
plus an optional report history in Module 28's `TimelineReportInput` shape.
This module re-runs nothing: it does not re-fuse decisions, re-evaluate rules
or re-derive the overall status. Doing any of those would create a second
source of truth that could disagree with the report the patient was already
shown, which is precisely the defect class this project's audits keep
finding.

NO MODEL IS CALLED AND NO PROSE IS GENERATED. Every sentence in the response
comes from a fixed template table in the service module, scanned by the
Module 24 safety scanner when this service starts, and no number or unit is
substituted into any template. The request schema has no field able to carry
a language model's output -- `ClinicalReport` forbids unknown fields and has
no explanation field of its own. The reasoning is on the record: Module 26
declined a generator for the same reason, and the Module 24 audit rated the
whole Module 1->26 flow FAIL when free prose reached a patient carrying a
fabricated diagnosis. A clinician may act on this document, so it is a
higher-stakes surface, not a lower one.

DETERMINISTIC AND OFFLINE. Same request in, same document out, apart from
`generated_at`. The only I/O is loading the committed knowledge index for the
reference section; a failure there removes that section with a stated reason
rather than failing the document.

AUTH: every route here handles medical values and is therefore PHI-bearing,
so the router carries the same service-key dependency as
`routes_comparison.py`. `tests/test_auth.py` walks the route tree recursively
and fails if any `/api/v1` route lacks it.
"""

from __future__ import annotations

from typing import Dict

from fastapi import APIRouter, Depends

from app.core.auth import require_service_key
from app.schemas.doctor_summary import (
    DoctorSummaryRequest,
    DoctorSummaryResponse,
)
from app.services.doctor_summary import (
    build_doctor_summary,
    doctor_summary_document,
)

router = APIRouter(
    prefix="/api/v1/doctor-summary",
    tags=["doctor-summary"],
    dependencies=[Depends(require_service_key)],
)


@router.post(
    "/generate",
    response_model=DoctorSummaryResponse,
    response_model_exclude_none=False,
    summary="Assemble a structured summary a patient can hand to a clinician",
)
async def generate(request: DoctorSummaryRequest) -> DoctorSummaryResponse:
    """The spec's clinician-oriented view of one already-analysed report.

    Send the body of `POST /api/v1/report/generate` as `report` (a relayed
    `{"success": true, "data": {...}}` envelope is accepted as-is). Add
    `history` -- the same report snapshots Modules 28 and 29 take -- to get
    the trend and historical-comparison sections; without at least two
    reports both sections are ABSENT with a stated reason code, never
    rendered as stable or unchanged.

    WHAT TO BRANCH ON. `trends.present` and `comparison.present`, not the
    emptiness of `trend_data` / `comparison_data`; and
    `overall.clean_bill_of_health`, not the emptiness of `abnormal_findings`.
    An unassessed report has no abnormal findings in exactly the way an empty
    set has no members, and `clean_bill_of_health` is the field that cannot be
    true in that case -- its type refuses to validate.

    Each assessment carries one entry per contributing source in `bases`. A
    rule's threshold comparison and a model's estimated likelihood are
    different quantities and are never combined; `basis_conflict` and
    `render_bases_separately` say when a renderer must keep them apart. Every
    model estimate travels with that model's recorded performance and the
    caveats those figures select.
    """
    return DoctorSummaryResponse(success=True, data=build_doctor_summary(request))


@router.get(
    "/policy",
    summary="What this document does and does not contain",
)
async def policy() -> Dict[str, object]:
    """The reviewable rules behind the document. No patient data.

    Includes the two cut-offs that select model caveats
    (`weak_discrimination_roc_auc`, `low_detection_recall`) so they can be
    reviewed as numbers rather than inferred from output, and the
    reference-range policy that keeps a canonical-unit value from being shown
    against an original-unit interval.
    """
    return {"success": True, "data": doctor_summary_document()}
