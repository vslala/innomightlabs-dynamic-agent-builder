from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPBearer

from src.agent_marketplace.models import (
    ArchiveMarketplaceAgentResponse,
    ImportMarketplaceAgentRequest,
    ImportMarketplaceAgentResponse,
    MarketplaceAgentDetailResponse,
    MarketplaceAgentSummaryResponse,
    MarketplaceImportPlanResponse,
    PublishMarketplaceAgentRequest,
    PublishMarketplaceAgentResponse,
)
from src.agent_marketplace.service import AgentMarketplaceService, get_agent_marketplace_service

security = HTTPBearer()

router = APIRouter(
    prefix="/agent-marketplace",
    tags=["agent-marketplace"],
    dependencies=[Depends(security)],
)


@router.get("/agents", response_model=list[MarketplaceAgentSummaryResponse])
async def list_marketplace_agents(
    service: Annotated[AgentMarketplaceService, Depends(get_agent_marketplace_service)],
    query: str | None = Query(None),
    limit: int = Query(20, ge=1, le=50),
) -> list[MarketplaceAgentSummaryResponse]:
    return service.list_agents(query=query, limit=limit)


@router.get("/agents/{template_id}", response_model=MarketplaceAgentDetailResponse)
async def get_marketplace_agent(
    template_id: str,
    service: Annotated[AgentMarketplaceService, Depends(get_agent_marketplace_service)],
) -> MarketplaceAgentDetailResponse:
    try:
        return service.get_agent(template_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/agents/{template_id}/import-plan", response_model=MarketplaceImportPlanResponse)
async def get_marketplace_agent_import_plan(
    request: Request,
    template_id: str,
    service: Annotated[AgentMarketplaceService, Depends(get_agent_marketplace_service)],
) -> MarketplaceImportPlanResponse:
    try:
        return service.get_import_plan(template_id=template_id, user_email=request.state.user_email)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post(
    "/agents/{template_id}/import",
    response_model=ImportMarketplaceAgentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def import_marketplace_agent(
    request: Request,
    template_id: str,
    body: ImportMarketplaceAgentRequest,
    service: Annotated[AgentMarketplaceService, Depends(get_agent_marketplace_service)],
) -> ImportMarketplaceAgentResponse:
    try:
        return service.import_agent(
            template_id=template_id,
            user_email=request.state.user_email,
            request=body,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post(
    "/agents/publish",
    response_model=PublishMarketplaceAgentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def publish_marketplace_agent(
    request: Request,
    body: PublishMarketplaceAgentRequest,
    service: Annotated[AgentMarketplaceService, Depends(get_agent_marketplace_service)],
) -> PublishMarketplaceAgentResponse:
    try:
        return service.publish_agent(user_email=request.state.user_email, request=body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/agents/{template_id}/archive", response_model=ArchiveMarketplaceAgentResponse)
async def archive_marketplace_agent(
    request: Request,
    template_id: str,
    service: Annotated[AgentMarketplaceService, Depends(get_agent_marketplace_service)],
) -> ArchiveMarketplaceAgentResponse:
    try:
        return service.archive_agent(template_id=template_id, user_email=request.state.user_email)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
