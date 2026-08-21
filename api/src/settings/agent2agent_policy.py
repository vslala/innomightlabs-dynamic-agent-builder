from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator

from src.settings.models import Agent2AgentAllowedOrigin, Agent2AgentSettings
from src.settings.repository import (
    Agent2AgentSettingsRepository,
    get_agent2agent_settings_repository,
)


class Agent2AgentPolicyError(ValueError):
    pass


class Agent2AgentSettingsRequest(BaseModel):
    allowed_origins: dict[str, str] | list[str] | str = Field(default_factory=dict)

    @field_validator("allowed_origins")
    @classmethod
    def normalize_allowed_origins(cls, value: dict[str, str] | list[str] | str) -> dict[str, str]:
        return parse_allowed_origins(value)


def parse_allowed_origins(raw: Any) -> dict[str, str]:
    if isinstance(raw, dict):
        return _normalize_origin_map(raw)
    if isinstance(raw, list):
        return _normalize_origin_map({str(item): "" for item in raw})
    if isinstance(raw, str):
        lines = [line.strip() for line in raw.replace(",", "\n").splitlines()]
        return _normalize_origin_map({line: "" for line in lines if line})
    return {}


def normalize_origin(raw_url: str) -> str:
    value = raw_url.strip().rstrip("/")
    if not value:
        raise Agent2AgentPolicyError("Agent2Agent origin cannot be empty")
    if not value.startswith(("http://", "https://")):
        value = f"https://{value}"

    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise Agent2AgentPolicyError(f"Invalid Agent2Agent URL: {raw_url}")

    netloc = parsed.hostname.lower()
    try:
        port = parsed.port
    except ValueError as exc:
        raise Agent2AgentPolicyError(f"Invalid Agent2Agent URL: {raw_url}") from exc
    if port:
        netloc = f"{netloc}:{port}"
    return f"{parsed.scheme.lower()}://{netloc}"


def settings_to_response_map(settings: Agent2AgentSettings) -> dict[str, str]:
    return {
        item.origin: item.label or ""
        for item in settings.allowed_origins
    }


class Agent2AgentPolicy:
    def __init__(
        self,
        repository: Agent2AgentSettingsRepository | None = None,
    ) -> None:
        self.repository = repository or get_agent2agent_settings_repository()

    def settings_for_user(self, user_email: str) -> Agent2AgentSettings:
        return self.repository.find_by_user(user_email) or Agent2AgentSettings(user_email=user_email)

    def save_settings(
        self,
        *,
        user_email: str,
        request: Agent2AgentSettingsRequest,
    ) -> Agent2AgentSettings:
        settings = Agent2AgentSettings(
            user_email=user_email,
            allowed_origins=[
                Agent2AgentAllowedOrigin(origin=origin, label=label or None)
                for origin, label in request.allowed_origins.items()
            ],
        )
        return self.repository.save(settings)

    def validate_urls_for_user(self, *, user_email: str, urls: list[str]) -> None:
        settings = self.settings_for_user(user_email)
        allowed = {item.origin for item in settings.allowed_origins}
        if not allowed:
            raise Agent2AgentPolicyError(
                "No Agent2Agent allowed origins are configured. Add trusted origins in User Settings before installing or using this skill."
            )

        denied = [url for url in urls if normalize_origin(url) not in allowed]
        if denied:
            allowed_preview = ", ".join(sorted(allowed))
            raise Agent2AgentPolicyError(
                f"Agent2Agent URL is not allowlisted: {denied[0]}. Allowed origins: {allowed_preview}"
            )


def _normalize_origin_map(raw: dict[str, Any]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in raw.items():
        origin_source = str(key).strip()
        if not origin_source:
            continue
        origin = normalize_origin(origin_source)
        label = str(value).strip() if value is not None else ""
        normalized[origin] = label
    return normalized
