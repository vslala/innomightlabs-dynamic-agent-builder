"""Connection details for a user-supplied Ollama endpoint.

Ollama is self-hosted, so unlike the hosted providers there is no fixed base
URL: each user configures their own `endpoint_url`, optionally behind a proxy
that requires a bearer token. Both the chat provider and model discovery need
the same parsing, validation, and header building, so it lives here.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from src.crypto import decrypt
from src.settings.models import ProviderSettings

#: Model discovery runs inside a form-rendering request, so it uses a short
#: timeout rather than the long one a streaming completion needs.
DISCOVERY_TIMEOUT_SECONDS = 10.0

ALLOWED_SCHEMES = ("http", "https")


@dataclass(frozen=True)
class OllamaConnection:
    """A validated Ollama endpoint plus its optional bearer credentials."""

    base_url: str
    api_key: str | None = None

    @classmethod
    def from_credentials(cls, credentials: Mapping[str, Any]) -> "OllamaConnection":
        """Build a connection from a decrypted provider-credentials dict."""
        endpoint_url = _clean_str(credentials.get("endpoint_url"))
        if not endpoint_url:
            raise ValueError("Missing required credential: 'endpoint_url'")

        parsed = urlparse(endpoint_url)
        if parsed.scheme not in ALLOWED_SCHEMES or not parsed.netloc:
            raise ValueError(
                "Ollama 'endpoint_url' must be an absolute http(s) URL, "
                f"for example http://localhost:11434 (received: {endpoint_url!r})"
            )

        return cls(base_url=endpoint_url.rstrip("/"), api_key=_clean_str(credentials.get("api_key")))

    @classmethod
    def from_provider_settings(cls, provider_settings: ProviderSettings) -> "OllamaConnection":
        """Build a connection by decrypting stored provider settings."""
        credentials = json.loads(decrypt(provider_settings.encrypted_credentials))
        if not isinstance(credentials, dict):
            raise ValueError("Ollama credentials must be a JSON object")
        return cls.from_credentials(credentials)

    @property
    def headers(self) -> dict[str, str]:
        """Request headers, carrying bearer auth only when a token is configured."""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers


def _clean_str(value: Any) -> str | None:
    return value.strip() or None if isinstance(value, str) else None


def merge_thinking_override(credentials: Mapping[str, Any], *, thinking_mode: str | None) -> dict[str, Any]:
    """Merge a per-agent thinking-mode choice into decrypted Ollama credentials.

    Whether a reasoning model (qwen3, deepseek-r1, ...) spends tokens thinking
    is a per-agent product decision -- one agent may want fast answers, another
    quality reasoning -- not part of the shared connection credentials. It is
    merged in here, at call time, rather than stored on `ProviderSettings`.

    `thinking_mode` is the agent's raw stored choice: "enabled", "disabled", or
    anything else (including None/"default") for "don't send a `think` key at
    all, let the model use its own default".
    """
    if thinking_mode not in ("enabled", "disabled"):
        return dict(credentials)
    return {**credentials, "think": thinking_mode == "enabled"}
