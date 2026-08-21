from __future__ import annotations

from typing import Any

import pytest
import httpx

from src.skills.agent2agent_client.actions import send_message
from src.skills.agent2agent_client.client import A2AHttpClient
from src.skills.agent2agent_client.credentials import A2ACredentialResolver
from src.skills.agent2agent_client.discovery import A2ADiscoveryClient
from src.skills.agent2agent_client.models import A2AAuthResult, A2ARegistryConfig, AgentRef, DiscoverAgentsRequest
from src.skills.agent2agent_client.models import SendMessageRequest
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
        protocol_binding: str | None = None,
    ) -> dict[str, Any]:
        self.sent.append(
            {
                "service_url": service_url,
                "request": request,
                "headers": headers,
                "protocol_binding": protocol_binding,
            }
        )
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


@pytest.mark.asyncio
async def test_discovery_empty_keyword_returns_first_page_of_all_agents():
    items = [
        {
            "name": f"Agent {index}",
            "description": "available",
            "service_url": f"https://registry.test/a2a/agents/{index}",
        }
        for index in range(12)
    ]
    payloads = {
        "https://registry.test/a2a/agents?limit=100": {"items": items},
        **{
            f"https://registry.test/a2a/agents/{index}/agent-card": {
                "protocolVersion": "1.0.0",
                "name": f"Agent {index}",
                "description": "available",
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

    result = await A2ADiscoveryClient(http_client=FakeA2AHttpClient(payloads)).search(
        request=DiscoverAgentsRequest(keyword="", limit=10),
        config=config,
    )

    assert len(result.items) == 10
    assert [item.name for item in result.items[:2]] == ["Agent 0", "Agent 1"]
    assert result.next_cursor


@pytest.mark.asyncio
async def test_discovery_expands_current_facilitator_card_without_legacy_metadata():
    http_client = FakeA2AHttpClient(
        {
            "https://registry.test/.well-known/agent-card.json": {
                "name": "Registry",
                "description": "Registry",
                "supportedInterfaces": [
                    {
                        "url": "https://registry.test/a2a",
                        "protocolBinding": "JSONRPC",
                        "protocolVersion": "1.0",
                    }
                ],
                "version": "1.0.0",
                "securitySchemes": {},
                "securityRequirements": [],
                "skills": [{"id": "discover_public_agents", "name": "Discover Public Agents"}],
            },
            "https://registry.test/a2a/agents?limit=100": {
                "items": [
                    {
                        "name": "Local Mail Agent",
                        "description": "Handles mail requests",
                        "service_url": "https://registry.test/a2a/agents/mail",
                        "agent_card_url": "https://registry.test/a2a/agents/mail/agent-card",
                    }
                ]
            },
            "https://registry.test/a2a/agents/mail/agent-card": {
                "name": "Local Mail Agent",
                "description": "Handles mail requests",
                "supportedInterfaces": [
                    {
                        "url": "https://registry.test/a2a/agents/mail",
                        "protocolBinding": "JSONRPC",
                        "protocolVersion": "1.0",
                    }
                ],
                "version": "1.0.0",
                "securitySchemes": {},
                "securityRequirements": [],
                "skills": [{"id": "mail", "name": "Mail", "description": "Email support"}],
            },
        }
    )
    config = A2ARegistryConfig.from_runtime_config(
        {
            "registry_set_name": "Current",
            "registry_urls": "https://registry.test/.well-known/agent-card.json",
        }
    )

    result = await A2ADiscoveryClient(http_client=http_client).search(
        request=DiscoverAgentsRequest(keyword="mail"),
        config=config,
    )

    assert len(result.items) == 1
    assert result.items[0].name == "Local Mail Agent"
    ref = decode_agent_ref(result.items[0].agent_ref)
    assert ref.protocol_binding == "JSONRPC"


def test_credential_resolver_uses_origin_default_api_key():
    credential = A2ACredentialResolver().resolve(
        card={
            "securitySchemes": {
                "agentApiKey": {
                    "apiKeySecurityScheme": {
                        "location": "header",
                        "name": "Authorization",
                    }
                }
            },
            "securityRequirements": [{"schemes": {"agentApiKey": {"list": []}}}],
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
                "name": "Mail Agent",
                "description": "mail",
                "supportedInterfaces": [
                    {
                        "url": "https://registry.test/a2a/agents/mail",
                        "protocolBinding": "JSONRPC",
                        "protocolVersion": "1.0",
                    },
                    {
                        "url": "https://registry.test/a2a/agents/mail",
                        "protocolBinding": "HTTP+JSON",
                        "protocolVersion": "1.0",
                    },
                ],
                "version": "1.0.0",
                "securitySchemes": {
                    "agentApiKey": {
                        "apiKeySecurityScheme": {
                            "location": "header",
                            "name": "Authorization",
                        }
                    }
                },
                "securityRequirements": [{"schemes": {"agentApiKey": {"list": []}}}],
                "skills": [],
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
    assert fake_http.sent[0]["protocol_binding"] == "JSONRPC"


@pytest.mark.asyncio
async def test_send_message_missing_api_key_returns_credential_setup_link(monkeypatch):
    class FakePolicy:
        def validate_urls_for_user(self, *, user_email: str, urls: list[str]) -> None:
            assert user_email == "owner@example.com"

    agent_ref = encode_agent_ref(
        AgentRef(
            registry_url="https://registry.test/a2a/agents",
            service_url="https://registry.test/a2a/agents/notion",
            card_url="https://registry.test/a2a/agents/notion/agent-card",
            name="Notion Manager",
        )
    )
    fake_http = FakeA2AHttpClient(
        {
            "https://registry.test/a2a/agents/notion/agent-card": {
                "name": "Notion Manager",
                "description": "notion",
                "supportedInterfaces": [
                    {
                        "url": "https://registry.test/a2a/agents/notion",
                        "protocolBinding": "JSONRPC",
                        "protocolVersion": "1.0",
                    }
                ],
                "version": "1.0.0",
                "securitySchemes": {
                    "agentApiKey": {
                        "apiKeySecurityScheme": {
                            "location": "header",
                            "name": "Authorization",
                        }
                    }
                },
                "securityRequirements": [{"schemes": {"agentApiKey": {"list": []}}}],
                "skills": [],
            },
        }
    )

    monkeypatch.setattr("src.skills.agent2agent_client.actions.Agent2AgentPolicy", FakePolicy)
    monkeypatch.setattr("src.skills.agent2agent_client.actions.settings.frontend_url", "http://localhost:5173")
    monkeypatch.setattr(A2AHttpClient, "get_json", fake_http.get_json)
    monkeypatch.setattr(A2AHttpClient, "send_message", fake_http.send_message)

    result = await send_message(
        arguments={"agent_ref": agent_ref, "message": "hello"},
        config={
            "registry_set_name": "Test",
            "registry_urls": "https://registry.test/a2a/agents",
        },
        context={
            "agent_id": "agent-123",
            "installed_skill_id": "agent2agent_client:test",
            "owner_email": "owner@example.com",
        },
    )

    assert result["ok"] is False
    assert result["auth_required"] is True
    assert result["credential_setup_label"] == "Add Agent2Agent credential"
    assert result["credential_setup_url"].startswith("http://localhost:5173/dashboard/agents/agent-123/skills?")
    assert "configure_skill=agent2agent_client%3Atest" in result["credential_setup_url"]
    assert "credential_origin=https%3A%2F%2Fregistry.test" in result["credential_setup_url"]
    assert result["credential_setup_url"] in result["message"]


@pytest.mark.asyncio
async def test_a2a_client_returns_structured_timeout(monkeypatch):
    async def raise_timeout(*args, **kwargs):
        raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr(httpx.AsyncClient, "post", raise_timeout)

    result = await A2AHttpClient().send_message(
        service_url="https://registry.test/a2a/agents/slow",
        request=SendMessageRequest(agent_ref="unused", message="hello", timeout_seconds=7),
        headers={},
        protocol_binding="JSONRPC",
    )

    assert result == {
        "ok": False,
        "status_code": 504,
        "message": "Remote A2A request timed out after 7 seconds.",
    }
