"""Automation steps that act for the owner: approved once when set up, valid while the step is what they saw.

See docs/LLD-action-consent.md.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.agents.architectures.base import AgentArchitecture, AgentInvocationResult
from src.agents.models import Agent
from src.agents.repository import AgentRepository
from src.automations.consent import ConsentRequiredError, StepChangedError
from src.automations.errors import AutomationValidationError
from src.automations.models import (
    Automation,
    AutomationEdge,
    AutomationNode,
    AutomationNodeType,
    AutomationSkill,
    AutomationStatus,
    AutomationTrigger,
    AutomationTriggerType,
    UpdateAutomationRequest,
    step_fingerprint,
)
from src.automations.repository import AutomationRepository
from src.automations.runner import AutomationRunner
from src.automations.service import AutomationGraph, AutomationService
from src.automations.validation import GraphValidationMode
from src.consent.models import ConsentScope, skill_key
from src.conversations.repository import ConversationRepository
from src.skills.models import AgentSkill
from src.skills.repository import AgentSkillRepository
from tests.mock_data import TEST_USER_EMAIL, agent_fields, automation_fields
from tests.mock_data import test_owner as _test_owner

OWNER = _test_owner()
AUTOMATION_ID = "auto-post"


def _post_step(text: str = "{{ $.input.text }}") -> AutomationNode:
    return AutomationNode(
        automation_id=AUTOMATION_ID, node_id="post", type=AutomationNodeType.ACTION, name="Post",
        config={"action_type": "skill_action", "installed_skill_id": "social_media", "skill_id": "social_media",
                "action": "publish", "arguments": {"text": text}},
    )


def _agent_step(agent_id: str = "agent-1") -> AutomationNode:
    return AutomationNode(
        automation_id=AUTOMATION_ID, node_id="write", type=AutomationNodeType.ACTION, name="Write",
        config={"action_type": "invoke_agent", "agent_id": agent_id, "prompt_template": "Write and post the summary"},
    )


def _save(step: AutomationNode) -> AutomationGraph:
    automation = Automation(automation_id=AUTOMATION_ID, title="Weekly post", **automation_fields(TEST_USER_EMAIL))
    start = AutomationNode(automation_id=AUTOMATION_ID, node_id="start", type=AutomationNodeType.START, name="Start")
    final = AutomationNode(automation_id=AUTOMATION_ID, node_id="final", type=AutomationNodeType.FINAL, name="Done")
    edges = [
        AutomationEdge(automation_id=AUTOMATION_ID, source_node_id="start", target_node_id=step.node_id),
        AutomationEdge(automation_id=AUTOMATION_ID, source_node_id=step.node_id, target_node_id="final"),
    ]
    trigger = AutomationTrigger(automation_id=AUTOMATION_ID, trigger_id="trigger-1", type=AutomationTriggerType.MANUAL,
                                name="Manual", enabled=True, entry_node_id="start")
    repo = AutomationRepository()
    repo.save_automation(automation)
    repo.save_graph(AUTOMATION_ID, [start, step, final], edges, [trigger])
    repo.save_skill(AutomationSkill(
        automation_id=AUTOMATION_ID, installed_skill_id="social_media", skill_id="social_media",
        namespace="integrations.social", skill_name="Social media", skill_description="Posts.", enabled_by=TEST_USER_EMAIL,
    ))
    return AutomationGraph(automation, [start, step, final], edges, [trigger])


def _activate(service: AutomationService) -> None:
    service.update_automation(AUTOMATION_ID, UpdateAutomationRequest(status=AutomationStatus.ACTIVE), OWNER)


def test_the_fingerprint_is_what_the_step_does_not_what_it_is_called():
    step = _post_step()
    renamed = step.model_copy(update={"name": "Share it", "position": {"x": 9, "y": 9}})
    assert step_fingerprint(renamed.config) == step_fingerprint(step.config)
    assert step_fingerprint(_post_step("Something else").config) != step_fingerprint(step.config)


def test_a_step_that_acts_for_the_owner_cannot_go_live_until_they_approve_it(dynamodb_table):
    graph = _save(_post_step())
    service = AutomationService()
    with pytest.raises(ConsentRequiredError) as refused:
        _activate(service)
    assert refused.value.node_ids == ["post"]

    [state] = service.consent.states(AUTOMATION_ID, graph.nodes)
    assert (state.node_id, state.kind, state.required, state.state) == ("post", "action", True, "missing")
    # The owner sees the templates the step will fill in, and the action's warning
    assert [block["kind"] for block in state.blocks] == ["fields", "code", "warning"]

    step = AutomationRepository().find_node(AUTOMATION_ID, "post")
    service.consent.grant(AUTOMATION_ID, step, fingerprint=state.fingerprint, granted_actions=[], owner=OWNER, via="editor")
    _activate(service)
    assert service.get_automation(AUTOMATION_ID, OWNER).status is AutomationStatus.ACTIVE


def test_editing_what_the_step_does_asks_again_but_saving_still_works(dynamodb_table):
    graph = _save(_post_step())
    service = AutomationService()
    step = AutomationRepository().find_node(AUTOMATION_ID, "post")
    service.consent.grant(AUTOMATION_ID, step, fingerprint=step_fingerprint(step.config), granted_actions=[], owner=OWNER,
                          via="editor")
    _activate(service)

    edited = _post_step("A different post")
    # An active automation's save is checked strictly, but not for consent: the owner approves only what is saved
    service.validate_graph([graph.nodes[0], edited, graph.nodes[2]], graph.edges, graph.triggers, OWNER, AUTOMATION_ID,
                           mode=GraphValidationMode.STRICT)
    with pytest.raises(ConsentRequiredError):
        service.validate_graph([graph.nodes[0], edited, graph.nodes[2]], graph.edges, graph.triggers, OWNER, AUTOMATION_ID)
    [state] = service.consent.states(AUTOMATION_ID, [edited])
    assert state.state == "stale"


def test_approval_is_for_the_step_as_the_owner_saw_it(dynamodb_table):
    _save(_post_step())
    service = AutomationService()
    step = AutomationRepository().find_node(AUTOMATION_ID, "post")
    with pytest.raises(StepChangedError):
        service.consent.grant(AUTOMATION_ID, step, fingerprint="old", granted_actions=[], owner=OWNER, via="editor")
    with pytest.raises(AutomationValidationError):
        service.consent.grant(AUTOMATION_ID, step, fingerprint=step_fingerprint(step.config),
                              granted_actions=["skill:x.y"], owner=OWNER, via="editor")


@pytest.mark.asyncio
async def test_a_run_carries_the_owners_consent_to_the_action(dynamodb_table, monkeypatch):
    graph = _save(_post_step())
    step = AutomationRepository().find_node(AUTOMATION_ID, "post")
    AutomationService().consent.grant(AUTOMATION_ID, step, fingerprint=step_fingerprint(step.config), granted_actions=[],
                                      owner=OWNER, via="editor")
    runner = AutomationRunner(automation_repo=AutomationRepository(), agent_repo=AgentRepository(),
                              conversation_repo=ConversationRepository())
    seen: dict[str, Any] = {}

    async def publish(skill_id, action_name, arguments, config, context):
        seen.update(arguments=arguments, grant=context.get("consent_grant"))
        return {"status": "published"}

    monkeypatch.setattr(runner.skill_service.registry, "execute_action", publish)
    run = await runner.run_test(graph, None, {"text": "Hello"}, OWNER)

    assert run.status == "succeeded"
    assert seen == {"arguments": {"text": "Hello"}, "grant": f"automation:{AUTOMATION_ID}/post"}


class _RecordingArchitecture(AgentArchitecture):
    scopes: list[ConsentScope] = []

    @property
    def name(self) -> str:
        return "recording"

    async def handle_message_buffered(self, **kwargs) -> AgentInvocationResult:
        self.scopes.append(kwargs["consent_scope"])
        return AgentInvocationResult(response_text="done")


@pytest.mark.asyncio
async def test_an_agent_step_takes_only_the_actions_the_owner_ticked(dynamodb_table, monkeypatch):
    AgentRepository().save(Agent(agent_id="agent-1", agent_name="Writer", agent_architecture="recording",
                                 agent_provider="Bedrock", agent_persona="p", **agent_fields(TEST_USER_EMAIL)))
    for skill_id, name in (("social_media", "Social media"), ("google_mail", "Gmail")):
        AgentSkillRepository().save(AgentSkill(agent_id="agent-1", installed_skill_id=skill_id, skill_id=skill_id,
                                               namespace="x", skill_name=name, skill_description="", installed_by=TEST_USER_EMAIL))
    graph = _save(_agent_step())
    service = AutomationService()

    [state] = service.consent.states(AUTOMATION_ID, graph.nodes)
    assert (state.kind, state.required, state.state) == ("agent", False, "missing")
    grants = next(block for block in state.blocks if block["kind"] == "grants")
    publish, send = skill_key("social_media", "publish"), skill_key("google_mail", "send")
    assert {item["key"] for item in grants["items"]} == {publish, send, skill_key("google_mail", "send_draft")}

    # An agent step without approval may still run: it just takes none of these actions
    _activate(service)
    step = AutomationRepository().find_node(AUTOMATION_ID, "write")
    service.consent.grant(AUTOMATION_ID, step, fingerprint=state.fingerprint, granted_actions=[publish], owner=OWNER,
                          via="editor")

    _RecordingArchitecture.scopes = []
    monkeypatch.setattr("src.automations.runner.get_agent_architecture", lambda _: _RecordingArchitecture())
    runner = AutomationRunner(automation_repo=AutomationRepository(), agent_repo=AgentRepository(),
                              conversation_repo=ConversationRepository())
    await runner.run_test(graph, None, {}, OWNER)

    [scope] = _RecordingArchitecture.scopes
    assert scope.granted == frozenset({publish}) and not scope.can_ask
    assert scope.grant_ref == f"automation:{AUTOMATION_ID}/write"
