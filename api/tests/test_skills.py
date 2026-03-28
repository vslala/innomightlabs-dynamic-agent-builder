from __future__ import annotations

import asyncio

from src.agents.models import Agent
from src.agents.repository import AgentRepository
from src.settings.models import ProviderSettings
from src.settings.repository import ProviderSettingsRepository
from src.skills.lead_capture.forms import parse_custom_inputs
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
    google_drive = next(item for item in payload if item["skill_id"] == "google_drive")
    assert google_drive["requires_oauth"] is True
    assert google_drive["oauth_provider_name"] == "GoogleDrive"
    assert google_drive["oauth_connected"] is False


def test_list_skills_catalog_reports_google_drive_connected(test_client, auth_headers, dynamodb_table):
    from tests.mock_data import TEST_USER_EMAIL

    repo = ProviderSettingsRepository()
    repo.save(
        ProviderSettings(
            user_email=TEST_USER_EMAIL,
            provider_name="GoogleDrive",
            encrypted_credentials="encrypted",
            auth_type="oauth",
        )
    )

    response = test_client.get("/skills", headers=auth_headers)
    assert response.status_code == 200
    payload = response.json()
    google_drive = next(item for item in payload if item["skill_id"] == "google_drive")
    assert google_drive["oauth_connected"] is True


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


def test_google_drive_install_requires_connected_provider_settings(test_client, auth_headers, dynamodb_table):
    from tests.mock_data import TEST_USER_EMAIL

    agent = _create_agent_for_user(TEST_USER_EMAIL)
    install_resp = test_client.post(
        f"/agents/{agent.agent_id}/skills?skill_id=google_drive",
        headers=auth_headers,
        json={"config": {}},
    )

    assert install_resp.status_code == 400
    assert "requires a connected GoogleDrive account" in install_resp.json()["detail"]


def test_google_drive_install_succeeds_when_provider_connected(test_client, auth_headers, dynamodb_table):
    from tests.mock_data import TEST_USER_EMAIL

    repo = ProviderSettingsRepository()
    repo.save(
        ProviderSettings(
            user_email=TEST_USER_EMAIL,
            provider_name="GoogleDrive",
            encrypted_credentials="encrypted",
            auth_type="oauth",
        )
    )
    agent = _create_agent_for_user(TEST_USER_EMAIL)

    install_resp = test_client.post(
        f"/agents/{agent.agent_id}/skills?skill_id=google_drive",
        headers=auth_headers,
        json={"config": {}},
    )

    assert install_resp.status_code == 201
    payload = install_resp.json()
    assert payload["skill_id"] == "google_drive"
    assert payload["config"] == {}


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
        assert context.get("owner_email") == TEST_USER_EMAIL
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
                owner_email=TEST_USER_EMAIL,
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
            owner_email=TEST_USER_EMAIL,
            actor_email=TEST_USER_EMAIL,
            actor_id=TEST_USER_EMAIL,
            conversation_id="conv-test",
        )
    )

    assert result == "ok"


def test_lead_capture_custom_form_normalizes_common_input_type_aliases():
    inputs = parse_custom_inputs(
        [
            {
                "input_type": "email",
                "name": "email",
                "label": "Work email",
                "attr": {"placeholder": "name@company.com"},
            },
            {
                "input_type": "textarea",
                "name": "requirements",
                "label": "Requirements",
            },
            {
                "input_type": "radio",
                "name": "contact_consent",
                "label": "Consent",
                "values": ["yes"],
            },
        ]
    )

    assert inputs[0].input_type.value == "text"
    assert inputs[0].attr == {
        "type": "email",
        "placeholder": "name@company.com",
    }
    assert inputs[1].input_type.value == "text_area"
    assert inputs[2].input_type.value == "choice"
    assert inputs[2].attr == {"variant": "radio"}


def test_lead_capture_custom_form_rejects_unknown_input_types():
    try:
        parse_custom_inputs(
            [
                {
                    "input_type": "date",
                    "name": "start_date",
                    "label": "Start date",
                }
            ]
        )
        assert False, "Expected ValueError for unsupported input_type"
    except ValueError as exc:
        assert "Invalid input_type for form_inputs[0]" in str(exc)
        assert "Unsupported input_type 'date'" in str(exc)


def test_lead_capture_manifest_declares_strict_custom_form_schema():
    runtime = SkillRuntimeService()
    loaded = runtime.skill_service.registry.get("lead_capture")
    assert loaded is not None

    action = next(a for a in loaded.manifest.actions if a.name == "render_custom_form")
    form_inputs = action.input_schema["properties"]["form_inputs"]
    item_props = form_inputs["items"]["properties"]

    assert item_props["input_type"]["enum"] == ["text", "text_area", "select", "choice"]
    assert "Do not use email" in item_props["input_type"]["description"]
    assert form_inputs["items"]["additionalProperties"] is False
