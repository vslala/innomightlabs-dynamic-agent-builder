"""The models an xAI key can use. xAI lists chat models and image models apart, and says what each takes in."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import httpx

from src.config import settings
from src.llm.models import ModelCapability, ModelInfo, chat_capabilities
from src.llm.providers.grok.chat import GROK_API_BASE_URL
from src.llm.providers.provider import stored_credentials
from src.settings.models import ProviderSettings

log = logging.getLogger(__name__)

CATALOG_TIMEOUT_SECONDS = 10


class GrokCatalog:
    def list_models(self, provider_settings: ProviderSettings) -> list[ModelInfo]:
        """Chat models (newest first), then image models. A listing that can't be read is replaced by the configured
        `GROK_MODELS` / `GROK_IMAGE_MODELS`, so both pickers always offer something."""
        api_key = stored_credentials(provider_settings).get("api_key", "")
        chat = _listing("language-models", api_key) or [
            {"id": slug, "input_modalities": ["text", "image"]} for slug in settings.grok_models
        ]
        drawing = _listing("image-generation-models", api_key) or [{"id": slug} for slug in settings.grok_image_models]
        return [
            *(_model(entry, chat_capabilities(reads_images=reads_images(entry))) for entry in _newest_first(chat)),
            *(_model(entry, [ModelCapability.IMAGE_GENERATION]) for entry in drawing),
        ]


def reads_images(entry: Mapping[str, Any]) -> bool:
    """`/v1/language-models` names each model's `input_modalities`."""
    return "image" in (entry.get("input_modalities") or [])


def _listing(path: str, api_key: str) -> list[dict[str, Any]]:
    try:
        response = httpx.get(
            f"{GROK_API_BASE_URL}/{path}",
            headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
            timeout=CATALOG_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as e:
        log.warning("Could not read xAI's %s, offering the configured models instead: %s", path, e)
        return []
    entries = payload.get("models", payload.get("data")) if isinstance(payload, dict) else None
    return [entry for entry in entries if isinstance(entry, dict) and entry.get("id")] if isinstance(entries, list) else []


def _newest_first(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(entries, key=_created, reverse=True)


def _created(entry: Mapping[str, Any]) -> int:
    created = entry.get("created")
    return created if isinstance(created, int) else 0


def _model(entry: Mapping[str, Any], capabilities: list[ModelCapability]) -> ModelInfo:
    slug = str(entry["id"])
    return ModelInfo(model_id=slug, model_name=slug, display_name=f"[Grok] {slug}", provider="grok", capabilities=capabilities)
