from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from src.config import settings
from src.connectors.mcp.delivery import OAuthDelivery
from src.connectors.mcp.models import MCPAuthType, MCPOAuthProviderConfig, MCPTransport
from src.connectors.mcp.resolved import MCPTarget
from src.form_models import FormInput, FormInputType

OAUTH_CLIENT_ID_INPUT = "oauth_client_id"
OAUTH_CLIENT_SECRET_INPUT = "oauth_client_secret"


@dataclass(frozen=True)
class ProviderInstall:
    """One user's values for a preset."""

    inputs: dict[str, str]

    @property
    def oauth_client_id(self) -> str:
        return self.inputs.get(OAUTH_CLIENT_ID_INPUT, "")

    @property
    def oauth_client_secret(self) -> str:
        return self.inputs.get(OAUTH_CLIENT_SECRET_INPUT, "")


@dataclass(frozen=True)
class FixedOAuth:
    """Known endpoints. The config is built from the preset and the user's own client, never stored."""

    config: Callable[[ProviderInstall], MCPOAuthProviderConfig]
    delivery: OAuthDelivery


@dataclass(frozen=True)
class DiscoveredOAuth:
    """Endpoints from the MCP server's OAuth metadata, discovered once at install and stored with it.

    register_client=True: the client comes from dynamic client registration and is stored with the install.
    register_client=False: the server does not offer registration, so the preset asks for the user's own client.
    """

    server_url: str
    delivery: OAuthDelivery
    register_client: bool = True


@dataclass(frozen=True)
class MCPProvider:
    """A catalog preset: everything about one provider except the values only the user can supply."""

    key: str  # stable id; never rename after users install
    display_name: str
    description: str
    icon: str
    docs_url: str
    target: Callable[[ProviderInstall], MCPTarget]  # static credentials already applied
    inputs: tuple[FormInput, ...] = ()
    oauth: FixedOAuth | DiscoveredOAuth | None = None
    # Must match the target's type (checked by tests). Declared because listings need it before inputs exist.
    transport: MCPTransport = MCPTransport.STREAMABLE_HTTP

    def missing_inputs(self, values: dict[str, str]) -> list[str]:
        return [field.label for field in self.inputs if not field.is_optional and not values.get(field.name)]

    def secret_input_names(self) -> set[str]:
        return {field.name for field in self.inputs if field.input_type == FormInputType.PASSWORD}

    def input_names(self) -> set[str]:
        return {field.name for field in self.inputs}

    def auth_type(self) -> MCPAuthType:
        """Stored on installs so listings and the SPA's Connect button work without loading presets."""
        if self.oauth is not None:
            return MCPAuthType.OAUTH
        return MCPAuthType.API_KEY if self.secret_input_names() else MCPAuthType.NONE

    def validated_inputs(self, values: dict[str, str]) -> dict[str, str]:
        unknown = sorted(set(values) - self.input_names())
        if unknown:
            raise ValueError(f"Unknown {self.display_name} inputs: {', '.join(unknown)}")
        cleaned = {name: value.strip() for name, value in values.items() if value.strip()}
        for field in self.inputs:
            if field.options and field.name in cleaned:
                allowed = {option.value for option in field.options}
                if cleaned[field.name] not in allowed:
                    raise ValueError(f"{field.label} must be one of: {', '.join(sorted(allowed))}")
        missing = self.missing_inputs(cleaned)
        if missing:
            raise ValueError(f"{self.display_name} needs: {', '.join(missing)}")
        return cleaned


def oauth_client_inputs(where: str) -> tuple[FormInput, ...]:
    """The user's own OAuth client, with the redirect URI they must register shown as help text."""
    help_text = f"Create an OAuth client in {where} with the redirect URI {settings.mcp_oauth_redirect_uri}"
    return (
        FormInput(
            input_type=FormInputType.TEXT,
            name=OAUTH_CLIENT_ID_INPUT,
            label="OAuth client ID",
            attr={"help_text": help_text},
        ),
        FormInput(
            input_type=FormInputType.PASSWORD,
            name=OAUTH_CLIENT_SECRET_INPUT,
            label="OAuth client secret",
        ),
    )
