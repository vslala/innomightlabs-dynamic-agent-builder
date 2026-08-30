from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse
from typing import Any

import pytest
import httpx

from src.skills.agent2agent_client.actions import send_message
from src.skills.agent2agent_client.client import A2AHttpClient
from src.skills.agent2agent_client.credentials import A2ACredentialResolver
from src.skills.agent2agent_client.discovery import A2ADiscoveryClient
from src.skills.agent2agent_client.models import A2AAuthResult, A2ARegistryConfig, AgentRef, DiscoverAgentsRequest
from src.skills.agent2agent_client.models import SendMessageRequest
from src.skills.agent2agent_client.oauth import (
    A2ARemoteOAuthAuthConfig,
    A2ARemoteOAuthCredentialRecord,
    A2ARemoteOAuthCredentials,
    A2ARemoteOAuthProviderConfig,
    A2ARemoteOAuthRepository,
    decode_state_session,
    decrypt_auth_config,
    encrypt_auth_config,
)
from src.skills.agent2agent_client.references import decode_agent_ref, encode_agent_ref
from src.skills.registry import SkillRegistry


class FakeA2AHttpClient:
    def __init__(self, payloads: dict[str, dict[str, Any]]):
        self.payloads = payloads
        self.sent: list[dict[str, Any]] = []
        self.gets: list[dict[str, Any]] = []
        self.oauth_requests: list[dict[str, Any]] = []

    async def get_json(self, url: str, *, headers: dict[str, str] | None = None) -> dict[str, Any]:
        self.gets.append({"url": url, "headers": headers or {}})
        payload = self.payloads.get(url.rstrip("/"))
        if payload is None:
            raise AssertionError(f"Unexpected GET {url}")
        return payload

    async def get_agent_card(self, url: str, *, headers: dict[str, str] | None = None) -> dict[str, Any]:
        return await self.get_json(url, headers=headers)

    def normalize_agent_card(self, payload: dict[str, Any]) -> dict[str, Any]:
        return payload

    async def send_message(
        self,
        *,
        agent_card: dict[str, Any],
        request,
        headers: dict[str, str],
        preferred_protocols: list[str] | None = None,
    ) -> dict[str, Any]:
        self.sent.append(
            {
                "agent_card": agent_card,
                "request": request,
                "headers": headers,
                "preferred_protocols": preferred_protocols,
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

    async def request_oauth_client_credentials_token(
        self,
        *,
        token_url: str,
        client_id: str,
        client_secret: str,
        scopes: list[str],
        timeout_seconds: int = 20,
    ) -> dict[str, Any]:
        del timeout_seconds
        self.oauth_requests.append(
            {
                "token_url": token_url,
                "client_id": client_id,
                "client_secret": client_secret,
                "scopes": scopes,
            }
        )
        return {
            "access_token": "oauth-access-token",
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": " ".join(scopes),
        }


def test_agent2agent_client_manifest_loads():
    manifest = SkillRegistry().get("agent2agent_client")

    assert manifest is not None
    assert manifest.manifest.repeatable is True
    field_names = [field.name for field in manifest.manifest.form]
    assert "registry_url" in field_names
    assert "registry_urls" in field_names
    assert [action.name for action in manifest.manifest.actions] == [
        "discover_agents",
        "get_agent_card",
        "send_message",
        "resume_message",
    ]
    assert "registry_set_name" in manifest.manifest.repeatable_identity_fields


def test_registry_config_merges_primary_and_additional_urls():
    config = A2ARegistryConfig.from_runtime_config(
        {
            "registry_set_name": "Test",
            "registry_url": "https://primary.test/a2a/agents",
            "registry_urls": "https://primary.test/a2a/agents\nhttps://secondary.test/a2a/agents",
        }
    )

    assert config.registry_urls == [
        "https://primary.test/a2a/agents",
        "https://secondary.test/a2a/agents",
    ]


@pytest.mark.asyncio
async def test_discovery_searches_agent_card_skills_and_returns_opaque_refs():
    http_client = FakeA2AHttpClient(
        {
            "https://registry.test/a2a/agents?limit=100": {
                "items": [
                    {
                        "id": "mail",
                        "name": "Mail Agent",
                        "description": "Handles communication",
                        "agentCardUrl": "https://registry.test/a2a/agents/mail/card",
                    },
                    {
                        "id": "research",
                        "name": "Research Agent",
                        "description": "Searches documents",
                        "agentCardUrl": "https://registry.test/a2a/agents/research/card",
                    },
                ]
            },
            "https://registry.test/a2a/agents/mail/card": {
                "name": "Mail Agent",
                "description": "Handles communication",
                "supportedInterfaces": [
                    {
                        "url": "https://registry.test/a2a/agents/mail",
                        "protocolBinding": "JSONRPC",
                        "protocolVersion": "1.0",
                    }
                ],
                "version": "1.0.0",
                "capabilities": {},
                "securitySchemes": {},
                "securityRequirements": [],
                "defaultInputModes": ["text/plain"],
                "defaultOutputModes": ["text/plain"],
                "skills": [
                    {
                        "id": "gmail",
                        "name": "Gmail",
                        "description": "Read and send Gmail messages.",
                        "tags": ["email"],
                    }
                ],
            },
            "https://registry.test/a2a/agents/research/card": {
                "name": "Research Agent",
                "description": "Searches documents",
                "supportedInterfaces": [
                    {
                        "url": "https://registry.test/a2a/agents/research",
                        "protocolBinding": "JSONRPC",
                        "protocolVersion": "1.0",
                    }
                ],
                "version": "1.0.0",
                "capabilities": {},
                "securitySchemes": {},
                "securityRequirements": [],
                "defaultInputModes": ["text/plain"],
                "defaultOutputModes": ["text/plain"],
                "skills": [],
            },
        }
    )
    config = A2ARegistryConfig.from_runtime_config(
        {
            "registry_set_name": "Test",
            "registry_url": "https://registry.test/a2a/agents",
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
    assert ref.card_url == "https://registry.test/a2a/agents/mail/card"


@pytest.mark.asyncio
async def test_discovery_paginates_keyword_matches():
    items = [
        {
            "name": f"Email Agent {index}",
            "description": "email",
            "serviceUrl": f"https://registry.test/a2a/agents/{index}",
            "agentCardUrl": f"https://registry.test/a2a/agents/{index}/card",
        }
        for index in range(12)
    ]
    payloads = {
        "https://registry.test/a2a/agents?limit=100": {"items": items},
        **{
            f"https://registry.test/a2a/agents/{index}/card": {
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
            "serviceUrl": f"https://registry.test/a2a/agents/{index}",
            "agentCardUrl": f"https://registry.test/a2a/agents/{index}/card",
        }
        for index in range(12)
    ]
    payloads = {
        "https://registry.test/a2a/agents?limit=100": {"items": items},
        **{
            f"https://registry.test/a2a/agents/{index}/card": {
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
async def test_discovery_treats_well_known_card_as_single_agent_without_registry_inference():
    http_client = FakeA2AHttpClient(
        {
            "https://registry.test/.well-known/agent-card.json": {
                "name": "Standalone Mail Agent",
                "description": "Handles mail requests",
                "supportedInterfaces": [
                    {
                        "url": "https://registry.test/a2a/agents/mail",
                        "protocolBinding": "JSONRPC",
                        "protocolVersion": "1.0",
                    }
                ],
                "version": "1.0.0",
                "capabilities": {},
                "securitySchemes": {},
                "securityRequirements": [],
                "defaultInputModes": ["text/plain"],
                "defaultOutputModes": ["text/plain"],
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
    assert result.items[0].name == "Standalone Mail Agent"
    ref = decode_agent_ref(result.items[0].agent_ref)
    assert ref.protocol_binding == "JSONRPC"
    assert ref.card_url == "https://registry.test/.well-known/agent-card.json"


@pytest.mark.asyncio
async def test_credential_resolver_uses_origin_default_api_key():
    credential = await A2ACredentialResolver().resolve(
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


@pytest.mark.asyncio
async def test_credential_resolver_accepts_bearer_http_auth_scheme_without_credential():
    credential = await A2ACredentialResolver().resolve(
        card={
            "securitySchemes": {
                "agentApiKey": {
                    "httpAuthSecurityScheme": {
                        "scheme": "Bearer",
                        "bearerFormat": "Opaque API key",
                    }
                }
            },
            "securityRequirements": [{"schemes": {"agentApiKey": {"list": []}}}],
        },
        target_url="https://registry.test/a2a/agents/mail",
        config=A2ARegistryConfig.from_runtime_config(
            {"registry_set_name": "Test", "registry_urls": "https://registry.test/.well-known/agent-card.json"}
        ),
    )

    assert credential.result == A2AAuthResult.REQUIRED
    assert "API key" in (credential.message or "")


@pytest.mark.asyncio
async def test_credential_resolver_reports_unsupported_non_api_key_auth():
    credential = await A2ACredentialResolver().resolve(
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


@pytest.mark.asyncio
async def test_credential_resolver_exchanges_oauth_client_credentials():
    http_client = FakeA2AHttpClient({})

    credential = await A2ACredentialResolver().resolve(
        card={
            "securitySchemes": {
                "oauth2ClientCredentials": {
                    "oauth2SecurityScheme": {
                        "flows": {
                            "clientCredentials": {
                                "tokenUrl": "https://registry.test/a2a/oauth/token",
                                "scopes": {
                                    "a2a:message": "Send messages",
                                    "a2a:tasks": "Read tasks",
                                },
                            }
                        }
                    }
                }
            },
            "securityRequirements": [
                {"schemes": {"oauth2ClientCredentials": {"list": ["a2a:message"]}}}
            ],
        },
        target_url="https://registry.test/a2a/agents/mail",
        config=A2ARegistryConfig.from_runtime_config(
            {
                "registry_set_name": "Test",
                "registry_urls": "https://registry.test/a2a/agents",
                "default_credentials": {"https://registry.test": "client-id:client-secret"},
            }
        ),
        http_client=http_client,
    )

    assert credential.result == A2AAuthResult.READY
    assert credential.headers == {"Authorization": "Bearer oauth-access-token"}
    assert http_client.oauth_requests == [
        {
            "token_url": "https://registry.test/a2a/oauth/token",
            "client_id": "client-id",
            "client_secret": "client-secret",
            "scopes": ["a2a:message"],
        }
    ]


@pytest.mark.asyncio
async def test_credential_resolver_requires_oauth_client_credentials_when_missing():
    credential = await A2ACredentialResolver().resolve(
        card={
            "securitySchemes": {
                "oauth2ClientCredentials": {
                    "oauth2SecurityScheme": {
                        "flows": {
                            "clientCredentials": {
                                "tokenUrl": "https://registry.test/a2a/oauth/token",
                                "scopes": {"a2a:message": "Send messages"},
                            }
                        }
                    }
                }
            },
            "securityRequirements": [{"schemes": {"oauth2ClientCredentials": {"list": ["a2a:message"]}}}],
        },
        target_url="https://registry.test/a2a/agents/mail",
        config=A2ARegistryConfig.from_runtime_config(
            {"registry_set_name": "Test", "registry_urls": "https://registry.test/a2a/agents"}
        ),
    )

    assert credential.result == A2AAuthResult.REQUIRED
    assert "OAuth 2.0 client credentials" in (credential.message or "")


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
            card_url="https://registry.test/a2a/agents/mail/card",
            name="Mail Agent",
        )
    )
    fake_http = FakeA2AHttpClient(
        {
            "https://registry.test/a2a/agents/mail/card": {
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
    monkeypatch.setattr("src.skills.agent2agent_client.oauth.settings.api_base_url", "http://localhost:8000")
    monkeypatch.setattr(A2AHttpClient, "get_agent_card", fake_http.get_agent_card)
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
    assert fake_http.sent[0]["preferred_protocols"][0] == "JSONRPC"


@pytest.mark.asyncio
async def test_send_message_missing_api_key_returns_credential_setup_link(monkeypatch):
    class FakePolicy:
        def validate_urls_for_user(self, *, user_email: str, urls: list[str]) -> None:
            assert user_email == "owner@example.com"

    agent_ref = encode_agent_ref(
        AgentRef(
            registry_url="https://registry.test/a2a/agents",
            service_url="https://registry.test/a2a/agents/notion",
            card_url="https://registry.test/a2a/agents/notion/card",
            name="Notion Manager",
        )
    )
    fake_http = FakeA2AHttpClient(
        {
            "https://registry.test/a2a/agents/notion/card": {
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
    monkeypatch.setattr(A2AHttpClient, "get_agent_card", fake_http.get_agent_card)
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
async def test_send_message_returns_remote_oauth_authorization_url(monkeypatch, dynamodb_table):
    class FakePolicy:
        def validate_urls_for_user(self, *, user_email: str, urls: list[str]) -> None:
            assert user_email == "owner@example.com"

    agent_ref = encode_agent_ref(
        AgentRef(
            registry_url="https://registry.test/a2a/agents",
            service_url="https://registry.test/a2a/agents/calendar",
            card_url="https://registry.test/a2a/agents/calendar/card",
            name="Calendar Agent",
        )
    )
    fake_http = FakeA2AHttpClient(
        {
            "https://registry.test/a2a/agents/calendar/card": {
                "name": "Calendar Agent",
                "description": "calendar",
                "supportedInterfaces": [
                    {
                        "url": "https://registry.test/a2a/agents/calendar",
                        "protocolBinding": "JSONRPC",
                        "protocolVersion": "1.0",
                    }
                ],
                "version": "1.0.0",
                "securitySchemes": {
                    "oauth": {
                        "oauth2SecurityScheme": {
                            "flows": {
                                "authorizationCode": {
                                    "authorizationUrl": "https://registry.test/oauth/authorize",
                                    "tokenUrl": "https://registry.test/oauth/token",
                                    "scopes": {"calendar.read": "Read calendar"},
                                    "pkceRequired": True,
                                }
                            }
                        }
                    }
                },
                "securityRequirements": [{"schemes": {"oauth": {"list": ["calendar.read"]}}}],
                "skills": [],
            },
        }
    )

    monkeypatch.setattr("src.skills.agent2agent_client.actions.Agent2AgentPolicy", FakePolicy)
    monkeypatch.setattr("src.skills.agent2agent_client.oauth.settings.api_base_url", "http://localhost:8000")
    monkeypatch.setattr(A2AHttpClient, "get_agent_card", fake_http.get_agent_card)
    monkeypatch.setattr(A2AHttpClient, "send_message", fake_http.send_message)

    result = await send_message(
        arguments={"agent_ref": agent_ref, "message": "hello"},
        config={
            "registry_set_name": "Test",
            "registry_urls": "https://registry.test/a2a/agents",
            "default_credentials": {
                "https://registry.test": {
                    "client_id": "calendar-client",
                    "client_secret": "calendar-secret",
                }
            },
        },
        context={
            "agent_id": "agent-123",
            "installed_skill_id": "agent2agent_client:test",
            "owner_email": "owner@example.com",
            "return_to": "http://localhost:5173/dashboard/agents/agent-123/skills",
        },
    )

    assert result["ok"] is False
    assert result["auth_required"] is True
    assert result["unsupported_auth"] is False
    assert result["credential_setup_label"] == "Connect Agent2Agent OAuth"
    parsed = urlparse(result["credential_setup_url"])
    query = parse_qs(parsed.query)
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == "https://registry.test/oauth/authorize"
    assert query["client_id"] == ["calendar-client"]
    assert query["redirect_uri"] == ["http://localhost:8000/skills/agent2agent_client/oauth/callback"]
    assert query["scope"] == ["calendar.read"]
    assert query["code_challenge_method"] == ["S256"]
    session = decode_state_session(query["state"][0])
    assert session is not None
    assert session.target_origin == "https://registry.test"
    assert session.installed_skill_id == "agent2agent_client:test"


def test_agent2agent_oauth_callback_stores_access_and_refresh_tokens(test_client, monkeypatch, dynamodb_table):
    from src.skills.agent2agent_client.oauth import (
        build_authorization_url,
        create_state_session,
        encode_state_session,
        generate_code_challenge,
    )

    async def fake_exchange_code_for_tokens(*, provider, code: str, code_verifier: str):
        assert provider.client_id == "calendar-client"
        assert code == "auth-code"
        assert code_verifier
        return {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "expires_in": 3600,
            "token_type": "Bearer",
            "scope": "calendar.read",
        }

    monkeypatch.setattr("src.skills.agent2agent_client.oauth.settings.api_base_url", "http://localhost:8000")
    provider = A2ARemoteOAuthProviderConfig(
        authorization_url="https://registry.test/oauth/authorize",
        token_url="https://registry.test/oauth/token",
        client_id="calendar-client",
        client_secret="calendar-secret",
        scope="calendar.read",
        target_origin="https://registry.test",
    )
    session = create_state_session(
        user_email="owner@example.com",
        agent_id="agent-123",
        installed_skill_id="agent2agent_client:test",
        service_url="https://registry.test/a2a/agents/calendar",
        return_to="http://localhost:5173/dashboard/agents/agent-123/skills",
        provider=provider,
    )
    state = encode_state_session(session)
    authorize_url = build_authorization_url(
        provider=provider,
        state=state,
        code_challenge=generate_code_challenge(session.code_verifier),
    )
    assert (
        "redirect_uri=http%3A%2F%2Flocalhost%3A8000"
        "%2Fskills%2Fagent2agent_client%2Foauth%2Fcallback"
    ) in authorize_url

    monkeypatch.setattr(
        "src.skills.agent2agent_client.router.exchange_code_for_tokens",
        fake_exchange_code_for_tokens,
    )

    response = test_client.get(
        "/skills/agent2agent_client/oauth/callback",
        params={"code": "auth-code", "state": state},
        follow_redirects=False,
    )

    assert response.status_code == 307
    assert "a2a_oauth=success" in response.headers["location"]
    record = A2ARemoteOAuthRepository().find(
        owner_email="owner@example.com",
        installed_skill_id="agent2agent_client:test",
        target_origin="https://registry.test",
    )
    assert record is not None
    auth = decrypt_auth_config(record)
    assert auth.credentials is not None
    assert auth.credentials.access_token == "access-token"
    assert auth.credentials.refresh_token == "refresh-token"


@pytest.mark.asyncio
async def test_send_message_refreshes_saved_remote_oauth_token(monkeypatch, dynamodb_table):
    class FakePolicy:
        def validate_urls_for_user(self, *, user_email: str, urls: list[str]) -> None:
            assert user_email == "owner@example.com"

    async def fake_refresh_access_token(*, provider, refresh_token: str):
        assert provider.token_url == "https://registry.test/oauth/token"
        assert refresh_token == "old-refresh"
        return {
            "access_token": "new-access",
            "refresh_token": "new-refresh",
            "expires_in": 3600,
            "token_type": "Bearer",
            "scope": "calendar.read",
        }

    agent_ref = encode_agent_ref(
        AgentRef(
            registry_url="https://registry.test/a2a/agents",
            service_url="https://registry.test/a2a/agents/calendar",
            card_url="https://registry.test/a2a/agents/calendar/card",
            name="Calendar Agent",
        )
    )
    provider = A2ARemoteOAuthProviderConfig(
        authorization_url="https://registry.test/oauth/authorize",
        token_url="https://registry.test/oauth/token",
        client_id="calendar-client",
        client_secret="calendar-secret",
        scope="calendar.read",
        target_origin="https://registry.test",
    )
    A2ARemoteOAuthRepository().save(
        A2ARemoteOAuthCredentialRecord(
            owner_email="owner@example.com",
            agent_id="agent-123",
            installed_skill_id="agent2agent_client:test",
            target_origin="https://registry.test",
            encrypted_auth_config=encrypt_auth_config(
                A2ARemoteOAuthAuthConfig(
                    provider=provider,
                    credentials=A2ARemoteOAuthCredentials(
                        access_token="old-access",
                        refresh_token="old-refresh",
                        expires_at=datetime.now(timezone.utc) + timedelta(seconds=30),
                        token_type="Bearer",
                        scope="calendar.read",
                    ),
                )
            ),
        )
    )
    fake_http = FakeA2AHttpClient(
        {
            "https://registry.test/a2a/agents/calendar/card": {
                "name": "Calendar Agent",
                "description": "calendar",
                "supportedInterfaces": [
                    {
                        "url": "https://registry.test/a2a/agents/calendar",
                        "protocolBinding": "JSONRPC",
                        "protocolVersion": "1.0",
                    }
                ],
                "version": "1.0.0",
                "securitySchemes": {
                    "oauth": {
                        "oauth2SecurityScheme": {
                            "flows": {
                                "authorizationCode": {
                                    "authorizationUrl": "https://registry.test/oauth/authorize",
                                    "tokenUrl": "https://registry.test/oauth/token",
                                    "scopes": {"calendar.read": "Read calendar"},
                                }
                            }
                        }
                    }
                },
                "securityRequirements": [{"schemes": {"oauth": {"list": ["calendar.read"]}}}],
                "skills": [],
            },
        }
    )

    monkeypatch.setattr("src.skills.agent2agent_client.actions.Agent2AgentPolicy", FakePolicy)
    monkeypatch.setattr("src.skills.agent2agent_client.oauth.refresh_access_token", fake_refresh_access_token)
    monkeypatch.setattr(A2AHttpClient, "get_agent_card", fake_http.get_agent_card)
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

    assert result["ok"] is True
    assert fake_http.sent[0]["headers"] == {"Authorization": "Bearer new-access"}


@pytest.mark.asyncio
async def test_a2a_client_returns_structured_timeout(monkeypatch):
    async def raise_timeout(*args, **kwargs):
        raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr(httpx.AsyncClient, "send", raise_timeout)

    result = await A2AHttpClient().send_message(
        agent_card={
            "name": "Slow Agent",
            "description": "slow",
            "supportedInterfaces": [
                {
                    "url": "https://registry.test/a2a/agents/slow",
                    "protocolBinding": "JSONRPC",
                    "protocolVersion": "1.0",
                }
            ],
            "version": "1.0.0",
            "capabilities": {},
            "securitySchemes": {},
            "securityRequirements": [],
            "defaultInputModes": ["text/plain"],
            "defaultOutputModes": ["text/plain"],
            "skills": [],
        },
        request=SendMessageRequest(agent_ref="unused", message="hello", timeout_seconds=7),
        headers={},
        preferred_protocols=["JSONRPC"],
    )

    assert result == {
        "ok": False,
        "status_code": 504,
        "message": "Remote A2A request timed out after 7 seconds.",
    }
