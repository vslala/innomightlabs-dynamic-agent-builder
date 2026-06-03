import pytest

from src.agents.models import Agent
from src.agents.repository import AgentRepository
from src.automations.models import (
    AutomationEdge,
    AutomationNode,
    AutomationStatus,
    AutomationTrigger,
    AutomationTriggerType,
    CreateAutomationRequest,
    CreateAutomationTriggerRequest,
    EnableAutomationSkillRequest,
    SaveAutomationGraphRequest,
    UpdateAutomationRequest,
    UpdateAutomationTriggerRequest,
)
from src.automations.repository import AutomationRepository
from src.automations.service import AutomationService, AutomationValidationError
from src.scheduler.models import CreateScheduleRequest, ScheduleTargetType
from src.scheduler.repository import SchedulerRepository
from src.scheduler.service import SchedulerService
from src.settings.models import ProviderSettings
from src.settings.repository import ProviderSettingsRepository
from tests.mock_data import TEST_USER_EMAIL


def make_service() -> AutomationService:
    return AutomationService(repo=AutomationRepository(), agent_repo=AgentRepository())


def make_default_graph():
    start = AutomationNode(automation_id="auto-1", node_id="start", type="start", name="Start")
    final = AutomationNode(automation_id="auto-1", node_id="final", type="final", name="Done")
    edge = AutomationEdge(
        automation_id="auto-1",
        source_node_id=start.node_id,
        target_node_id=final.node_id,
        label="next",
    )
    trigger = AutomationTrigger(
        automation_id="auto-1",
        type="manual",
        name="Manual",
        enabled=True,
        entry_node_id=start.node_id,
    )
    return [start, final], [edge], [trigger]


def make_scheduler_action_graph(automation_id: str):
    start = AutomationNode(automation_id=automation_id, node_id="start", type="start", name="Start")
    action = AutomationNode(
        automation_id=automation_id,
        node_id="schedule-node",
        type="action",
        name="Schedule Automation",
        config={
            "action_type": "skill_action",
            "skill_id": "scheduler",
            "action": "schedule_automation",
            "arguments": {
                "schedule_id": "scheduled-workflow",
                "name": "Scheduled workflow",
                "cron_expression": "*/5 * * * *",
                "input": {"source": "scheduler"},
            },
        },
    )
    final = AutomationNode(automation_id=automation_id, node_id="final", type="final", name="Done")
    edges = [
        AutomationEdge(
            automation_id=automation_id,
            edge_id="start-action",
            source_node_id="start",
            target_node_id="schedule-node",
        ),
        AutomationEdge(
            automation_id=automation_id,
            edge_id="action-final",
            source_node_id="schedule-node",
            target_node_id="final",
        ),
        AutomationEdge(
            automation_id=automation_id,
            edge_id="start-final",
            source_node_id="start",
            target_node_id="final",
        ),
    ]
    trigger = AutomationTrigger(
        automation_id=automation_id,
        trigger_id="manual",
        type="manual",
        name="Manual",
        enabled=True,
        entry_node_id="start",
    )
    return [start, action, final], edges, [trigger]


def create_schedule_for_scheduler_node(automation_id: str, node_id: str):
    return SchedulerService().create_schedule(
        CreateScheduleRequest(
            name="Scheduled workflow",
            cron_expression="*/5 * * * *",
            target_type=ScheduleTargetType.AUTOMATION_RUN,
            target={"automation_id": automation_id, "input": {"source": "scheduler"}},
            source_type="automation_skill",
            source_ref={"automation_id": automation_id, "automation_node_id": node_id},
        ),
        owner_email=TEST_USER_EMAIL,
        created_by=TEST_USER_EMAIL,
    )


def test_validate_accepts_default_graph(dynamodb_table):
    nodes, edges, triggers = make_default_graph()

    make_service().validate_graph(nodes, edges, triggers, TEST_USER_EMAIL)


def test_validate_rejects_missing_final(dynamodb_table):
    start = AutomationNode(automation_id="auto-1", node_id="start", type="start", name="Start")

    with pytest.raises(AutomationValidationError, match="final"):
        make_service().validate_graph([start], [], [], TEST_USER_EMAIL)


def test_validate_rejects_invalid_edge_reference(dynamodb_table):
    nodes, _, triggers = make_default_graph()
    bad_edge = AutomationEdge(
        automation_id="auto-1",
        source_node_id="start",
        target_node_id="missing",
    )

    with pytest.raises(AutomationValidationError, match="target node"):
        make_service().validate_graph(nodes, [bad_edge], triggers, TEST_USER_EMAIL)


def test_validate_rejects_invalid_condition_branches(dynamodb_table):
    start = AutomationNode(automation_id="auto-1", node_id="start", type="start", name="Start")
    condition = AutomationNode(
        automation_id="auto-1",
        node_id="condition",
        type="condition",
        name="Check",
        config={"expression": "$.input.ok"},
    )
    final = AutomationNode(automation_id="auto-1", node_id="final", type="final", name="Done")
    edges = [
        AutomationEdge(
            automation_id="auto-1",
            source_node_id="start",
            target_node_id="condition",
        ),
        AutomationEdge(
            automation_id="auto-1",
            source_node_id="condition",
            target_node_id="final",
            label="true",
        ),
    ]
    trigger = AutomationTrigger(
        automation_id="auto-1",
        type="manual",
        name="Manual",
        entry_node_id="start",
    )

    with pytest.raises(AutomationValidationError, match="true and false"):
        make_service().validate_graph([start, condition, final], edges, [trigger], TEST_USER_EMAIL)


def test_validate_rejects_cycle(dynamodb_table):
    start = AutomationNode(automation_id="auto-1", node_id="start", type="start", name="Start")
    action = AutomationNode(
        automation_id="auto-1",
        node_id="action",
        type="action",
        name="Action",
        config={"action_type": "invoke_agent", "agent_id": "agent-1", "prompt_template": "Hi"},
    )
    final = AutomationNode(automation_id="auto-1", node_id="final", type="final", name="Done")
    edges = [
        AutomationEdge(automation_id="auto-1", source_node_id="start", target_node_id="action"),
        AutomationEdge(automation_id="auto-1", source_node_id="action", target_node_id="start"),
        AutomationEdge(automation_id="auto-1", source_node_id="action", target_node_id="final", label="error"),
    ]
    trigger = AutomationTrigger(
        automation_id="auto-1",
        type="manual",
        name="Manual",
        entry_node_id="start",
    )

    with pytest.raises(AutomationValidationError, match="cycles"):
        make_service().validate_graph([start, action, final], edges, [trigger], TEST_USER_EMAIL)


def test_validate_invoke_agent_requires_owned_agent(dynamodb_table):
    agent = Agent(
        agent_id="agent-1",
        agent_name="Helper",
        agent_architecture="krishna-mini",
        agent_provider="Bedrock",
        agent_persona="Helpful",
        created_by=TEST_USER_EMAIL,
    )
    AgentRepository().save(agent)
    start = AutomationNode(automation_id="auto-1", node_id="start", type="start", name="Start")
    action = AutomationNode(
        automation_id="auto-1",
        node_id="action",
        type="action",
        name="Action",
        config={"action_type": "invoke_agent", "agent_id": agent.agent_id, "prompt_template": "Hi"},
    )
    final = AutomationNode(automation_id="auto-1", node_id="final", type="final", name="Done")
    edges = [
        AutomationEdge(automation_id="auto-1", source_node_id="start", target_node_id="action"),
        AutomationEdge(automation_id="auto-1", source_node_id="action", target_node_id="final"),
    ]
    trigger = AutomationTrigger(
        automation_id="auto-1",
        type="manual",
        name="Manual",
        entry_node_id="start",
    )

    make_service().validate_graph([start, action, final], edges, [trigger], TEST_USER_EMAIL)


def test_validate_skill_action_requires_enabled_automation_skill(dynamodb_table):
    start = AutomationNode(automation_id="auto-1", node_id="start", type="start", name="Start")
    action = AutomationNode(
        automation_id="auto-1",
        node_id="action",
        type="action",
        name="Search Mail",
        config={
            "action_type": "skill_action",
            "skill_id": "google_mail",
            "action": "search",
            "arguments": {"recent_20": True},
        },
    )
    final = AutomationNode(automation_id="auto-1", node_id="final", type="final", name="Done")
    edges = [
        AutomationEdge(automation_id="auto-1", source_node_id="start", target_node_id="action"),
        AutomationEdge(automation_id="auto-1", source_node_id="action", target_node_id="final"),
    ]
    trigger = AutomationTrigger(
        automation_id="auto-1",
        type="manual",
        name="Manual",
        entry_node_id="start",
    )

    with pytest.raises(AutomationValidationError, match="not enabled"):
        make_service().validate_graph([start, action, final], edges, [trigger], TEST_USER_EMAIL)


def test_validate_skill_action_accepts_enabled_skill_with_connector(dynamodb_table):
    automation = make_service().create_automation(CreateAutomationRequest(title="Workflow"), TEST_USER_EMAIL).automation
    ProviderSettingsRepository().save(
        ProviderSettings(
            user_email=TEST_USER_EMAIL,
            provider_name="GoogleMail",
            encrypted_credentials="encrypted",
            auth_type="oauth",
        )
    )
    make_service().enable_skill(
        automation.automation_id,
        "google_mail",
        EnableAutomationSkillRequest(config={}),
        TEST_USER_EMAIL,
    )
    start = AutomationNode(automation_id=automation.automation_id, node_id="start", type="start", name="Start")
    action = AutomationNode(
        automation_id=automation.automation_id,
        node_id="action",
        type="action",
        name="Search Mail",
        config={
            "action_type": "skill_action",
            "skill_id": "google_mail",
            "action": "search",
            "arguments": {"recent_20": True},
        },
    )
    final = AutomationNode(automation_id=automation.automation_id, node_id="final", type="final", name="Done")
    edges = [
        AutomationEdge(automation_id=automation.automation_id, source_node_id="start", target_node_id="action"),
        AutomationEdge(automation_id=automation.automation_id, source_node_id="action", target_node_id="final"),
    ]
    trigger = AutomationTrigger(
        automation_id=automation.automation_id,
        type="manual",
        name="Manual",
        entry_node_id="start",
    )

    make_service().validate_graph([start, action, final], edges, [trigger], TEST_USER_EMAIL)


def test_validate_skill_action_rejects_action_disabled_for_automation(dynamodb_table):
    service = make_service()
    automation = service.create_automation(CreateAutomationRequest(title="Workflow"), TEST_USER_EMAIL).automation
    service.enable_skill(
        automation.automation_id,
        "scheduler",
        EnableAutomationSkillRequest(config={}),
        TEST_USER_EMAIL,
    )
    start = AutomationNode(automation_id=automation.automation_id, node_id="start", type="start", name="Start")
    action = AutomationNode(
        automation_id=automation.automation_id,
        node_id="action",
        type="action",
        name="Schedule Agent",
        config={
            "action_type": "skill_action",
            "skill_id": "scheduler",
            "action": "create_or_update",
            "arguments": {
                "name": "Agent wake-up",
                "cron_expression": "*/5 * * * *",
                "message": "Wake up",
            },
        },
    )
    final = AutomationNode(automation_id=automation.automation_id, node_id="final", type="final", name="Done")
    edges = [
        AutomationEdge(automation_id=automation.automation_id, source_node_id="start", target_node_id="action"),
        AutomationEdge(automation_id=automation.automation_id, source_node_id="action", target_node_id="final"),
    ]
    trigger = AutomationTrigger(
        automation_id=automation.automation_id,
        type="manual",
        name="Manual",
        entry_node_id="start",
    )

    with pytest.raises(AutomationValidationError, match="not available for automations"):
        service.validate_graph([start, action, final], edges, [trigger], TEST_USER_EMAIL)


def test_add_trigger_does_not_validate_unrelated_action_nodes(dynamodb_table):
    service = make_service()
    automation = service.create_automation(CreateAutomationRequest(title="Workflow"), TEST_USER_EMAIL).automation
    graph = service.get_graph(automation.automation_id, TEST_USER_EMAIL)
    start = next(node for node in graph.nodes if node.type == "start")
    final = next(node for node in graph.nodes if node.type == "final")
    legacy_action = AutomationNode(
        automation_id=automation.automation_id,
        node_id="legacy-scheduler-action",
        type="action",
        name="Legacy scheduler action",
        config={
            "action_type": "skill_action",
            "skill_id": "scheduler",
            "action": "create_or_update",
            "arguments": {
                "name": "Agent wake-up",
                "cron_expression": "*/5 * * * *",
                "message": "Wake up",
            },
        },
    )
    repo = AutomationRepository()
    repo.save_node(legacy_action)
    repo.save_edge(
        AutomationEdge(
            automation_id=automation.automation_id,
            edge_id="start-legacy-action",
            source_node_id=start.node_id,
            target_node_id=legacy_action.node_id,
        )
    )
    repo.save_edge(
        AutomationEdge(
            automation_id=automation.automation_id,
            edge_id="legacy-action-final",
            source_node_id=legacy_action.node_id,
            target_node_id=final.node_id,
        )
    )

    trigger = service.add_trigger(
        automation.automation_id,
        CreateAutomationTriggerRequest(
            trigger_id="daily-cleanup",
            type=AutomationTriggerType.SCHEDULE,
            name="Daily cleanup",
            enabled=True,
            entry_node_id=start.node_id,
            config={
                "cron_expression": "0 9 * * *",
                "timezone": "UTC",
                "input": {"source": "scheduler"},
            },
        ),
        TEST_USER_EMAIL,
    )

    assert trigger.trigger_id == "daily-cleanup"


def test_schedule_trigger_lifecycle_creates_updates_pauses_and_deletes_schedule(dynamodb_table):
    service = make_service()
    automation = service.create_automation(CreateAutomationRequest(title="Workflow"), TEST_USER_EMAIL).automation
    graph = service.get_graph(automation.automation_id, TEST_USER_EMAIL)
    start = next(node for node in graph.nodes if node.type == "start")

    trigger = service.add_trigger(
        automation.automation_id,
        CreateAutomationTriggerRequest(
            trigger_id="daily-cleanup",
            type=AutomationTriggerType.SCHEDULE,
            name="Daily cleanup",
            enabled=True,
            entry_node_id=start.node_id,
            config={
                "cron_expression": "0 9 * * *",
                "timezone": "UTC",
                "input": {"source": "scheduler"},
            },
        ),
        TEST_USER_EMAIL,
    )

    schedule_id = f"automation:{automation.automation_id}:trigger:{trigger.trigger_id}"
    schedule = SchedulerRepository().find_schedule(TEST_USER_EMAIL, schedule_id)
    assert schedule is not None
    assert schedule.status.value == "paused"
    assert schedule.source_type == "automation_trigger"
    assert schedule.source_ref == {
        "automation_id": automation.automation_id,
        "trigger_id": "daily-cleanup",
    }
    assert schedule.target == {
        "automation_id": automation.automation_id,
        "input": {"source": "scheduler"},
        "trigger_id": "daily-cleanup",
    }

    service.update_automation(
        automation.automation_id,
        UpdateAutomationRequest(status=AutomationStatus.ACTIVE),
        TEST_USER_EMAIL,
    )
    schedule = SchedulerRepository().find_schedule(TEST_USER_EMAIL, schedule_id)
    assert schedule is not None
    assert schedule.status.value == "active"

    service.update_trigger(
        automation.automation_id,
        trigger.trigger_id,
        UpdateAutomationTriggerRequest(
            name="Every 15 minutes",
            config={
                "cron_expression": "*/15 * * * *",
                "timezone": "UTC",
                "input": {"source": "updated"},
            },
        ),
        TEST_USER_EMAIL,
    )
    schedule = SchedulerRepository().find_schedule(TEST_USER_EMAIL, schedule_id)
    assert schedule is not None
    assert schedule.name == "Every 15 minutes"
    assert schedule.cron_expression == "*/15 * * * *"
    assert schedule.target["input"] == {"source": "updated"}

    service.update_automation(
        automation.automation_id,
        UpdateAutomationRequest(status=AutomationStatus.DISABLED),
        TEST_USER_EMAIL,
    )
    schedule = SchedulerRepository().find_schedule(TEST_USER_EMAIL, schedule_id)
    assert schedule is not None
    assert schedule.status.value == "paused"

    service.delete_trigger(automation.automation_id, trigger.trigger_id, TEST_USER_EMAIL)
    assert SchedulerRepository().find_schedule(TEST_USER_EMAIL, schedule_id) is None


def test_save_graph_preserves_existing_triggers_and_schedules(dynamodb_table):
    service = make_service()
    automation = service.create_automation(CreateAutomationRequest(title="Workflow"), TEST_USER_EMAIL).automation
    graph = service.get_graph(automation.automation_id, TEST_USER_EMAIL)
    start = next(node for node in graph.nodes if node.type == "start")
    final = next(node for node in graph.nodes if node.type == "final")

    trigger = service.add_trigger(
        automation.automation_id,
        CreateAutomationTriggerRequest(
            trigger_id="five-minute-cleanup",
            type=AutomationTriggerType.SCHEDULE,
            name="Five minute cleanup",
            enabled=True,
            entry_node_id=start.node_id,
            config={
                "cron_expression": "*/5 * * * *",
                "timezone": "UTC",
                "input": {},
            },
        ),
        TEST_USER_EMAIL,
    )
    schedule_id = f"automation:{automation.automation_id}:trigger:{trigger.trigger_id}"

    saved = service.save_graph(
        automation.automation_id,
        SaveAutomationGraphRequest(
            nodes=[
                {"node_id": start.node_id, "type": "start", "name": "Start"},
                {"node_id": final.node_id, "type": "final", "name": "Done"},
            ],
            edges=[
                {
                    "edge_id": "start-final",
                    "source_node_id": start.node_id,
                    "target_node_id": final.node_id,
                }
            ],
        ),
        TEST_USER_EMAIL,
    )

    assert {item.trigger_id for item in saved.triggers} == {
        "five-minute-cleanup",
        *{item.trigger_id for item in graph.triggers},
    }
    assert SchedulerRepository().find_schedule(TEST_USER_EMAIL, schedule_id) is not None


def test_delete_scheduler_automation_step_deletes_matching_schedule(dynamodb_table):
    service = make_service()
    automation = service.create_automation(CreateAutomationRequest(title="Workflow"), TEST_USER_EMAIL).automation
    nodes, edges, triggers = make_scheduler_action_graph(automation.automation_id)
    service.repo.save_graph(automation.automation_id, nodes, edges, triggers)
    schedule = create_schedule_for_scheduler_node(automation.automation_id, "schedule-node")

    service.delete_node(automation.automation_id, "schedule-node", TEST_USER_EMAIL)

    assert SchedulerRepository().find_schedule(TEST_USER_EMAIL, schedule.schedule_id) is None


def test_save_graph_deletes_schedule_for_removed_scheduler_step(dynamodb_table):
    service = make_service()
    automation = service.create_automation(CreateAutomationRequest(title="Workflow"), TEST_USER_EMAIL).automation
    nodes, edges, triggers = make_scheduler_action_graph(automation.automation_id)
    service.repo.save_graph(automation.automation_id, nodes, edges, triggers)
    schedule = create_schedule_for_scheduler_node(automation.automation_id, "schedule-node")

    service.save_graph(
        automation.automation_id,
        SaveAutomationGraphRequest(
            nodes=[
                {"node_id": "start", "type": "start", "name": "Start"},
                {"node_id": "final", "type": "final", "name": "Done"},
            ],
            edges=[
                {
                    "edge_id": "start-final",
                    "source_node_id": "start",
                    "target_node_id": "final",
                }
            ],
            triggers=[
                {
                    "trigger_id": "manual",
                    "type": "manual",
                    "name": "Manual",
                    "enabled": True,
                    "entry_node_id": "start",
                }
            ],
        ),
        TEST_USER_EMAIL,
    )

    assert SchedulerRepository().find_schedule(TEST_USER_EMAIL, schedule.schedule_id) is None


def test_delete_automation_deletes_scheduler_action_schedules(dynamodb_table):
    service = make_service()
    automation = service.create_automation(CreateAutomationRequest(title="Workflow"), TEST_USER_EMAIL).automation
    nodes, edges, triggers = make_scheduler_action_graph(automation.automation_id)
    service.repo.save_graph(automation.automation_id, nodes, edges, triggers)
    schedule = create_schedule_for_scheduler_node(automation.automation_id, "schedule-node")

    service.delete_automation(automation.automation_id, TEST_USER_EMAIL)

    assert SchedulerRepository().find_schedule(TEST_USER_EMAIL, schedule.schedule_id) is None


def test_validate_skill_action_requires_installed_id_when_repeatable_is_ambiguous(dynamodb_table):
    service = make_service()
    automation = service.create_automation(CreateAutomationRequest(title="Workflow"), TEST_USER_EMAIL).automation
    service.enable_skill(
        automation.automation_id,
        "send_email",
        EnableAutomationSkillRequest(config={"to": "first@example.com"}),
        TEST_USER_EMAIL,
    )
    service.enable_skill(
        automation.automation_id,
        "send_email",
        EnableAutomationSkillRequest(config={"to": "second@example.com"}),
        TEST_USER_EMAIL,
    )
    start = AutomationNode(automation_id=automation.automation_id, node_id="start", type="start", name="Start")
    action = AutomationNode(
        automation_id=automation.automation_id,
        node_id="action",
        type="action",
        name="Send Email",
        config={
            "action_type": "skill_action",
            "skill_id": "send_email",
            "action": "send",
            "arguments": {"subject": "Hello", "body": "<p>Hello</p>"},
        },
    )
    final = AutomationNode(automation_id=automation.automation_id, node_id="final", type="final", name="Done")
    edges = [
        AutomationEdge(automation_id=automation.automation_id, source_node_id="start", target_node_id="action"),
        AutomationEdge(automation_id=automation.automation_id, source_node_id="action", target_node_id="final"),
    ]
    trigger = AutomationTrigger(
        automation_id=automation.automation_id,
        type="manual",
        name="Manual",
        entry_node_id="start",
    )

    with pytest.raises(AutomationValidationError, match="multiple installed instances"):
        service.validate_graph([start, action, final], edges, [trigger], TEST_USER_EMAIL)
