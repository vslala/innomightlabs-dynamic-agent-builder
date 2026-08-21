from __future__ import annotations

from typing import Any

import pytest

from src.skills.agent2agent_client.actions import send_message
from src.skills.agent2agent_client.client import A2AHttpClient
from src.skills.agent2agent_client.credentials import A2ACredentialResolver
from src.skills.agent2agent_client.discovery import A2ADiscoveryClient
from src.skills.agent2agent_client.models import A2AAuthResult, A2ARegistryConfig, AgentRef, DiscoverAgentsRequest
from src.skills.agent2agent_client.references import decode_agent_ref, encode_agent_ref
from src.skills.registry import SkillRegistry


class FakeA2AHttpClient:
    def __init__(self, payloads: dict[str, dict[str, Any]]):
        self.payloads = payloads
        self.sent: list[dict[str, Any]] = []

    async def get_json(self, url: str, *, headers: dict[str, str] | None = None) -> dict[str, Any]:
        del headers
        payload = self.payloads.get(url.rstrip("/"))
        if payload is None:
            raise AssertionError(f"Unexpected GET {url}")
        return payload

    async def send_message(
        self,
        *,
        service_url: str,
        request,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        self.sent.append({"service_url": service_url, "request": request, "headers": headers})
        return {
            "ok": True,
            "status_code": 200,
            "task": {
                "status": {
                    "message": {
                        "parts": [{"text": "Remote agent response"}],
                    }
                }
            },
        }


def test_agent2agent_client_manifest_loads():
    manifest = SkillRegistry().get("agent2agent_client")

    assert manifest is not None
    assert manifest.manifest.repeatable is True
    assert [action.name for action in manifest.manifest.actions] == [
        "discover_agents",
        "get_agent_card",
        "send_message",
        "resume_message",
    ]
    assert "registry_set_name" in manifest.manifest.repeatable_identity_fields


@pytest.mark.asyncio
async def test_discovery_searches_agent_card_skills_and_returns_opaque_refs():
    http_client = FakeA2AHttpClient(
        {
            "https://registry.test/.well-known/agent-card.json": {
                "protocolVersion": "1.0.0",
                "name": "Registry",
                "description": "Registry",
                "url": "https://registry.test/a2a",
                "version": "1.0.0",
                "securitySchemes": {},
                "security": [],
                "skills": [],
                "metadata": {
                    "agents": [
                        {
                            "name": "Mail Agent",
                            "description": "Handles communication",
                            "service_url": "https://registry.test/a2a/agents/mail",
                        },
                        {
                            "name": "Research Agent",
                            "description": "Searches documents",
                            "service_url": "https://registry.test/a2a/agents/research",
                        },
                    ]
                },
            },
            "https://registry.test/a2a/agents/mail/agent-card": {
                "protocolVersion": "1.0.0",
                "name": "Mail Agent",
                "description": "Handles communication",
                "url": "https://registry.test/a2a/agents/mail",
                "version": "1.0.0",
                "securitySchemes": {},
                "security": [],
                "skills": [
                    {
                        "id": "gmail",
                        "name": "Gmail",
                        "description": "Read and send Gmail messages.",
                        "tags": ["email"],
                    }
                ],
                "metadata": {},
            },
            "https://registry.test/a2a/agents/research/agent-card": {
                "protocolVersion": "1.0.0",
                "name": "Research Agent",
                "description": "Searches documents",
                "url": "https://registry.test/a2a/agents/research",
                "version": "1.0.0",
                "securitySchemes": {},
                "security": [],
                "skills": [],
                "metadata": {},
            },
        }
    )
    config = A2ARegistryConfig.from_runtime_config(
        {
            "registry_set_name": "Test",
            "registry_urls": "https://registry.test/.well-known/agent-card.json",
        }
    )

    result = await A2ADiscoveryClient(http_client=http_client).search(
        request=DiscoverAgentsRequest(keyword="gmail"),
        config=config,
    )

    assert len(result.items) == 1
    assert result.items[0].name == "Mail Agent"
    assert result.items[0].skills[0].id == "gmail"
    ref = decode_agent_ref(result.items[0].agent_ref)
    assert ref.service_url == "https://registry.test/a2a/agents/mail"


@pytest.mark.asyncio
async def test_discovery_paginates_keyword_matches():
    items = [
        {
            "name": f"Email Agent {index}",
            "description": "email",
            "service_url": f"https://registry.test/a2a/agents/{index}",
        }
        for index in range(12)
    ]
    payloads = {
        "https://registry.test/a2a/agents?limit=100": {"items": items},
        **{
            f"https://registry.test/a2a/agents/{index}/agent-card": {
                "protocolVersion": "1.0.0",
                "name": f"Email Agent {index}",
                "description": "email",
                "url": f"https://registry.test/a2a/agents/{index}",
                "version": "1.0.0",
                "securitySchemes": {},
                "security": [],
                "skills": [],
                "metadata": {},
            }
            for index in range(12)
        },
    }
    config = A2ARegistryConfig.from_runtime_config(
        {"registry_set_name": "Test", "registry_urls": "https://registry.test/a2a/agents"}
    )
    client = A2ADiscoveryClient(http_client=FakeA2AHttpClient(payloads))

    first = await client.search(request=DiscoverAgentsRequest(keyword="email", limit=10), config=config)
    second = await client.search(
        request=DiscoverAgentsRequest(keyword="email", limit=10, cursor=first.next_cursor),
        config=config,
    )

    assert len(first.items) == 10
    assert first.next_cursor
    assert [item.name for item in second.items] == ["Email Agent 10", "Email Agent 11"]
    assert second.next_cursor is None


def test_credential_resolver_uses_origin_default_api_key():
    credential = A2ACredentialResolver().resolve(
        card={
            "securitySchemes": {"agentApiKey": {"type": "apiKey", "in": "header", "name": "Authorization"}},
            "security": [{"agentApiKey": []}],
        },
        target_url="https://registry.test/a2a/agents/mail",
        config=A2ARegistryConfig.from_runtime_config(
            {
                "registry_set_name": "Test",
                "registry_urls": "https://registry.test/.well-known/agent-card.json",
                "default_credentials": {"https://registry.test": "pk_live_test"},
            }
        ),
    )

    assert credential.result == A2AAuthResult.READY
    assert credential.headers == {"Authorization": "Bearer pk_live_test"}


def test_credential_resolver_reports_unsupported_non_api_key_auth():
    credential = A2ACredentialResolver().resolve(
        card={
            "securitySchemes": {"oauth": {"type": "oauth2"}},
            "security": [{"oauth": []}],
        },
        target_url="https://registry.test/a2a/agents/mail",
        config=A2ARegistryConfig.from_runtime_config(
            {"registry_set_name": "Test", "registry_urls": "https://registry.test/.well-known/agent-card.json"}
        ),
    )

    assert credential.result == A2AAuthResult.UNSUPPORTED


def test_registry_config_allows_localhost_for_phase_one_testing():
    config = A2ARegistryConfig.from_runtime_config(
        {"registry_set_name": "Local", "registry_urls": "http://localhost:1455/.well-known/agent-card.json"}
    )

    assert config.registry_urls == ["http://localhost:1455/.well-known/agent-card.json"]


@pytest.mark.asyncio
async def test_send_message_uses_install_time_api_key(monkeypatch):
    class FakePolicy:
        def validate_urls_for_user(self, *, user_email: str, urls: list[str]) -> None:
            assert user_email == "owner@example.com"
            assert "https://registry.test/a2a/agents/mail" in urls

    agent_ref = encode_agent_ref(
        AgentRef(
            registry_url="https://registry.test/a2a/agents",
            service_url="https://registry.test/a2a/agents/mail",
            card_url="https://registry.test/a2a/agents/mail/agent-card",
            name="Mail Agent",
        )
    )
    fake_http = FakeA2AHttpClient(
        {
            "https://registry.test/a2a/agents/mail/agent-card": {
                "protocolVersion": "1.0.0",
                "name": "Mail Agent",
                "description": "mail",
                "url": "https://registry.test/a2a/agents/mail",
                "version": "1.0.0",
                "securitySchemes": {
                    "agentApiKey": {"type": "apiKey", "in": "header", "name": "Authorization"}
                },
                "security": [{"agentApiKey": []}],
                "skills": [],
                "metadata": {},
            },
        }
    )

    monkeypatch.setattr("src.skills.agent2agent_client.actions.Agent2AgentPolicy", FakePolicy)
    monkeypatch.setattr(A2AHttpClient, "get_json", fake_http.get_json)
    monkeypatch.setattr(A2AHttpClient, "send_message", fake_http.send_message)

    result = await send_message(
        arguments={"agent_ref": agent_ref, "message": "hello"},
        config={
            "registry_set_name": "Test",
            "registry_urls": "https://registry.test/a2a/agents",
            "default_credentials": {"https://registry.test": "pk_live_test"},
        },
        context={"owner_email": "owner@example.com"},
    )

    assert result["ok"] is True
    assert result["response_text"] == "Remote agent response"
    assert fake_http.sent[0]["headers"] == {"Authorization": "Bearer pk_live_test"}
