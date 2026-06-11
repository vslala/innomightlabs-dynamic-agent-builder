from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from src.agents.models import Agent
from src.agents.repository import AgentRepository
from src.conversations.models import Conversation
from src.conversations.repository import ConversationRepository
from src.scheduler.repository import SchedulerRepository
from src.settings.models import ProviderSettings
from src.settings.repository import ProviderSettingsRepository
from src.skills.lead_capture.forms import parse_custom_inputs
from src.skills.lifecycle import SkillLifecycleRunner
from src.skills.service import SkillRuntimeService, SkillService


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
    assert google_drive["oauth_start_path"] == "/auth/google-drive/start"
    google_mail = next(item for item in payload if item["skill_id"] == "google_mail")
    assert google_mail["requires_oauth"] is True
    assert google_mail["oauth_provider_name"] == "GoogleMail"
    assert google_mail["oauth_connected"] is False
    assert google_mail["oauth_start_path"] == "/auth/google-mail/start"
    scheduler = next(item for item in payload if item["skill_id"] == "scheduler")
    assert scheduler["name"] == "Scheduler"
    assert scheduler["action_names"] == [
        "create_or_update",
        "schedule_automation",
        "pause",
        "resume",
        "delete",
        "list",
    ]
    image_generation = next(item for item in payload if item["skill_id"] == "image_generation")
    assert image_generation["name"] == "Image Generation"
    assert image_generation["action_names"] == ["generate"]


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


def test_agent_skill_uninstall_runs_skill_delete_lifecycle(dynamodb_table):
    from tests.mock_data import TEST_USER_EMAIL

    calls = []

    class FakeLifecycleRunner:
        def run_skill_delete(self, **kwargs):
            calls.append(kwargs)

    agent = _create_agent_for_user(TEST_USER_EMAIL)
    service = SkillService(lifecycle_runner=FakeLifecycleRunner())
    service.install_skill(
        agent_id=agent.agent_id,
        skill_id="wordpress_search",
        user_email=TEST_USER_EMAIL,
        raw_config={
            "site_url": "https://example.com",
            "username": "admin",
            "app_password": "secret-pass",
        },
    )

    deleted = service.uninstall(
        agent_id=agent.agent_id,
        installed_skill_id="wordpress_search",
        user_email=TEST_USER_EMAIL,
    )

    assert deleted is True
    assert len(calls) == 1
    assert calls[0]["skill_id"] == "wordpress_search"
    assert calls[0]["installed_skill_id"] == "wordpress_search"
    assert calls[0]["owner_email"] == TEST_USER_EMAIL
    assert calls[0]["config"]["site_url"] == "https://example.com"
    assert calls[0]["config"]["app_password"] == "secret-pass"
    assert calls[0]["metadata"]["agent_id"] == agent.agent_id


def test_skill_lifecycle_hook_failure_does_not_raise(monkeypatch):
    runner = SkillLifecycleRunner()

    def broken_handler(*args, **kwargs):
        raise RuntimeError("hook failed")

    monkeypatch.setattr(runner.registry, "_resolve_handler", broken_handler)

    runner.run_action_delete(
        skill_id="scheduler",
        installed_skill_id="scheduler",
        action_name="schedule_automation",
        owner_email="user@example.com",
        config={},
        arguments={},
        metadata={"automation_id": "automation-1", "automation_node_id": "node-1"},
    )


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
    assert payload["requires_oauth"] is True
    assert payload["oauth_provider_name"] == "GoogleDrive"


def test_oauth_skill_uninstall_keeps_provider_settings_by_default(test_client, auth_headers, dynamodb_table):
    from tests.mock_data import TEST_USER_EMAIL

    repo = ProviderSettingsRepository()
    repo.save(
        ProviderSettings(
            user_email=TEST_USER_EMAIL,
            provider_name="GoogleMail",
            encrypted_credentials="encrypted",
            auth_type="oauth",
        )
    )
    agent = _create_agent_for_user(TEST_USER_EMAIL)

    install_resp = test_client.post(
        f"/agents/{agent.agent_id}/skills?skill_id=google_mail",
        headers=auth_headers,
        json={"config": {}},
    )
    assert install_resp.status_code == 201

    delete_resp = test_client.delete(
        f"/agents/{agent.agent_id}/skills/google_mail",
        headers=auth_headers,
    )
    assert delete_resp.status_code == 204
    assert repo.find_by_provider(TEST_USER_EMAIL, "GoogleMail") is not None


def test_oauth_skill_uninstall_can_disconnect_provider_settings(test_client, auth_headers, dynamodb_table):
    from tests.mock_data import TEST_USER_EMAIL

    repo = ProviderSettingsRepository()
    repo.save(
        ProviderSettings(
            user_email=TEST_USER_EMAIL,
            provider_name="GoogleMail",
            encrypted_credentials="encrypted",
            auth_type="oauth",
        )
    )
    agent = _create_agent_for_user(TEST_USER_EMAIL)

    install_resp = test_client.post(
        f"/agents/{agent.agent_id}/skills?skill_id=google_mail",
        headers=auth_headers,
        json={"config": {}},
    )
    assert install_resp.status_code == 201

    delete_resp = test_client.delete(
        f"/agents/{agent.agent_id}/skills/google_mail?disconnect_oauth=true",
        headers=auth_headers,
    )
    assert delete_resp.status_code == 204
    assert repo.find_by_provider(TEST_USER_EMAIL, "GoogleMail") is None


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


def test_skill_runtime_passes_user_message_id_to_actions(test_client, auth_headers, dynamodb_table, monkeypatch):
    from tests.mock_data import TEST_USER_EMAIL

    agent = _create_agent_for_user(TEST_USER_EMAIL)
    install_resp = test_client.post(
        f"/agents/{agent.agent_id}/skills?skill_id=image_generation",
        headers=auth_headers,
        json={"config": {}},
    )
    assert install_resp.status_code == 201

    runtime = SkillRuntimeService()

    async def fake_execute_action(skill_id, action_name, arguments, config, context):
        assert skill_id == "image_generation"
        assert action_name == "generate"
        assert arguments == {"prompt": "A product mockup"}
        assert config == {}
        assert context["user_message_id"] == "user-message-1"
        return {"ok": True}

    monkeypatch.setattr(runtime.skill_service.registry, "execute_action", fake_execute_action)

    result = asyncio.run(
        runtime.handle_tool_call(
            tool_name="execute_skill_action",
            tool_input={
                "skill_id": "image_generation",
                "action": "generate",
                "arguments": {"prompt": "A product mockup"},
            },
            agent_id=agent.agent_id,
            owner_email=TEST_USER_EMAIL,
            actor_email=TEST_USER_EMAIL,
            actor_id=TEST_USER_EMAIL,
            conversation_id="conv-test",
            user_message_id="user-message-1",
        )
    )

    assert json.loads(result) == {"ok": True}


def test_image_generation_skill_action_uses_agent_turn_service(monkeypatch):
    from src.skills.image_generation.actions import generate
    from src.llm.events import SSEEvent, SSEEventType

    captured = {}

    class FakeService:
        async def stream_for_agent_turn(self, **kwargs):
            captured.update(kwargs)
            yield SSEEvent(
                event_type=SSEEventType.IMAGE_GENERATION_PARTIAL,
                content="Rendering image preview...",
                image_b64="abc123",
                image_mime_type="image/png",
            )
            yield SSEEvent(
                event_type=SSEEventType.IMAGE_GENERATION_COMPLETE,
                content="Image generation complete",
                message_id="assistant-message-1",
                images=[
                    {
                        "image_id": "image-1",
                        "url": "https://signed.example/image.png",
                        "filename": "generated-image-1.png",
                        "mime_type": "image/png",
                    }
                ],
            )

    monkeypatch.setattr(
        "src.skills.image_generation.actions.AgentImageGenerationService",
        lambda: FakeService(),
    )

    result = asyncio.run(
        generate(
            arguments={
                "prompt": "A clean SaaS dashboard hero image",
                "size": "1024x1024",
                "quality": "high",
                "output_format": "webp",
            },
            config={},
            context={
                "agent_id": "agent-1",
                "conversation_id": "conversation-1",
                "owner_email": "owner@example.com",
                "actor_email": "actor@example.com",
                "user_message_id": "user-message-1",
            },
        )
    )

    assert captured["agent_id"] == "agent-1"
    assert captured["conversation_id"] == "conversation-1"
    assert captured["owner_email"] == "owner@example.com"
    assert captured["actor_email"] == "actor@example.com"
    assert captured["user_message_id"] == "user-message-1"
    assert captured["request"].prompt == "A clean SaaS dashboard hero image"
    assert captured["request"].size == "1024x1024"
    assert captured["request"].quality == "high"
    assert captured["request"].output_format == "webp"
    assert result["type"] == "generated_image"
    assert result["assistant_message_id"] == "assistant-message-1"
    assert result["images"][0]["url"] == "https://signed.example/image.png"


def test_agent_invocation_runs_as_agent_skill(test_client, auth_headers, dynamodb_table, monkeypatch):
    from tests.mock_data import TEST_USER_EMAIL

    source_agent = _create_agent_for_user(TEST_USER_EMAIL)
    target_agent = _create_agent_for_user(TEST_USER_EMAIL)
    conversation = ConversationRepository().save(
        Conversation(
            title="Agent skill invocation",
            agent_id=source_agent.agent_id,
            created_by=TEST_USER_EMAIL,
        )
    )

    install_resp = test_client.post(
        f"/agents/{source_agent.agent_id}/skills?skill_id=agent_invocation",
        headers=auth_headers,
        json={
            "config": {
                "target_agent_id": target_agent.agent_id,
                "usage_description": "Use for lead summaries that need a specialist agent.",
            }
        },
    )
    assert install_resp.status_code == 201
    installed_skill_id = install_resp.json()["installed_skill_id"]
    assert installed_skill_id.startswith("agent_invocation:")

    captured = {}
    captured_repositories = []

    class FakeArchitecture:
        async def handle_message_buffered(
            self,
            *,
            agent,
            conversation,
            user_message,
            owner_email,
            actor_email,
            actor_id,
            attachments=None,
        ):
            captured.update(
                {
                    "agent_id": agent.agent_id,
                    "conversation_id": conversation.conversation_id,
                    "user_message": user_message,
                    "owner_email": owner_email,
                    "actor_email": actor_email,
                    "actor_id": actor_id,
                    "attachments": attachments,
                }
            )
            return SimpleNamespace(
                success=True,
                error=None,
                response_text="delegated response",
                events=[],
                user_message_id="user-message-1",
                assistant_message_id="assistant-message-1",
            )

    monkeypatch.setattr(
        "src.skills.agent_invocation.actions.get_agent_architecture",
        lambda architecture_name, *, message_repository=None: (
            captured_repositories.append(message_repository) or FakeArchitecture()
        ),
    )

    result = asyncio.run(
        SkillRuntimeService().handle_tool_call(
            tool_name="execute_skill_action",
            tool_input={
                "skill_id": "agent_invocation",
                "action": "invoke",
                "arguments": {
                    "prompt_template": "Summarize the lead",
                },
            },
            agent_id=source_agent.agent_id,
            owner_email=TEST_USER_EMAIL,
            actor_email=TEST_USER_EMAIL,
            actor_id=TEST_USER_EMAIL,
            conversation_id=conversation.conversation_id,
        )
    )

    payload = json.loads(result)
    assert payload["response_text"] == "delegated response"
    assert payload["message_ids"] == {
        "user_message_id": "user-message-1",
        "assistant_message_id": "assistant-message-1",
    }
    assert captured == {
        "agent_id": target_agent.agent_id,
        "conversation_id": conversation.conversation_id,
        "user_message": "Summarize the lead",
        "owner_email": TEST_USER_EMAIL,
        "actor_email": TEST_USER_EMAIL,
        "actor_id": TEST_USER_EMAIL,
        "attachments": None,
    }
    assert len(captured_repositories) == 1
    assert captured_repositories[0].__class__.__name__ == "InMemoryMessageRepository"

    loaded_payload = json.loads(
        asyncio.run(
            SkillRuntimeService().handle_tool_call(
                tool_name="load_skill",
                tool_input={"skill_id": "agent_invocation"},
                agent_id=source_agent.agent_id,
                owner_email=TEST_USER_EMAIL,
                actor_email=TEST_USER_EMAIL,
                actor_id=TEST_USER_EMAIL,
                conversation_id=conversation.conversation_id,
            )
        )
    )
    assert loaded_payload["installed_skill_id"] == installed_skill_id
    assert loaded_payload["execute_contract"]["required_shape"]["skill_id"] == installed_skill_id
    assert loaded_payload["usage_context"] == [
        {
            "name": "usage_description",
            "label": "Use when",
            "value": "Use for lead summaries that need a specialist agent.",
        }
    ]
    prompt_addendum = SkillRuntimeService().build_system_prompt_addendum(
        SkillRuntimeService().list_enabled(source_agent.agent_id)
    )
    assert "Use when: Use for lead summaries that need a specialist agent." in prompt_addendum


def test_agent_invocation_install_schema_hydrates_agent_options(test_client, auth_headers, dynamodb_table):
    from tests.mock_data import TEST_USER_EMAIL

    agent = _create_agent_for_user(TEST_USER_EMAIL)

    response = test_client.get("/skills/agent_invocation/install-schema", headers=auth_headers)

    assert response.status_code == 200
    schema = response.json()
    target_field = next(field for field in schema["form_inputs"] if field["name"] == "target_agent_id")
    assert target_field["options_source"] == {
        "type": "agents",
        "mode": "hydrate",
    }
    assert {"value": agent.agent_id, "label": agent.agent_name} in target_field["options"]
    usage_field = next(field for field in schema["form_inputs"] if field["name"] == "usage_description")
    assert usage_field["label"] == "When should this agent be invoked?"
    assert usage_field["attr"]["expose_to_runtime"] == "true"


def test_scheduler_skill_creates_conversation_bound_schedule(test_client, auth_headers, dynamodb_table):
    from tests.mock_data import TEST_USER_EMAIL

    agent = _create_agent_for_user(TEST_USER_EMAIL)
    conversation = ConversationRepository().save(
        Conversation(
            title="Scheduler skill",
            agent_id=agent.agent_id,
            created_by=TEST_USER_EMAIL,
        )
    )

    install_resp = test_client.post(
        f"/agents/{agent.agent_id}/skills?skill_id=scheduler",
        headers=auth_headers,
        json={"config": {}},
    )
    assert install_resp.status_code == 201
    assert install_resp.json()["installed_skill_id"] == "scheduler"

    result = asyncio.run(
        SkillRuntimeService().handle_tool_call(
            tool_name="execute_skill_action",
            tool_input={
                "skill_id": "scheduler",
                "action": "create_or_update",
                "arguments": {
                    "name": "Lead follow-up",
                    "cron_expression": "*/5 * * * *",
                    "timezone": "UTC",
                    "message": "Check new leads and summarize any follow-up needed.",
                },
            },
            agent_id=agent.agent_id,
            owner_email=TEST_USER_EMAIL,
            actor_email=TEST_USER_EMAIL,
            actor_id=TEST_USER_EMAIL,
            conversation_id=conversation.conversation_id,
        )
    )

    payload = json.loads(result)
    schedule = payload["schedule"]
    assert schedule["source_type"] == "agent_skill"
    assert schedule["target_type"] == "agent_message"
    assert schedule["target"]["agent_id"] == agent.agent_id
    assert schedule["target"]["conversation_id"] == conversation.conversation_id
    assert schedule["target"]["conversation_policy"] == "existing"
    assert schedule["target"]["message"] == "Check new leads and summarize any follow-up needed."
    assert schedule["next_run_at"]

    saved = SchedulerRepository().find_schedule(TEST_USER_EMAIL, schedule["schedule_id"])
    assert saved is not None
    assert saved.target["conversation_id"] == conversation.conversation_id


def test_scheduler_skill_accepts_agent_id_argument_for_automation_context(dynamodb_table):
    from tests.mock_data import TEST_USER_EMAIL
    from src.skills.scheduler.actions import create_or_update

    agent = _create_agent_for_user(TEST_USER_EMAIL)
    conversation = ConversationRepository().save(
        Conversation(
            title="Automation scheduler",
            agent_id=agent.agent_id,
            created_by=TEST_USER_EMAIL,
        )
    )

    payload = asyncio.run(
        create_or_update(
            arguments={
                "agent_id": agent.agent_id,
                "name": "Automation-created schedule",
                "cron_expression": "*/5 * * * *",
                "timezone": "UTC",
                "message": "Run the scheduled automation follow-up.",
            },
            config={},
            context={
                "owner_email": TEST_USER_EMAIL,
                "actor_email": TEST_USER_EMAIL,
                "actor_id": TEST_USER_EMAIL,
                "conversation_id": conversation.conversation_id,
                "automation_id": "automation-1",
                "orchestrator_type": "automation",
            },
        )
    )

    schedule = payload["schedule"]
    assert schedule["target"]["agent_id"] == agent.agent_id
    assert schedule["target"]["conversation_id"] == conversation.conversation_id
    assert schedule["target"]["message"] == "Run the scheduled automation follow-up."


def test_scheduler_skill_creates_automation_run_schedule(dynamodb_table):
    from tests.mock_data import TEST_USER_EMAIL
    from src.skills.scheduler.actions import schedule_automation

    payload = asyncio.run(
        schedule_automation(
            arguments={
                "schedule_id": "scheduled-workflow",
                "name": "Scheduled workflow",
                "cron_expression": "*/5 * * * *",
                "timezone": "UTC",
                "input": {"source": "scheduler"},
            },
            config={},
            context={
                "owner_email": TEST_USER_EMAIL,
                "actor_email": TEST_USER_EMAIL,
                "actor_id": TEST_USER_EMAIL,
                "automation_id": "automation-1",
                "automation_node_id": "node-1",
                "orchestrator_type": "automation",
            },
        )
    )

    schedule = payload["schedule"]
    assert schedule["schedule_id"] == "scheduled-workflow"
    assert schedule["source_type"] == "automation_skill"
    assert schedule["target_type"] == "automation_run"
    assert schedule["target"] == {
        "automation_id": "automation-1",
        "input": {"source": "scheduler"},
        "trigger_id": "node-1",
    }

    updated = asyncio.run(
        schedule_automation(
            arguments={
                "schedule_id": "scheduled-workflow",
                "name": "Updated scheduled workflow",
                "cron_expression": "*/10 * * * *",
                "timezone": "UTC",
                "input": {"source": "updated"},
            },
            config={},
            context={
                "owner_email": TEST_USER_EMAIL,
                "actor_email": TEST_USER_EMAIL,
                "actor_id": TEST_USER_EMAIL,
                "automation_id": "automation-1",
                "automation_node_id": "node-1",
                "orchestrator_type": "automation",
            },
        )
    )

    assert updated["schedule"]["schedule_id"] == "scheduled-workflow"
    assert updated["schedule"]["name"] == "Updated scheduled workflow"
    assert updated["schedule"]["cron_expression"] == "*/10 * * * *"
    assert updated["schedule"]["target"]["input"] == {"source": "updated"}
    assert [
        schedule.schedule_id
        for schedule in SchedulerRepository().list_schedules(TEST_USER_EMAIL)
        if schedule.source_type == "automation_skill"
    ] == ["scheduled-workflow"]


def test_repeatable_skill_install_is_deterministic_by_identity_fields(test_client, auth_headers, dynamodb_table):
    from tests.mock_data import TEST_USER_EMAIL

    source_agent = _create_agent_for_user(TEST_USER_EMAIL)
    target_agent = _create_agent_for_user(TEST_USER_EMAIL)
    payload = {
        "config": {
            "target_agent_id": target_agent.agent_id,
            "usage_description": "Use for delegated specialist work.",
        }
    }

    first = test_client.post(
        f"/agents/{source_agent.agent_id}/skills?skill_id=agent_invocation",
        headers=auth_headers,
        json=payload,
    )
    second = test_client.post(
        f"/agents/{source_agent.agent_id}/skills?skill_id=agent_invocation",
        headers=auth_headers,
        json=payload,
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["installed_skill_id"] == second.json()["installed_skill_id"]
    list_resp = test_client.get(f"/agents/{source_agent.agent_id}/skills", headers=auth_headers)
    listed = [item for item in list_resp.json() if item["skill_id"] == "agent_invocation"]
    assert len(listed) == 1


def test_repeatable_skill_base_id_requires_unambiguous_instance(test_client, auth_headers, dynamodb_table):
    from tests.mock_data import TEST_USER_EMAIL

    source_agent = _create_agent_for_user(TEST_USER_EMAIL)
    first_target = _create_agent_for_user(TEST_USER_EMAIL)
    second_target = _create_agent_for_user(TEST_USER_EMAIL)

    first = test_client.post(
        f"/agents/{source_agent.agent_id}/skills?skill_id=agent_invocation",
        headers=auth_headers,
        json={
            "config": {
                "target_agent_id": first_target.agent_id,
                "usage_description": "Use for first specialist work.",
            }
        },
    )
    second = test_client.post(
        f"/agents/{source_agent.agent_id}/skills?skill_id=agent_invocation",
        headers=auth_headers,
        json={
            "config": {
                "target_agent_id": second_target.agent_id,
                "usage_description": "Use for second specialist work.",
            }
        },
    )
    assert first.status_code == 201
    assert second.status_code == 201

    try:
        asyncio.run(
            SkillRuntimeService().handle_tool_call(
                tool_name="load_skill",
                tool_input={"skill_id": "agent_invocation"},
                agent_id=source_agent.agent_id,
                owner_email=TEST_USER_EMAIL,
                actor_email=TEST_USER_EMAIL,
                actor_id=TEST_USER_EMAIL,
                conversation_id="conv-test",
            )
        )
        assert False, "Expected ambiguous repeatable skill lookup to fail"
    except ValueError as exc:
        message = str(exc)
        assert "multiple installed instances" in message
        assert first.json()["installed_skill_id"] in message
        assert second.json()["installed_skill_id"] in message


def test_send_email_install_schema_declares_configured_recipients(test_client, auth_headers):
    response = test_client.get("/skills/send_email/install-schema", headers=auth_headers)

    assert response.status_code == 200
    schema = response.json()
    assert [field["name"] for field in schema["form_inputs"]] == ["to"]
    to_field = schema["form_inputs"][0]
    assert to_field["validation"] == {
        "format": "email",
        "multiple": True,
        "separator": ",",
        "min_items": 1,
    }


def test_send_email_installs_with_normalized_recipient_list(
    test_client,
    auth_headers,
    dynamodb_table,
):
    from tests.mock_data import TEST_USER_EMAIL

    agent = _create_agent_for_user(TEST_USER_EMAIL)

    response = test_client.post(
        f"/agents/{agent.agent_id}/skills?skill_id=send_email",
        headers=auth_headers,
        json={"config": {"to": " FIRST@example.com, second@example.com, first@example.com "}},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["config"]["to"] == "first@example.com, second@example.com"


def test_send_email_rejects_invalid_configured_recipient(
    test_client,
    auth_headers,
    dynamodb_table,
):
    from tests.mock_data import TEST_USER_EMAIL

    agent = _create_agent_for_user(TEST_USER_EMAIL)

    response = test_client.post(
        f"/agents/{agent.agent_id}/skills?skill_id=send_email",
        headers=auth_headers,
        json={"config": {"to": "not-an-email"}},
    )

    assert response.status_code == 400
    assert "Invalid email address" in response.json()["detail"]


def test_send_email_uses_configured_recipients_only(
    test_client,
    auth_headers,
    dynamodb_table,
    monkeypatch,
):
    from tests.mock_data import TEST_USER_EMAIL

    agent = _create_agent_for_user(TEST_USER_EMAIL)
    install_resp = test_client.post(
        f"/agents/{agent.agent_id}/skills?skill_id=send_email",
        headers=auth_headers,
        json={"config": {"to": "owner@example.com, team@example.com"}},
    )
    assert install_resp.status_code == 201

    sent_messages = []

    async def fake_send_agent_response_email(self, *, to_email, subject, body_html):
        del self
        sent_messages.append(
            {"to_email": to_email, "subject": subject, "body_html": body_html}
        )
        return to_email == "owner@example.com"

    monkeypatch.setattr(
        "src.email.EmailService.send_agent_response_email",
        fake_send_agent_response_email,
    )

    result = asyncio.run(
        SkillRuntimeService().handle_tool_call(
            tool_name="execute_skill_action",
            tool_input={
                "skill_id": "send_email",
                "action": "send",
                "arguments": {
                    "to": "attacker@example.com",
                    "subject": "Agent update",
                    "body": "<p>Hello</p>",
                },
            },
            agent_id=agent.agent_id,
            owner_email=TEST_USER_EMAIL,
            actor_email=TEST_USER_EMAIL,
            actor_id=TEST_USER_EMAIL,
            conversation_id="conversation-1",
        )
    )

    payload = json.loads(result)
    assert payload == {
        "sent": True,
        "total": 2,
        "succeeded": 1,
        "failed": 1,
        "recipients": [
            {"email": "owner@example.com", "sent": True},
            {"email": "team@example.com", "sent": False},
        ],
    }
    assert sent_messages == [
        {
            "to_email": "owner@example.com",
            "subject": "Agent update",
            "body_html": "<p>Hello</p>",
        },
        {
            "to_email": "team@example.com",
            "subject": "Agent update",
            "body_html": "<p>Hello</p>",
        },
    ]


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
