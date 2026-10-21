from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPBearer

from src.auth.oauth_handoff import handoff_redirect, safe_return_to
from src.config import settings
from src.connectors.social.connect import authorize_url_for, decode_state
from src.connectors.social.models import (
    SocialAccountResponse,
    SocialConnectRequest,
    SocialConnectResponse,
    SocialNetworkResponse,
)
from src.connectors.social.networks import enabled_networks, network_for
from src.connectors.social.repository import SocialAccountRepository
from src.iam.dependencies import get_principal
from src.iam.principal import Principal
from src.settings.access import settings_manager

log = logging.getLogger(__name__)

security = HTTPBearer()

# Like the account's other connections: admins connect and disconnect (`settings:Manage`), any member may look
router = APIRouter(prefix="/connectors/social", tags=["social-connectors"], dependencies=[Depends(security)])
public_router = APIRouter(tags=["social-connectors"])

Member = Annotated[Principal, Depends(get_principal)]
Manager = Annotated[Principal, Depends(settings_manager)]


@router.get("/networks", response_model=list[SocialNetworkResponse])
async def list_networks(_: Member) -> list[SocialNetworkResponse]:
    """The networks an account can be connected on. The dashboard renders only this, so a new network appears here."""
    return [
        SocialNetworkResponse(key=network.key, display_name=network.display_name, icon=network.icon)
        for network in enabled_networks()
    ]


@router.post("/networks/{network}/connect", response_model=SocialConnectResponse)
async def connect_network(
    request: Request, network: str, body: SocialConnectRequest, principal: Manager
) -> SocialConnectResponse:
    user_email = getattr(request.state, "user_email", None)
    if not user_email:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        authorize_url = authorize_url_for(
            network,
            account_id=principal.account_id,
            user_id=principal.user_id,
            user_email=str(user_email),
            return_to=safe_return_to(body.return_to),
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return SocialConnectResponse(authorize_url=authorize_url)


@public_router.get("/connectors/social/oauth/callback")
async def social_oauth_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """Hand the result to the SPA; it completes the connection as the signed-in user (see oauth_handoff)."""
    session = decode_state(state)
    fallback = f"{settings.frontend_url}/dashboard/connectors?tab=social"
    try:
        return_to = safe_return_to(session.return_to) if session else fallback
    except ValueError:
        return_to = fallback
    return handoff_redirect(return_to, flow="social", state=state, code=code, error=error)


@router.get("/accounts", response_model=list[SocialAccountResponse])
async def list_accounts(principal: Member) -> list[SocialAccountResponse]:
    return [account.to_response() for account in SocialAccountRepository().list(principal.account_id)]


@router.delete("/accounts/{social_account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_account(social_account_id: str, principal: Manager) -> None:
    repository = SocialAccountRepository()
    account = repository.get(principal.account_id, social_account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Social account not found")
    try:
        await network_for(account.network).revoke(account.credentials())
    except Exception as error:  # ending the grant is best effort; the account is disconnected either way
        log.warning("Could not revoke %s access: %s", account.network, type(error).__name__)
    repository.delete(account)
