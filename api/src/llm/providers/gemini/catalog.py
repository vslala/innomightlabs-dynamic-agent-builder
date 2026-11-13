"""The Gemini models an API key can chat with, and the image models it can draw with."""

from __future__ import annotations

import logging

from google import genai

from src.llm.models import ModelCapability, ModelInfo, chat_capabilities
from src.llm.providers.provider import stored_credentials
from src.settings.models import ProviderSettings

log = logging.getLogger(__name__)

#: Gemini model ids that are not chat models, whatever their prefix.
NON_CHAT_MARKERS = ("embedding", "imagen", "tts", "aqa")
#: Gemini's image models ("Nano Banana"), by name: `models.list` has no modality field, and they support the same
#: `generateContent` as the chat models. They draw (`GeminiImages`) and are not offered for chat. Checked against
#: aistudio.google.com/docs/image-generation on 2026-11-12 (`gemini-3-pro-image`, `gemini-3.1-flash-image`,
#: `gemini-2.5-flash-image`, `gemini-nano-banana-2.1`). Imagen is shut down.
IMAGE_MODEL_MARKERS = ("-image", "nano-banana")

#: Offered first, in this order; the rest follow alphabetically.
PREFERRED_MODELS = ("gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash")

FALLBACK_MODELS = (
    ModelInfo(
        model_id="gemini-2.5-flash",
        model_name="gemini-2.5-flash",
        display_name="[Gemini] Gemini 2.5 Flash",
        provider="gemini",
        capabilities=chat_capabilities(reads_images=True),
    ),
    ModelInfo(
        model_id="gemini-2.5-pro",
        model_name="gemini-2.5-pro",
        display_name="[Gemini] Gemini 2.5 Pro",
        provider="gemini",
        capabilities=chat_capabilities(reads_images=True),
    ),
    ModelInfo(
        model_id="gemini-2.5-flash-image",
        model_name="gemini-2.5-flash-image",
        display_name="[Gemini] Gemini 2.5 Flash Image",
        provider="gemini",
        capabilities=[ModelCapability.IMAGE_GENERATION],
    ),
)


class GeminiCatalog:
    def list_models(self, provider_settings: ProviderSettings) -> list[ModelInfo]:
        """Models that support `generateContent`, preferred ones first, or the fallback list when listing fails."""
        try:
            api_key = stored_credentials(provider_settings).get("api_key")
            if not api_key:
                raise ValueError("Missing required Gemini credential: 'api_key'")
            listed = genai.Client(api_key=api_key).models.list(config={"page_size": 1000, "query_base": True})
            models = [_model_info(model) for model in listed if _chats(model)]
        except Exception as e:
            log.error("Error fetching Gemini models: %s", e, exc_info=True)
            models = []
        return sorted(models, key=_preference) if models else list(FALLBACK_MODELS)


def _chats(model: object) -> bool:
    supported_actions = getattr(model, "supported_actions", None) or []
    return bool(_model_id(model)) and (not supported_actions or "generateContent" in supported_actions)


def _model_info(model: object) -> ModelInfo:
    model_id = _model_id(model)
    return ModelInfo(
        model_id=model_id,
        model_name=model_id,
        display_name=f"[Gemini] {getattr(model, 'display_name', None) or model_id}",
        provider="gemini",
        capabilities=(
            [ModelCapability.IMAGE_GENERATION]
            if is_image_model(model_id)
            else chat_capabilities(reads_images=reads_images(model_id))
        ),
    )


def _model_id(model: object) -> str:
    return str(getattr(model, "name", "") or "").removeprefix("models/").strip()


def _preference(model: ModelInfo) -> tuple[int, str]:
    rank = PREFERRED_MODELS.index(model.model_name) if model.model_name in PREFERRED_MODELS else len(PREFERRED_MODELS)
    return rank, model.model_name


def is_image_model(model_id: str) -> bool:
    return any(marker in model_id for marker in IMAGE_MODEL_MARKERS)


def reads_images(model_id: str) -> bool:
    """Google documents every Gemini model version as multimodal; the listing has no modality field."""
    return model_id.startswith("gemini-") and not any(marker in model_id for marker in NON_CHAT_MARKERS)
