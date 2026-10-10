"""Dashboard management of an agent's secret keys for the public /v1 API."""

from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPBearer

from src.agents.access import agent_with
from src.agents.models import Agent
from src.iam.dependencies import get_principal
from src.iam.principal import Principal
from src.public_api.keys import (
    AgentSecretKey,
    CreatedSecretKeyResponse,
    CreateSecretKeyRequest,
    SecretKeyRepository,
    SecretKeyResponse,
    UpdateSecretKeyRequest,
)
from src.token_usage.models import TokenUsagePeriod, TokenUsageTimeseriesResponse
from src.token_usage.service import TokenUsageService

router = APIRouter(
    prefix="/agents/{agent_id}/secret-keys",
    tags=["secret-keys"],
    dependencies=[Depends(HTTPBearer())],
)


def get_secret_key_repository() -> SecretKeyRepository:
    return SecretKeyRepository()


def get_token_usage_service() -> TokenUsageService:
    return TokenUsageService()


# Secret keys reach the agent as its owner, so managing them is the agent's apikeys:* actions
can_list_keys = agent_with("apikeys:ListKeys")
can_create_keys = agent_with("apikeys:CreateKey")
can_revoke_keys = agent_with("apikeys:RevokeKey")


@router.post("", response_model=CreatedSecretKeyResponse, status_code=status.HTTP_201_CREATED)
async def create_secret_key(
    agent_id: str,
    body: CreateSecretKeyRequest,
    _agent: Annotated[Agent, Depends(can_create_keys)],
    principal: Annotated[Principal, Depends(get_principal)],
    repo: Annotated[SecretKeyRepository, Depends(get_secret_key_repository)],
) -> CreatedSecretKeyResponse:
    """Create a secret key. The plaintext secret is returned here and never again."""
    # created_by is for audit: the key acts as the agent's owner
    key, secret = AgentSecretKey.issue(agent_id=agent_id, name=body.name, created_by=principal.user_id)
    repo.create(key)
    return CreatedSecretKeyResponse(**key.to_response().model_dump(), secret=secret)


@router.get("", response_model=list[SecretKeyResponse])
async def list_secret_keys(
    agent_id: str,
    _agent: Annotated[Agent, Depends(can_list_keys)],
    repo: Annotated[SecretKeyRepository, Depends(get_secret_key_repository)],
) -> list[SecretKeyResponse]:
    keys = sorted(repo.find_all_by_agent(agent_id), key=lambda key: key.created_at, reverse=True)
    return [key.to_response() for key in keys]


@router.get("/{key_id}", response_model=SecretKeyResponse)
async def get_secret_key(
    agent_id: str,
    key_id: str,
    _agent: Annotated[Agent, Depends(can_list_keys)],
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
    _agent: Annotated[Agent, Depends(can_create_keys)],
    repo: Annotated[SecretKeyRepository, Depends(get_secret_key_repository)],
) -> SecretKeyResponse:
    key = repo.update(agent_id, key_id, name=body.name, is_active=body.is_active)
    if not key:
        raise HTTPException(status_code=404, detail="Secret key not found")
    return key.to_response()


@router.get("/{key_id}/usage", response_model=TokenUsageTimeseriesResponse)
async def get_secret_key_usage(
    agent_id: str,
    key_id: str,
    period: TokenUsagePeriod,
    agent: Annotated[Agent, Depends(can_list_keys)],
    repo: Annotated[SecretKeyRepository, Depends(get_secret_key_repository)],
    service: Annotated[TokenUsageService, Depends(get_token_usage_service)],
    llm_model: Optional[str] = Query(default=None),
    from_at: Annotated[Optional[datetime], Query(alias="from")] = None,
    to_at: Annotated[Optional[datetime], Query(alias="to")] = None,
) -> TokenUsageTimeseriesResponse:
    """Token usage of calls made with this key, in the same shape as agent token usage."""
    if not repo.find_by_id(agent_id, key_id):
        raise HTTPException(status_code=404, detail="Secret key not found")
    return service.get_usage(
        agent=agent,
        period=period,
        from_at=from_at,
        to_at=to_at,
        llm_model=llm_model,
        api_key_id=key_id,
    )


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_secret_key(
    agent_id: str,
    key_id: str,
    _agent: Annotated[Agent, Depends(can_revoke_keys)],
    repo: Annotated[SecretKeyRepository, Depends(get_secret_key_repository)],
) -> None:
    """Delete a secret key. Idempotent."""
    repo.delete_by_id(agent_id, key_id)
