from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.security import HTTPBearer

from src.artifacts.models import ArtifactListResponse, ArtifactResponse
from src.artifacts.service import ArtifactNotFoundError, ArtifactNotViewableError, ArtifactService

security = HTTPBearer()

router = APIRouter(
    prefix="/artifacts",
    tags=["artifacts"],
    dependencies=[Depends(security)],
)


def get_artifact_service() -> ArtifactService:
    return ArtifactService()


@router.get("", response_model=ArtifactListResponse)
async def list_artifacts(
    request: Request,
    service: Annotated[ArtifactService, Depends(get_artifact_service)],
    limit: int = Query(50, ge=1, le=100),
) -> ArtifactListResponse:
    return ArtifactListResponse(items=service.list_artifacts(request.state.user_email, limit=limit))


@router.get("/{artifact_id}", response_model=ArtifactResponse)
async def get_artifact(
    request: Request,
    artifact_id: str,
    service: Annotated[ArtifactService, Depends(get_artifact_service)],
) -> ArtifactResponse:
    try:
        return service.get_artifact(request.state.user_email, artifact_id)
    except ArtifactNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Artifact not found") from exc


@router.get("/{artifact_id}/download")
async def get_artifact_download_url(
    request: Request,
    artifact_id: str,
    service: Annotated[ArtifactService, Depends(get_artifact_service)],
) -> dict[str, str]:
    try:
        return {"url": service.download_url(request.state.user_email, artifact_id)}
    except ArtifactNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Artifact not found") from exc


@router.get("/{artifact_id}/view")
async def get_artifact_view_url(
    request: Request,
    artifact_id: str,
    service: Annotated[ArtifactService, Depends(get_artifact_service)],
) -> dict[str, str]:
    try:
        return {"url": service.view_url(request.state.user_email, artifact_id)}
    except ArtifactNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Artifact not found") from exc
    except ArtifactNotViewableError as exc:
        raise HTTPException(status_code=400, detail="Artifact is not browser-viewable") from exc
