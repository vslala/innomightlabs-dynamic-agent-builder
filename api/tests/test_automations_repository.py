from datetime import timedelta

from src.automations.models import (
    Automation,
    AutomationEdge,
    AutomationNode,
    AutomationRun,
    AutomationRunNodeResult,
    AutomationTrigger,
)
from src.automations.repository import AutomationRepository
from tests.mock_data import TEST_USER_EMAIL, TEST_USER_EMAIL_2, automation_fields, owner_ids


def test_save_and_find_automation_by_owner(automation_repository):
    automation = Automation(title="Customer Follow-up", **automation_fields(TEST_USER_EMAIL))
    automation_repository.save_automation(automation)

    found = automation_repository.find_in_account(owner_ids(TEST_USER_EMAIL)[0], automation.automation_id)
    other_user = automation_repository.find_in_account(owner_ids(TEST_USER_EMAIL_2)[0], automation.automation_id)

    assert found is not None
    assert found.title == "Customer Follow-up"
    assert other_user is None


def test_save_and_replace_graph(automation_repository):
    automation = automation_repository.save_automation(
        Automation(title="Workflow", **automation_fields(TEST_USER_EMAIL))
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


def test_get_graph_reads_all_query_pages():
    start = AutomationNode(automation_id="auto-1", node_id="start", type="start", name="Start")
    end = AutomationNode(automation_id="auto-1", node_id="end", type="start", name="End")
    trigger = AutomationTrigger(
        automation_id="auto-1",
        trigger_id="manual",
        type="manual",
        name="Manual",
        enabled=True,
        entry_node_id="start",
    )
    asked: list[tuple[str, bool]] = []

    class PaginatedTable:
        def query(self, **kwargs):
            prefix = kwargs["KeyConditionExpression"].get_expression()["values"][1].get_expression()["values"][1]
            asked.append((prefix, "ExclusiveStartKey" in kwargs))
            if prefix == "Node#" and "ExclusiveStartKey" not in kwargs:
                return {"Items": [start.to_dynamo_item()], "LastEvaluatedKey": {"pk": start.pk, "sk": start.sk}}
            if prefix == "Node#":
                assert kwargs["ExclusiveStartKey"] == {"pk": "Automation#auto-1", "sk": "Node#start"}
                return {"Items": [end.to_dynamo_item()]}
            return {"Items": [trigger.to_dynamo_item()] if prefix == "Trigger#" else []}

    repo = AutomationRepository.__new__(AutomationRepository)
    repo.table = PaginatedTable()

    nodes, edges, triggers = repo.get_graph("auto-1")

    assert sorted(node.node_id for node in nodes) == ["end", "start"]
    assert edges == []
    assert [item.trigger_id for item in triggers] == ["manual"]
    assert asked == [("Node#", False), ("Node#", True), ("Edge#", False), ("Trigger#", False)]


def test_get_graph_never_reads_runs_skills_or_the_rest_of_the_partition(automation_repository, monkeypatch):
    automation = Automation(title="Busy", **automation_fields(TEST_USER_EMAIL))
    automation_repository.save_automation(automation)
    aid = automation.automation_id
    start = AutomationNode(automation_id=aid, node_id="start", type="start", name="Start")
    end = AutomationNode(automation_id=aid, node_id="end", type="start", name="End")
    edge = AutomationEdge(automation_id=aid, edge_id="e1", source_node_id="start", target_node_id="end")
    trigger = AutomationTrigger(automation_id=aid, trigger_id="manual", type="manual", name="Manual",
                                enabled=True, entry_node_id="start")
    automation_repository.save_graph(aid, [start, end], [edge], [trigger])
    for n in range(5):
        automation_repository.save_run(AutomationRun(automation_id=aid, trigger_id="manual", created_by="u"))
    for sk in ("Skill#web", "Consent#start", "Schedule#s1"):
        automation_repository.table.put_item(Item={"pk": f"Automation#{aid}", "sk": sk, "entity_type": "Other"})

    read: list[str] = []
    real_query = automation_repository.table.query

    def spy(**kwargs):
        response = real_query(**kwargs)
        read.extend(item["sk"] for item in response["Items"])
        return response

    monkeypatch.setattr(automation_repository.table, "query", spy, raising=False)
    nodes, edges, triggers = automation_repository.get_graph(aid)

    assert sorted(node.node_id for node in nodes) == ["end", "start"]
    assert [e.edge_id for e in edges] == ["e1"]
    assert [t.trigger_id for t in triggers] == ["manual"]
    assert sorted(read) == ["Edge#e1", "Node#end", "Node#start", "Trigger#manual"]


def test_list_triggers_reads_all_query_pages():
    older = AutomationTrigger(
        automation_id="auto-1",
        trigger_id="older",
        type="manual",
        name="Older",
        enabled=True,
        entry_node_id="start",
    )
    newer = AutomationTrigger(
        automation_id="auto-1",
        trigger_id="newer",
        type="manual",
        name="Newer",
        enabled=True,
        entry_node_id="start",
    )
    newer.created_at = older.created_at + timedelta(microseconds=1)

    class PaginatedTriggerTable:
        def __init__(self):
            self.calls = 0

        def query(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                assert "ExclusiveStartKey" not in kwargs
                return {
                    "Items": [newer.to_dynamo_item()],
                    "LastEvaluatedKey": {"pk": "Automation#auto-1", "sk": "Trigger#newer"},
                }
            assert kwargs["ExclusiveStartKey"] == {
                "pk": "Automation#auto-1",
                "sk": "Trigger#newer",
            }
            return {"Items": [older.to_dynamo_item()]}

    repo = AutomationRepository.__new__(AutomationRepository)
    repo.table = PaginatedTriggerTable()

    triggers = repo.list_triggers("auto-1")

    assert [item.trigger_id for item in triggers] == ["older", "newer"]
    assert repo.table.calls == 2


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

    found = automation_repository.find_run_by_id(run.run_id)
    results = automation_repository.find_node_results(run.run_id)

    assert found is not None
    assert found.run_id == run.run_id
    assert [item.node_id for item in results] == ["node-1"]
