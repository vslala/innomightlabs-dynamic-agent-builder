from __future__ import annotations

import os
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


def expand_env_placeholders(value: Any) -> Any:
    if isinstance(value, str):
        return PLACEHOLDER_RE.sub(_environment_value, value)
    if isinstance(value, list):
        return [expand_env_placeholders(item) for item in value]
    if isinstance(value, dict):
        return {key: expand_env_placeholders(item) for key, item in value.items()}
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


def _environment_value(match: re.Match[str]) -> str:
    name = match.group(1)
    if name not in os.environ:
        raise ValueError(f"Missing environment variable for REST Template placeholder: {name}")
    return os.environ[name]
