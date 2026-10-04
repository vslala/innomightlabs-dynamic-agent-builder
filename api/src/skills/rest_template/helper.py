from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

PLACEHOLDER_RE = re.compile(r"{{\s*([A-Za-z_][A-Za-z0-9_]*)\s*}}")
REDACTED = "[redacted]"
SENSITIVE_HEADER_NAMES = {
    "authorization",
    "proxy-authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "api-key",
}


def normalize_string_map(value: Any, field_name: str) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be an object")
    return {
        str(raw_key).strip(): "" if raw_value is None else str(raw_value)
        for raw_key, raw_value in value.items()
        if str(raw_key).strip()
    }


class AgentSecrets:
    """The secrets the agent's owner configured on this install, for `{{ name }}` placeholders.

    The model writes the placeholders but never sees the values. Every value that went
    into a request is scrubbed from whatever comes back, so an endpoint that echoes its
    request cannot hand it to the model.
    """

    def __init__(self, secrets: dict[str, str]):
        self._secrets = secrets
        self.used: set[str] = set()

    def expand(self, value: Any) -> Any:
        if isinstance(value, str):
            return PLACEHOLDER_RE.sub(self._value_for, value)
        if isinstance(value, list):
            return [self.expand(item) for item in value]
        if isinstance(value, dict):
            return {key: self.expand(item) for key, item in value.items()}
        return value

    def scrub(self, value: Any) -> Any:
        if isinstance(value, str):
            for secret in sorted(self.used, key=len, reverse=True):
                value = value.replace(secret, REDACTED)
            return value
        if isinstance(value, list):
            return [self.scrub(item) for item in value]
        if isinstance(value, dict):
            return {key: self.scrub(item) for key, item in value.items()}
        return value

    def carried_by(self, header_value: str) -> bool:
        return any(secret in header_value for secret in self.used)

    def _value_for(self, match: re.Match[str]) -> str:
        name = match.group(1)
        value = self._secrets.get(name)
        if not value:
            raise ValueError(
                f"{{{{ {name} }}}} is not one of this skill's configured secrets. "
                "Secrets are set by the agent's owner in the skill settings."
            )
        self.used.add(value)
        return value


def body_preview(text: str, max_chars: int) -> tuple[str, bool]:
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars], True


def content_type(headers: httpx.Headers | dict[str, str]) -> str:
    return str(headers.get("content-type", "")).split(";", 1)[0].strip().lower()


def parse_body_json(response: httpx.Response, response_content_type: str) -> Any | None:
    if response_content_type != "application/json":
        return None
    try:
        return response.json()
    except ValueError:
        return None


def redact_headers(headers: httpx.Headers | dict[str, str]) -> dict[str, str]:
    return {
        key: REDACTED if key.lower() in SENSITIVE_HEADER_NAMES else value
        for key, value in dict(headers).items()
    }


def redact_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def compact_response(response: httpx.Response, preview: str) -> dict[str, Any]:
    return {
        "ok": response.is_success,
        "status_code": response.status_code,
        "body_preview": preview,
    }


def full_response(
    *,
    method: str,
    response: httpx.Response,
    preview: str,
    body_json: Any | None,
    truncated: bool,
    elapsed_ms: int,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": response.is_success,
        "method": method,
        "url": redact_url(str(response.url)),
        "status_code": response.status_code,
        "reason": response.reason_phrase,
        "headers": redact_headers(response.headers),
        "content_type": content_type(response.headers),
        "body_preview": preview,
        "truncated": truncated,
        "elapsed_ms": elapsed_ms,
    }
    if body_json is not None:
        payload["body_json"] = body_json
    return payload


def transport_error_response(message: str) -> dict[str, Any]:
    return {
        "ok": False,
        "status_code": None,
        "body_preview": "",
        "error": message,
    }

