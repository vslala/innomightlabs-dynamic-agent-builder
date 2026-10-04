from __future__ import annotations

import logging
from typing import Annotated

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
    MCPProviderInstallRequest,
    MCPProviderInstallResponse,
    MCPProviderResponse,
    MCPRuntimeStatusResponse,
    MCPStdioPackageResponse,
)
from src.auth.oauth_handoff import handoff_redirect, safe_return_to
from src.config import settings
from src.connectors.mcp.oauth import decode_state_session
from src.connectors.mcp.service import MCPConnectorService, get_mcp_connector_service
from src.form_models import Form

log = logging.getLogger(__name__)

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


# Registered before /connectors/mcp/{mcp_id} so "providers" is not read as a connector id.
@router.get("/connectors/mcp/providers", response_model=list[MCPProviderResponse])
async def list_mcp_providers(
    request: Request,
    service: Annotated[MCPConnectorService, Depends(get_mcp_connector_service)],
) -> list[MCPProviderResponse]:
    return service.list_providers(_user_email(request))


@router.get("/connectors/mcp/providers/{key}/forms/install", response_model=Form)
async def get_mcp_provider_install_form(
    key: str,
    service: Annotated[MCPConnectorService, Depends(get_mcp_connector_service)],
) -> Form:
    try:
        return service.provider_install_form(key)
    except ValueError as error:
        raise _not_found_from_value_error(error) from error


@router.post(
    "/connectors/mcp/providers/{key}/install",
    response_model=MCPProviderInstallResponse,
    status_code=status.HTTP_201_CREATED,
)
async def install_mcp_provider(
    request: Request,
    key: str,
    body: MCPProviderInstallRequest,
    service: Annotated[MCPConnectorService, Depends(get_mcp_connector_service)],
) -> MCPProviderInstallResponse:
    try:
        return await service.install_provider(_user_email(request), key, body)
    except ValueError as error:
        raise _not_found_from_value_error(error) from error


@router.get("/connectors/mcp/stdio/packages", response_model=list[MCPStdioPackageResponse])
async def list_mcp_stdio_packages(
    service: Annotated[MCPConnectorService, Depends(get_mcp_connector_service)],
) -> list[MCPStdioPackageResponse]:
    try:
        return await service.list_stdio_packages()
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error


@router.get("/connectors/mcp/{mcp_id}/runtime", response_model=MCPRuntimeStatusResponse)
async def get_mcp_runtime(
    request: Request,
    mcp_id: str,
    service: Annotated[MCPConnectorService, Depends(get_mcp_connector_service)],
) -> MCPRuntimeStatusResponse:
    try:
        return await service.runtime_status(_user_email(request), mcp_id)
    except ValueError as error:
        raise _not_found_from_value_error(error) from error


@router.post("/connectors/mcp/{mcp_id}/runtime/restart", response_model=MCPRuntimeStatusResponse)
async def restart_mcp_runtime(
    request: Request,
    mcp_id: str,
    service: Annotated[MCPConnectorService, Depends(get_mcp_connector_service)],
) -> MCPRuntimeStatusResponse:
    try:
        return await service.restart_runtime(_user_email(request), mcp_id)
    except ValueError as error:
        raise _not_found_from_value_error(error) from error


@router.get("/connectors/mcp/{mcp_id}/forms/settings", response_model=Form)
async def get_mcp_connection_settings_form(
    request: Request,
    mcp_id: str,
    service: Annotated[MCPConnectorService, Depends(get_mcp_connector_service)],
) -> Form:
    try:
        return service.connection_settings_form(_user_email(request), mcp_id)
    except ValueError as error:
        raise _not_found_from_value_error(error) from error


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
        return await service.update_connection(_user_email(request), mcp_id, body)
    except ValueError as error:
        raise _not_found_from_value_error(error) from error


@router.delete("/connectors/mcp/{mcp_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mcp_connection(
    request: Request,
    mcp_id: str,
    service: Annotated[MCPConnectorService, Depends(get_mcp_connector_service)],
) -> None:
    try:
        await service.delete_connection(_user_email(request), mcp_id)
    except ValueError as error:
        raise _not_found_from_value_error(error) from error


@router.post("/connectors/mcp/oauth/discover", response_model=MCPOAuthDiscoveryResponse)
async def discover_mcp_oauth(
    body: MCPOAuthDiscoveryRequest,
    service: Annotated[MCPConnectorService, Depends(get_mcp_connector_service)],
) -> MCPOAuthDiscoveryResponse:
    try:
        if body.issuer_url is not None:
            return await service.discover_oauth_issuer(str(body.issuer_url))
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
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """Hand the result to the SPA; it completes the connection as the signed-in user (see oauth_handoff)."""
    session = decode_state_session(state)
    fallback = f"{settings.frontend_url}/dashboard/connectors"
    try:
        return_to = safe_return_to(session.return_to) if session else fallback
    except ValueError:
        return_to = fallback
    return handoff_redirect(return_to, flow="mcp", state=state, code=code, error=error)


async def complete_mcp_oauth(
    *, state: str | None, code: str | None, error: str | None, user_email: str
) -> dict[str, str]:
    """Store the tokens, if the signed-in user started this flow. Returns the page's result parameters."""
    session = decode_state_session(state)
    if not session or session.is_expired() or session.user_email != user_email:
        return {"mcp_oauth": "error", "reason": "invalid_state"}
    if error:
        return {"mcp_oauth": "error", "reason": "cancelled"}
    if not code:
        return {"mcp_oauth": "error", "reason": "missing_code"}
    try:
        await get_mcp_connector_service().complete_oauth(
            owner_email=session.user_email,
            mcp_id=session.mcp_id,
            code=code,
            code_verifier=session.code_verifier,
        )
    except Exception as exc:
        log.error("MCP OAuth completion failed for %s: %s", session.mcp_id, exc, exc_info=True)
        return {"mcp_oauth": "error", "reason": "callback_failed"}
    return {"mcp_oauth": "success", "mcp_id": session.mcp_id}


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
