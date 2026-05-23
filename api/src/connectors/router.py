from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPBearer
from pydantic import BaseModel

from src.auth.router import SkillOAuthStartResponse, _google_skill_oauth_flows
from src.connectors.models import ConnectorStatus
from src.connectors.service import ConnectorService, get_connector_service

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
    request: Request,
    service: Annotated[ConnectorService, Depends(get_connector_service)],
) -> list[ConnectorStatus]:
    user_email = getattr(request.state, "user_email", None)
    if not user_email:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return service.list_statuses(str(user_email))


@router.post("/{connector_id}/start", response_model=SkillOAuthStartResponse)
async def start_connector_oauth(
    request: Request,
    connector_id: str,
    body: ConnectorStartRequest,
    service: Annotated[ConnectorService, Depends(get_connector_service)],
) -> SkillOAuthStartResponse:
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

    session = flow.create_state_session(
        user_email=str(user_email),
        agent_id="",
        skill_id=flow.skill_id,
        return_to=body.return_to,
        ttl_seconds=flow.ttl_seconds,
    )
    state = flow.encode_state_session(session)
    return SkillOAuthStartResponse(authorize_url=flow.build_authorization_url(state=state))
