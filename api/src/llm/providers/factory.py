"""
LLM Provider factory.

Returns the appropriate LLM provider based on the agent's provider configuration.
"""

from .base import LLMProvider
from .bedrock import BedrockProvider


def get_llm_provider(provider_name: str) -> LLMProvider:
    """
    Get an LLM provider instance by name.

    Args:
        provider_name: The name of the provider (e.g., "Bedrock", "OpenAI")

    Returns:
        An instance of the appropriate LLM provider

    Raises:
        ValueError: If the provider name is not supported
    """
    providers: dict[str, LLMProvider] = {
        "Bedrock": BedrockProvider(),
        # Future providers:
        # "OpenAI": OpenAIProvider(),
        # "Anthropic": AnthropicProvider(),
    }

    provider = providers.get(provider_name)
    if not provider:
        supported = ", ".join(providers.keys())
        raise ValueError(
            f"Unknown provider: '{provider_name}'. Supported providers: {supported}"
        )

    return provider
