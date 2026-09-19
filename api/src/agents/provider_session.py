"""Resolving the LLM provider an agent talks to.

Every architecture needs the same three things before it can stream: the
agent's provider settings, decrypted credentials, and a provider client. This
is that step, once.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from src.llm.credentials import load_provider_credentials
from src.llm.ollama import merge_thinking_override
from src.llm.providers import get_llm_provider
from src.settings.repository import ProviderSettingsRepository

if TYPE_CHECKING:
    from src.agents.models import Agent


class ProviderNotConfigured(Exception):
    """The agent names a provider the owner has not set up."""

    def __init__(self, provider_name: str):
        self.provider_name = provider_name
        super().__init__(
            f"Provider '{provider_name}' is not configured. "
            "Please configure it in Settings > Provider Configuration."
        )


@dataclass(frozen=True)
class ProviderSession:
    """A provider client and the credentials to call it with."""

    provider: Any
    credentials: dict[str, Any]


async def open_provider_session(
    agent: "Agent",
    *,
    owner_email: str,
    provider_settings_repo: ProviderSettingsRepository,
) -> ProviderSession:
    """Raises ProviderNotConfigured if the owner has no settings for the provider."""
    provider_settings = provider_settings_repo.find_by_provider(
        owner_email, agent.agent_provider
    )
    if not provider_settings:
        raise ProviderNotConfigured(agent.agent_provider)

    credentials = await load_provider_credentials(
        provider_name=agent.agent_provider,
        provider_settings=provider_settings,
        provider_settings_repo=provider_settings_repo,
    )
    # Reasoning-model thinking mode is an Ollama-only knob; every other
    # provider ignores it, so don't put it in their credentials at all.
    if agent.agent_provider == "Ollama":
        credentials = merge_thinking_override(
            credentials, thinking_mode=agent.agent_ollama_thinking
        )

    return ProviderSession(
        provider=get_llm_provider(agent.agent_provider),
        credentials=credentials,
    )
