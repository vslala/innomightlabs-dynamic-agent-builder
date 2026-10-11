"""
LLM Router - endpoints for LLM-related operations.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.security import HTTPBearer

from src.iam.dependencies import get_principal
from src.iam.principal import Principal
from src.llm.models import find_model_source, models_service, ModelInfo
from src.settings.repository import ProviderSettingsRepository, get_provider_settings_repository

# Security scheme for Swagger UI
security = HTTPBearer()

router = APIRouter(
    prefix="/llm",
    tags=["llm"],
    dependencies=[Depends(security)]
)


@router.get("/models/{provider}", response_model=list[ModelInfo])
async def get_available_models(
    provider: str,
    principal: Annotated[Principal, Depends(get_principal)],
    provider_settings_repo: ProviderSettingsRepository = Depends(get_provider_settings_repository),
) -> list[ModelInfo]:
    """
    Get available models for a provider.

    Bedrock is always available; every other provider requires the account to have
    configured it in Settings. An unknown or unconfigured provider returns an
    empty list rather than an error, so callers can probe safely.

    Returns:
        List of available models with their IDs and display names
    """
    if provider.lower() == "bedrock":
        return models_service.get_bedrock_models()

    source = find_model_source(provider)
    if not source:
        return []

    provider_settings = provider_settings_repo.find_by_provider(principal.account_id, source.provider_name)
    if not provider_settings:
        return []

    return source.load_models(provider_settings)
