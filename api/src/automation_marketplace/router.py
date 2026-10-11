from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPBearer

from src.automations.access import require_automation
from src.iam.actions import ResourceRef
from src.iam.dependencies import get_owner, get_principal
from src.automation_marketplace.models import (
    ArchiveMarketplaceAutomationResponse,
    ImportMarketplaceAutomationRequest,
    ImportMarketplaceAutomationResponse,
    MarketplaceAutomationImportSessionResponse,
    MarketplaceAutomationDetailResponse,
    MarketplaceAutomationImportPlanResponse,
    MarketplaceAutomationSummaryResponse,
    PublishMarketplaceAutomationRequest,
    PublishMarketplaceAutomationResponse,
    SaveMarketplaceAutomationImportSessionRequest,
)
from src.automation_marketplace.service import (
    AutomationMarketplaceService,
    get_automation_marketplace_service,
)

security = HTTPBearer()

router = APIRouter(
    prefix="/automation-marketplace",
    tags=["automation-marketplace"],
    dependencies=[Depends(security)],
)


@router.get("/automations", response_model=list[MarketplaceAutomationSummaryResponse])
async def list_marketplace_automations(
    service: Annotated[AutomationMarketplaceService, Depends(get_automation_marketplace_service)],
    query: str | None = Query(None),
    limit: int = Query(20, ge=1, le=50),
) -> list[MarketplaceAutomationSummaryResponse]:
    return service.list_automations(query=query, limit=limit)


@router.get("/automations/{template_id}", response_model=MarketplaceAutomationDetailResponse)
async def get_marketplace_automation(
    template_id: str,
    service: Annotated[AutomationMarketplaceService, Depends(get_automation_marketplace_service)],
) -> MarketplaceAutomationDetailResponse:
    try:
        return service.get_automation(template_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/automations/{template_id}/import-plan", response_model=MarketplaceAutomationImportPlanResponse)
async def get_marketplace_automation_import_plan(
    request: Request,
    template_id: str,
    service: Annotated[AutomationMarketplaceService, Depends(get_automation_marketplace_service)],
) -> MarketplaceAutomationImportPlanResponse:
    try:
        return service.get_import_plan(template_id=template_id, owner=get_owner(request))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/automations/{template_id}/import-session",
    response_model=MarketplaceAutomationImportSessionResponse,
)
async def save_marketplace_automation_import_session(
    request: Request,
    template_id: str,
    body: SaveMarketplaceAutomationImportSessionRequest,
    service: Annotated[AutomationMarketplaceService, Depends(get_automation_marketplace_service)],
) -> MarketplaceAutomationImportSessionResponse:
    try:
        return service.save_import_session(
            template_id=template_id,
            owner=get_owner(request),
            request=body,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/automations/{template_id}/import",
    response_model=ImportMarketplaceAutomationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def import_marketplace_automation(
    request: Request,
    template_id: str,
    body: ImportMarketplaceAutomationRequest,
    service: Annotated[AutomationMarketplaceService, Depends(get_automation_marketplace_service)],
) -> ImportMarketplaceAutomationResponse:
    # It lands in the account the request acts in, owned by the caller
    get_principal(request).require("automations:Create", ResourceRef("automation"))
    try:
        return service.import_automation(
            template_id=template_id,
            owner=get_owner(request),
            request=body,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/automations/publish",
    response_model=PublishMarketplaceAutomationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def publish_marketplace_automation(
    request: Request,
    body: PublishMarketplaceAutomationRequest,
    service: Annotated[AutomationMarketplaceService, Depends(get_automation_marketplace_service)],
) -> PublishMarketplaceAutomationResponse:
    try:
        # Publishing hands the graph to everyone: it takes the right to share the automation
        require_automation(get_principal(request), body.automation_id, "automations:Share")
        return service.publish_automation(owner=get_owner(request), request=body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/automations/{template_id}/archive", response_model=ArchiveMarketplaceAutomationResponse)
async def archive_marketplace_automation(
    request: Request,
    template_id: str,
    service: Annotated[AutomationMarketplaceService, Depends(get_automation_marketplace_service)],
) -> ArchiveMarketplaceAutomationResponse:
    try:
        return service.archive_automation(template_id=template_id, owner=get_owner(request))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
