from typing import Annotated

from fastapi import Depends, HTTPException, Request

from src.agents.repository import AgentRepository
from src.apikeys.models import AgentApiKey
from src.apikeys.repository import ApiKeyRepository

BEARER_CHALLENGE = {"WWW-Authenticate": "Bearer"}


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
    credential = _bearer_token(request.headers.get("Authorization"))
    if not credential:
        credential = request.headers.get("X-API-Key")

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

    agent = agent_repo.find_agent_by_id(agent_id, api_key.created_by)
    if not agent or not agent.is_agent2agent_enabled:
        raise HTTPException(status_code=404, detail="Agent not found")

    api_key_repo.increment_request_count(api_key.agent_id, api_key.key_id)
    return api_key
