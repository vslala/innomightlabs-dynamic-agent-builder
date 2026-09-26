from __future__ import annotations

import json
from typing import Literal, Optional

from pydantic import BaseModel, Field

from src.connectors.mcp.models import (
    MCPConnection,
    MCPOAuthAuthConfig,
    MCPOAuthCredentials,
    MCPOAuthProviderConfig,
)
from src.connectors.mcp.providers import get_provider
from src.connectors.mcp.providers.base import DiscoveredOAuth, FixedOAuth, MCPProvider, ProviderInstall
from src.connectors.mcp.resolved import OAuthBinding, ResolvedConnection
from src.crypto import decrypt, encrypt

SetupState = Literal["needs_input", "needs_sign_in", "ready"]


class ProviderInstallSecrets(BaseModel):
    """What an install stores: only what cannot be derived from its preset."""

    inputs: dict[str, str] = Field(default_factory=dict)
    # DiscoveredOAuth only: endpoints found at install, plus the registered client when the server offers DCR.
    oauth_provider: Optional[MCPOAuthProviderConfig] = None
    oauth_credentials: Optional[MCPOAuthCredentials] = None

    def encrypted(self) -> str:
        return encrypt(self.model_dump_json())

    @classmethod
    def of(cls, connection: MCPConnection) -> "ProviderInstallSecrets":
        return cls.model_validate(json.loads(decrypt(connection.encrypted_auth_config)))


class ProviderResolver:
    """Catalog installs: a preset plus the user's stored values."""

    def resolve(self, connection: MCPConnection) -> ResolvedConnection:
        provider = get_provider(connection.provider_key)
        secrets = ProviderInstallSecrets.of(connection)
        missing = provider.missing_inputs(secrets.inputs)
        if missing:
            raise ValueError(f"{provider.display_name} needs setup: {', '.join(missing)}")

        target = provider.target(ProviderInstall(inputs=secrets.inputs))
        if provider.oauth is None:
            return ResolvedConnection(target=target)
        return ResolvedConnection(
            target=target,
            oauth=OAuthBinding(
                auth=MCPOAuthAuthConfig(
                    provider=self._oauth_config(provider, secrets),
                    credentials=secrets.oauth_credentials,
                ),
                delivery=provider.oauth.delivery,
            ),
        )

    def store_oauth_credentials(self, connection: MCPConnection, credentials: MCPOAuthCredentials) -> str:
        secrets = ProviderInstallSecrets.of(connection)
        return secrets.model_copy(update={"oauth_credentials": credentials}).encrypted()

    def setup_state(self, connection: MCPConnection) -> SetupState:
        provider = get_provider(connection.provider_key)
        secrets = ProviderInstallSecrets.of(connection)
        if provider.missing_inputs(secrets.inputs):
            return "needs_input"
        if provider.oauth is not None and secrets.oauth_credentials is None:
            return "needs_sign_in"
        return "ready"

    def _oauth_config(self, provider: MCPProvider, secrets: ProviderInstallSecrets) -> MCPOAuthProviderConfig:
        install = ProviderInstall(inputs=secrets.inputs)
        if isinstance(provider.oauth, FixedOAuth):
            return provider.oauth.config(install)

        assert isinstance(provider.oauth, DiscoveredOAuth)
        if secrets.oauth_provider is None:
            raise ValueError(f"{provider.display_name} sign-in was not discovered. Reinstall the connector.")
        if provider.oauth.register_client:
            return secrets.oauth_provider
        # The server has no dynamic registration: discovered endpoints plus the user's own client.
        return secrets.oauth_provider.model_copy(
            update={"client_id": install.oauth_client_id, "client_secret": install.oauth_client_secret}
        )
