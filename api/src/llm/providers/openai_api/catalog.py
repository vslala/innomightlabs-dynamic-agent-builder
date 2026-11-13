"""The chat models an OpenAI API key can use, newest first.

`GET /v1/models` returns every model the key can reach, embeddings and speech included, with no capability field, so
chat models are picked by name. When the list can't be read the configured `OPENAI_MODELS` are offered instead, so
the picker is never empty.
"""

from __future__ import annotations

import logging
import re

import httpx

from src.agents.image_generation.capabilities import image_capability_registry
from src.config import settings
from src.llm.models import ModelInfo
from src.llm.providers.openai_api.chat import OPENAI_API_BASE_URL
from src.llm.providers.provider import stored_credentials
from src.settings.models import ProviderSettings
from src.vision import capabilities as vision

log = logging.getLogger(__name__)

CATALOG_TIMEOUT_SECONDS = 10

#: Fragments of the model ids `GET /v1/models` lists that cannot hold an agent's chat: the Responses
#: API refuses audio, realtime, image, embedding, search and most codex models, and `-pro` models
#: think for minutes, past the stream timeout. Checked against the live API on 2026-10-10.
NON_CHAT_MARKERS = (
    "audio", "realtime", "transcribe", "tts", "image", "search", "embedding", "moderation",
    "instruct", "codex", "chat-latest", "live", "-pro",
)
#: Legacy models a funded account lists but the Responses API answers with `model_not_found`.
REFUSED_MODELS = frozenset({"gpt-4", "gpt-4-turbo"})
#: A chat family (`gpt-5.5`, `o4-mini`), not a dated snapshot of one (`gpt-4o-2024-08-06`, `gpt-3.5-turbo-0125`).
CHAT_MODEL = re.compile(r"^(gpt-|o\d)(?!.*-\d{4}(-\d{2}-\d{2})?$)")


class OpenAIAPICatalog:
    def list_models(self, provider_settings: ProviderSettings) -> list[ModelInfo]:
        try:
            response = httpx.get(
                f"{OPENAI_API_BASE_URL}/models",
                headers={
                    "Authorization": f"Bearer {stored_credentials(provider_settings)['api_key']}",
                    "Accept": "application/json",
                },
                timeout=CATALOG_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            entries = response.json().get("data")
            if not isinstance(entries, list):
                raise ValueError("OpenAI /v1/models returned an unexpected payload shape")
        except Exception as e:
            log.warning("Falling back to configured OpenAI API models: %s", e)
            entries = []

        listed = sorted(
            (entry for entry in entries if is_chat_model(entry)),
            key=lambda entry: entry.get("created") if isinstance(entry.get("created"), int) else 0,
            reverse=True,
        )
        slugs = [str(entry["id"]) for entry in listed] or [slug.strip() for slug in settings.openai_models if slug.strip()]
        return [
            ModelInfo(
                model_id=slug,
                model_name=slug,
                display_name=f"[OpenAI API] {slug}",
                provider="openai_api",
                capabilities=[
                    *image_capability_registry.capabilities_for("OpenAIAPI", slug),
                    *vision.understanding(vision.openai_api_reads_images(slug)),
                ],
            )
            for slug in slugs
        ]


def is_chat_model(entry: object) -> bool:
    model_id = entry.get("id") if isinstance(entry, dict) else None
    return (
        isinstance(model_id, str)
        and bool(CHAT_MODEL.match(model_id))
        and model_id not in REFUSED_MODELS
        and not any(marker in model_id for marker in NON_CHAT_MARKERS)
    )
