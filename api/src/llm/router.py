"""
LLM Router - endpoints for LLM-related operations.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.security import HTTPBearer

from src.llm.models import models_service, ModelInfo
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
    request: Request,
    provider: str,
    provider_settings_repo: ProviderSettingsRepository = Depends(get_provider_settings_repository),
) -> list[ModelInfo]:
    """
    Get available models for a provider.

    Currently supported providers:
    - bedrock: Amazon Bedrock (Claude models)

    Returns:
        List of available models with their IDs and display names
    """
    if provider.lower() == "bedrock":
        return models_service.get_bedrock_models()
    if provider.lower() == "openai":
        user_email = request.state.user_email
        provider_settings = provider_settings_repo.find_by_provider(user_email=user_email, provider_name="OpenAI")
        if not provider_settings:
            return []
        return models_service.get_openai_models()

    return []
