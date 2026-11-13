"""The models a ChatGPT sign-in can use: the Codex backend's own catalog (`GET …/codex/models`, the one the Codex CLI
reads), since that is the backend this provider chats with."""

from __future__ import annotations

import logging
import time
from typing import Any, Mapping

import httpx

from src.agents.image_generation.capabilities import image_capability_registry
from src.auth.openai_oauth import credentials_from_provider_settings, extract_account_id_from_access_token
from src.config import settings
from src.llm.models import ModelInfo
from src.llm.providers.openai.credentials import load_openai_credentials_blocking
from src.settings.models import ProviderSettings
from src.settings.repository import get_provider_settings_repository
from src.vision import capabilities as vision

log = logging.getLogger(__name__)

#: How long one account's catalog is reused: it changes when OpenAI ships a model, not per request.
CATALOG_TTL_SECONDS = 3600
CATALOG_TIMEOUT_SECONDS = 10


class OpenAICatalog:
    def __init__(self) -> None:
        #: account id -> (expires at, models)
        self._cache: dict[str, tuple[float, list[ModelInfo]]] = {}

    def list_models(self, provider_settings: ProviderSettings) -> list[ModelInfo]:
        """Models the catalog lists and marks usable over the API, in its own priority order. When it can't be read
        (an expired token, an outage, a new payload shape) the configured `OPENAI_MODELS` are offered instead, so the
        picker is never empty."""
        try:
            catalog = self._catalog(provider_settings)
        except Exception as e:
            log.warning("Could not read the OpenAI model catalog, offering the configured models instead: %s", e)
            catalog = []
        return catalog or [openai_model(slug.strip()) for slug in settings.openai_models if slug and slug.strip()]

    def _catalog(self, provider_settings: ProviderSettings) -> list[ModelInfo]:
        # The stored token may be expired, but it names the account well enough to find its cached catalog.
        stored = credentials_from_provider_settings(provider_settings)
        cache_key = (
            stored.account_id or extract_account_id_from_access_token(stored.access_token) or provider_settings.account_id
        )
        cached = self._cache.get(cache_key)
        if cached and cached[0] > time.monotonic():
            return cached[1]

        credentials = load_openai_credentials_blocking(provider_settings, get_provider_settings_repository())
        account_id = credentials.account_id or extract_account_id_from_access_token(credentials.access_token)
        headers = {"Authorization": f"Bearer {credentials.access_token}", "Accept": "application/json"}
        if account_id:
            headers["ChatGPT-Account-ID"] = account_id
        if settings.openai_oauth_originator:
            headers["originator"] = settings.openai_oauth_originator
        response = httpx.get(
            settings.openai_oauth_responses_url.rsplit("/", 1)[0] + "/models",
            params={"client_version": settings.openai_codex_client_version},
            headers=headers,
            timeout=CATALOG_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        entries = response.json().get("models")
        if not isinstance(entries, list):
            raise ValueError("Codex model catalog returned an unexpected payload shape")

        models = [
            openai_model(str(entry["slug"]), entry.get("display_name"), vision.codex_reads_images(entry))
            for entry in sorted(
                (entry for entry in entries if _is_listed(entry)),
                key=lambda entry: entry.get("priority") if isinstance(entry.get("priority"), int) else 1_000,
            )
        ]
        if models:
            self._cache[cache_key] = (time.monotonic() + CATALOG_TTL_SECONDS, models)
        return models


def openai_model(slug: str, display_name: Any = None, reads_images: bool = True) -> ModelInfo:
    return ModelInfo(
        model_id=slug,
        model_name=slug,
        display_name=f"[OpenAI] {display_name if isinstance(display_name, str) and display_name else slug}",
        provider="openai",
        capabilities=[
            *image_capability_registry.capabilities_for("OpenAI", slug),
            *vision.understanding(reads_images),
        ],
    )


def _is_listed(entry: object) -> bool:
    """A catalog entry the Codex model picker would show: named, listed, and usable over the API."""
    return (
        isinstance(entry, Mapping)
        and isinstance(entry.get("slug"), str)
        and bool(entry["slug"].strip())
        and entry.get("visibility") == "list"
        and entry.get("supported_in_api") is not False
    )
