"""
Settings router: the account's provider configurations and A2A trust settings, which admins manage and every
member's agents use, and a member's default agent.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer
from pydantic import BaseModel, ValidationError
from typing import Annotated
import json
import logging

import src.form_models as form_models
from src.agents.access import require_agent
from src.agents.repository import AgentRepository
from src.iam.dependencies import get_principal
from src.iam.principal import Principal
from src.settings.access import MANAGE_SETTINGS, settings_manager
from src.settings.agent2agent_policy import (
    Agent2AgentPolicy,
    Agent2AgentPolicyError,
    Agent2AgentSettingsRequest,
    settings_to_response_map,
)
from src.settings.models import (
    Agent2AgentSettingsResponse,
    DefaultAgentPreference,
    DefaultAgentPreferenceResponse,
    ProviderSettings,
    ProviderSettingsResponse,
)
from src.settings.repository import (
    DefaultAgentPreferenceRepository,
    ProviderSettingsRepository,
    get_default_agent_preference_repository,
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

agent_repository = AgentRepository()


class ProviderWithStatus(BaseModel):
    """Provider schema with configuration status."""
    provider_name: str
    form: form_models.Form
    is_configured: bool


class SetDefaultAgentRequest(BaseModel):
    agent_id: str


class SettingsAccessResponse(BaseModel):
    """Whether the caller may change the account's settings and credentials, so pages can offer the controls."""
    can_manage: bool


def get_agent2agent_policy() -> Agent2AgentPolicy:
    return Agent2AgentPolicy()


def _to_agent2agent_response(settings) -> Agent2AgentSettingsResponse:
    return Agent2AgentSettingsResponse(
        allowed_origins=settings.allowed_origins,
        allowed_origins_map=settings_to_response_map(settings),
        created_at=settings.created_at,
        updated_at=settings.updated_at,
    )


@router.get("/access", response_model=SettingsAccessResponse)
async def get_settings_access(principal: Annotated[Principal, Depends(get_principal)]) -> SettingsAccessResponse:
    return SettingsAccessResponse(can_manage=principal.can(MANAGE_SETTINGS).allowed)


@router.get("/agent2agent", response_model=Agent2AgentSettingsResponse)
async def get_agent2agent_settings(
    principal: Annotated[Principal, Depends(get_principal)],
    policy: Annotated[Agent2AgentPolicy, Depends(get_agent2agent_policy)],
) -> Agent2AgentSettingsResponse:
    return _to_agent2agent_response(policy.settings_for_account(principal.account_id))


@router.get("/agent2agent/schema", response_model=form_models.Form, response_model_exclude_none=True)
async def get_agent2agent_settings_form() -> form_models.Form:
    return get_agent2agent_settings_schema()


@router.put("/agent2agent", response_model=Agent2AgentSettingsResponse)
async def save_agent2agent_settings(
    body: dict,
    principal: Annotated[Principal, Depends(settings_manager)],
    policy: Annotated[Agent2AgentPolicy, Depends(get_agent2agent_policy)],
) -> Agent2AgentSettingsResponse:
    try:
        settings_request = Agent2AgentSettingsRequest.model_validate(body)
        saved = policy.save_settings(account_id=principal.account_id, updated_by=principal.user_id,
                                     request=settings_request)
    except (Agent2AgentPolicyError, ValidationError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return _to_agent2agent_response(saved)


@router.get("/providers", response_model=list[ProviderWithStatus])
async def list_providers(
    principal: Annotated[Principal, Depends(get_principal)],
    repo: Annotated[ProviderSettingsRepository, Depends(get_provider_settings_repository)],
) -> list[ProviderWithStatus]:
    """
    List all supported providers with their configuration status.

    Returns each provider's form schema and whether the account has configured it. Any member may look.
    """
    configured_providers = {s.provider_name for s in repo.find_all_in_account(principal.account_id)}

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
    provider_name: str,
    principal: Annotated[Principal, Depends(get_principal)],
    repo: Annotated[ProviderSettingsRepository, Depends(get_provider_settings_repository)],
) -> ProviderSettingsResponse:
    """
    Get the account's configuration status for a specific provider.

    Note: Actual credentials are not returned for security.
    """

    # Validate provider name
    if provider_name not in SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown provider: {provider_name}. Supported: {SUPPORTED_PROVIDERS}"
        )

    settings = repo.find_by_provider(principal.account_id, provider_name)

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
    provider_name: str,
    body: dict,
    principal: Annotated[Principal, Depends(settings_manager)],
    repo: Annotated[ProviderSettingsRepository, Depends(get_provider_settings_repository)],
) -> ProviderSettingsResponse:
    """
    Save or update the account's provider credentials (admins only).

    The credentials are encrypted before storage.
    """

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

    # Validate required fields from schema (fields marked optional may be blank)
    missing_fields = [
        field.name
        for field in schema.form_inputs
        if not field.is_optional and not body.get(field.name)
    ]
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
        account_id=principal.account_id,
        provider_name=provider_name,
        encrypted_credentials=encrypted_credentials,
        updated_by=principal.user_id,
    )
    saved = repo.save(settings)

    return ProviderSettingsResponse(
        provider_name=provider_name,
        is_configured=True,
        created_at=saved.created_at,
        updated_at=saved.updated_at,
    )


@router.delete("/providers/{provider_name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider_settings(
    provider_name: str,
    principal: Annotated[Principal, Depends(settings_manager)],
    repo: Annotated[ProviderSettingsRepository, Depends(get_provider_settings_repository)],
) -> None:
    """
    Delete the account's provider configuration (admins only).
    """

    # Validate provider name
    if provider_name not in SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown provider: {provider_name}. Supported: {SUPPORTED_PROVIDERS}"
        )

    success = repo.delete(principal.account_id, provider_name)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete provider settings"
        )


@router.get("/default-agent", response_model=DefaultAgentPreferenceResponse)
async def get_default_agent(
    principal: Annotated[Principal, Depends(get_principal)],
    repo: Annotated[DefaultAgentPreferenceRepository, Depends(get_default_agent_preference_repository)],
) -> DefaultAgentPreferenceResponse:
    """
    Get the member's default-agent preference in this account.

    Returns the raw stored agent_id with no server-side existence check —
    callers (e.g. the conversation-start screen, which already has the
    user's agent list) are responsible for treating a stale/deleted agent_id
    as unset.
    """
    preference = repo.find_for_member(principal.account_id, principal.user_id)
    if not preference:
        return DefaultAgentPreferenceResponse()

    return DefaultAgentPreferenceResponse(agent_id=preference.agent_id, updated_at=preference.updated_at)


@router.put("/default-agent", response_model=DefaultAgentPreferenceResponse)
async def set_default_agent(
    body: SetDefaultAgentRequest,
    repo: Annotated[DefaultAgentPreferenceRepository, Depends(get_default_agent_preference_repository)],
    principal: Annotated[Principal, Depends(get_principal)],
) -> DefaultAgentPreferenceResponse:
    """Set the user's default agent: one they may chat with, their own or shared with them."""
    require_agent(principal, body.agent_id, "agents:Chat", agent_repository)

    saved = repo.save(DefaultAgentPreference(account_id=principal.account_id, user_id=principal.user_id,
                                             agent_id=body.agent_id))

    return DefaultAgentPreferenceResponse(agent_id=saved.agent_id, updated_at=saved.updated_at)


@router.delete("/default-agent", status_code=status.HTTP_204_NO_CONTENT)
async def clear_default_agent(
    principal: Annotated[Principal, Depends(get_principal)],
    repo: Annotated[DefaultAgentPreferenceRepository, Depends(get_default_agent_preference_repository)],
) -> None:
    """Clear the member's default-agent preference."""
    repo.delete(principal.account_id, principal.user_id)
