"""Generic HTTP executor.

This module provides a robust, safe-ish HTTP client that can be exposed to the LLM
as native tools (http_get/http_post/http_put/http_patch/http_delete) and later used
as an executor backend for declarative skill tool definitions.

Security model (MVP):
- Only http/https.
- Blocks obvious local/private targets (localhost, RFC1918, link-local, etc.) when URL host is an IP.
- Optional allowlist of hosts (exact or suffix) via settings.http_executor_allowed_hosts.
- Timeouts + response-size limits.

Note: This is not a full SSRF defense (DNS rebinding, etc.). For production, add
DNS resolution checks per request and egress network policies.
"""

from __future__ import annotations

import ipaddress
import json
from dataclasses import dataclass
from typing import Any, Mapping, Optional
from urllib.parse import urlencode, urlparse, urlunparse, parse_qsl

import httpx

from src.config import settings


SENSITIVE_HEADER_KEYS = {
    "authorization",
    "proxy-authorization",
    "x-api-key",
    "x-auth-token",
    "cookie",
    "set-cookie",
}


@dataclass
class HttpExecutorResult:
    ok: bool
    status_code: int
    url: str
    headers: dict[str, str]
    body_text: str
    truncated: bool

    def to_json(self) -> str:
        return json.dumps(
            {
                "ok": self.ok,
                "status_code": self.status_code,
                "url": self.url,
                "headers": self.headers,
                "body_text": self.body_text,
                "truncated": self.truncated,
            },
            ensure_ascii=False,
        )


class HttpExecutorError(Exception):
    """Raised for validation/execution errors in HttpExecutor."""

    pass


class HttpExecutor:
    def __init__(
        self,
        timeout_seconds: Optional[float] = None,
        max_response_bytes: Optional[int] = None,
        allowed_hosts: Optional[list[str]] = None,
        client: Optional[httpx.AsyncClient] = None,
    ):
        self.timeout_seconds = timeout_seconds if timeout_seconds is not None else getattr(settings, "http_executor_timeout_seconds", 10.0)
        self.max_response_bytes = max_response_bytes if max_response_bytes is not None else getattr(settings, "http_executor_max_response_bytes", 200_000)
        self.allowed_hosts = allowed_hosts if allowed_hosts is not None else getattr(settings, "http_executor_allowed_hosts", [])
        self._client = client

    def _validate_url(self, url: str) -> str:
        if not url or not isinstance(url, str):
            raise HttpExecutorError("url is required")

        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise HttpExecutorError("Only http/https URLs are allowed")

        if not parsed.hostname:
            raise HttpExecutorError("URL must include a hostname")

        host = parsed.hostname.strip().lower()

        allow_local = bool(getattr(settings, "http_executor_allow_local", False))

        # Basic host checks
        if not allow_local:
            if host in {"localhost"} or host.endswith(".localhost"):
                raise HttpExecutorError("Refusing to call localhost")
            if host.endswith(".local") or host.endswith(".internal"):
                raise HttpExecutorError("Refusing to call internal hostnames")

        # If host is an IP literal, block private/link-local/etc.
        try:
            ip = ipaddress.ip_address(host)
            if not allow_local:
                # In practice, only globally-routable IPs should be reachable.
                # If it's not global, treat it as unsafe.
                if not ip.is_global:
                    # Block cloud metadata IP explicitly (also not-global, but clearer message)
                    if str(ip) == "169.254.169.254":
                        raise HttpExecutorError("Refusing to call metadata service")
                    raise HttpExecutorError("Refusing to call non-global (private/local) IPs")
        except ValueError:
            # Not an IP literal
            pass

        # Optional allowlist
        if self.allowed_hosts:
            allowed = False
            for entry in self.allowed_hosts:
                e = entry.strip().lower()
                if not e:
                    continue
                if host == e:
                    allowed = True
                    break
                # suffix match: allow "*.example.com" semantics by listing ".example.com" or "example.com"
                if e.startswith(".") and host.endswith(e):
                    allowed = True
                    break
                if host.endswith("." + e):
                    allowed = True
                    break
            if not allowed:
                raise HttpExecutorError(f"Host '{host}' is not in the allowed list")

        return url

    def _merge_query_params(self, url: str, query: Optional[Mapping[str, Any]]) -> str:
        if not query:
            return url

        parsed = urlparse(url)
        existing = dict(parse_qsl(parsed.query, keep_blank_values=True))
        for k, v in query.items():
            if v is None:
                continue
            existing[str(k)] = str(v)

        new_query = urlencode(existing, doseq=True)
        return urlunparse(parsed._replace(query=new_query))

    def _sanitize_headers_for_output(self, headers: Mapping[str, str]) -> dict[str, str]:
        out: dict[str, str] = {}
        for k, v in headers.items():
            lk = k.lower()
            if lk in SENSITIVE_HEADER_KEYS:
                out[k] = "[REDACTED]"
            else:
                out[k] = v
        return out

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Optional[Mapping[str, str]] = None,
        query: Optional[Mapping[str, Any]] = None,
        json_body: Optional[Any] = None,
        text_body: Optional[str] = None,
    ) -> HttpExecutorResult:
        method_u = method.upper().strip()
        if method_u not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
            raise HttpExecutorError("Unsupported HTTP method")

        url = self._validate_url(url)
        url = self._merge_query_params(url, query)

        # Prepare headers
        req_headers: dict[str, str] = {}
        if headers:
            for k, v in headers.items():
                if v is None:
                    continue
                req_headers[str(k)] = str(v)

        # A predictable UA helps debugging
        req_headers.setdefault("User-Agent", "InnomightLabsSkillExecutor/1.0")

        timeout = httpx.Timeout(self.timeout_seconds)
        client = self._client or httpx.AsyncClient(timeout=timeout, follow_redirects=True)
        close_client = self._client is None

        try:
            # Validate body rules
            if method_u in {"GET", "DELETE"}:
                if json_body is not None or text_body is not None:
                    raise HttpExecutorError(f"{method_u} requests must not include a body")

            kwargs: dict[str, Any] = {"headers": req_headers}
            if json_body is not None:
                kwargs["json"] = json_body
            elif text_body is not None:
                kwargs["content"] = text_body

            resp = await client.request(method_u, url, **kwargs)

            raw = resp.content
            truncated = False
            if len(raw) > self.max_response_bytes:
                raw = raw[: self.max_response_bytes]
                truncated = True

            # Decode as best-effort text; LLM-friendly.
            try:
                body_text = raw.decode(resp.encoding or "utf-8", errors="replace")
            except Exception:
                body_text = raw.decode("utf-8", errors="replace")

            return HttpExecutorResult(
                ok=200 <= resp.status_code < 300,
                status_code=resp.status_code,
                url=str(resp.url),
                headers=self._sanitize_headers_for_output(dict(resp.headers)),
                body_text=body_text,
                truncated=truncated,
            )
        except httpx.TimeoutException:
            raise HttpExecutorError("HTTP request timed out")
        except httpx.HTTPError as e:
            raise HttpExecutorError(f"HTTP error: {e}")
        finally:
            if close_client:
                await client.aclose()
