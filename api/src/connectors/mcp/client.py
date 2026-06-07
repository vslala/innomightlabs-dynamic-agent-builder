from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import httpx

from src.connectors.mcp.models import MCPConnection

MCP_PROTOCOL_VERSION = "2025-06-18"
MCP_SESSION_HEADER = "Mcp-Session-Id"
MAX_LOGGED_RESPONSE_CHARS = 10000
TOKEN_REDACTION_PATTERNS = [
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE),
    re.compile(r'("(?:access_token|refresh_token|client_secret)"\s*:\s*")[^"]+(")', re.IGNORECASE),
]

log = logging.getLogger(__name__)


class MCPClientError(ValueError):
    """Raised when a Streamable HTTP MCP request fails."""


@dataclass(frozen=True)
class MCPSession:
    session_id: str | None
    protocol_version: str


class StreamableHTTPMCPClient:
    """Small JSON-RPC client for MCP Streamable HTTP servers."""

    def __init__(self, *, timeout: float = 30.0, transport: httpx.AsyncBaseTransport | None = None):
        self.timeout = timeout
        self.transport = transport

    async def list_tools(
        self,
        connection: MCPConnection,
        auth_headers: dict[str, str],
    ) -> dict[str, Any]:
        session = await self._initialize_session(connection=connection, auth_headers=auth_headers)
        response = await self._rpc(
            connection=connection,
            auth_headers=auth_headers,
            session=session,
            method="tools/list",
            params={},
        )
        result = response.get("result")
        if not isinstance(result, dict):
            raise MCPClientError("MCP tools/list returned an invalid result")
        return result

    async def call_tool(
        self,
        connection: MCPConnection,
        auth_headers: dict[str, str],
        *,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        session = await self._initialize_session(connection=connection, auth_headers=auth_headers)
        response = await self._rpc(
            connection=connection,
            auth_headers=auth_headers,
            session=session,
            method="tools/call",
            params={"name": tool_name, "arguments": arguments},
        )
        result = response.get("result")
        if not isinstance(result, dict):
            raise MCPClientError("MCP tools/call returned an invalid result")
        return result

    async def _rpc(
        self,
        *,
        connection: MCPConnection,
        auth_headers: dict[str, str],
        session: MCPSession,
        method: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        request_id = str(uuid4())
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }
        headers = self._headers(auth_headers=auth_headers, session=session)

        try:
            async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
                response = await client.post(connection.server_url, headers=headers, json=payload)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            response_text = _sanitize_response_text(exc.response.text)
            log.warning(
                "MCP HTTP error mcp_id=%s name=%s method=%s status=%s url=%s response=%s",
                connection.mcp_id,
                connection.name,
                method,
                exc.response.status_code,
                connection.server_url,
                response_text,
            )
            raise MCPClientError(
                f"MCP server returned HTTP {exc.response.status_code}: {response_text}"
            ) from exc
        except httpx.HTTPError as exc:
            log.warning(
                "MCP request failed mcp_id=%s name=%s method=%s url=%s error=%s",
                connection.mcp_id,
                connection.name,
                method,
                connection.server_url,
                exc,
            )
            raise MCPClientError(f"MCP server request failed: {exc}") from exc

        body = self._decode_response(response, request_id=request_id)
        if "error" in body:
            error_body = json.dumps(body["error"], ensure_ascii=True)
            log.warning(
                "MCP JSON-RPC error mcp_id=%s name=%s method=%s error=%s",
                connection.mcp_id,
                connection.name,
                method,
                _sanitize_response_text(error_body),
            )
            raise MCPClientError(f"MCP {method} error: {_sanitize_response_text(error_body)}")
        return body

    async def _initialize_session(
        self,
        *,
        connection: MCPConnection,
        auth_headers: dict[str, str],
    ) -> MCPSession:
        request_id = str(uuid4())
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "initialize",
            "params": {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {
                    "name": "innomightlabs",
                    "title": "InnoMight Labs",
                    "version": "1.0.0",
                },
            },
        }
        headers = self._headers(auth_headers=auth_headers, session=None)

        try:
            async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
                response = await client.post(connection.server_url, headers=headers, json=payload)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            response_text = _sanitize_response_text(exc.response.text)
            log.warning(
                "MCP initialize HTTP error mcp_id=%s name=%s status=%s url=%s response=%s",
                connection.mcp_id,
                connection.name,
                exc.response.status_code,
                connection.server_url,
                response_text,
            )
            raise MCPClientError(
                f"MCP initialize returned HTTP {exc.response.status_code}: {response_text}"
            ) from exc
        except httpx.HTTPError as exc:
            log.warning(
                "MCP initialize request failed mcp_id=%s name=%s url=%s error=%s",
                connection.mcp_id,
                connection.name,
                connection.server_url,
                exc,
            )
            raise MCPClientError(f"MCP initialize request failed: {exc}") from exc

        body = self._decode_response(response, request_id=request_id)
        if "error" in body:
            error_body = json.dumps(body["error"], ensure_ascii=True)
            raise MCPClientError(f"MCP initialize error: {_sanitize_response_text(error_body)}")

        result = body.get("result")
        if not isinstance(result, dict):
            raise MCPClientError("MCP initialize returned an invalid result")

        protocol_version = str(result.get("protocolVersion") or MCP_PROTOCOL_VERSION)
        session_id = response.headers.get(MCP_SESSION_HEADER)
        session = MCPSession(session_id=session_id, protocol_version=protocol_version)
        log.info(
            "Initialized MCP session mcp_id=%s name=%s has_session_id=%s protocol_version=%s",
            connection.mcp_id,
            connection.name,
            bool(session_id),
            protocol_version,
        )
        await self._send_initialized_notification(
            connection=connection,
            auth_headers=auth_headers,
            session=session,
        )
        return session

    async def _send_initialized_notification(
        self,
        *,
        connection: MCPConnection,
        auth_headers: dict[str, str],
        session: MCPSession,
    ) -> None:
        payload = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        headers = self._headers(auth_headers=auth_headers, session=session)

        try:
            async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
                response = await client.post(connection.server_url, headers=headers, json=payload)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            response_text = _sanitize_response_text(exc.response.text)
            log.warning(
                "MCP initialized notification HTTP error mcp_id=%s name=%s status=%s response=%s",
                connection.mcp_id,
                connection.name,
                exc.response.status_code,
                response_text,
            )
            raise MCPClientError(
                f"MCP initialized notification returned HTTP {exc.response.status_code}: {response_text}"
            ) from exc
        except httpx.HTTPError as exc:
            log.warning(
                "MCP initialized notification failed mcp_id=%s name=%s error=%s",
                connection.mcp_id,
                connection.name,
                exc,
            )
            raise MCPClientError(f"MCP initialized notification failed: {exc}") from exc

    def _headers(self, *, auth_headers: dict[str, str], session: MCPSession | None) -> dict[str, str]:
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "MCP-Protocol-Version": session.protocol_version if session else MCP_PROTOCOL_VERSION,
        }
        headers.update(auth_headers)
        if session and session.session_id:
            headers[MCP_SESSION_HEADER] = session.session_id
        return headers

    def _decode_response(self, response: httpx.Response, request_id: str | None = None) -> dict[str, Any]:
        content_type = response.headers.get("content-type", "")
        if "text/event-stream" in content_type:
            return self._decode_sse_response(response.text, request_id=request_id)

        try:
            body = response.json()
        except ValueError as exc:
            raise MCPClientError("MCP server returned non-JSON response") from exc

        if not isinstance(body, dict):
            raise MCPClientError("MCP server returned invalid JSON-RPC response")
        return body

    def _decode_sse_response(self, text: str, request_id: str | None = None) -> dict[str, Any]:
        messages = self._decode_sse_messages(text)
        if not messages:
            raise MCPClientError("MCP server returned empty event-stream response")
        if request_id is None:
            return messages[-1]

        for message in messages:
            if message.get("id") == request_id:
                return message
        raise MCPClientError("MCP server event-stream did not include a response for the request")

    def _decode_sse_messages(self, text: str) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        data_lines: list[str] = []
        for line in text.splitlines():
            if line.startswith("data:"):
                data_lines.append(line.removeprefix("data:").strip())
                continue
            if not line.strip() and data_lines:
                messages.append(self._decode_sse_data(data_lines))
                data_lines = []
        if data_lines:
            messages.append(self._decode_sse_data(data_lines))
        return messages

    def _decode_sse_data(self, data_lines: list[str]) -> dict[str, Any]:
        try:
            body = json.loads("\n".join(data_lines))
        except json.JSONDecodeError as exc:
            raise MCPClientError("MCP server returned invalid event-stream JSON") from exc
        if not isinstance(body, dict):
            raise MCPClientError("MCP server returned invalid event-stream JSON-RPC response")
        return body


def _sanitize_response_text(text: str) -> str:
    cleaned = text.replace("\n", " ").replace("\r", " ").strip()
    for pattern in TOKEN_REDACTION_PATTERNS:
        if pattern.groups == 2:
            cleaned = pattern.sub(r"\1[REDACTED]\2", cleaned)
        else:
            cleaned = pattern.sub("Bearer [REDACTED]", cleaned)
    if len(cleaned) <= MAX_LOGGED_RESPONSE_CHARS:
        return cleaned
    return f"{cleaned[:MAX_LOGGED_RESPONSE_CHARS]}..."
