from datetime import datetime, timezone

from src.automations.models import (
    Automation,
    AutomationEdge,
    AutomationNode,
    AutomationRun,
    AutomationRunNodeResult,
    AutomationTrigger,
)
from tests.mock_data import TEST_USER_EMAIL


def test_automation_dynamo_round_trip():
    automation = Automation(
        title="Customer Follow-up",
        description="Draft a reply",
        created_by=TEST_USER_EMAIL,
    )

    hydrated = Automation.from_dynamo_item(automation.to_dynamo_item())

    assert hydrated.automation_id == automation.automation_id
    assert hydrated.pk == f"User#{TEST_USER_EMAIL}"
    assert hydrated.sk == f"Automation#{automation.automation_id}"
    assert hydrated.status == "draft"


def test_graph_entity_key_shapes():
    node = AutomationNode(automation_id="auto-1", type="start", name="Start")
    edge = AutomationEdge(
        automation_id="auto-1",
        source_node_id="start",
        target_node_id="final",
    )
    trigger = AutomationTrigger(
        automation_id="auto-1",
        type="manual",
        name="Manual",
        entry_node_id="start",
    )

    assert node.pk == "Automation#auto-1"
    assert node.sk == f"Node#{node.node_id}"
    assert edge.sk == f"Edge#{edge.edge_id}"
    assert trigger.sk == f"Trigger#{trigger.trigger_id}"


def test_run_and_node_result_round_trip():
    run = AutomationRun(
        automation_id="auto-1",
        trigger_id="trigger-1",
        conversation_id="conversation-1",
        status="running",
        context={"input": {"name": "Ada"}},
        created_by=TEST_USER_EMAIL,
        last_heartbeat_at=datetime.now(timezone.utc),
        current_node_id="node-1",
        current_node_started_at=datetime.now(timezone.utc),
        heartbeat_timeout_seconds=900,
    )
    result = AutomationRunNodeResult(
        run_id=run.run_id,
        automation_id=run.automation_id,
        node_id="node-1",
        status="succeeded",
        output={"response_text": "hello"},
        message_ids={"assistant_message_id": "m-1"},
    )

    hydrated_run = AutomationRun.from_dynamo_item(run.to_dynamo_item())
    assert hydrated_run.context == run.context
    assert hydrated_run.last_heartbeat_at == run.last_heartbeat_at
    assert hydrated_run.current_node_id == "node-1"
    assert hydrated_run.current_node_started_at == run.current_node_started_at
    assert hydrated_run.heartbeat_timeout_seconds == 900
    response = hydrated_run.to_response()
    assert response.current_node_id == "node-1"
    assert response.heartbeat_timeout_seconds == 900
    assert run.to_owner_lookup_item()["sk"] == f"AutomationRun#{run.run_id}"
    assert AutomationRunNodeResult.from_dynamo_item(
        result.to_dynamo_item()
    ).message_ids == result.message_ids
