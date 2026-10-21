from typing import AsyncIterator

from src.agents.architectures.base import AgentArchitecture
from src.agents.models import Agent
from src.agents.repository import AgentRepository
from src.automations.models import (
    Automation,
    AutomationEdge,
    AutomationNode,
    AutomationNodeType,
    AutomationSkill,
    AutomationTrigger,
    AutomationTriggerType,
)
from src.automations.repository import AutomationRepository
from src.automations.runner import AutomationRunner
from src.automations.service import AutomationGraph
from src.conversations.models import AutomationConversation
from src.conversations.repository import ConversationRepository
from src.llm.events import SSEEvent, SSEEventType
from tests.mock_data import TEST_USER_EMAIL, agent_fields, conversations_of, automation_fields
from src.skills.models import ActorKind
from tests.mock_data import test_owner as _test_owner

TEST_OWNER = _test_owner()



class SuccessfulArchitecture(AgentArchitecture):
    async def handle_message(
        self,
        agent,
        conversation,
        user_message: str,
        owner_email: str,
        actor_email: str,
        actor_id: str,
        actor_kind: ActorKind,
        attachments=None,
        api_key_id=None,
    ) -> AsyncIterator[SSEEvent]:
        yield SSEEvent(
            event_type=SSEEventType.USER_MESSAGE_SAVED,
            content="saved",
            message_id="user-message-1",
        )
        yield SSEEvent(event_type=SSEEventType.AGENT_RESPONSE_TO_USER, content=f"Echo: {user_message}")
        yield SSEEvent(
            event_type=SSEEventType.ASSISTANT_MESSAGE_SAVED,
            content="saved",
            message_id="assistant-message-1",
        )
        yield SSEEvent(event_type=SSEEventType.STREAM_COMPLETE, content="done")

    @property
    def name(self) -> str:
        return "successful"


class FailingArchitecture(AgentArchitecture):
    async def handle_message(
        self,
        agent,
        conversation,
        user_message: str,
        owner_email: str,
        actor_email: str,
        actor_id: str,
        actor_kind: ActorKind,
        attachments=None,
        api_key_id=None,
    ) -> AsyncIterator[SSEEvent]:
        yield SSEEvent(event_type=SSEEventType.ERROR, content="provider failed")

    @property
    def name(self) -> str:
        return "failing"


def build_graph(agent_id: str, include_error_edge: bool = False) -> AutomationGraph:
    automation = Automation(
        automation_id="auto-1",
        title="Workflow",
        **automation_fields(TEST_USER_EMAIL),
    )
    start = AutomationNode(automation_id="auto-1", node_id="start", type=AutomationNodeType.START, name="Start")
    action = AutomationNode(
        automation_id="auto-1",
        node_id="draft",
        type=AutomationNodeType.ACTION,
        name="Draft",
        config={
            "action_type": "invoke_agent",
            "agent_id": agent_id,
            "prompt_template": "Hello {{ $.input.name }}",
        },
    )
    final = AutomationNode(automation_id="auto-1", node_id="final", type=AutomationNodeType.FINAL, name="Done")
    edges = [
        AutomationEdge(automation_id="auto-1", source_node_id="start", target_node_id="draft"),
        AutomationEdge(automation_id="auto-1", source_node_id="draft", target_node_id="final"),
    ]
    if include_error_edge:
        edges.append(
            AutomationEdge(
                automation_id="auto-1",
                source_node_id="draft",
                target_node_id="final",
                label="error",
            )
        )
    trigger = AutomationTrigger(
        automation_id="auto-1",
        trigger_id="trigger-1",
        type=AutomationTriggerType.MANUAL,
        name="Manual",
        enabled=True,
        entry_node_id="start",
    )
    return AutomationGraph(automation, [start, action, final], edges, [trigger])


async def test_runner_invokes_agent_and_stores_run_context(dynamodb_table, monkeypatch):
    agent = Agent(
        agent_id="agent-1",
        agent_name="Helper",
        agent_architecture="successful",
        agent_provider="Bedrock",
        agent_persona="Helpful",
        **agent_fields(TEST_USER_EMAIL),
    )
    AgentRepository().save(agent)
    monkeypatch.setattr(
        "src.automations.runner.get_agent_architecture",
        lambda _: SuccessfulArchitecture(),
    )

    runner = AutomationRunner(
        automation_repo=AutomationRepository(),
        agent_repo=AgentRepository(),
        conversation_repo=ConversationRepository(),
    )
    run = await runner.run_test(build_graph(agent.agent_id), None, {"name": "Ada"}, TEST_OWNER)

    assert run.status == "succeeded"
    assert run.conversation_id is not None
    assert run.context["nodes"]["draft"]["output"]["response_text"] == "Echo: Hello Ada"
    assert run.context["nodes"]["draft"]["message_ids"] == {
        "user_message_id": "user-message-1",
        "assistant_message_id": "assistant-message-1",
    }
    conversation = ConversationRepository().find_by_id(run.conversation_id, conversations_of(TEST_USER_EMAIL))
    assert isinstance(conversation, AutomationConversation)
    assert conversation.automation_run_id == run.run_id


async def test_runner_creates_pending_run_then_executes_by_id(dynamodb_table, monkeypatch):
    agent = Agent(
        agent_id="agent-1",
        agent_name="Helper",
        agent_architecture="successful",
        agent_provider="Bedrock",
        agent_persona="Helpful",
        **agent_fields(TEST_USER_EMAIL),
    )
    AgentRepository().save(agent)
    graph = build_graph(agent.agent_id)
    repo = AutomationRepository()
    repo.save_automation(graph.automation)
    repo.save_graph(graph.automation.automation_id, graph.nodes, graph.edges, graph.triggers)
    monkeypatch.setattr(
        "src.automations.runner.get_agent_architecture",
        lambda _: SuccessfulArchitecture(),
    )

    runner = AutomationRunner(
        automation_repo=repo,
        agent_repo=AgentRepository(),
        conversation_repo=ConversationRepository(),
    )
    pending = runner.create_test_run(graph, None, {"name": "Ada"}, TEST_OWNER)

    assert pending.status == "pending"
    assert pending.started_at is None
    assert pending.conversation_id is not None

    completed = await runner.execute_run(pending.run_id, TEST_OWNER)

    assert completed.status == "succeeded"
    assert completed.started_at is not None
    assert completed.completed_at is not None
    assert completed.last_heartbeat_at is not None
    assert completed.current_node_id is None
    assert completed.current_node_started_at is None
    assert completed.context["nodes"]["draft"]["output"]["response_text"] == "Echo: Hello Ada"


async def test_runner_follows_error_edge_for_failed_agent(dynamodb_table, monkeypatch):
    agent = Agent(
        agent_id="agent-1",
        agent_name="Helper",
        agent_architecture="failing",
        agent_provider="Bedrock",
        agent_persona="Helpful",
        **agent_fields(TEST_USER_EMAIL),
    )
    AgentRepository().save(agent)
    monkeypatch.setattr(
        "src.automations.runner.get_agent_architecture",
        lambda _: FailingArchitecture(),
    )

    runner = AutomationRunner(
        automation_repo=AutomationRepository(),
        agent_repo=AgentRepository(),
        conversation_repo=ConversationRepository(),
    )
    run = await runner.run_test(
        build_graph(agent.agent_id, include_error_edge=True),
        None,
        {"name": "Ada"},
        TEST_OWNER,
    )

    assert run.status == "succeeded"
    assert run.context["nodes"]["draft"]["status"] == "failed"
    assert run.context["nodes"]["draft"]["error"] == "provider failed"


async def test_runner_executes_skill_action_and_renders_arguments(dynamodb_table, monkeypatch):
    automation = Automation(
        automation_id="auto-skill",
        title="Workflow",
        **automation_fields(TEST_USER_EMAIL),
    )
    start = AutomationNode(automation_id="auto-skill", node_id="start", type=AutomationNodeType.START, name="Start")
    action = AutomationNode(
        automation_id="auto-skill",
        node_id="search",
        type=AutomationNodeType.ACTION,
        name="Search",
        config={
            "action_type": "skill_action",
            "installed_skill_id": "wordpress_search:configured",
            "skill_id": "wordpress_search",
            "action": "search",
            "arguments": {"query": "{{ $.input.query }}", "per_page": "{{ $.input.limit }}"},
        },
    )
    final = AutomationNode(automation_id="auto-skill", node_id="final", type=AutomationNodeType.FINAL, name="Done")
    graph = AutomationGraph(
        automation,
        [start, action, final],
        [
            AutomationEdge(automation_id="auto-skill", source_node_id="start", target_node_id="search"),
            AutomationEdge(automation_id="auto-skill", source_node_id="search", target_node_id="final"),
        ],
        [
            AutomationTrigger(
                automation_id="auto-skill",
                trigger_id="trigger-1",
                type="manual",
                name="Manual",
                enabled=True,
                entry_node_id="start",
            )
        ],
    )
    repo = AutomationRepository()
    repo.save_skill(
        AutomationSkill(
            automation_id="auto-skill",
            installed_skill_id="wordpress_search:configured",
            skill_id="wordpress_search",
            namespace="integrations.wordpress",
            skill_name="WordPress Search",
            skill_description="Search posts",
            enabled_by=TEST_USER_EMAIL,
            config={"site_url": "https://example.com"},
        )
    )

    runner = AutomationRunner(
        automation_repo=repo,
        agent_repo=AgentRepository(),
        conversation_repo=ConversationRepository(),
    )

    async def fake_execute_action(skill_id, action_name, arguments, config, context):
        assert skill_id == "wordpress_search"
        assert action_name == "search"
        assert arguments == {"query": "pricing", "per_page": 3}
        assert config == {"site_url": "https://example.com"}
        assert context["automation_id"] == "auto-skill"
        return {"ok": True}

    monkeypatch.setattr(runner.skill_service.registry, "execute_action", fake_execute_action)

    run = await runner.run_test(graph, None, {"query": "pricing", "limit": 3}, TEST_OWNER)

    assert run.status == "succeeded"
    assert run.context["nodes"]["search"]["output"]["result"] == {"ok": True}
    assert run.context["nodes"]["search"]["output"]["installed_skill_id"] == "wordpress_search:configured"


def build_two_trigger_graph(agent_id: str) -> AutomationGraph:
    """A manual trigger and a schedule trigger, each entering its own branch."""
    graph = build_graph(agent_id)
    scheduled_start = AutomationNode(
        automation_id="auto-1", node_id="scheduled_start", type=AutomationNodeType.START, name="Scheduled start"
    )
    scheduled_draft = AutomationNode(
        automation_id="auto-1",
        node_id="scheduled_draft",
        type=AutomationNodeType.ACTION,
        name="Scheduled draft",
        config={"action_type": "invoke_agent", "agent_id": agent_id, "prompt_template": "Scheduled {{ input.name }}"},
    )
    schedule_trigger = AutomationTrigger(
        automation_id="auto-1",
        trigger_id="trigger-schedule",
        type=AutomationTriggerType.SCHEDULE,
        name="Every morning",
        enabled=True,
        entry_node_id="scheduled_start",
        config={"cron_expression": "0 9 * * *", "timezone": "UTC"},
    )
    return AutomationGraph(
        graph.automation,
        [*graph.nodes, scheduled_start, scheduled_draft],
        [
            *graph.edges,
            AutomationEdge(automation_id="auto-1", source_node_id="scheduled_start", target_node_id="scheduled_draft"),
            AutomationEdge(automation_id="auto-1", source_node_id="scheduled_draft", target_node_id="final"),
        ],
        [*graph.triggers, schedule_trigger],
    )


async def test_scheduled_run_enters_at_its_schedule_trigger(dynamodb_table, monkeypatch):
    agent = Agent(
        agent_id="agent-1",
        agent_name="Helper",
        agent_architecture="successful",
        agent_provider="Bedrock",
        agent_persona="Helpful",
        **agent_fields(TEST_USER_EMAIL),
    )
    AgentRepository().save(agent)
    monkeypatch.setattr("src.automations.runner.get_agent_architecture", lambda _: SuccessfulArchitecture())
    runner = AutomationRunner(
        automation_repo=AutomationRepository(),
        agent_repo=AgentRepository(),
        conversation_repo=ConversationRepository(),
    )
    graph = build_two_trigger_graph(agent.agent_id)

    run = runner.create_scheduled_run(graph, {"name": "Ada"}, TEST_OWNER, "schedule-1", trigger_id="trigger-schedule")
    completed = await runner.execute_run_graph(graph, run, TEST_OWNER)

    assert run.trigger_id == "trigger-schedule"
    assert completed.status == "succeeded"
    assert completed.context["nodes"]["scheduled_draft"]["output"]["response_text"] == "Echo: Scheduled Ada"
    assert "draft" not in completed.context["nodes"]


async def test_scheduled_run_without_a_trigger_enters_at_the_manual_trigger(dynamodb_table, monkeypatch):
    agent = Agent(
        agent_id="agent-1",
        agent_name="Helper",
        agent_architecture="successful",
        agent_provider="Bedrock",
        agent_persona="Helpful",
        **agent_fields(TEST_USER_EMAIL),
    )
    AgentRepository().save(agent)
    monkeypatch.setattr("src.automations.runner.get_agent_architecture", lambda _: SuccessfulArchitecture())
    runner = AutomationRunner(
        automation_repo=AutomationRepository(),
        agent_repo=AgentRepository(),
        conversation_repo=ConversationRepository(),
    )
    graph = build_two_trigger_graph(agent.agent_id)

    run = runner.create_scheduled_run(graph, {"name": "Ada"}, TEST_OWNER, "schedule-1")
    completed = await runner.execute_run_graph(graph, run, TEST_OWNER)

    assert completed.status == "succeeded"
    assert completed.context["nodes"]["draft"]["output"]["response_text"] == "Echo: Hello Ada"
    assert "scheduled_draft" not in completed.context["nodes"]
