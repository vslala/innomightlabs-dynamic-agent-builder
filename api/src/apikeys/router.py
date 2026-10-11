"""
API Key management router.

Endpoints for creating, listing, updating, and revoking API keys for agents.
These keys are used for widget authentication.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer

from src.agents.access import agent_with
from src.agents.models import Agent
from src.agents.repository import AgentRepository
from src.apikeys.models import (
    A2ASecretResponse,
    AgentApiKey,
    ApiKeyResponse,
    CreateApiKeyRequest,
    UpdateApiKeyRequest,
)
from src.apikeys.repository import ApiKeyRepository
from src.iam.dependencies import get_principal
from src.iam.principal import Principal

log = logging.getLogger(__name__)

security = HTTPBearer()

router = APIRouter(
    prefix="/agents/{agent_id}/api-keys",
    tags=["api-keys"],
    dependencies=[Depends(security)],
)


def get_api_key_repository() -> ApiKeyRepository:
    """Dependency for ApiKeyRepository."""
    return ApiKeyRepository()


def get_agent_repository() -> AgentRepository:
    """Dependency for AgentRepository."""
    return AgentRepository()


@router.post(
    "",
    response_model=ApiKeyResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_api_key(
    principal: Annotated[Principal, Depends(get_principal)],
    agent_id: str,
    body: CreateApiKeyRequest,
    api_key_repo: Annotated[ApiKeyRepository, Depends(get_api_key_repository)],
    agent: Annotated[Agent, Depends(agent_with("apikeys:CreateKey"))],
) -> ApiKeyResponse:
    """
    Create a new API key for an agent.

    The public key (pk_live_xxx) is automatically generated and should be
    shared with the customer for widget integration.

    Args:
        agent_id: The agent to create the key for
        body: API key creation request with name and allowed origins

    Returns:
        The created API key with its public key
    """

    api_key = AgentApiKey(
        agent_id=agent_id,
        name=body.name,
        allowed_origins=body.allowed_origins,
        allow_guests=body.allow_guests,
        created_by=principal.user_id,  # audit only: the key acts as the agent's owner
    )

    saved = api_key_repo.save(api_key)
    log.info(f"Created API key {saved.key_id} for agent {agent_id}")

    return saved.to_response()


@router.get("", response_model=list[ApiKeyResponse])
async def list_api_keys(
    agent_id: str,
    api_key_repo: Annotated[ApiKeyRepository, Depends(get_api_key_repository)],
    agent: Annotated[Agent, Depends(agent_with("apikeys:ListKeys"))],
) -> list[ApiKeyResponse]:
    """
    List all API keys for an agent.

    Args:
        agent_id: The agent to list keys for

    Returns:
        List of API keys for the agent
    """

    keys = api_key_repo.find_all_by_agent(agent_id)
    return [key.to_response() for key in keys]


@router.get("/{key_id}", response_model=ApiKeyResponse)
async def get_api_key(
    agent_id: str,
    key_id: str,
    api_key_repo: Annotated[ApiKeyRepository, Depends(get_api_key_repository)],
    agent: Annotated[Agent, Depends(agent_with("apikeys:ListKeys"))],
) -> ApiKeyResponse:
    """
    Get a specific API key by ID.

    Args:
        agent_id: The agent the key belongs to
        key_id: The unique key identifier

    Returns:
        The API key details
    """

    api_key = api_key_repo.find_by_id(agent_id, key_id)
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")

    return api_key.to_response()


@router.patch("/{key_id}", response_model=ApiKeyResponse)
async def update_api_key(
    agent_id: str,
    key_id: str,
    body: UpdateApiKeyRequest,
    api_key_repo: Annotated[ApiKeyRepository, Depends(get_api_key_repository)],
    agent: Annotated[Agent, Depends(agent_with("apikeys:CreateKey"))],
) -> ApiKeyResponse:
    """
    Update an API key's settings.

    Can update name, allowed_origins, and is_active status.
    Only provided fields are updated.

    Args:
        agent_id: The agent the key belongs to
        key_id: The unique key identifier
        body: Fields to update

    Returns:
        The updated API key
    """

    api_key = api_key_repo.find_by_id(agent_id, key_id)
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")

    # Apply updates only for provided fields
    if body.name is not None:
        api_key.name = body.name
    if body.allowed_origins is not None:
        api_key.allowed_origins = body.allowed_origins
    if body.is_active is not None:
        api_key.is_active = body.is_active
    if body.allow_guests is not None:
        api_key.allow_guests = body.allow_guests

    saved = api_key_repo.save(api_key)
    log.info(f"Updated API key {key_id} for agent {agent_id}")

    return saved.to_response()


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_api_key(
    agent_id: str,
    key_id: str,
    api_key_repo: Annotated[ApiKeyRepository, Depends(get_api_key_repository)],
    agent: Annotated[Agent, Depends(agent_with("apikeys:RevokeKey"))],
) -> None:
    """
    Revoke/delete an API key.

    This is idempotent - returns success even if key doesn't exist.

    Args:
        agent_id: The agent the key belongs to
        key_id: The unique key identifier
    """

    api_key_repo.delete_by_id(agent_id, key_id)
    log.info(f"Deleted API key {key_id} for agent {agent_id}")


@router.post("/{key_id}/a2a-secret", response_model=A2ASecretResponse, status_code=status.HTTP_201_CREATED)
async def issue_a2a_secret(
    agent_id: str,
    key_id: str,
    api_key_repo: Annotated[ApiKeyRepository, Depends(get_api_key_repository)],
    agent: Annotated[Agent, Depends(agent_with("apikeys:CreateKey"))],
) -> A2ASecretResponse:
    """Issue (or rotate) the key's A2A client secret. The public key is embedded in web pages, so it
    is never an A2A credential."""

    api_key = api_key_repo.find_by_id(agent_id, key_id)
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")

    secret = api_key_repo.issue_a2a_secret(api_key)
    log.info(f"Issued A2A secret for API key {key_id} on agent {agent_id}")
    return A2ASecretResponse(client_id=api_key.key_id, client_secret=secret)
