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

_REF = r"^[A-Za-z0-9._:-]{1,128}$"


class SnapshotNotFound(ServiceError):

    status_code = 404
    code = "SNAPSHOT_NOT_FOUND"


@router.post(
    "/load",
    response_model=RepositorySnapshotResponse,
    response_model_exclude_none=False,
    summary="Store one validated feature set as a snapshot",
)
async def load(request: RepositoryLoadRequest) -> RepositorySnapshotResponse:
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
            feature=stored,
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
    return {"success": True, "data": repository_document()}
