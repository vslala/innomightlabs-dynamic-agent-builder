from __future__ import annotations

import uuid
from typing import Any

import httpx

from src.skills.agent2agent_client.models import (
    A2A_PROTOCOL_HTTP_JSON,
    A2A_PROTOCOL_JSONRPC,
    SendMessageRequest,
    normalize_protocol_binding,
)


class A2AHttpClient:
    def __init__(self, *, timeout_seconds: float = 20.0) -> None:
        self.timeout_seconds = timeout_seconds

    async def get_json(self, url: str, *, headers: dict[str, str] | None = None) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True) as client:
            response = await client.get(url, headers=self._headers(headers))
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError(f"A2A endpoint returned a non-object payload: {url}")
        return payload

    async def send_message(
        self,
        *,
        service_url: str,
        request: SendMessageRequest,
        headers: dict[str, str],
        protocol_binding: str | None = None,
    ) -> dict[str, Any]:
        body = {
            "message": {
                "messageId": str(uuid.uuid4()),
                "role": "ROLE_USER",
                "parts": [{"text": request.message}],
            },
            "configuration": {"acceptedOutputModes": ["text/plain"]},
        }
        if request.context_id:
            body["message"]["contextId"] = request.context_id
        if request.task_id:
            body["message"]["taskId"] = request.task_id

        protocol = normalize_protocol_binding(protocol_binding or A2A_PROTOCOL_JSONRPC)
        if protocol == A2A_PROTOCOL_JSONRPC:
            return await self._send_jsonrpc_message(
                service_url=service_url,
                body=body,
                request=request,
                headers=headers,
            )
        if protocol == A2A_PROTOCOL_HTTP_JSON:
            return await self._send_http_json_message(
                service_url=service_url,
                body=body,
                request=request,
                headers=headers,
            )
        raise ValueError(f"Unsupported A2A protocol binding: {protocol}")

    async def _send_jsonrpc_message(
        self,
        *,
        service_url: str,
        body: dict[str, Any],
        request: SendMessageRequest,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        endpoint = service_url.rstrip("/")
        rpc_body = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "message/send",
            "params": body,
        }
        try:
            async with httpx.AsyncClient(timeout=request.timeout_seconds, follow_redirects=True) as client:
                response = await client.post(endpoint, json=rpc_body, headers=self._headers(headers))
        except httpx.TimeoutException:
            return _timeout_payload(request.timeout_seconds)

        payload = self._parse_response(response, request.max_response_chars)
        error = payload.get("error") if isinstance(payload.get("error"), dict) else None
        if error:
            return {
                "ok": False,
                "status_code": response.status_code,
                "message": str(error.get("message") or "Remote A2A JSON-RPC request failed"),
            }
        result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
        result["status_code"] = response.status_code
        result["ok"] = response.is_success
        return result

    async def _send_http_json_message(
        self,
        *,
        service_url: str,
        body: dict[str, Any],
        request: SendMessageRequest,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        endpoint = f"{service_url.rstrip('/')}/message:send"
        try:
            async with httpx.AsyncClient(timeout=request.timeout_seconds, follow_redirects=True) as client:
                response = await client.post(endpoint, json=body, headers=self._headers(headers))
        except httpx.TimeoutException:
            return _timeout_payload(request.timeout_seconds)

        payload = self._parse_response(response, request.max_response_chars)
        payload["status_code"] = response.status_code
        payload["ok"] = response.is_success
        return payload

    def _parse_response(self, response: httpx.Response, max_response_chars: int) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        try:
            parsed = response.json()
            if isinstance(parsed, dict):
                payload = parsed
        except ValueError:
            payload = {"body_preview": response.text[:max_response_chars]}
        return payload

    def _headers(self, headers: dict[str, str] | None = None) -> dict[str, str]:
        merged = {
            "Accept": "application/a2a+json, application/json",
            "Content-Type": "application/json",
            "User-Agent": "InnomightLabs-Agent2AgentClientSkill/1.0",
        }
        merged.update(headers or {})
        return merged


def _timeout_payload(timeout_seconds: int) -> dict[str, Any]:
    return {
        "ok": False,
        "status_code": 504,
        "message": f"Remote A2A request timed out after {timeout_seconds} seconds.",
    }
