"""/leads: the account's lead forms, statuses and captures. Agents capture through the lead_capture skill, never here."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from fastapi.security import HTTPBearer

from src.iam.dependencies import get_principal
from src.iam.principal import Principal
from src.leads.models import (
    Capture,
    CaptureFilters,
    CapturePage,
    CreateLeadFormRequest,
    FileDownload,
    LeadForm,
    LeadFormFields,
    LeadSettings,
    LeadSettingsRequest,
    LeadUsage,
    UpdateCaptureRequest,
)
from src.leads.service import LeadsService

router = APIRouter(prefix="/leads", tags=["leads"], dependencies=[Depends(HTTPBearer())])


def allowed_to(action: str) -> Callable[..., Principal]:
    """A route dependency: the caller, once they may `action` in their account."""

    def dependency(principal: Annotated[Principal, Depends(get_principal)]) -> Principal:
        principal.require(action)
        return principal

    return dependency


def get_leads_service() -> LeadsService:
    return LeadsService()


Service = Annotated[LeadsService, Depends(get_leads_service)]


# Forms

@router.get("/forms", response_model=list[LeadForm])
async def list_forms(principal: Annotated[Principal, Depends(allowed_to("leads:ListForms"))], leads: Service) -> list[LeadForm]:
    return leads.list_forms(principal.account_id)


@router.post("/forms", response_model=LeadForm, status_code=201)
async def create_form(
    body: CreateLeadFormRequest,
    principal: Annotated[Principal, Depends(allowed_to("leads:ManageForms"))],
    leads: Service,
) -> LeadForm:
    return leads.create_form(principal.account_id, principal.user_id, body)


@router.get("/forms/{form_id}", response_model=LeadForm)
async def get_form(form_id: str, principal: Annotated[Principal, Depends(allowed_to("leads:ListForms"))], leads: Service) -> LeadForm:
    return leads.get_form(principal.account_id, form_id)


@router.put("/forms/{form_id}", response_model=LeadForm)
async def update_form(
    form_id: str,
    body: LeadFormFields,
    principal: Annotated[Principal, Depends(allowed_to("leads:ManageForms"))],
    leads: Service,
) -> LeadForm:
    return leads.update_form(principal.account_id, form_id, body)


@router.post("/forms/{form_id}/archive", response_model=LeadForm)
async def archive_form(
    form_id: str, principal: Annotated[Principal, Depends(allowed_to("leads:ManageForms"))], leads: Service
) -> LeadForm:
    return leads.archive_form(principal.account_id, form_id)


@router.post("/forms/{form_id}/restore", response_model=LeadForm)
async def restore_form(
    form_id: str, principal: Annotated[Principal, Depends(allowed_to("leads:ManageForms"))], leads: Service
) -> LeadForm:
    return leads.restore_form(principal.account_id, form_id)


@router.delete("/forms/{form_id}", status_code=204)
async def delete_form(
    form_id: str, principal: Annotated[Principal, Depends(allowed_to("leads:ManageForms"))], leads: Service
) -> Response:
    leads.delete_form(principal.account_id, form_id)
    return Response(status_code=204)


# Statuses and usage

@router.get("/settings", response_model=LeadSettings)
async def get_settings(principal: Annotated[Principal, Depends(allowed_to("leads:ListForms"))], leads: Service) -> LeadSettings:
    """Every member who can see forms needs the status labels too."""
    return leads.settings(principal.account_id)


@router.put("/settings", response_model=LeadSettings)
async def update_settings(
    body: LeadSettingsRequest,
    principal: Annotated[Principal, Depends(allowed_to("leads:ManageSettings"))],
    leads: Service,
) -> LeadSettings:
    return leads.update_settings(principal.account_id, principal.user_id, body)


@router.get("/usage", response_model=LeadUsage)
async def get_usage(principal: Annotated[Principal, Depends(allowed_to("leads:ViewCaptures"))], leads: Service) -> LeadUsage:
    return leads.usage(principal.account_id)


# Captures

@router.get("/captures", response_model=CapturePage)
async def list_captures(
    principal: Annotated[Principal, Depends(allowed_to("leads:ViewCaptures"))],
    leads: Service,
    agent_id: str | None = None,
    form: str | None = Query(default=None, description="A form slug"),
    status: str | None = None,
    include_tests: bool = False,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    cursor: str | None = None,
) -> CapturePage:
    filters = CaptureFilters(
        agent_id=agent_id, form_slug=form, status=status, include_tests=include_tests, since=since, until=until
    )
    return leads.list_captures(principal.account_id, filters, limit=limit, cursor=cursor)


@router.get("/captures/{capture_id}", response_model=Capture)
async def get_capture(
    capture_id: str, principal: Annotated[Principal, Depends(allowed_to("leads:ViewCaptures"))], leads: Service
) -> Capture:
    return leads.get_capture(principal.account_id, capture_id)


@router.patch("/captures/{capture_id}", response_model=Capture)
async def update_capture(
    capture_id: str,
    body: UpdateCaptureRequest,
    principal: Annotated[Principal, Depends(allowed_to("leads:ManageCaptures"))],
    leads: Service,
) -> Capture:
    return leads.update_capture_status(principal.account_id, capture_id, body.status)


@router.get("/captures/{capture_id}/files/{file_id}", response_model=FileDownload)
async def download_file(
    capture_id: str,
    file_id: str,
    principal: Annotated[Principal, Depends(allowed_to("leads:ViewCaptures"))],
    leads: Service,
) -> FileDownload:
    """A short-lived link that downloads the file as an attachment."""
    return FileDownload(url=leads.file_download_url(principal.account_id, capture_id, file_id))


@router.delete("/captures/{capture_id}", status_code=204)
async def delete_capture(
    capture_id: str, principal: Annotated[Principal, Depends(allowed_to("leads:ManageCaptures"))], leads: Service
) -> Response:
    leads.delete_capture(principal.account_id, capture_id)
    return Response(status_code=204)
