"""
API Key management router.

Endpoints for creating, listing, updating, and revoking API keys for agents.
These keys are used for widget authentication.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer

from src.agents.repository import AgentRepository
from src.apikeys.models import (
    AgentApiKey,
    ApiKeyResponse,
    CreateApiKeyRequest,
    UpdateApiKeyRequest,
)
from src.apikeys.repository import ApiKeyRepository

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


def get_user_email(request: Request) -> str:
    """Extract user email from request state (set by auth middleware)."""
    user_email = getattr(request.state, "user_email", None)
    if not user_email:
        raise HTTPException(status_code=401, detail="User not authenticated")
    return str(user_email)


def validate_agent_ownership(
    agent_id: str,
    user_email: str,
    agent_repo: AgentRepository,
) -> None:
    """
    Validate that the agent exists and belongs to the user.

    Raises HTTPException if agent not found or not owned by user.
    """
    agent = agent_repo.find_agent_by_id(agent_id, user_email)
    if not agent:
        raise HTTPException(
            status_code=404,
            detail=f"Agent '{agent_id}' not found or does not belong to you",
        )


@router.post(
    "",
    response_model=ApiKeyResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_api_key(
    request: Request,
    agent_id: str,
    body: CreateApiKeyRequest,
    api_key_repo: Annotated[ApiKeyRepository, Depends(get_api_key_repository)],
    agent_repo: Annotated[AgentRepository, Depends(get_agent_repository)],
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
    user_email = get_user_email(request)
    validate_agent_ownership(agent_id, user_email, agent_repo)

    api_key = AgentApiKey(
        agent_id=agent_id,
        name=body.name,
        allowed_origins=body.allowed_origins,
        created_by=user_email,
    )

    saved = api_key_repo.save(api_key)
    log.info(f"Created API key {saved.key_id} for agent {agent_id}")

    return saved.to_response()


@router.get("", response_model=list[ApiKeyResponse])
async def list_api_keys(
    request: Request,
    agent_id: str,
    api_key_repo: Annotated[ApiKeyRepository, Depends(get_api_key_repository)],
    agent_repo: Annotated[AgentRepository, Depends(get_agent_repository)],
) -> list[ApiKeyResponse]:
    """
    List all API keys for an agent.

    Args:
        agent_id: The agent to list keys for

    Returns:
        List of API keys for the agent
    """
    user_email = get_user_email(request)
    validate_agent_ownership(agent_id, user_email, agent_repo)

    keys = api_key_repo.find_all_by_agent(agent_id)
    return [key.to_response() for key in keys]


@router.get("/{key_id}", response_model=ApiKeyResponse)
async def get_api_key(
    request: Request,
    agent_id: str,
    key_id: str,
    api_key_repo: Annotated[ApiKeyRepository, Depends(get_api_key_repository)],
    agent_repo: Annotated[AgentRepository, Depends(get_agent_repository)],
) -> ApiKeyResponse:
    """
    Get a specific API key by ID.

    Args:
        agent_id: The agent the key belongs to
        key_id: The unique key identifier

    Returns:
        The API key details
    """
    user_email = get_user_email(request)
    validate_agent_ownership(agent_id, user_email, agent_repo)

    api_key = api_key_repo.find_by_id(agent_id, key_id)
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")

    return api_key.to_response()


@router.patch("/{key_id}", response_model=ApiKeyResponse)
async def update_api_key(
    request: Request,
    agent_id: str,
    key_id: str,
    body: UpdateApiKeyRequest,
    api_key_repo: Annotated[ApiKeyRepository, Depends(get_api_key_repository)],
    agent_repo: Annotated[AgentRepository, Depends(get_agent_repository)],
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
    user_email = get_user_email(request)
    validate_agent_ownership(agent_id, user_email, agent_repo)

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

    saved = api_key_repo.save(api_key)
    log.info(f"Updated API key {key_id} for agent {agent_id}")

    return saved.to_response()


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_api_key(
    request: Request,
    agent_id: str,
    key_id: str,
    api_key_repo: Annotated[ApiKeyRepository, Depends(get_api_key_repository)],
    agent_repo: Annotated[AgentRepository, Depends(get_agent_repository)],
) -> None:
    """
    Revoke/delete an API key.

    This is idempotent - returns success even if key doesn't exist.

    Args:
        agent_id: The agent the key belongs to
        key_id: The unique key identifier
    """
    user_email = get_user_email(request)
    validate_agent_ownership(agent_id, user_email, agent_repo)

    api_key_repo.delete_by_id(agent_id, key_id)
    log.info(f"Deleted API key {key_id} for agent {agent_id}")
