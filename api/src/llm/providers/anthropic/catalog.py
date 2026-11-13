"""The models an Anthropic API key can use."""

from __future__ import annotations

from typing import Any

import anthropic

from src.llm.models import ModelInfo, chat_capabilities
from src.llm.providers.provider import stored_credentials
from src.settings.models import ProviderSettings


class AnthropicCatalog:
    def list_models(self, provider_settings: ProviderSettings) -> list[ModelInfo]:
        client = anthropic.Anthropic(api_key=stored_credentials(provider_settings)["api_key"])
        return [
            ModelInfo(
                model_id=model.id,
                model_name=model.id,
                display_name=f"[Anthropic] {model.display_name}",
                provider="anthropic",
                capabilities=chat_capabilities(reads_images=reads_images(model)),
            )
            for model in client.models.list()
        ]


def reads_images(model: Any) -> bool:
    """`GET /v1/models` reports `capabilities.image_input.supported`; it can be null, and then every Claude 3+ model
    reads."""
    supported = getattr(getattr(getattr(model, "capabilities", None), "image_input", None), "supported", None)
    return bool(supported) if supported is not None else str(model.id).startswith("claude-")
