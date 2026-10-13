"""Which models can read images.

Each provider's model lister holds the raw catalog entry and asks the matching function here, then marks
the model `image_understanding`. Where the provider's API says (Anthropic, Bedrock, Codex, Ollama) we ask
it; OpenAI API keys and Gemini publish no per-model field, so the documented rule applies. See
docs/LLD-image-input-and-read-image-tool.md, section 3.13.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import httpx

from src.agents.image_generation.capabilities import ImageCapability
from src.config import settings
from src.llm.ollama import DISCOVERY_TIMEOUT_SECONDS, OllamaConnection

log = logging.getLogger(__name__)

#: How long one Ollama model's answer is reused: pulling a model is rare, and `/api/show` is one call each.
OLLAMA_CAPABILITY_TTL_SECONDS = 3600
#: Models asked about at once, so a long `/api/tags` list doesn't stall the settings form.
OLLAMA_SHOW_CONCURRENCY = 4

#: Gemini model ids that are not chat models, whatever their prefix.
GEMINI_NON_CHAT_MARKERS = ("embedding", "imagen", "tts", "aqa")

_ollama_cache: dict[tuple[str, str], tuple[float, bool]] = {}


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


def ollama_reads_images(connection: OllamaConnection, tag: str) -> bool:
    """`POST /api/show` lists a model's `capabilities`, which include `vision` for image models."""
    key = (connection.base_url, tag)
    cached = _ollama_cache.get(key)
    if cached and cached[0] > time.monotonic():
        return cached[1]
    try:
        response = httpx.post(
            f"{connection.base_url}/api/show",
            json={"model": tag},
            headers=connection.headers,
            timeout=DISCOVERY_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        reads = "vision" in (response.json().get("capabilities") or [])
    except Exception as exc:
        # Not cached: a model that failed to answer may answer next time.
        log.warning("Could not read Ollama capabilities for %s: %s", tag, exc)
        return False
    _ollama_cache[key] = (time.monotonic() + OLLAMA_CAPABILITY_TTL_SECONDS, reads)
    return reads


def ollama_models_reading_images(connection: OllamaConnection, tags: list[str]) -> dict[str, bool]:
    with ThreadPoolExecutor(max_workers=OLLAMA_SHOW_CONCURRENCY) as pool:
        return dict(zip(tags, pool.map(lambda tag: ollama_reads_images(connection, tag), tags), strict=True))
