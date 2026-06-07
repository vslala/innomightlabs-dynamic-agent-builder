from __future__ import annotations

from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPBearer

from src.connectors.mcp.models import (
    AgentMCPConnectionResponse,
    AgentMCPConnectionUpdateRequest,
    MCPConnectionCreateRequest,
    MCPConnectionResponse,
    MCPConnectionUpdateRequest,
    MCPOAuthDiscoveryRequest,
    MCPOAuthDiscoveryResponse,
    MCPOAuthStartRequest,
    MCPOAuthStartResponse,
)
from src.connectors.mcp.oauth import decode_state_session
from src.connectors.mcp.service import MCPConnectorService, get_mcp_connector_service

security = HTTPBearer()

router = APIRouter(tags=["mcp-connectors"], dependencies=[Depends(security)])
public_router = APIRouter(tags=["mcp-connectors"])


def _user_email(request: Request) -> str:
    user_email = getattr(request.state, "user_email", None)
    if not user_email:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return str(user_email)


def _not_found_from_value_error(error: ValueError) -> HTTPException:
    detail = str(error)
    status_code = status.HTTP_404_NOT_FOUND if "not found" in detail.lower() else status.HTTP_400_BAD_REQUEST
    return HTTPException(status_code=status_code, detail=detail)


def _callback_redirect(return_to: str, *, status_value: str, reason: str | None = None, mcp_id: str | None = None) -> RedirectResponse:
    params = [f"mcp_oauth={quote(status_value)}"]
    if reason:
        params.append(f"reason={quote(reason)}")
    if mcp_id:
        params.append(f"mcp_id={quote(mcp_id)}")
    separator = "&" if "?" in return_to else "?"
    return RedirectResponse(f"{return_to}{separator}{'&'.join(params)}")


@router.get("/connectors/mcp", response_model=list[MCPConnectionResponse])
async def list_mcp_connections(
    request: Request,
    service: Annotated[MCPConnectorService, Depends(get_mcp_connector_service)],
) -> list[MCPConnectionResponse]:
    return service.list_connections(_user_email(request))


@router.post("/connectors/mcp", response_model=MCPConnectionResponse, status_code=status.HTTP_201_CREATED)
async def create_mcp_connection(
    request: Request,
    body: MCPConnectionCreateRequest,
    service: Annotated[MCPConnectorService, Depends(get_mcp_connector_service)],
) -> MCPConnectionResponse:
    try:
        return service.create_connection(_user_email(request), body)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error


@router.get("/connectors/mcp/{mcp_id}", response_model=MCPConnectionResponse)
async def get_mcp_connection(
    request: Request,
    mcp_id: str,
    service: Annotated[MCPConnectorService, Depends(get_mcp_connector_service)],
) -> MCPConnectionResponse:
    try:
        return service.get_connection(_user_email(request), mcp_id)
    except ValueError as error:
        raise _not_found_from_value_error(error) from error


@router.patch("/connectors/mcp/{mcp_id}", response_model=MCPConnectionResponse)
async def update_mcp_connection(
    request: Request,
    mcp_id: str,
    body: MCPConnectionUpdateRequest,
    service: Annotated[MCPConnectorService, Depends(get_mcp_connector_service)],
) -> MCPConnectionResponse:
    try:
        return service.update_connection(_user_email(request), mcp_id, body)
    except ValueError as error:
        raise _not_found_from_value_error(error) from error


@router.delete("/connectors/mcp/{mcp_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mcp_connection(
    request: Request,
    mcp_id: str,
    service: Annotated[MCPConnectorService, Depends(get_mcp_connector_service)],
) -> None:
    try:
        service.delete_connection(_user_email(request), mcp_id)
    except ValueError as error:
        raise _not_found_from_value_error(error) from error


@router.post("/connectors/mcp/oauth/discover", response_model=MCPOAuthDiscoveryResponse)
async def discover_mcp_oauth(
    body: MCPOAuthDiscoveryRequest,
    service: Annotated[MCPConnectorService, Depends(get_mcp_connector_service)],
) -> MCPOAuthDiscoveryResponse:
    try:
        return await service.discover_oauth(str(body.server_url))
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error


@router.post("/connectors/mcp/{mcp_id}/oauth/start", response_model=MCPOAuthStartResponse)
async def start_mcp_oauth(
    request: Request,
    mcp_id: str,
    body: MCPOAuthStartRequest,
    service: Annotated[MCPConnectorService, Depends(get_mcp_connector_service)],
) -> MCPOAuthStartResponse:
    try:
        authorize_url = service.start_oauth(
            owner_email=_user_email(request),
            mcp_id=mcp_id,
            return_to=body.return_to,
        )
        return MCPOAuthStartResponse(authorize_url=authorize_url)
    except ValueError as error:
        raise _not_found_from_value_error(error) from error


@public_router.get("/connectors/mcp/oauth/callback")
async def mcp_oauth_callback(
    service: Annotated[MCPConnectorService, Depends(get_mcp_connector_service)],
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
) -> RedirectResponse:
    session = decode_state_session(state)
    if not session or session.is_expired():
        return _callback_redirect("/dashboard/connectors", status_value="error", reason="invalid_state")

    if error:
        reason = error_description or error
        return _callback_redirect(session.return_to, status_value="error", reason=reason)

    if not code:
        return _callback_redirect(session.return_to, status_value="error", reason="missing_code")

    try:
        await service.complete_oauth(
            owner_email=session.user_email,
            mcp_id=session.mcp_id,
            code=code,
            code_verifier=session.code_verifier,
        )
    except Exception as exc:
        return _callback_redirect(session.return_to, status_value="error", reason=str(exc))

    return _callback_redirect(session.return_to, status_value="success", mcp_id=session.mcp_id)


@router.get("/agents/{agent_id}/mcp-connections", response_model=list[AgentMCPConnectionResponse])
async def list_agent_mcp_connections(
    request: Request,
    agent_id: str,
    service: Annotated[MCPConnectorService, Depends(get_mcp_connector_service)],
) -> list[AgentMCPConnectionResponse]:
    try:
        return service.list_agent_connections(owner_email=_user_email(request), agent_id=agent_id)
    except ValueError as error:
        raise _not_found_from_value_error(error) from error


@router.put("/agents/{agent_id}/mcp-connections/{mcp_id}", response_model=AgentMCPConnectionResponse)
async def update_agent_mcp_connection(
    request: Request,
    agent_id: str,
    mcp_id: str,
    body: AgentMCPConnectionUpdateRequest,
    service: Annotated[MCPConnectorService, Depends(get_mcp_connector_service)],
) -> AgentMCPConnectionResponse:
    try:
        return service.enable_for_agent(
            owner_email=_user_email(request),
            agent_id=agent_id,
            mcp_id=mcp_id,
            enabled=body.enabled,
        )
    except ValueError as error:
        raise _not_found_from_value_error(error) from error


@router.delete("/agents/{agent_id}/mcp-connections/{mcp_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent_mcp_connection(
    request: Request,
    agent_id: str,
    mcp_id: str,
    service: Annotated[MCPConnectorService, Depends(get_mcp_connector_service)],
) -> None:
    try:
        service.disable_for_agent(owner_email=_user_email(request), agent_id=agent_id, mcp_id=mcp_id)
    except ValueError as error:
        raise _not_found_from_value_error(error) from error
