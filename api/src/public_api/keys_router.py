"""Dashboard management of an agent's secret keys for the public /v1 API."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer

from src.agents.repository import AgentRepository
from src.apikeys.router import get_agent_repository, get_user_email, validate_agent_ownership
from src.public_api.keys import (
    AgentSecretKey,
    CreatedSecretKeyResponse,
    CreateSecretKeyRequest,
    SecretKeyRepository,
    SecretKeyResponse,
    UpdateSecretKeyRequest,
)

router = APIRouter(
    prefix="/agents/{agent_id}/secret-keys",
    tags=["secret-keys"],
    dependencies=[Depends(HTTPBearer())],
)


def get_secret_key_repository() -> SecretKeyRepository:
    return SecretKeyRepository()


def require_agent_owner(
    request: Request,
    agent_id: str,
    agent_repo: Annotated[AgentRepository, Depends(get_agent_repository)],
) -> str:
    """The signed-in owner's email, once the agent is confirmed to be theirs."""
    user_email = get_user_email(request)
    validate_agent_ownership(agent_id, user_email, agent_repo)
    return user_email


@router.post("", response_model=CreatedSecretKeyResponse, status_code=status.HTTP_201_CREATED)
async def create_secret_key(
    agent_id: str,
    body: CreateSecretKeyRequest,
    owner_email: Annotated[str, Depends(require_agent_owner)],
    repo: Annotated[SecretKeyRepository, Depends(get_secret_key_repository)],
) -> CreatedSecretKeyResponse:
    """Create a secret key. The plaintext secret is returned here and never again."""
    key, secret = AgentSecretKey.issue(agent_id=agent_id, name=body.name, created_by=owner_email)
    repo.create(key)
    return CreatedSecretKeyResponse(**key.to_response().model_dump(), secret=secret)


@router.get("", response_model=list[SecretKeyResponse])
async def list_secret_keys(
    agent_id: str,
    _owner_email: Annotated[str, Depends(require_agent_owner)],
    repo: Annotated[SecretKeyRepository, Depends(get_secret_key_repository)],
) -> list[SecretKeyResponse]:
    keys = sorted(repo.find_all_by_agent(agent_id), key=lambda key: key.created_at, reverse=True)
    return [key.to_response() for key in keys]


@router.get("/{key_id}", response_model=SecretKeyResponse)
async def get_secret_key(
    agent_id: str,
    key_id: str,
    _owner_email: Annotated[str, Depends(require_agent_owner)],
    repo: Annotated[SecretKeyRepository, Depends(get_secret_key_repository)],
) -> SecretKeyResponse:
    key = repo.find_by_id(agent_id, key_id)
    if not key:
        raise HTTPException(status_code=404, detail="Secret key not found")
    return key.to_response()


@router.patch("/{key_id}", response_model=SecretKeyResponse)
async def update_secret_key(
    agent_id: str,
    key_id: str,
    body: UpdateSecretKeyRequest,
    _owner_email: Annotated[str, Depends(require_agent_owner)],
    repo: Annotated[SecretKeyRepository, Depends(get_secret_key_repository)],
) -> SecretKeyResponse:
    key = repo.update(agent_id, key_id, name=body.name, is_active=body.is_active)
    if not key:
        raise HTTPException(status_code=404, detail="Secret key not found")
    return key.to_response()


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_secret_key(
    agent_id: str,
    key_id: str,
    _owner_email: Annotated[str, Depends(require_agent_owner)],
    repo: Annotated[SecretKeyRepository, Depends(get_secret_key_repository)],
) -> None:
    """Delete a secret key. Idempotent."""
    repo.delete_by_id(agent_id, key_id)
