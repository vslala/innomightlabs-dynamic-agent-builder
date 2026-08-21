from __future__ import annotations

import uuid
from typing import Any

import httpx

from src.skills.agent2agent_client.models import SendMessageRequest


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

        endpoint = f"{service_url.rstrip('/')}/message:send"
        async with httpx.AsyncClient(timeout=request.timeout_seconds, follow_redirects=True) as client:
            response = await client.post(endpoint, json=body, headers=self._headers(headers))

        payload: dict[str, Any] = {}
        try:
            parsed = response.json()
            if isinstance(parsed, dict):
                payload = parsed
        except ValueError:
            payload = {"body_preview": response.text[: request.max_response_chars]}

        payload["status_code"] = response.status_code
        payload["ok"] = response.is_success
        return payload

    def _headers(self, headers: dict[str, str] | None = None) -> dict[str, str]:
        merged = {
            "Accept": "application/a2a+json, application/json",
            "Content-Type": "application/json",
            "User-Agent": "InnomightLabs-Agent2AgentClientSkill/1.0",
        }
        merged.update(headers or {})
        return merged
