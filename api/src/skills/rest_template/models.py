from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field, model_validator

from src.skills.rest_template.helper import normalize_string_map

DEFAULT_TIMEOUT_SECONDS = 20
MIN_TIMEOUT_SECONDS = 1
MAX_TIMEOUT_SECONDS = 60
DEFAULT_MAX_RESPONSE_CHARS = 12000
MAX_RESPONSE_CHARS_LIMIT = 50000


class RestRequest(BaseModel):
    url: str
    headers: dict[str, Any] = Field(default_factory=dict)
    query: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    max_response_chars: int = DEFAULT_MAX_RESPONSE_CHARS
    include_full_response: bool = False

    @model_validator(mode="after")
    def normalize(self) -> "RestRequest":
        self.url = self.url.strip()
        parsed = urlparse(self.url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("url must be an absolute http or https URL")
        if parsed.username or parsed.password:
            raise ValueError("url must not include embedded username or password credentials")
        self.headers = normalize_string_map(self.headers, "headers")
        self.query = normalize_string_map(self.query, "query")
        self.timeout_seconds = max(MIN_TIMEOUT_SECONDS, min(MAX_TIMEOUT_SECONDS, int(self.timeout_seconds)))
        self.max_response_chars = max(1, min(MAX_RESPONSE_CHARS_LIMIT, int(self.max_response_chars)))
        return self


class RestPostRequest(RestRequest):
    json_body: Any | None = None
    text_body: str | None = None

    @model_validator(mode="after")
    def validate_body(self) -> "RestPostRequest":
        if isinstance(self.json_body, str):
            stripped = self.json_body.strip()
            self.json_body = json.loads(stripped) if stripped else None
        if self.json_body is not None and self.text_body:
            raise ValueError("Provide either json_body or text_body, not both")
        return self
