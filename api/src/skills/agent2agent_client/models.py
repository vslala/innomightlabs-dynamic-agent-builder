from __future__ import annotations

from enum import Enum
from typing import Annotated, Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field, StringConstraints, field_validator, model_validator

MAX_DISCOVERY_LIMIT = 10


class A2AAuthResult(str, Enum):
    READY = "ready"
    REQUIRED = "auth_required"
    UNSUPPORTED = "unsupported_auth"


class A2ASkillSummary(BaseModel):
    id: str
    name: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)


class A2AAgentCardView(BaseModel):
    protocol_version: str = Field(alias="protocolVersion")
    name: str
    description: str = ""
    url: str
    security_schemes: dict[str, dict[str, Any]] = Field(default_factory=dict, alias="securitySchemes")
    security: list[dict[str, list[str]]] = Field(default_factory=list)
    skills: list[A2ASkillSummary] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class A2ARegistryConfig(BaseModel):
    registry_set_name: str
    registry_urls: list[str]
    default_credentials: dict[str, str] = Field(default_factory=dict)

    @classmethod
    def from_runtime_config(cls, config: dict[str, Any]) -> "A2ARegistryConfig":
        return cls(
            registry_set_name=str(config.get("registry_set_name") or "A2A Registry").strip(),
            registry_urls=_parse_registry_urls(config.get("registry_urls")),
            default_credentials=_parse_credentials(config.get("default_credentials")),
        )

    @field_validator("registry_urls")
    @classmethod
    def validate_registry_urls(cls, value: list[str]) -> list[str]:
        urls = [_normalize_url(item) for item in value if str(item).strip()]
        if not urls:
            raise ValueError("At least one Agent2Agent discovery URL is required")
        return list(dict.fromkeys(urls))


class DiscoverAgentsRequest(BaseModel):
    keyword: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    limit: int = MAX_DISCOVERY_LIMIT
    cursor: str | None = None
    include_cards: bool = False

    @model_validator(mode="after")
    def clamp_limit(self) -> "DiscoverAgentsRequest":
        self.limit = max(1, min(MAX_DISCOVERY_LIMIT, int(self.limit or MAX_DISCOVERY_LIMIT)))
        return self


class DiscoveredAgent(BaseModel):
    agent_ref: str
    registry_url: str
    card_url: str | None = None
    service_url: str
    name: str
    description: str | None = None
    skills: list[A2ASkillSummary] = Field(default_factory=list)
    auth: A2AAuthResult = A2AAuthResult.READY


class DiscoverAgentsResponse(BaseModel):
    keyword: str
    items: list[DiscoveredAgent]
    next_cursor: str | None = None
    searched_registries: list[str]


class GetAgentCardRequest(BaseModel):
    agent_ref: str


class SendMessageRequest(BaseModel):
    agent_ref: str
    message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=32000)]
    context_id: str | None = None
    task_id: str | None = None
    timeout_seconds: int = 60
    max_response_chars: int = 12000

    @model_validator(mode="after")
    def clamp_bounds(self) -> "SendMessageRequest":
        self.timeout_seconds = max(5, min(120, int(self.timeout_seconds or 60)))
        self.max_response_chars = max(1000, min(50000, int(self.max_response_chars or 12000)))
        return self


class SendMessageResponse(BaseModel):
    ok: bool
    auth_required: bool = False
    unsupported_auth: bool = False
    message: str | None = None
    task: dict[str, Any] | None = None
    response_text: str | None = None
    status_code: int | None = None
    service_url: str | None = None
    agent_name: str | None = None


class AgentRef(BaseModel):
    registry_url: str
    service_url: str
    card_url: str | None = None
    name: str


class RegistryAgentCandidate(BaseModel):
    registry_url: str
    service_url: str
    card_url: str | None = None
    name: str
    description: str | None = None
    skills: list[A2ASkillSummary] = Field(default_factory=list)
    card: A2AAgentCardView | None = None


def _parse_registry_urls(raw: Any) -> list[str]:
    if isinstance(raw, str):
        return [line.strip() for line in raw.replace(",", "\n").splitlines() if line.strip()]
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    return []


def _parse_credentials(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    credentials: dict[str, str] = {}
    for key, value in raw.items():
        secret = str(value).strip()
        if not str(key).strip() or not secret:
            continue
        credentials[_normalize_url(str(key))] = secret
    return credentials


def _normalize_url(raw: str) -> str:
    value = raw.strip().rstrip("/")
    if not value:
        return ""
    if not value.startswith(("http://", "https://")):
        value = f"https://{value}"
    _validate_url(value)
    return value


def _validate_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"Invalid Agent2Agent URL: {url}")
