from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPBearer
from pydantic import BaseModel

from src.auth.router import SkillOAuthStartResponse, _google_skill_authorize, _google_skill_oauth_flows
from src.connectors.models import ConnectorStatus
from src.connectors.service import ConnectorService, get_connector_service
from src.iam.dependencies import get_principal
from src.iam.principal import Principal
from src.settings.access import settings_manager

security = HTTPBearer()

router = APIRouter(
    prefix="/connectors",
    tags=["connectors"],
    dependencies=[Depends(security)],
)


class ConnectorStartRequest(BaseModel):
    return_to: str


@router.get("", response_model=list[ConnectorStatus])
async def list_connectors(
    principal: Annotated[Principal, Depends(get_principal)],
    service: Annotated[ConnectorService, Depends(get_connector_service)],
) -> list[ConnectorStatus]:
    """The account's connectors and whether each is connected; any member may look."""
    return service.list_statuses(principal.account_id)


@router.post("/{connector_id}/start", response_model=SkillOAuthStartResponse)
async def start_connector_oauth(
    request: Request,
    connector_id: str,
    body: ConnectorStartRequest,
    service: Annotated[ConnectorService, Depends(get_connector_service)],
    principal: Annotated[Principal, Depends(settings_manager)],
) -> SkillOAuthStartResponse:
    """Connect a Google account for the whole account (admins only)."""
    user_email = getattr(request.state, "user_email", None)
    if not user_email:
        raise HTTPException(status_code=401, detail="Unauthorized")

    definition = service.get_definition(connector_id)
    if not definition:
        raise HTTPException(status_code=404, detail="Connector not found")

    flow = _google_skill_oauth_flows().get(connector_id)
    if not flow:
        raise HTTPException(status_code=400, detail="Connector does not support OAuth start")
    if not flow.is_configured():
        raise HTTPException(status_code=500, detail=f"{flow.display_name} OAuth is not configured")

    return _google_skill_authorize(flow, user_email=str(user_email), account_id=principal.account_id, agent_id="",
                                   return_to=body.return_to)
