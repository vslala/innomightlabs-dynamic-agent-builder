from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from src.agent_marketplace.models import (
    ImportMarketplaceAgentRequest,
    MarketplaceAgentSkillTemplate,
    MarketplaceAgentStatus,
    MarketplaceAgentTemplate,
)
from src.agent_marketplace.repository import AgentMarketplaceRepository
from src.agent_marketplace.service import AgentMarketplaceService
from src.agents.models import Agent
from src.agents.repository import AgentRepository
from src.skills.service import SkillService
from tests.mock_data import TEST_USER_EMAIL, TEST_USER_EMAIL_2


def _create_agent(user_email: str = TEST_USER_EMAIL) -> Agent:
    return AgentRepository().save(
        Agent(
            agent_name="Marketplace Source Agent",
            agent_architecture="krishna-mini",
            agent_provider="Bedrock",
            agent_model="claude-3-7-sonnet",
            agent_persona="You are a marketplace-ready assistant.",
            agent_description="Marketplace source",
            created_by=user_email,
        )
    )


def test_marketplace_publish_import_and_secret_stripping(test_client: TestClient, auth_headers: dict, dynamodb_table):
    agent = _create_agent()
    skill_service = SkillService()
    skill_service.install_skill(
        agent_id=agent.agent_id,
        skill_id="wordpress_search",
        user_email=TEST_USER_EMAIL,
        raw_config={
            "site_url": "https://example.com",
            "username": "admin",
            "app_password": "secret-pass",
        },
    )

    publish_response = test_client.post(
        "/agent-marketplace/agents/publish",
        headers=auth_headers,
        json={
            "agent_id": agent.agent_id,
            "title": "WordPress Helper",
            "short_description": "Searches a WordPress site.",
            "full_description": "A reusable agent for searching a WordPress site.",
            "tags": ["wordpress", "search"],
            "included_skill_ids": ["wordpress_search"],
            "status": "published",
        },
    )

    assert publish_response.status_code == 201
    template_id = publish_response.json()["template_id"]
    template = AgentMarketplaceRepository().find_by_id(template_id)
    assert template is not None
    assert template.status == MarketplaceAgentStatus.PUBLISHED
    assert template.skills[0].default_config["site_url"] == "https://example.com"
    assert "app_password" not in template.skills[0].default_config

    import_response = test_client.post(
        f"/agent-marketplace/agents/{template_id}/import",
        headers=auth_headers,
        json={
            "agent_name": "Imported WordPress Helper",
            "agent_provider": "Bedrock",
            "agent_model": "claude-3-7-sonnet",
            "skill_configs": {
                "wordpress_search": {
                    "app_password": "importer-secret",
                }
            },
        },
    )

    assert import_response.status_code == 201
    imported = import_response.json()
    imported_agent = AgentRepository().find_agent_by_id(imported["agent_id"], TEST_USER_EMAIL)
    assert imported_agent is not None
    assert imported_agent.agent_name == "Imported WordPress Helper"

    installed_raw = dynamodb_table.get_item(
        Key={"pk": f"Agent#{imported_agent.agent_id}", "sk": "Skill#wordpress_search"}
    )["Item"]
    assert installed_raw["config"]["site_url"] == "https://example.com"
    assert installed_raw["encrypted_secrets"]


def test_marketplace_list_ranks_by_import_count_recency_then_title(dynamodb_table):
    del dynamodb_table
    repo = AgentMarketplaceRepository()
    older = repo.save(
        MarketplaceAgentTemplate(
            title="Alpha",
            short_description="Alpha",
            full_description="Alpha",
            agent_name="Alpha",
            agent_architecture="krishna-mini",
            agent_provider="Bedrock",
            agent_model="claude-3-7-sonnet",
            agent_persona="Alpha",
            status=MarketplaceAgentStatus.PUBLISHED,
            import_count=2,
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
    )
    newer = repo.save(
        MarketplaceAgentTemplate(
            title="Beta",
            short_description="Beta",
            full_description="Beta",
            agent_name="Beta",
            agent_architecture="krishna-mini",
            agent_provider="Bedrock",
            agent_model="claude-3-7-sonnet",
            agent_persona="Beta",
            status=MarketplaceAgentStatus.PUBLISHED,
            import_count=2,
            created_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
        )
    )
    popular = repo.save(
        MarketplaceAgentTemplate(
            title="Zoo",
            short_description="Zoo",
            full_description="Zoo",
            agent_name="Zoo",
            agent_architecture="krishna-mini",
            agent_provider="Bedrock",
            agent_model="claude-3-7-sonnet",
            agent_persona="Zoo",
            status=MarketplaceAgentStatus.PUBLISHED,
            import_count=10,
            created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )
    )

    listed = repo.list_latest_published()

    assert [item.template_id for item in listed[:3]] == [
        popular.template_id,
        newer.template_id,
        older.template_id,
    ]


def test_marketplace_publishing_same_agent_creates_new_version(test_client: TestClient, auth_headers: dict):
    agent = _create_agent()
    payload = {
        "agent_id": agent.agent_id,
        "title": "Versioned Agent",
        "short_description": "Version one",
        "full_description": "Version one",
        "tags": [],
        "included_skill_ids": [],
        "status": "published",
    }

    first = test_client.post("/agent-marketplace/agents/publish", headers=auth_headers, json=payload)
    second = test_client.post(
        "/agent-marketplace/agents/publish",
        headers=auth_headers,
        json={**payload, "short_description": "Version two", "full_description": "Version two"},
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["template_version"] == 1
    assert second.json()["template_version"] == 2
    assert first.json()["template_id"] != second.json()["template_id"]


def test_marketplace_publish_rejects_unowned_agent(test_client: TestClient, auth_headers: dict):
    other_agent = _create_agent(TEST_USER_EMAIL_2)

    response = test_client.post(
        "/agent-marketplace/agents/publish",
        headers=auth_headers,
        json={
            "agent_id": other_agent.agent_id,
            "title": "Not Mine",
            "short_description": "No",
            "full_description": "No",
            "tags": [],
            "included_skill_ids": [],
            "status": "published",
        },
    )

    assert response.status_code == 400


def test_marketplace_import_installs_oauth_skill_disabled_without_connection(dynamodb_table):
    template = AgentMarketplaceRepository().save(
        MarketplaceAgentTemplate(
            title="Drive Agent",
            short_description="Drive",
            full_description="Drive",
            agent_name="Drive Agent",
            agent_architecture="krishna-mini",
            agent_provider="Bedrock",
            agent_model="claude-3-7-sonnet",
            agent_persona="Use Drive.",
            status=MarketplaceAgentStatus.PUBLISHED,
            skills=[
                MarketplaceAgentSkillTemplate(
                    template_skill_key="google_drive",
                    skill_id="google_drive",
                    display_name="Google Drive",
                    enabled_on_import=False,
                    required=True,
                )
            ],
        )
    )

    imported = AgentMarketplaceService().import_agent(
        template_id=template.template_id,
        user_email=TEST_USER_EMAIL,
        request=ImportMarketplaceAgentRequest(
            agent_name="Imported Drive",
            agent_provider="Bedrock",
            agent_model="claude-3-7-sonnet",
            skill_configs={"google_drive": {}},
        ),
    )

    raw_skill = dynamodb_table.get_item(
        Key={"pk": f"Agent#{imported.agent_id}", "sk": "Skill#google_drive"}
    )["Item"]
    assert raw_skill["enabled"] is False
