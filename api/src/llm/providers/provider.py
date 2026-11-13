"""What one LLM provider offers an account: chat, a model catalog, a settings form and how its credentials load.

Each provider package (`providers/<name>/__init__.py`) builds one `Provider`; `PROVIDERS` lists them all. Everything
that differs by provider is a field here, so no code outside the provider packages names a provider.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from src.crypto import decrypt
from src.form_models import Form
from src.settings.models import ProviderSettings

from src.llm.chat import LLMProvider

if TYPE_CHECKING:
    from src.llm.images import ImageGenerator
    from src.llm.models import ModelInfo
    from src.settings.repository import ProviderSettingsRepository


class ModelCatalog(Protocol):
    """The models an account's credentials can use, as the provider describes them."""

    def list_models(self, provider_settings: ProviderSettings) -> list[ModelInfo]:
        """Blocking HTTP. A vendor outage is not an error: fall back to a configured list (or none, where nothing
        sensible exists), so a form that offers models still renders."""
        ...


class CredentialSource(Protocol):
    """How a provider's stored credentials become the dict its chat client and catalog are given."""

    async def load(
        self, provider_settings: ProviderSettings, provider_settings_repo: ProviderSettingsRepository
    ) -> dict[str, Any]: ...


def stored_credentials(provider_settings: ProviderSettings) -> dict[str, Any]:
    """The credentials an admin saved in Settings, decrypted."""
    credentials = json.loads(decrypt(provider_settings.encrypted_credentials))
    if not isinstance(credentials, dict):
        raise ValueError(f"Provider '{provider_settings.provider_name}' credentials must be a JSON object")
    return credentials


class StoredCredentials:
    """Credentials used as saved: an API key, an endpoint. Every provider but a signed-in one."""

    async def load(
        self, provider_settings: ProviderSettings, provider_settings_repo: ProviderSettingsRepository
    ) -> dict[str, Any]:
        return stored_credentials(provider_settings)


@dataclass(frozen=True)
class OAuthSignIn:
    """A provider an admin signs into instead of pasting a key. The Settings page renders it as is: a button that
    opens `start_path`'s authorize URL, the steps, then the form, whose `submit_path` takes the pasted callback."""

    start_path: str
    button_label: str
    guide: str
    submit_label: str = "Complete Connection"


def _never_refuses(exc: Exception) -> bool:
    return False


@dataclass(frozen=True)
class Provider:
    """One LLM provider. `name` is stored on agents (`agent_provider`), on `ProviderSettings` and on the account's
    model settings, so it never changes."""

    name: str
    #: What Settings calls it ("OpenAI (API key)")
    title: str
    settings_form: Form
    chat: LLMProvider
    catalog: ModelCatalog
    #: None: an API-key form, saved through `/settings/providers/{name}`.
    oauth: OAuthSignIn | None = None
    credentials: CredentialSource = StoredCredentials()
    #: True when the vendor's error means "this model isn't available to you", so ModelFallbackProvider retries.
    refuses_model: Callable[[Exception], bool] = _never_refuses
    #: How this provider draws, if it can (the account's Image Generation setting picks the model).
    images: ImageGenerator | None = None
    #: Applies an agent's thinking mode to a call's credentials, for providers that have the knob.
    apply_thinking: Callable[[dict[str, Any], str | None], dict[str, Any]] | None = None
