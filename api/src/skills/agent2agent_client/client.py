from __future__ import annotations

import uuid
from typing import Any

import httpx
from a2a.client import ClientCallContext, ClientConfig, ClientFactory
from a2a.client.card_resolver import parse_agent_card
from a2a.client.errors import A2AClientError, A2AClientTimeoutError
from a2a.types import AgentCard, SendMessageRequest as A2ASdkSendMessageRequest
from a2a.utils.constants import TransportProtocol
from google.protobuf.json_format import MessageToDict, ParseDict

from src.skills.agent2agent_client.models import (
    A2A_PROTOCOL_HTTP_JSON,
    A2A_PROTOCOL_JSONRPC,
    SendMessageRequest,
    normalize_protocol_binding,
)


class A2AHttpClient:
    def __init__(self, *, timeout_seconds: float = 20.0) -> None:
        self.timeout_seconds = timeout_seconds

    async def get_json(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True) as client:
            response = await client.get(url, headers=self._headers(headers))
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError(f"A2A endpoint returned a non-object payload: {url}")
        return payload

    async def get_agent_card(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        payload = await self.get_json(url, headers=headers)
        return self.normalize_agent_card(payload)

    async def request_oauth_client_credentials_token(
        self,
        *,
        token_url: str,
        client_id: str,
        client_secret: str,
        scopes: list[str],
        timeout_seconds: int = 20,
    ) -> dict[str, Any]:
        data = {"grant_type": "client_credentials"}
        if scopes:
            data["scope"] = " ".join(scopes)
        async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client:
            response = await client.post(
                token_url,
                data=data,
                auth=(client_id, client_secret),
                headers={
                    "Accept": "application/json",
                    "User-Agent": "InnomightLabs-Agent2AgentClientSkill/1.0",
                },
            )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError(f"A2A OAuth token endpoint returned a non-object payload: {token_url}")
        return payload

    def normalize_agent_card(self, payload: dict[str, Any]) -> dict[str, Any]:
        return _agent_card_to_dict(parse_agent_card(payload))

    async def send_message(
        self,
        *,
        agent_card: dict[str, Any],
        request: SendMessageRequest,
        headers: dict[str, str],
        preferred_protocols: list[str] | None = None,
    ) -> dict[str, Any]:
        sdk_card = _parse_agent_card(agent_card)
        sdk_request = _build_send_message_request(request)
        protocol_bindings = _transport_protocols(preferred_protocols)

        try:
            async with httpx.AsyncClient(
                timeout=request.timeout_seconds,
                follow_redirects=True,
                headers=self._headers(headers),
            ) as client:
                sdk_client = ClientFactory(
                    ClientConfig(
                        streaming=False,
                        httpx_client=client,
                        supported_protocol_bindings=protocol_bindings,
                        use_client_preference=True,
                        accepted_output_modes=["text/plain"],
                    )
                ).create(sdk_card)
                context = ClientCallContext(
                    timeout=request.timeout_seconds,
                    service_parameters=headers,
                )
                final_event: dict[str, Any] | None = None
                async for event in sdk_client.send_message(sdk_request, context=context):
                    final_event = MessageToDict(event)
        except (A2AClientTimeoutError, httpx.TimeoutException):
            return _timeout_payload(request.timeout_seconds)
        except A2AClientError as exc:
            return _error_payload(str(exc))
        except httpx.HTTPError as exc:
            return _error_payload(str(exc))
        except ValueError as exc:
            return _error_payload(str(exc))

        if not final_event:
            return _error_payload("Remote A2A agent returned no response.")

        payload = _payload_from_stream_response(final_event)
        payload["status_code"] = 200
        payload["ok"] = True
        return payload

    def _headers(self, headers: dict[str, str] | None = None) -> dict[str, str]:
        merged = {
            "Accept": "application/a2a+json, application/json",
            "Content-Type": "application/json",
            "User-Agent": "InnomightLabs-Agent2AgentClientSkill/1.0",
        }
        merged.update(headers or {})
        return merged


def _build_send_message_request(request: SendMessageRequest) -> A2ASdkSendMessageRequest:
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
    return ParseDict(body, A2ASdkSendMessageRequest(), ignore_unknown_fields=False)


def _parse_agent_card(payload: dict[str, Any]) -> AgentCard:
    return parse_agent_card(payload)


def _agent_card_to_dict(card: AgentCard) -> dict[str, Any]:
    return MessageToDict(card)


def _transport_protocols(protocols: list[str] | None) -> list[str]:
    bindings = [
        normalize_protocol_binding(protocol)
        for protocol in protocols or [A2A_PROTOCOL_JSONRPC]
    ]
    mapped = []
    for binding in bindings:
        if binding == A2A_PROTOCOL_JSONRPC:
            mapped.append(TransportProtocol.JSONRPC.value)
        elif binding == A2A_PROTOCOL_HTTP_JSON:
            mapped.append(TransportProtocol.HTTP_JSON.value)
    return list(dict.fromkeys(mapped)) or [TransportProtocol.JSONRPC.value]


def _payload_from_stream_response(event: dict[str, Any]) -> dict[str, Any]:
    for key in ("task", "message", "statusUpdate", "artifactUpdate"):
        value = event.get(key)
        if isinstance(value, dict):
            return {key: value}
    return {}


def _error_payload(message: str) -> dict[str, Any]:
    return {
        "ok": False,
        "status_code": 502,
        "message": message,
    }


def _timeout_payload(timeout_seconds: int) -> dict[str, Any]:
    return {
        "ok": False,
        "status_code": 504,
        "message": f"Remote A2A request timed out after {timeout_seconds} seconds.",
    }
