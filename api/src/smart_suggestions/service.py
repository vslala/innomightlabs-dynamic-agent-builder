"""Service layer for smart suggestions."""

from __future__ import annotations

from src.llm.credentials import load_provider_credentials
from src.llm.providers import get_llm_provider
from src.settings.repository import ProviderSettingsRepository, get_provider_settings_repository
from src.smart_suggestions.models import SmartSuggestionRequest, SmartSuggestionResponse
from src.smart_suggestions.repository import (
    SmartSuggestionSettingsRepository,
    get_smart_suggestion_settings_repository,
)
from src.smart_suggestions.strategies import (
    SmartSuggestionError,
    SmartSuggestionStrategyRegistry,
)


class SmartSuggestionNotConfiguredError(ValueError):
    """Raised when a user has not configured smart suggestions."""


class SmartSuggestionService:
    def __init__(
        self,
        *,
        settings_repository: SmartSuggestionSettingsRepository | None = None,
        provider_settings_repository: ProviderSettingsRepository | None = None,
        strategy_registry: SmartSuggestionStrategyRegistry | None = None,
    ):
        self.settings_repository = settings_repository or get_smart_suggestion_settings_repository()
        self.provider_settings_repository = provider_settings_repository or get_provider_settings_repository()
        self.strategy_registry = strategy_registry or SmartSuggestionStrategyRegistry()

    async def suggest(
        self,
        *,
        user_email: str,
        request: SmartSuggestionRequest,
    ) -> SmartSuggestionResponse:
        settings = self.settings_repository.find_by_user(user_email)
        if not settings or not settings.enabled or not settings.provider_name or not settings.model_name:
            raise SmartSuggestionNotConfiguredError("Smart suggestions are not configured")

        provider_settings = self.provider_settings_repository.find_by_provider(
            user_email,
            settings.provider_name,
        )
        if not provider_settings:
            raise SmartSuggestionNotConfiguredError(
                f"Provider '{settings.provider_name}' is not configured"
            )

        strategy = self.strategy_registry.get(request.suggestion_type)
        credentials = await load_provider_credentials(
            provider_name=settings.provider_name,
            provider_settings=provider_settings,
            provider_settings_repo=self.provider_settings_repository,
        )
        provider = get_llm_provider(settings.provider_name)
        raw_response = ""
        async for event in provider.stream_response(
            strategy.build_messages(request),
            credentials,
            tools=None,
            model=settings.model_name,
        ):
            if event.type == "text":
                raw_response += event.content

        if not raw_response.strip():
            raise SmartSuggestionError("Model returned an empty smart suggestion")

        return strategy.parse_response(raw_response, request)


def get_smart_suggestion_service() -> SmartSuggestionService:
    return SmartSuggestionService()

