from __future__ import annotations

from typing import Annotated
from urllib.parse import quote, urlparse

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from src.agents.repository import AgentRepository
from src.skills.agent2agent_client.discovery import A2ADiscoveryClient
from src.skills.agent2agent_client.models import A2ARegistryConfig
from src.skills.agent2agent_client.oauth import (
    A2ARemoteOAuthAuthConfig,
    A2ARemoteOAuthCredentialRecord,
    A2ARemoteOAuthRepository,
    A2ARemoteOAuthError,
    authorization_code_provider_from_card_with_dcr,
    build_credentials,
    build_authorization_url,
    create_state_session,
    decode_state_session,
    encode_state_session,
    encrypt_auth_config,
    exchange_code_for_tokens,
    generate_code_challenge,
)
from src.skills.repository import AgentSkillRepository, get_agent_skill_repository

router = APIRouter(tags=["agent2agent-client"])
security = HTTPBearer()


class A2ARemoteOAuthStartRequest(BaseModel):
    agent_id: str
    installed_skill_id: str
    service_url: str | None = None
    target_origin: str | None = None
    return_to: str


class A2ARemoteOAuthStartResponse(BaseModel):
    authorize_url: str


def get_a2a_remote_oauth_repository() -> A2ARemoteOAuthRepository:
    return A2ARemoteOAuthRepository()


def get_agent_repository() -> AgentRepository:
    return AgentRepository()


@router.post("/oauth/start", response_model=A2ARemoteOAuthStartResponse, dependencies=[Depends(security)])
async def start_a2a_remote_oauth(
    request: Request,
    body: A2ARemoteOAuthStartRequest,
    agent_repo: Annotated[AgentRepository, Depends(get_agent_repository)],
    skill_repo: Annotated[AgentSkillRepository, Depends(get_agent_skill_repository)],
) -> A2ARemoteOAuthStartResponse:
    user_email: str = request.state.user_email
    agent = agent_repo.find_agent_by_id(body.agent_id, user_email)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    installed = skill_repo.find_by_id(body.agent_id, body.installed_skill_id)
    if not installed or installed.skill_id != "agent2agent_client" or not installed.enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent2Agent skill installation not found")

    try:
        registry_config = A2ARegistryConfig.from_runtime_config(skill_repo.get_runtime_config(installed))
        discovery = A2ADiscoveryClient()
        candidates = await discovery._load_candidates(registry_config)
        candidate = _select_oauth_candidate(
            candidates,
            service_url=body.service_url,
            target_origin=body.target_origin,
        )
        if not candidate or not candidate.card_url:
            raise A2ARemoteOAuthError("Unable to resolve an Agent Card for this A2A OAuth target")

        raw_card = await discovery.http_client.get_agent_card(candidate.card_url)
        service_url = candidate.service_url or body.service_url or ""
        provider = await authorization_code_provider_from_card_with_dcr(
            card=raw_card,
            target_url=service_url,
            config=registry_config,
        )
        if not provider:
            raise A2ARemoteOAuthError("Remote A2A agent does not advertise an OAuth authorization-code flow")

        session = create_state_session(
            user_email=user_email,
            agent_id=body.agent_id,
            installed_skill_id=body.installed_skill_id,
            service_url=service_url,
            return_to=body.return_to,
            provider=provider,
        )
        return A2ARemoteOAuthStartResponse(
            authorize_url=build_authorization_url(
                provider=provider,
                state=encode_state_session(session),
                code_challenge=generate_code_challenge(session.code_verifier),
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/oauth/callback")
async def a2a_remote_oauth_callback(
    repository: A2ARemoteOAuthRepository = Depends(get_a2a_remote_oauth_repository),
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
) -> RedirectResponse:
    session = decode_state_session(state)
    if not session or session.is_expired():
        return _callback_redirect("/dashboard/agents", status_value="error", reason="invalid_state")

    if error:
        return _callback_redirect(
            session.return_to,
            status_value="error",
            reason=error_description or error,
            installed_skill_id=session.installed_skill_id,
        )

    if not code:
        return _callback_redirect(
            session.return_to,
            status_value="error",
            reason="missing_code",
            installed_skill_id=session.installed_skill_id,
        )

    try:
        tokens = await exchange_code_for_tokens(
            provider=session.provider,
            code=code,
            code_verifier=session.code_verifier,
        )
        credentials = build_credentials(tokens, default_scope=session.provider.scope)
        repository.save(
            A2ARemoteOAuthCredentialRecord(
                owner_email=session.user_email,
                agent_id=session.agent_id,
                installed_skill_id=session.installed_skill_id,
                target_origin=session.target_origin,
                encrypted_auth_config=encrypt_auth_config(
                    A2ARemoteOAuthAuthConfig(
                        provider=session.provider,
                        credentials=credentials,
                    )
                ),
            )
        )
    except Exception as exc:
        return _callback_redirect(
            session.return_to,
            status_value="error",
            reason=str(exc)[:300],
            installed_skill_id=session.installed_skill_id,
        )

    return _callback_redirect(
        session.return_to,
        status_value="success",
        installed_skill_id=session.installed_skill_id,
    )


def _callback_redirect(
    return_to: str,
    *,
    status_value: str,
    reason: str | None = None,
    installed_skill_id: str | None = None,
) -> RedirectResponse:
    params = [f"a2a_oauth={quote(status_value)}"]
    if reason:
        params.append(f"reason={quote(reason)}")
    if installed_skill_id:
        params.append(f"installed_skill_id={quote(installed_skill_id)}")
    separator = "&" if "?" in return_to else "?"
    return RedirectResponse(f"{return_to}{separator}{'&'.join(params)}")


def _select_oauth_candidate(candidates, *, service_url: str | None, target_origin: str | None):
    if service_url:
        for candidate in candidates:
            if candidate.service_url.rstrip("/") == service_url.rstrip("/"):
                return candidate
    origin = target_origin or _origin(service_url or "")
    if origin:
        for candidate in candidates:
            if _origin(candidate.service_url) == origin:
                return candidate
    return candidates[0] if len(candidates) == 1 else None


def _origin(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"
