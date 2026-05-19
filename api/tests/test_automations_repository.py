from src.automations.models import (
    Automation,
    AutomationEdge,
    AutomationNode,
    AutomationRun,
    AutomationRunNodeResult,
    AutomationTrigger,
)
from tests.mock_data import TEST_USER_EMAIL, TEST_USER_EMAIL_2


def test_save_and_find_automation_by_owner(automation_repository):
    automation = Automation(title="Customer Follow-up", created_by=TEST_USER_EMAIL)
    automation_repository.save_automation(automation)

    found = automation_repository.find_automation_by_id(
        automation.automation_id, TEST_USER_EMAIL
    )
    other_user = automation_repository.find_automation_by_id(
        automation.automation_id, TEST_USER_EMAIL_2
    )

    assert found is not None
    assert found.title == "Customer Follow-up"
    assert other_user is None


def test_save_and_replace_graph(automation_repository):
    automation = automation_repository.save_automation(
        Automation(title="Workflow", created_by=TEST_USER_EMAIL)
    )
    start = AutomationNode(automation_id=automation.automation_id, type="start", name="Start")
    final = AutomationNode(automation_id=automation.automation_id, type="final", name="Done")
    edge = AutomationEdge(
        automation_id=automation.automation_id,
        source_node_id=start.node_id,
        target_node_id=final.node_id,
    )
    trigger = AutomationTrigger(
        automation_id=automation.automation_id,
        type="manual",
        name="Manual",
        enabled=True,
        entry_node_id=start.node_id,
    )

    automation_repository.save_graph(automation.automation_id, [start, final], [edge], [trigger])
    nodes, edges, triggers = automation_repository.get_graph(automation.automation_id)

    assert [node.node_id for node in nodes] == [start.node_id, final.node_id]
    assert [item.edge_id for item in edges] == [edge.edge_id]
    assert [item.trigger_id for item in triggers] == [trigger.trigger_id]

    automation_repository.save_graph(automation.automation_id, [start, final], [], [trigger])
    _, edges, _ = automation_repository.get_graph(automation.automation_id)

    assert edges == []


def test_save_and_find_run_details(automation_repository):
    run = AutomationRun(
        automation_id="auto-1",
        status="succeeded",
        context={"nodes": {}},
        created_by=TEST_USER_EMAIL,
    )
    result = AutomationRunNodeResult(
        run_id=run.run_id,
        automation_id=run.automation_id,
        node_id="node-1",
        status="succeeded",
    )

    automation_repository.save_run(run)
    automation_repository.save_node_result(result)

    found = automation_repository.find_run_by_id(run.run_id, TEST_USER_EMAIL)
    results = automation_repository.find_node_results(run.run_id)

    assert found is not None
    assert found.run_id == run.run_id
    assert [item.node_id for item in results] == ["node-1"]
