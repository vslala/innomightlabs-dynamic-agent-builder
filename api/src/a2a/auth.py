from typing import Annotated

from fastapi import Depends, HTTPException, Request

from src.agents.repository import AgentRepository
from src.apikeys.models import AgentApiKey
from src.apikeys.repository import ApiKeyRepository
from src.a2a.oauth import (
    A2A_SCOPE_MESSAGE,
    A2A_SCOPE_TASKS,
    bearer_challenge,
    validate_a2a_access_token,
)

BEARER_CHALLENGE = bearer_challenge()


def get_api_key_repository() -> ApiKeyRepository:
    return ApiKeyRepository()


def get_agent_repository() -> AgentRepository:
    return AgentRepository()


def _bearer_token(value: str | None) -> str | None:
    if not value:
        return None
    scheme, _, token = value.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token.strip()


def get_a2a_client(
    request: Request,
    agent_id: str,
    api_key_repo: Annotated[ApiKeyRepository, Depends(get_api_key_repository)],
    agent_repo: Annotated[AgentRepository, Depends(get_agent_repository)],
) -> AgentApiKey:
    return _authenticate_a2a_client(
        request=request,
        agent_id=agent_id,
        api_key_repo=api_key_repo,
        agent_repo=agent_repo,
        required_scopes={A2A_SCOPE_MESSAGE, A2A_SCOPE_TASKS},
    )


def require_a2a_client(required_scopes: set[str]):
    def dependency(
        request: Request,
        agent_id: str,
        api_key_repo: Annotated[ApiKeyRepository, Depends(get_api_key_repository)],
        agent_repo: Annotated[AgentRepository, Depends(get_agent_repository)],
    ) -> AgentApiKey:
        return _authenticate_a2a_client(
            request=request,
            agent_id=agent_id,
            api_key_repo=api_key_repo,
            agent_repo=agent_repo,
            required_scopes=required_scopes,
        )

    return dependency


def _authenticate_a2a_client(
    *,
    request: Request,
    agent_id: str,
    api_key_repo: ApiKeyRepository,
    agent_repo: AgentRepository,
    required_scopes: set[str],
) -> AgentApiKey:
    credential = _bearer_token(request.headers.get("Authorization"))
    if credential and _looks_like_jwt(credential):
        api_key = validate_a2a_access_token(
            token=credential,
            agent_id=agent_id,
            api_key_repo=api_key_repo,
            required_scopes=required_scopes,
        )
        _validate_agent_enabled(agent_id=agent_id, api_key=api_key, agent_repo=agent_repo)
        api_key_repo.increment_request_count(api_key.agent_id, api_key.key_id)
        return api_key

    credential = credential or request.headers.get("X-API-Key")

    if not credential:
        raise HTTPException(
            status_code=401,
            detail="Missing A2A credential",
            headers=BEARER_CHALLENGE,
        )

    api_key = api_key_repo.find_by_public_key(credential)
    if not api_key or not api_key.is_active or api_key.agent_id != agent_id:
        raise HTTPException(
            status_code=401,
            detail="Invalid A2A credential",
            headers=BEARER_CHALLENGE,
        )

    _validate_agent_enabled(agent_id=agent_id, api_key=api_key, agent_repo=agent_repo)
    api_key_repo.increment_request_count(api_key.agent_id, api_key.key_id)
    return api_key


def _validate_agent_enabled(*, agent_id: str, api_key: AgentApiKey, agent_repo: AgentRepository) -> None:
    agent = agent_repo.find_agent_by_id(agent_id, api_key.created_by)
    if not agent or not agent.is_agent2agent_enabled:
        raise HTTPException(status_code=404, detail="Agent not found")


def _looks_like_jwt(token: str) -> bool:
    return token.count(".") == 2
