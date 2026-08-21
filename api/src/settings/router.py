"""
Settings router for managing user provider configurations.
"""

from fastapi import APIRouter, Depends, Request, HTTPException, status
from fastapi.security import HTTPBearer
from pydantic import BaseModel, ValidationError
from typing import Annotated
import json
import logging

import src.form_models as form_models
from src.settings.agent2agent_policy import (
    Agent2AgentPolicy,
    Agent2AgentPolicyError,
    Agent2AgentSettingsRequest,
    settings_to_response_map,
)
from src.settings.models import (
    Agent2AgentSettingsResponse,
    ProviderSettings,
    ProviderSettingsResponse,
)
from src.settings.repository import (
    ProviderSettingsRepository,
    get_provider_settings_repository,
)
from src.settings.schemas import (
    PROVIDER_SCHEMAS,
    SUPPORTED_PROVIDERS,
    get_agent2agent_settings_schema,
    get_provider_schema,
)
from src.crypto import encrypt, decrypt

log = logging.getLogger(__name__)

# Security scheme for Swagger UI
security = HTTPBearer()

router = APIRouter(
    prefix="/settings",
    tags=["settings"],
    dependencies=[Depends(security)]
)


class ProviderWithStatus(BaseModel):
    """Provider schema with configuration status."""
    provider_name: str
    form: form_models.Form
    is_configured: bool


def get_agent2agent_policy() -> Agent2AgentPolicy:
    return Agent2AgentPolicy()


def _to_agent2agent_response(settings) -> Agent2AgentSettingsResponse:
    return Agent2AgentSettingsResponse(
        allowed_origins=settings.allowed_origins,
        allowed_origins_map=settings_to_response_map(settings),
        created_at=settings.created_at,
        updated_at=settings.updated_at,
    )


@router.get("/agent2agent", response_model=Agent2AgentSettingsResponse)
async def get_agent2agent_settings(
    request: Request,
    policy: Annotated[Agent2AgentPolicy, Depends(get_agent2agent_policy)],
) -> Agent2AgentSettingsResponse:
    user_email: str = request.state.user_email
    return _to_agent2agent_response(policy.settings_for_user(user_email))


@router.get("/agent2agent/schema", response_model=form_models.Form, response_model_exclude_none=True)
async def get_agent2agent_settings_form() -> form_models.Form:
    return get_agent2agent_settings_schema()


@router.put("/agent2agent", response_model=Agent2AgentSettingsResponse)
async def save_agent2agent_settings(
    request: Request,
    body: dict,
    policy: Annotated[Agent2AgentPolicy, Depends(get_agent2agent_policy)],
) -> Agent2AgentSettingsResponse:
    user_email: str = request.state.user_email
    try:
        settings_request = Agent2AgentSettingsRequest.model_validate(body)
        saved = policy.save_settings(user_email=user_email, request=settings_request)
    except (Agent2AgentPolicyError, ValidationError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return _to_agent2agent_response(saved)


@router.get("/providers", response_model=list[ProviderWithStatus])
async def list_providers(
    request: Request,
    repo: Annotated[ProviderSettingsRepository, Depends(get_provider_settings_repository)],
) -> list[ProviderWithStatus]:
    """
    List all supported providers with their configuration status.

    Returns each provider's form schema and whether the user has configured it.
    """
    user_email: str = request.state.user_email

    # Get user's configured providers
    user_settings = repo.find_all_by_user(user_email)
    configured_providers = {s.provider_name for s in user_settings}

    # Build response with all providers
    result = []
    for provider_name in SUPPORTED_PROVIDERS:
        schema = PROVIDER_SCHEMAS[provider_name]
        result.append(ProviderWithStatus(
            provider_name=provider_name,
            form=schema,
            is_configured=provider_name in configured_providers,
        ))

    return result


@router.get("/providers/{provider_name}", response_model=ProviderSettingsResponse)
async def get_provider_settings(
    request: Request,
    provider_name: str,
    repo: Annotated[ProviderSettingsRepository, Depends(get_provider_settings_repository)],
) -> ProviderSettingsResponse:
    """
    Get user's configuration status for a specific provider.

    Note: Actual credentials are not returned for security.
    """
    user_email: str = request.state.user_email

    # Validate provider name
    if provider_name not in SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown provider: {provider_name}. Supported: {SUPPORTED_PROVIDERS}"
        )

    settings = repo.find_by_provider(user_email, provider_name)

    if settings:
        return ProviderSettingsResponse(
            provider_name=provider_name,
            is_configured=True,
            created_at=settings.created_at,
            updated_at=settings.updated_at,
        )
    else:
        return ProviderSettingsResponse(
            provider_name=provider_name,
            is_configured=False,
        )


@router.post("/providers/{provider_name}", response_model=ProviderSettingsResponse, status_code=status.HTTP_201_CREATED)
async def save_provider_settings(
    request: Request,
    provider_name: str,
    body: dict,
    repo: Annotated[ProviderSettingsRepository, Depends(get_provider_settings_repository)],
) -> ProviderSettingsResponse:
    """
    Save or update provider credentials.

    The credentials are encrypted before storage.
    """
    user_email: str = request.state.user_email

    # Validate provider name
    schema = get_provider_schema(provider_name)
    if not schema:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown provider: {provider_name}. Supported: {SUPPORTED_PROVIDERS}"
        )

    if provider_name == "OpenAI":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OpenAI must be configured using OAuth via /auth/openai/complete",
        )
    if provider_name == "GoogleDrive":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GoogleDrive must be configured using OAuth via /auth/google-drive/start",
        )

    # Validate required fields from schema
    required_fields = [field.name for field in schema.form_inputs]
    missing_fields = [f for f in required_fields if f not in body or not body[f]]
    if missing_fields:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Missing required fields: {missing_fields}"
        )

    # Encrypt credentials as JSON string
    credentials_json = json.dumps(body)
    encrypted_credentials = encrypt(credentials_json)

    # Save settings
    settings = ProviderSettings(
        user_email=user_email,
        provider_name=provider_name,
        encrypted_credentials=encrypted_credentials,
    )
    saved = repo.save(settings)

    log.info(f"Saved provider settings for {provider_name} for user {user_email}")

    return ProviderSettingsResponse(
        provider_name=provider_name,
        is_configured=True,
        created_at=saved.created_at,
        updated_at=saved.updated_at,
    )


@router.delete("/providers/{provider_name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider_settings(
    request: Request,
    provider_name: str,
    repo: Annotated[ProviderSettingsRepository, Depends(get_provider_settings_repository)],
) -> None:
    """
    Delete provider configuration.
    """
    user_email: str = request.state.user_email

    # Validate provider name
    if provider_name not in SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown provider: {provider_name}. Supported: {SUPPORTED_PROVIDERS}"
        )

    success = repo.delete(user_email, provider_name)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete provider settings"
        )

    log.info(f"Deleted provider settings for {provider_name} for user {user_email}")
