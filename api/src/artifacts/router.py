from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.security import HTTPBearer

from src.accounts.owner import Owner
from src.iam.dependencies import get_owner

from src.artifacts.models import ArtifactListResponse, ArtifactResponse
from src.artifacts.service import ArtifactNotFoundError, ArtifactNotViewableError, ArtifactService

security = HTTPBearer()

# Artifacts are each member's own, in the account the request acts in
router = APIRouter(
    prefix="/artifacts",
    tags=["artifacts"],
    dependencies=[Depends(security)],
)


def get_artifact_service() -> ArtifactService:
    return ArtifactService()


@router.get("", response_model=ArtifactListResponse)
async def list_artifacts(
    owner: Annotated[Owner, Depends(get_owner)],
    service: Annotated[ArtifactService, Depends(get_artifact_service)],
    limit: int = Query(50, ge=1, le=100),
) -> ArtifactListResponse:
    return ArtifactListResponse(items=service.list_artifacts(owner.member_pk, limit=limit))


@router.get("/{artifact_id}", response_model=ArtifactResponse)
async def get_artifact(
    owner: Annotated[Owner, Depends(get_owner)],
    artifact_id: str,
    service: Annotated[ArtifactService, Depends(get_artifact_service)],
) -> ArtifactResponse:
    try:
        return service.get_artifact(owner.member_pk, artifact_id)
    except ArtifactNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Artifact not found") from exc


@router.get("/{artifact_id}/download")
async def get_artifact_download_url(
    owner: Annotated[Owner, Depends(get_owner)],
    artifact_id: str,
    service: Annotated[ArtifactService, Depends(get_artifact_service)],
) -> dict[str, str]:
    try:
        return {"url": service.download_url(owner.member_pk, artifact_id)}
    except ArtifactNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Artifact not found") from exc


@router.get("/{artifact_id}/view")
async def get_artifact_view_url(
    owner: Annotated[Owner, Depends(get_owner)],
    artifact_id: str,
    service: Annotated[ArtifactService, Depends(get_artifact_service)],
) -> dict[str, str]:
    try:
        return {"url": service.view_url(owner.member_pk, artifact_id)}
    except ArtifactNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Artifact not found") from exc
    except ArtifactNotViewableError as exc:
        raise HTTPException(status_code=400, detail="Artifact is not browser-viewable") from exc


@router.get("/{artifact_id}/content")
async def get_artifact_content(
    owner: Annotated[Owner, Depends(get_owner)],
    artifact_id: str,
    service: Annotated[ArtifactService, Depends(get_artifact_service)],
) -> Response:
    try:
        body, mime_type = service.get_content(owner.member_pk, artifact_id)
    except ArtifactNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Artifact not found") from exc
    except ArtifactNotViewableError as exc:
        raise HTTPException(status_code=400, detail="Artifact content is not inline-fetchable") from exc
    return Response(content=body, media_type=mime_type)
