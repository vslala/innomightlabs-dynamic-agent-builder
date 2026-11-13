"""Every LLM provider, and finding one by name. Add a provider by adding its package and listing it here."""

from .anthropic import ANTHROPIC
from .bedrock import BEDROCK
from .gemini import GEMINI
from .ollama import OLLAMA
from .openai import OPENAI
from .openai_api import OPENAI_API
from .provider import Provider

#: In the order Settings and the model pickers show them.
PROVIDERS: tuple[Provider, ...] = (BEDROCK, ANTHROPIC, OPENAI, OPENAI_API, GEMINI, OLLAMA)


def find_provider(name: str) -> Provider | None:
    """Case-insensitive, because `/llm/models/{provider}` takes the name from a URL."""
    wanted = name.strip().lower()
    return next((candidate for candidate in PROVIDERS if candidate.name.lower() == wanted), None)


def provider(name: str) -> Provider:
    found = find_provider(name)
    if not found:
        raise ValueError(f"Unknown provider: '{name}'. Supported: {', '.join(p.name for p in PROVIDERS)}")
    return found


__all__ = ["PROVIDERS", "Provider", "find_provider", "provider"]
