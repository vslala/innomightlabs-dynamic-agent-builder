"""Which models can read images.

Each provider's model lister holds the raw catalog entry and asks the matching function here, then marks
the model `image_understanding`. Where the provider's API says (Anthropic, Bedrock, Codex, Ollama) we ask
it (Ollama's `/api/show` check lives in its catalog, `src/llm/providers/ollama/catalog.py`); OpenAI API keys
and Gemini publish no per-model field, so the documented rule applies. See
docs/LLD-image-input-and-read-image-tool.md, section 3.13.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.agents.image_generation.capabilities import ImageCapability
from src.config import settings

#: Gemini model ids that are not chat models, whatever their prefix.
GEMINI_NON_CHAT_MARKERS = ("embedding", "imagen", "tts", "aqa")


def understanding(reads_images: bool) -> list[str]:
    """The `ModelInfo.capabilities` entry for a model that can (or cannot) read images."""
    return [ImageCapability.UNDERSTANDING.value] if reads_images else []


def anthropic_reads_images(model: Any) -> bool:
    """`GET /v1/models` reports `capabilities.image_input.supported`; it can be null, and then every Claude 3+ model reads."""
    supported = getattr(getattr(getattr(model, "capabilities", None), "image_input", None), "supported", None)
    return bool(supported) if supported is not None else str(model.id).startswith("claude-")


def bedrock_reads_images(summary: Mapping[str, Any]) -> bool:
    """`ListFoundationModels` names each model's `inputModalities` (TEXT, IMAGE, ...)."""
    return "IMAGE" in (summary.get("inputModalities") or [])


def codex_reads_images(entry: Mapping[str, Any]) -> bool:
    """The Codex catalog's `input_modalities`; Codex itself treats a missing field as text and image."""
    return "image" in (entry.get("input_modalities") or ["text", "image"])


def openai_api_reads_images(model_id: str) -> bool:
    """`/v1/models` has no modality field, so the vision families are matched by prefix (settings)."""
    return model_id.startswith(tuple(settings.openai_api_vision_model_prefixes))


def gemini_reads_images(model_id: str) -> bool:
    """Google documents every Gemini model version as multimodal."""
    return model_id.startswith("gemini-") and not any(marker in model_id for marker in GEMINI_NON_CHAT_MARKERS)
