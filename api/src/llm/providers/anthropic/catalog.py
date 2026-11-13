"""The models an Anthropic API key can use."""

from __future__ import annotations

import anthropic

from src.llm.models import ModelInfo
from src.llm.providers.provider import stored_credentials
from src.settings.models import ProviderSettings
from src.vision import capabilities as vision


class AnthropicCatalog:
    def list_models(self, provider_settings: ProviderSettings) -> list[ModelInfo]:
        client = anthropic.Anthropic(api_key=stored_credentials(provider_settings)["api_key"])
        return [
            ModelInfo(
                model_id=model.id,
                model_name=model.id,
                display_name=f"[Anthropic] {model.display_name}",
                provider="anthropic",
                capabilities=vision.understanding(vision.anthropic_reads_images(model)),
            )
            for model in client.models.list()
        ]
