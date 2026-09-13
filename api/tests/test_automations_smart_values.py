"""Smart value resolution, alias generation, and draft/strict validation modes."""

import json

import pytest

from src.automations.aliases import (
    alias_errors,
    assign_missing_aliases,
    slugify_alias,
    unique_alias,
)
from src.automations.models import (
    AutomationEdge,
    AutomationNode,
    AutomationNodeType,
    AutomationStatus,
    AutomationTrigger,
    AutomationTriggerType,
    CreateAutomationRequest,
    SaveAutomationGraphRequest,
    SmartValuePreviewRequest,
    UpdateAutomationRequest,
)
from src.automations.smart_values import SmartValueResolver
from src.automations.validation import GraphValidationMode
from src.automations.errors import AutomationValidationError
from tests.mock_data import TEST_USER_EMAIL
from tests.test_automations_service_validation import make_service


def make_pointer_context() -> dict:
    """Current shape: each result stored once, the alias indexing it."""
    return {
        "input": {"topic": "inbox cleanup", "count": 3},
        "trigger": {"type": "manual", "trigger_id": "trig-1"},
        "nodes": {
            "action-1": {
                "status": "succeeded",
                "output": {
                    "response_text": "found 12 senders",
                    "messages": [{"subject": "Q3 recap"}, {"subject": "Sale"}],
                },
                "message_ids": {},
                "error": None,
            }
        },
        "steps": {
            "find_senders": {
                "node_id": "action-1",
                "name": "Find Senders",
                "type": "action",
            }
        },
        "execution": {"last_step_alias": "find_senders", "last_node_id": "action-1"},
    }


def make_context() -> dict:
    """Legacy shape: the result inlined under the alias as well.

    Kept as the compatibility fixture -- every run stored before results were
    written once still has to resolve.
    """
    return {
        "input": {"topic": "inbox cleanup", "count": 3},
        "trigger": {"type": "manual", "trigger_id": "trig-1"},
        "nodes": {
            "action-1": {
                "status": "succeeded",
                "output": {"response_text": "found 12 senders"},
                "message_ids": {},
                "error": None,
            }
        },
        "steps": {
            "find_senders": {
                "node_id": "action-1",
                "name": "Find Senders",
                "type": "action",
                "status": "succeeded",
                "output": {
                    "response_text": "found 12 senders",
                    "messages": [{"subject": "Q3 recap"}, {"subject": "Sale"}],
                },
                "message_ids": {},
                "error": None,
            }
        },
        "execution": {"last_step_alias": "find_senders", "last_node_id": "action-1"},
    }


def test_alias_slug_and_uniqueness():
    assert slugify_alias("Find Promotional Senders") == "find_promotional_senders"
    assert slugify_alias("Gmail: search") == "gmail_search"
    assert slugify_alias("  ") == "step"
    assert slugify_alias("123 go") == "step_123_go"
    assert unique_alias("input", set()) == "input_step"
    assert unique_alias("summarize", {"summarize"}) == "summarize_2"


def test_assign_missing_aliases_skips_system_nodes_and_keeps_existing():
    nodes = [
        AutomationNode(automation_id="a", type=AutomationNodeType.START, name="Start"),
        AutomationNode(automation_id="a", type=AutomationNodeType.ACTION, name="Summarize"),
        AutomationNode(automation_id="a", type=AutomationNodeType.ACTION, name="Summarize"),
        AutomationNode(
            automation_id="a",
            type=AutomationNodeType.CONDITION,
            name="Has results",
            alias="kept",
        ),
        AutomationNode(automation_id="a", type=AutomationNodeType.FINAL, name="Done"),
    ]
    assign_missing_aliases(nodes)
    assert nodes[0].alias is None
    assert nodes[1].alias == "summarize"
    assert nodes[2].alias == "summarize_2"
    assert nodes[3].alias == "kept"
    assert nodes[4].alias is None


def test_alias_errors_reject_reserved_duplicate_and_malformed():
    nodes = [
        AutomationNode(automation_id="a", type=AutomationNodeType.ACTION, name="A", alias="steps"),
        AutomationNode(automation_id="a", type=AutomationNodeType.ACTION, name="B", alias="Bad Alias"),
        AutomationNode(automation_id="a", type=AutomationNodeType.ACTION, name="C", alias="dup"),
        AutomationNode(automation_id="a", type=AutomationNodeType.ACTION, name="D", alias="dup"),
    ]
    errors = alias_errors(nodes)
    assert any("reserved" in error for error in errors)
    assert any("lowercase" in error for error in errors)
    assert any("more than one step" in error for error in errors)


def test_legacy_context_paths_still_render():
    resolver = SmartValueResolver(make_context())
    assert resolver.render_template("Topic: {{ $.input.topic }}") == "Topic: inbox cleanup"
    assert (
        resolver.render_template("{{ $.nodes.action-1.output.response_text }}")
        == "found 12 senders"
    )


def test_alias_and_root_paths_render():
    resolver = SmartValueResolver(make_context())
    assert resolver.render_template("{{ input.topic }}") == "inbox cleanup"
    assert resolver.render_template("{{ trigger.type }}") == "manual"
    assert (
        resolver.render_template("{{ steps.find_senders.output.response_text }}")
        == "found 12 senders"
    )
    assert resolver.render_template("{{ last.output.response_text }}") == "found 12 senders"
    assert resolver.render_template("{{ steps.find_senders.output.messages.0.subject }}") == "Q3 recap"


def test_missing_values_render_empty_and_unknown_roots_are_ignored():
    resolver = SmartValueResolver(make_context())
    assert resolver.render_template("[{{ steps.nope.output.x }}]") == "[]"
    assert resolver.render_template("[{{ bogus.path }}]") == "[]"


def test_filters():
    resolver = SmartValueResolver(make_context())
    assert resolver.render_template("{{ steps.find_senders.output.messages | length }}") == "2"
    assert resolver.render_template("{{ steps.nope.output.x | default(\"none\") }}") == "none"
    assert (
        resolver.render_template("{{ steps.find_senders.output.messages.0 | json }}")
        == '{"subject": "Q3 recap"}'
    )


def test_render_value_preserves_types_for_whole_token_strings():
    resolver = SmartValueResolver(make_context())
    rendered = resolver.render_value(
        {
            "count": "{{ input.count }}",
            "messages": "{{ steps.find_senders.output.messages }}",
            "mixed": "n={{ input.count }}",
        }
    )
    assert rendered["count"] == 3
    assert rendered["messages"] == [{"subject": "Q3 recap"}, {"subject": "Sale"}]
    assert rendered["mixed"] == "n=3"


def test_condition_evaluation():
    resolver = SmartValueResolver(make_context())
    assert resolver.evaluate_condition("steps.find_senders.status == 'succeeded'") is True
    assert resolver.evaluate_condition('steps.find_senders.status == "failed"') is False
    assert resolver.evaluate_condition("steps.find_senders.output.response_text != ''") is True
    assert resolver.evaluate_condition("steps.find_senders.output.messages") is True
    assert resolver.evaluate_condition("steps.nope.output.result") is False
    assert resolver.evaluate_condition("$.input.topic == 'inbox cleanup'") is True
    assert resolver.evaluate_condition("") is False


def test_condition_can_compare_two_paths():
    resolver = SmartValueResolver(make_context())
    assert resolver.evaluate_condition("input.topic == steps.find_senders.name") is False
    assert resolver.evaluate_condition("input.count == 3") is True


def test_alias_paths_resolve_through_the_node_result():
    """The alias is an index: following it must give the same values as inlining."""
    resolver = SmartValueResolver(make_pointer_context())

    assert (
        resolver.render_template("{{ steps.find_senders.output.response_text }}")
        == "found 12 senders"
    )
    assert resolver.render_template("{{ steps.find_senders.status }}") == "succeeded"
    assert resolver.render_template("{{ last.output.response_text }}") == "found 12 senders"
    assert (
        resolver.render_template("{{ steps.find_senders.output.messages.0.subject }}") == "Q3 recap"
    )
    assert resolver.evaluate_condition("steps.find_senders.status == 'succeeded'") is True


def test_alias_entry_keeps_its_own_identity_fields():
    resolver = SmartValueResolver(make_pointer_context())

    assert resolver.render_template("{{ steps.find_senders.name }}") == "Find Senders"
    assert resolver.render_template("{{ steps.find_senders.node_id }}") == "action-1"
    assert resolver.render_template("{{ steps.find_senders.type }}") == "action"


def test_whole_step_object_still_carries_the_result():
    step = SmartValueResolver(make_pointer_context()).resolve("steps.find_senders")

    assert step["node_id"] == "action-1"
    assert step["output"]["response_text"] == "found 12 senders"


def test_unknown_alias_and_dangling_reference_resolve_empty():
    context = make_pointer_context()
    context["steps"]["orphan"] = {"node_id": "gone", "name": "Orphan", "type": "action"}
    resolver = SmartValueResolver(context)

    assert resolver.render_template("[{{ steps.nope.output.response_text }}]") == "[]"
    assert resolver.render_template("[{{ steps.orphan.output.response_text }}]") == "[]"
    assert resolver.render_template("{{ steps.orphan.name }}") == "Orphan"


def test_run_context_stores_each_result_once(dynamodb_table):
    """The size fix: a node output must not be duplicated under its alias."""
    from src.automations.models import AutomationNode, AutomationNodeType, AutomationRun
    from src.automations.runner import AutomationRunner

    node = AutomationNode(
        automation_id="auto-1",
        node_id="action-1",
        type=AutomationNodeType.ACTION,
        name="Find Senders",
        alias="find_senders",
    )
    run = AutomationRun(automation_id="auto-1", created_by=TEST_USER_EMAIL, context={})
    payload = {"response_text": "x" * 5_000}

    AutomationRunner()._store_context_node(run, node, "succeeded", payload, {})

    assert run.context["nodes"]["action-1"]["output"] == payload
    assert run.context["steps"]["find_senders"] == {
        "node_id": "action-1",
        "name": "Find Senders",
        "type": "action",
    }
    assert "output" not in run.context["steps"]["find_senders"]
    assert run.context["execution"] == {
        "last_node_id": "action-1",
        "last_step_alias": "find_senders",
    }
    # The alias costs bytes, not a second copy of the payload.
    assert len(json.dumps(run.context)) < len(json.dumps(payload)) * 2


def test_preview_reports_token_status():
    preview = SmartValueResolver(make_context()).preview(
        "{{ steps.find_senders.output.response_text }} / {{ steps.nope.output.x }}"
    )
    assert preview.rendered == "found 12 senders / "
    assert [token.status for token in preview.tokens] == ["resolved", "unknown"]
    assert preview.tokens[0].value == "found 12 senders"


def make_incomplete_action_graph(
    automation_id: str,
    start_node_id: str = "start",
    final_node_id: str = "final",
):
    """A start -> unconfigured action -> final graph: structurally sound, not runnable."""
    start = AutomationNode(
        automation_id=automation_id,
        node_id=start_node_id,
        type=AutomationNodeType.START,
        name="Start",
    )
    action = AutomationNode(
        automation_id=automation_id,
        node_id="action",
        type=AutomationNodeType.ACTION,
        name="Summarize",
        config={
            "action_type": "skill_action",
            "skill_id": "agent_invocation",
            "action": "invoke",
            "arguments": {},
        },
    )
    final = AutomationNode(
        automation_id=automation_id,
        node_id=final_node_id,
        type=AutomationNodeType.FINAL,
        name="Done",
    )
    edges = [
        AutomationEdge(
            automation_id=automation_id,
            edge_id="e1",
            source_node_id=start_node_id,
            target_node_id="action",
            label="next",
        ),
        AutomationEdge(
            automation_id=automation_id,
            edge_id="e2",
            source_node_id="action",
            target_node_id=final_node_id,
            label="next",
        ),
    ]
    trigger = AutomationTrigger(
        automation_id=automation_id,
        type=AutomationTriggerType.MANUAL,
        name="Manual",
        enabled=True,
        entry_node_id=start_node_id,
    )
    return [start, action, final], edges, [trigger]


def graph_for_automation(service, automation_id: str):
    """Rebuild the incomplete graph on top of an automation's real boundary nodes."""
    existing = service.get_graph(automation_id, TEST_USER_EMAIL)
    start = next(node for node in existing.nodes if node.type == AutomationNodeType.START)
    final = next(node for node in existing.nodes if node.type == AutomationNodeType.FINAL)
    return make_incomplete_action_graph(automation_id, start.node_id, final.node_id)


def save_request(nodes, edges) -> SaveAutomationGraphRequest:
    return SaveAutomationGraphRequest(
        nodes=[
            {
                "node_id": node.node_id,
                "type": node.type,
                "name": node.name,
                "position": node.position,
                "config": node.config,
            }
            for node in nodes
        ],
        edges=[
            {
                "edge_id": edge.edge_id,
                "source_node_id": edge.source_node_id,
                "target_node_id": edge.target_node_id,
                "label": edge.label,
            }
            for edge in edges
        ],
    )


def test_draft_mode_allows_unconfigured_action(dynamodb_table):
    service = make_service()
    nodes, edges, triggers = make_incomplete_action_graph("auto-draft")

    service.validate_graph(
        nodes, edges, triggers, TEST_USER_EMAIL, "auto-draft", mode=GraphValidationMode.DRAFT
    )

    with pytest.raises(AutomationValidationError):
        service.validate_graph(
            nodes, edges, triggers, TEST_USER_EMAIL, "auto-draft", mode=GraphValidationMode.STRICT
        )


def test_draft_mode_still_rejects_structural_problems(dynamodb_table):
    service = make_service()
    nodes, edges, triggers = make_incomplete_action_graph("auto-draft")

    with pytest.raises(AutomationValidationError, match="unreachable"):
        service.validate_graph(
            nodes, edges[:1], triggers, TEST_USER_EMAIL, "auto-draft", mode=GraphValidationMode.DRAFT
        )

    with pytest.raises(AutomationValidationError, match="final node"):
        service.validate_graph(
            nodes[:2], edges[:1], triggers, TEST_USER_EMAIL, "auto-draft", mode=GraphValidationMode.DRAFT
        )


def test_save_graph_accepts_incomplete_draft_and_backfills_aliases(dynamodb_table):
    service = make_service()
    created = service.create_automation(
        CreateAutomationRequest(title="Draft flow"), TEST_USER_EMAIL
    )
    nodes, edges, _ = graph_for_automation(service, created.automation.automation_id)

    saved = service.save_graph(
        created.automation.automation_id,
        save_request(nodes, edges),
        TEST_USER_EMAIL,
    )

    action = next(node for node in saved.nodes if node.type == AutomationNodeType.ACTION)
    assert action.alias == "summarize"

    reloaded = service.get_graph(created.automation.automation_id, TEST_USER_EMAIL)
    reloaded_action = next(
        node for node in reloaded.nodes if node.type == AutomationNodeType.ACTION
    )
    assert reloaded_action.alias == "summarize"


def test_active_automation_rejects_incomplete_save(dynamodb_table):
    service = make_service()
    created = service.create_automation(
        CreateAutomationRequest(title="Live flow"), TEST_USER_EMAIL
    )
    automation_id = created.automation.automation_id
    service.update_automation(
        automation_id, UpdateAutomationRequest(status=AutomationStatus.ACTIVE), TEST_USER_EMAIL
    )
    nodes, edges, _ = graph_for_automation(service, automation_id)

    with pytest.raises(AutomationValidationError):
        service.save_graph(automation_id, save_request(nodes, edges), TEST_USER_EMAIL)


def test_preview_smart_values_uses_latest_run_context(dynamodb_table):
    service = make_service()
    created = service.create_automation(
        CreateAutomationRequest(title="Preview flow"), TEST_USER_EMAIL
    )
    automation_id = created.automation.automation_id

    from src.automations.models import AutomationRun

    service.repo.save_run(
        AutomationRun(
            automation_id=automation_id,
            created_by=TEST_USER_EMAIL,
            context=make_context(),
        )
    )

    response = service.preview_smart_values(
        automation_id,
        SmartValuePreviewRequest(template="Hi {{ steps.find_senders.output.response_text }}"),
        TEST_USER_EMAIL,
    )

    assert response.rendered == "Hi found 12 senders"
    assert response.tokens[0].status == "resolved"
    assert response.run_id is not None


def test_preview_smart_values_without_runs(dynamodb_table):
    service = make_service()
    created = service.create_automation(
        CreateAutomationRequest(title="No runs"), TEST_USER_EMAIL
    )

    response = service.preview_smart_values(
        created.automation.automation_id,
        SmartValuePreviewRequest(template="{{ input.topic }}"),
        TEST_USER_EMAIL,
    )

    assert response.rendered == ""
    assert response.run_id is None
    assert response.tokens[0].status == "unknown"
