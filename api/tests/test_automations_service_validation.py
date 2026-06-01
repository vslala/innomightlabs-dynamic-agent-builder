import pytest

from src.agents.models import Agent
from src.agents.repository import AgentRepository
from src.automations.models import (
    AutomationEdge,
    AutomationNode,
    AutomationTrigger,
    CreateAutomationRequest,
    EnableAutomationSkillRequest,
)
from src.automations.repository import AutomationRepository
from src.automations.service import AutomationService, AutomationValidationError
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
