"""Skills run with the owner's credentials, so who is chatting decides which ones they get."""

from __future__ import annotations

import asyncio

import pytest

from src.agents.models import Agent
from src.agents.repository import AgentRepository
from src.skills.agent_invocation.actions import _target_agent_id
from src.skills.agent_invocation.models import InvokeAgentRequest
from src.skills.models import ActorKind
from src.skills.service import SkillRuntimeService
from tests.mock_data import TEST_USER_EMAIL


def _agent() -> Agent:
    return AgentRepository().save(
        Agent(
            agent_name="Support Bot",
            agent_architecture="krishna-memgpt",
            agent_provider="Bedrock",
            agent_model="claude-3-7-sonnet",
            agent_persona="Helpful",
            created_by=TEST_USER_EMAIL,
        )
    )


def _install(test_client, auth_headers, agent_id: str, skill_id: str, config: dict | None = None) -> str:
    response = test_client.post(
        f"/agents/{agent_id}/skills?skill_id={skill_id}", headers=auth_headers, json={"config": config or {}}
    )
    assert response.status_code == 201, response.text
    return response.json()["installed_skill_id"]


def _execute(runtime: SkillRuntimeService, agent_id: str, skill_id: str, action: str, actor_kind: ActorKind) -> str:
    return asyncio.run(
        runtime.handle_tool_call(
            tool_name="execute_skill_action",
            tool_input={"skill_id": skill_id, "action": action, "arguments": {"url": "https://example.com"}},
            agent_id=agent_id,
            owner_email=TEST_USER_EMAIL,
            actor_email="visitor@example.com",
            actor_id="visitor-1",
            actor_kind=actor_kind,
            conversation_id="conv-1",
        )
    )


def _runtime(monkeypatch) -> SkillRuntimeService:
    runtime = SkillRuntimeService()

    async def fake_execute_action(**kwargs):
        return "ran"

    monkeypatch.setattr(runtime.skill_service.registry, "execute_action", fake_execute_action)
    return runtime


def test_a_new_install_is_for_the_owner_only(test_client, auth_headers):
    agent = _agent()
    _install(test_client, auth_headers, agent.agent_id, "lead_capture")
    runtime = SkillRuntimeService()

    assert [s.skill_id for s in runtime.list_usable(agent.agent_id, ActorKind.OWNER)] == ["lead_capture"]
    for kind in (ActorKind.VISITOR, ActorKind.API, ActorKind.A2A):
        assert runtime.list_usable(agent.agent_id, kind) == []


def test_the_owner_can_offer_a_skill_to_visitors(test_client, auth_headers):
    agent = _agent()
    skill_id = _install(test_client, auth_headers, agent.agent_id, "lead_capture")

    response = test_client.patch(
        f"/agents/{agent.agent_id}/skills/{skill_id}", headers=auth_headers, json={"available_to": ["visitor"]}
    )

    assert response.status_code == 200
    assert response.json()["available_to"] == ["owner", "visitor"]
    runtime = SkillRuntimeService()
    assert [s.skill_id for s in runtime.list_usable(agent.agent_id, ActorKind.VISITOR)] == ["lead_capture"]
    assert runtime.list_usable(agent.agent_id, ActorKind.API) == []


def test_an_owner_only_skill_cannot_be_offered_to_anyone_else(test_client, auth_headers):
    agent = _agent()
    skill_id = _install(test_client, auth_headers, agent.agent_id, "rest_template")

    response = test_client.patch(
        f"/agents/{agent.agent_id}/skills/{skill_id}", headers=auth_headers, json={"available_to": ["visitor"]}
    )

    assert response.status_code == 400
    listed = test_client.get(f"/agents/{agent.agent_id}/skills", headers=auth_headers).json()
    assert listed[0]["owner_only"] is True


def test_a_visitor_calling_a_skill_they_were_not_offered_is_refused(test_client, auth_headers, monkeypatch):
    agent = _agent()
    _install(test_client, auth_headers, agent.agent_id, "rest_template")
    runtime = _runtime(monkeypatch)

    assert _execute(runtime, agent.agent_id, "rest_template", "get", ActorKind.OWNER) == "ran"
    for kind in (ActorKind.VISITOR, ActorKind.API, ActorKind.A2A):
        with pytest.raises(ValueError, match="is not installed/enabled"):
            _execute(runtime, agent.agent_id, "rest_template", "get", kind)


def test_agent_invocation_in_a_chat_stays_on_its_configured_agent():
    request = InvokeAgentRequest(agent_id="someone-elses-agent", prompt_template="hi")
    config = {"target_agent_id": "configured-agent"}

    assert _target_agent_id(request, config, {"orchestrator_type": None}) == "configured-agent"
    assert _target_agent_id(request, config, {"orchestrator_type": "automation"}) == "someone-elses-agent"
