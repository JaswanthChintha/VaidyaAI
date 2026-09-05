"""The Module 7 (Feature Repository) endpoints.

Thin HTTP wrappers. All logic lives in `app.services.feature_repository`, whose
`load_features()`, `history()` and `latest()` are importable directly by
Module 15 (Decision Engine) exactly as `engineer_features`,
`validate_features`, `evaluate_rules` and `predict_all` are. **The in-process
API is the primary interface**; this router exists so the Node backend, which
already drives the pipeline over HTTP, can load and read a feature set without
a second integration style.

The router lives in its own file and carries its own prefix so it can be
mounted alongside the other routers without either module owning the other.

AUTH: every route here handles medical feature values and is therefore
PHI-bearing, so the router carries the same service-key dependency as
`routes_ml.py`. `tests/test_auth.py` walks the route tree recursively and fails
if any `/api/v1` route lacks it.

STORAGE: the process-wide backend is IN-MEMORY (see
`app/services/repository_backend.py`). Snapshots do not survive a restart and
are not shared between workers. That is deliberate for Module 7 and is the
thing a future persistent backend replaces -- without changing these routes.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Path

from app.core.auth import require_service_key
from app.core.errors import ServiceError
from app.data.feature_catalog import CANONICAL_FEATURES
from app.schemas.repository import (
    FeatureReadData,
    FeatureReadResponse,
    RepositoryLoadRequest,
    RepositorySnapshotListData,
    RepositorySnapshotListResponse,
    RepositorySnapshotResponse,
)
from app.services.feature_repository import (
    get_snapshot,
    load_features,
    references,
    repository_document,
)

router = APIRouter(
    prefix="/api/v1/repository",
    tags=["feature-repository"],
    dependencies=[Depends(require_service_key)],
)

#: Path-parameter guard. Opaque ids only -- these never carry a patient name.
_REF = r"^[A-Za-z0-9._:-]{1,128}$"


class SnapshotNotFound(ServiceError):
    """404 in the service-wide envelope, with no report content in it."""

    status_code = 404
    code = "SNAPSHOT_NOT_FOUND"


@router.post(
    "/load",
    response_model=RepositorySnapshotResponse,
    response_model_exclude_none=False,
    summary="Store one validated feature set as a snapshot",
)
async def load(request: RepositoryLoadRequest) -> RepositorySnapshotResponse:
    # The WHOLE Module 6 object is passed, not just `valid`: its warnings,
    # upstream extraction context and missing-feature list must survive this
    # boundary or the final report cannot tell a damaged scan from a clean one.
    repo = load_features(
        request.validated,
        engineered=request.engineered,
        patient_ref=request.patient_ref,
        report_ref=request.report_ref,
        report_date=request.report_date,
        snapshot_id=request.snapshot_id,
    )
    return RepositorySnapshotResponse(success=True, data=repo.snapshot)


@router.get(
    "/snapshots/{snapshot_id}",
    response_model=RepositorySnapshotResponse,
    response_model_exclude_none=False,
    summary="Read one stored snapshot back",
)
async def read_snapshot(
    snapshot_id: str = Path(..., pattern=_REF),
) -> RepositorySnapshotResponse:
    repo = get_snapshot(snapshot_id)
    if repo is None:
        raise SnapshotNotFound("No snapshot with that id is held.")
    return RepositorySnapshotResponse(success=True, data=repo.snapshot)


@router.get(
    "/snapshots/{snapshot_id}/features/{name}",
    response_model=FeatureReadResponse,
    response_model_exclude_none=False,
    summary="Read one feature, or be told exactly why it is unavailable",
)
async def read_feature(
    snapshot_id: str = Path(..., pattern=_REF),
    name: str = Path(..., pattern=r"^[a-z0-9_]{1,64}$"),
) -> FeatureReadResponse:
    """`available` is the field to branch on.

    When it is false there is NO `value` anywhere in the response -- not
    `null`, not `0`, not `false`. `unavailable.reason_code` says why instead.
    """
    if name not in CANONICAL_FEATURES:
        raise SnapshotNotFound(f"{name!r} is not a canonical feature.")
    repo = get_snapshot(snapshot_id)
    if repo is None:
        raise SnapshotNotFound("No snapshot with that id is held.")
    stored: Optional[object] = repo.feature(name, default=None)
    return FeatureReadResponse(
        success=True,
        data=FeatureReadData(
            name=name,
            available=stored is not None,
            feature=stored,  # type: ignore[arg-type]
            unavailable=repo.why_unavailable(name),
        ),
    )


@router.get(
    "/patients/{patient_ref}/snapshots",
    response_model=RepositorySnapshotListResponse,
    response_model_exclude_none=False,
    summary="A patient's snapshots in chronological order (identities only)",
)
async def list_snapshots(
    patient_ref: str = Path(..., pattern=_REF),
) -> RepositorySnapshotListResponse:
    """Oldest first, by report date (or record time when undated).

    Identity and shape only -- a listing must not ship every patient value.
    This is the ordered sequence Modules 28-30 will walk; the ordering is all
    Module 7 provides, and no trend or comparison is computed here.
    """
    items = references(patient_ref)
    return RepositorySnapshotListResponse(
        success=True,
        data=RepositorySnapshotListData(
            patient_ref=patient_ref, count=len(items), snapshots=items
        ),
    )


@router.get(
    "/interface",
    summary="The repository interface and its policy, machine-readable",
)
async def interface() -> dict:
    """Shape only -- no PHI, no values, no identifiers."""
    return {"success": True, "data": repository_document()}
