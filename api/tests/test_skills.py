from __future__ import annotations

import asyncio

from src.agents.models import Agent
from src.agents.repository import AgentRepository
from src.skills.service import SkillRuntimeService


def _create_agent_for_user(user_email: str) -> Agent:
    repo = AgentRepository()
    agent = Agent(
        agent_name="Skill Test Agent",
        agent_architecture="krishna-memgpt",
        agent_provider="Bedrock",
        agent_model="claude-3-7-sonnet",
        agent_persona="Helpful",
        created_by=user_email,
    )
    return repo.save(agent)


def test_list_skills_catalog(test_client, auth_headers):
    response = test_client.get("/skills", headers=auth_headers)
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    assert any(item["skill_id"] == "wordpress_search" for item in payload)


def test_skill_install_update_and_uninstall_flow(test_client, auth_headers, dynamodb_table):
    from tests.mock_data import TEST_USER_EMAIL

    agent = _create_agent_for_user(TEST_USER_EMAIL)

    schema_resp = test_client.get(f"/skills/wordpress_search/install-schema", headers=auth_headers)
    assert schema_resp.status_code == 200
    schema = schema_resp.json()
    field_names = [field["name"] for field in schema["form_inputs"]]
    assert "site_url" in field_names
    assert "app_password" in field_names

    install_resp = test_client.post(
        f"/agents/{agent.agent_id}/skills?skill_id=wordpress_search",
        headers=auth_headers,
        json={
            "config": {
                "site_url": "https://example.com",
                "username": "admin",
                "app_password": "secret-pass",
            }
        },
    )
    assert install_resp.status_code == 201
    installed = install_resp.json()
    assert installed["skill_id"] == "wordpress_search"
    assert installed["enabled"] is True
    assert installed["config"]["site_url"] == "https://example.com"
    assert "app_password" not in installed["config"]
    assert "app_password" in installed["secret_fields"]

    # Verify raw DynamoDB item: plain config and encrypted secret blob split
    raw = dynamodb_table.get_item(
        Key={"pk": f"Agent#{agent.agent_id}", "sk": "Skill#wordpress_search"}
    )["Item"]
    assert raw["config"]["site_url"] == "https://example.com"
    assert raw["encrypted_secrets"]

    list_resp = test_client.get(f"/agents/{agent.agent_id}/skills", headers=auth_headers)
    assert list_resp.status_code == 200
    listed = list_resp.json()
    assert len(listed) == 1
    assert listed[0]["skill_id"] == "wordpress_search"

    update_resp = test_client.patch(
        f"/agents/{agent.agent_id}/skills/wordpress_search",
        headers=auth_headers,
        json={"enabled": False, "config": {"site_url": "https://example.org"}},
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()
    assert updated["enabled"] is False
    assert updated["config"]["site_url"] == "https://example.org"

    delete_resp = test_client.delete(
        f"/agents/{agent.agent_id}/skills/wordpress_search",
        headers=auth_headers,
    )
    assert delete_resp.status_code == 204

    list_after_delete = test_client.get(f"/agents/{agent.agent_id}/skills", headers=auth_headers)
    assert list_after_delete.status_code == 200
    assert list_after_delete.json() == []


def test_execute_skill_action_requires_nested_arguments(test_client, auth_headers, dynamodb_table, monkeypatch):
    from tests.mock_data import TEST_USER_EMAIL

    agent = _create_agent_for_user(TEST_USER_EMAIL)
    install_resp = test_client.post(
        f"/agents/{agent.agent_id}/skills?skill_id=wordpress_search",
        headers=auth_headers,
        json={
            "config": {
                "site_url": "https://example.com",
            }
        },
    )
    assert install_resp.status_code == 201

    runtime = SkillRuntimeService()

    async def fake_execute_action(skill_id, action_name, arguments, config, context):
        assert skill_id == "wordpress_search"
        assert action_name == "search"
        assert arguments.get("query") == "pricing"
        assert config.get("site_url") == "https://example.com"
        return "ok"

    monkeypatch.setattr(runtime.skill_service.registry, "execute_action", fake_execute_action)

    # Wrong shape: query at top-level should fail
    try:
        asyncio.run(
            runtime.handle_tool_call(
                tool_name="execute_skill_action",
                tool_input={
                    "skill_id": "wordpress_search",
                    "action": "search",
                    "query": "pricing",
                },
                agent_id=agent.agent_id,
                actor_email=TEST_USER_EMAIL,
                actor_id=TEST_USER_EMAIL,
                conversation_id="conv-test",
            )
        )
        assert False, "Expected ValueError for invalid argument shape"
    except ValueError as exc:
        assert "'arguments' must be an object" in str(exc)

    # Correct shape: nested arguments
    result = asyncio.run(
        runtime.handle_tool_call(
            tool_name="execute_skill_action",
            tool_input={
                "skill_id": "wordpress_search",
                "action": "search",
                "arguments": {"query": "pricing"},
            },
            agent_id=agent.agent_id,
            actor_email=TEST_USER_EMAIL,
            actor_id=TEST_USER_EMAIL,
            conversation_id="conv-test",
        )
    )

    assert result == "ok"
