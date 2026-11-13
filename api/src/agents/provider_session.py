"""Resolving the LLM provider an agent talks to.

Every architecture needs the same three things before it can stream: the
agent's provider settings, decrypted credentials, and a provider client. This
is that step, once.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from src.llm.credentials import load_provider_credentials
from src.llm.model_fallback import ModelFallbackProvider
from src.llm.providers import provider
from src.settings.repository import ProviderSettingsRepository
from src.exceptions import UserFacingError

if TYPE_CHECKING:
    from src.agents.models import Agent


class ProviderNotConfigured(UserFacingError):
    """The agent names a provider its account has not set up."""

    def __init__(self, provider_name: str):
        self.provider_name = provider_name
        super().__init__(
            f"Provider '{provider_name}' is not configured. "
            "An account admin can configure it in Settings > Provider Configuration."
        )


@dataclass(frozen=True)
class ProviderSession:
    """A provider client and the credentials to call it with."""

    provider: Any
    credentials: dict[str, Any]


async def open_provider_session(
    agent: "Agent",
    *,
    provider_settings_repo: ProviderSettingsRepository,
) -> ProviderSession:
    """The agent's account's provider, whoever owns the agent or talks to it. Raises ProviderNotConfigured if the
    account has no settings for the provider."""
    provider_settings = provider_settings_repo.find_by_provider(
        agent.account_id, agent.agent_provider
    )
    if not provider_settings:
        raise ProviderNotConfigured(agent.agent_provider)

    chosen = provider(agent.agent_provider)
    credentials = await load_provider_credentials(
        provider_name=chosen.name,
        provider_settings=provider_settings,
        provider_settings_repo=provider_settings_repo,
    )
    # Thinking mode is a knob only some providers have; the others never see it in their credentials.
    if chosen.apply_thinking:
        credentials = chosen.apply_thinking(credentials, agent.agent_ollama_thinking)

    return ProviderSession(provider=ModelFallbackProvider(chosen, provider_settings), credentials=credentials)
