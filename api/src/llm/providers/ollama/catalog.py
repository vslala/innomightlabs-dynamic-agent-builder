"""The models pulled on an account's own Ollama host (`GET /api/tags`)."""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

from src.llm.models import ModelInfo, chat_capabilities
from src.llm.providers.ollama.connection import DISCOVERY_TIMEOUT_SECONDS, OllamaConnection
from src.settings.models import ProviderSettings

log = logging.getLogger(__name__)

#: How long one model's answer to "do you read images?" is reused: pulling a model is rare, and `/api/show` is one
#: call each.
CAPABILITY_TTL_SECONDS = 3600
#: Models asked about at once, so a long `/api/tags` list doesn't stall the settings form.
SHOW_CONCURRENCY = 4

#: (endpoint, tag) -> (expires at, reads images)
_reads_images_cache: dict[tuple[str, str], tuple[float, bool]] = {}


class OllamaCatalog:
    def list_models(self, provider_settings: ProviderSettings) -> list[ModelInfo]:
        """No fallback list: which models exist depends entirely on what the user has pulled, so an unreachable
        endpoint yields no models rather than tags that would fail at call time."""
        try:
            connection = OllamaConnection.from_provider_settings(provider_settings)
            response = httpx.get(
                f"{connection.base_url}/api/tags", headers=connection.headers, timeout=DISCOVERY_TIMEOUT_SECONDS
            )
            response.raise_for_status()
            models = response.json().get("models")
        except Exception as e:
            log.error("Error fetching Ollama models: %s", e, exc_info=True)
            return []

        if not isinstance(models, list):
            log.error("Ollama /api/tags returned an unexpected payload shape")
            return []

        tags = [tag for tag in (_tag(model) for model in models) if tag]
        reading = models_reading_images(connection, tags)
        return [
            ModelInfo(
                model_id=tag,
                model_name=tag,
                display_name=f"[Ollama] {tag}",
                provider="ollama",
                capabilities=chat_capabilities(reads_images=reading[tag]),
            )
            for tag in tags
        ]


def _tag(model: object) -> str | None:
    name = model.get("name") if isinstance(model, dict) else None
    return name.strip() or None if isinstance(name, str) else None


def models_reading_images(connection: OllamaConnection, tags: list[str]) -> dict[str, bool]:
    with ThreadPoolExecutor(max_workers=SHOW_CONCURRENCY) as pool:
        return dict(zip(tags, pool.map(lambda tag: reads_images(connection, tag), tags), strict=True))


def reads_images(connection: OllamaConnection, tag: str) -> bool:
    """`POST /api/show` lists a model's `capabilities`, which include `vision` for image models."""
    key = (connection.base_url, tag)
    cached = _reads_images_cache.get(key)
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
    _reads_images_cache[key] = (time.monotonic() + CAPABILITY_TTL_SECONDS, reads)
    return reads
