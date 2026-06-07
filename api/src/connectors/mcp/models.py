from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator


class MCPAuthType(str, Enum):
    API_KEY = "api_key"
    OAUTH = "oauth"


class MCPTransport(str, Enum):
    STREAMABLE_HTTP = "streamable_http"


class MCPAuthHeader(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    value: str = Field(min_length=1)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Header name is required")
        if any(ch.isspace() for ch in cleaned):
            raise ValueError("Header name cannot contain whitespace")
        return cleaned

    @field_validator("value")
    @classmethod
    def validate_value(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Header value is required")
        return cleaned


class MCPApiKeyAuthConfig(BaseModel):
    headers: list[MCPAuthHeader] = Field(min_length=1)

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_single_header(cls, value: Any) -> Any:
        if isinstance(value, dict) and "headers" not in value:
            header_name = value.get("header_name")
            header_value = value.get("header_value")
            if header_name is not None or header_value is not None:
                return {
                    **value,
                    "headers": [
                        {
                            "name": header_name or "Authorization",
                            "value": header_value,
                        }
                    ],
                }
        return value

    @model_validator(mode="after")
    def validate_unique_headers(self) -> "MCPApiKeyAuthConfig":
        seen: set[str] = set()
        for header in self.headers:
            key = header.name.lower()
            if key in seen:
                raise ValueError(f"Duplicate auth header: {header.name}")
            seen.add(key)
        return self


class MCPOAuthProviderConfig(BaseModel):
    authorization_url: HttpUrl
    token_url: HttpUrl
    client_id: str = Field(min_length=1)
    client_secret: str = ""
    scope: str = ""
    resource_url: str = ""

    @field_validator("client_id", "client_secret", "scope", "resource_url")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class MCPOAuthCredentials(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    expires_at: datetime
    token_type: str = "Bearer"
    scope: str = ""

    def is_expiring_soon(self, refresh_buffer_seconds: int = 60) -> bool:
        now = datetime.now(timezone.utc)
        return (self.expires_at - now).total_seconds() <= refresh_buffer_seconds


class MCPOAuthAuthConfig(BaseModel):
    provider: MCPOAuthProviderConfig
    credentials: Optional[MCPOAuthCredentials] = None


class MCPConnectionCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    server_url: HttpUrl
    auth_type: MCPAuthType = MCPAuthType.API_KEY
    api_key: Optional[MCPApiKeyAuthConfig] = None
    oauth: Optional[MCPOAuthProviderConfig] = None
    enabled: bool = True

    @model_validator(mode="after")
    def validate_auth_config(self) -> "MCPConnectionCreateRequest":
        if self.auth_type == MCPAuthType.API_KEY and self.api_key is None:
            raise ValueError("api_key is required for API key MCP authentication")
        if self.auth_type == MCPAuthType.OAUTH and self.oauth is None:
            raise ValueError("oauth is required for OAuth MCP authentication")
        return self


class MCPConnectionUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    server_url: Optional[HttpUrl] = None
    auth_type: Optional[MCPAuthType] = None
    api_key: Optional[MCPApiKeyAuthConfig] = None
    oauth: Optional[MCPOAuthProviderConfig] = None
    enabled: Optional[bool] = None

    @model_validator(mode="after")
    def validate_not_empty(self) -> "MCPConnectionUpdateRequest":
        if (
            self.name is None
            and self.server_url is None
            and self.auth_type is None
            and self.api_key is None
            and self.oauth is None
            and self.enabled is None
        ):
            raise ValueError("At least one field must be provided")
        return self


class MCPConnectionResponse(BaseModel):
    mcp_id: str
    name: str
    server_url: str
    transport: MCPTransport
    auth_type: MCPAuthType
    oauth_connected: bool = False
    enabled: bool
    created_at: datetime
    updated_at: Optional[datetime] = None


class MCPOAuthStartRequest(BaseModel):
    return_to: str = Field(min_length=1)


class MCPOAuthStartResponse(BaseModel):
    authorize_url: str


class MCPOAuthDiscoveryRequest(BaseModel):
    server_url: HttpUrl


class MCPOAuthDiscoveryResponse(BaseModel):
    authorization_url: str
    token_url: str
    client_id: str = ""
    client_secret: str = ""
    scope: str = ""
    resource_url: str
    authorization_server: str
    registration_endpoint: Optional[str] = None
    registered_client: bool = False


class AgentMCPConnectionResponse(BaseModel):
    agent_id: str
    mcp_id: str
    name: str
    server_url: str
    enabled: bool
    created_at: datetime
    updated_at: Optional[datetime] = None


class AgentMCPConnectionUpdateRequest(BaseModel):
    enabled: bool = True


class MCPToolListRequest(BaseModel):
    mcp_id: Optional[str] = None


class MCPToolCallRequest(BaseModel):
    mcp_id: str
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class MCPConnection(BaseModel):
    mcp_id: str = Field(default_factory=lambda: str(uuid4()))
    owner_email: str
    name: str
    server_url: str
    transport: MCPTransport = MCPTransport.STREAMABLE_HTTP
    auth_type: MCPAuthType = MCPAuthType.API_KEY
    encrypted_auth_config: str
    enabled: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None

    @property
    def pk(self) -> str:
        return f"User#{self.owner_email}"

    @property
    def sk(self) -> str:
        return f"MCPConnection#{self.mcp_id}"

    def to_dynamo_item(self) -> dict[str, Any]:
        return {
            "pk": self.pk,
            "sk": self.sk,
            "entity_type": "MCPConnection",
            "mcp_id": self.mcp_id,
            "owner_email": self.owner_email,
            "name": self.name,
            "server_url": self.server_url,
            "transport": self.transport.value,
            "auth_type": self.auth_type.value,
            "encrypted_auth_config": self.encrypted_auth_config,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "MCPConnection":
        return cls(
            mcp_id=item["mcp_id"],
            owner_email=item["owner_email"],
            name=item["name"],
            server_url=item["server_url"],
            transport=MCPTransport(item.get("transport", MCPTransport.STREAMABLE_HTTP.value)),
            auth_type=MCPAuthType(item.get("auth_type", MCPAuthType.API_KEY.value)),
            encrypted_auth_config=item["encrypted_auth_config"],
            enabled=bool(item.get("enabled", True)),
            created_at=datetime.fromisoformat(item["created_at"]),
            updated_at=datetime.fromisoformat(item["updated_at"]) if item.get("updated_at") else None,
        )

    def to_response(self) -> MCPConnectionResponse:
        return MCPConnectionResponse(
            mcp_id=self.mcp_id,
            name=self.name,
            server_url=self.server_url,
            transport=self.transport,
            auth_type=self.auth_type,
            enabled=self.enabled,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


class AgentMCPConnection(BaseModel):
    agent_id: str
    owner_email: str
    mcp_id: str
    enabled: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None

    @property
    def pk(self) -> str:
        return f"Agent#{self.agent_id}"

    @property
    def sk(self) -> str:
        return f"MCPConnection#{self.mcp_id}"

    def to_dynamo_item(self) -> dict[str, Any]:
        return {
            "pk": self.pk,
            "sk": self.sk,
            "entity_type": "AgentMCPConnection",
            "agent_id": self.agent_id,
            "owner_email": self.owner_email,
            "mcp_id": self.mcp_id,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "AgentMCPConnection":
        return cls(
            agent_id=item["agent_id"],
            owner_email=item["owner_email"],
            mcp_id=item["mcp_id"],
            enabled=bool(item.get("enabled", True)),
            created_at=datetime.fromisoformat(item["created_at"]),
            updated_at=datetime.fromisoformat(item["updated_at"]) if item.get("updated_at") else None,
        )
