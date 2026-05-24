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
class ImageModelCapability:
    """Image capability metadata attached to an agent-selected model."""

    provider: str
    model_id: str
    capabilities: frozenset[ImageCapability]
    backend: str = "codex_oauth"
    default_size: str = "auto"
    default_quality: str = "auto"
    output_format: str = "png"

    def as_strings(self) -> list[str]:
        return sorted(capability.value for capability in self.capabilities)


class ImageCapabilityRegistry:
    """Resolve image capabilities for provider/model pairs."""

    def __init__(self, entries: list[ImageModelCapability]):
        self._by_provider_model = {
            (entry.provider.lower(), entry.model_id): entry
            for entry in entries
        }

    def for_agent_model(
        self,
        provider: str,
        model_id: str | None,
    ) -> ImageModelCapability | None:
        if not model_id:
            return None
        return self._by_provider_model.get((provider.lower(), model_id))

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
    entries = [
        ImageModelCapability(
            provider="OpenAI",
            model_id=model,
            capabilities=frozenset({ImageCapability.GENERATION}),
            backend=settings.openai_image_generation_backend,
        )
        for model in settings.openai_image_generation_models
    ]
    return ImageCapabilityRegistry(entries)


image_capability_registry = build_image_capability_registry()
