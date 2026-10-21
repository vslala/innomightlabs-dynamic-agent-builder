"""Image generation capability registry for agent-selected models."""

from dataclasses import dataclass
from enum import StrEnum

from src.config import settings


class ImageCapability(StrEnum):
    """Image capabilities understood by the agent image-generation subdomain."""

    GENERATION = "image_generation"
    UNDERSTANDING = "image_understanding"
    EDITING = "image_editing"


@dataclass(frozen=True)
class ImageProviderCapability:
    """What a provider's models can do with images. It is per provider, not per model: the model only drives the
    request and the provider's image tool draws the picture, so every model the provider offers (and every one it adds
    later) can generate. A model that can't fails at the call with the provider's own error."""

    provider: str
    capabilities: frozenset[ImageCapability]
    backend: str = "codex_oauth"
    default_size: str = "auto"
    default_quality: str = "auto"
    output_format: str = "png"

    def as_strings(self) -> list[str]:
        return sorted(capability.value for capability in self.capabilities)


class ImageCapabilityRegistry:
    """Resolve image capabilities for an agent's provider and model."""

    def __init__(self, entries: list[ImageProviderCapability]):
        self._by_provider = {entry.provider.lower(): entry for entry in entries}

    def for_agent_model(
        self,
        provider: str,
        model_id: str | None,
    ) -> ImageProviderCapability | None:
        if not model_id:
            return None
        return self._by_provider.get(provider.lower())

    def supports(
        self,
        provider: str,
        model_id: str | None,
        capability: ImageCapability,
    ) -> bool:
        entry = self.for_agent_model(provider, model_id)
        return bool(entry and capability in entry.capabilities)

    def capabilities_for(self, provider: str, model_id: str | None) -> list[str]:
        entry = self.for_agent_model(provider, model_id)
        return entry.as_strings() if entry else []


def build_image_capability_registry() -> ImageCapabilityRegistry:
    return ImageCapabilityRegistry([
        ImageProviderCapability(
            provider="OpenAI",
            capabilities=frozenset({ImageCapability.GENERATION}),
            backend=settings.openai_image_generation_backend,
        )
    ])


image_capability_registry = build_image_capability_registry()
