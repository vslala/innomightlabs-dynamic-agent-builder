"""Graph and node validation policies for automations."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, Protocol

from src.agents.repository import AgentRepository
from src.automations.errors import AutomationValidationError
from src.automations.models import (
    AutomationActionType,
    AutomationEdge,
    AutomationNode,
    AutomationNodeType,
    AutomationSkill,
    AutomationTrigger,
    AutomationTriggerType,
    ConditionNodeConfig,
    SkillActionConfig,
)
from src.automations.triggers.models import ScheduleTriggerConfig
from src.connectors.service import ConnectorService
from src.scheduler.cron import ScheduleExpression, validate_schedule_expression
from src.skills.registry import SkillRegistry


@dataclass(frozen=True)
class GraphValidationContext:
    nodes: list[AutomationNode]
    edges: list[AutomationEdge]
    triggers: list[AutomationTrigger]
    node_by_id: dict[str, AutomationNode]
    outgoing: dict[str, list[AutomationEdge]]
    user_email: str
    automation_id: str


@dataclass(frozen=True)
class ActionValidationContext:
    user_email: str
    automation_id: str


class NodeValidationPolicy(Protocol):
    node_type: AutomationNodeType

    def validate(self, node: AutomationNode, ctx: GraphValidationContext) -> None:
        ...


class ActionConfigValidator(Protocol):
    action_type: str

    def validate(self, config: dict, ctx: ActionValidationContext) -> None:
        ...


class StartNodeValidationPolicy:
    node_type = AutomationNodeType.START

    def validate(self, node: AutomationNode, ctx: GraphValidationContext) -> None:
        _require_outgoing(node, ctx)


class FinalNodeValidationPolicy:
    node_type = AutomationNodeType.FINAL

    def validate(self, node: AutomationNode, ctx: GraphValidationContext) -> None:
        if ctx.outgoing.get(node.node_id):
            raise AutomationValidationError("Final nodes cannot have outgoing edges")


class ConditionNodeValidationPolicy:
    node_type = AutomationNodeType.CONDITION

    def validate(self, node: AutomationNode, ctx: GraphValidationContext) -> None:
        node_edges = _require_outgoing(node, ctx)
        try:
            config = ConditionNodeConfig(**node.config)
        except Exception as exc:
            raise AutomationValidationError("Condition node requires a valid expression") from exc
        labels = {edge.label for edge in node_edges}
        if config.true_label not in labels or config.false_label not in labels:
            raise AutomationValidationError(
                "Condition nodes must have valid true and false outgoing branches"
            )


class ActionNodeValidationPolicy:
    node_type = AutomationNodeType.ACTION

    def __init__(self, validators: list[ActionConfigValidator]):
        self._validators = {validator.action_type: validator for validator in validators}

    def validate(self, node: AutomationNode, ctx: GraphValidationContext) -> None:
        _require_outgoing(node, ctx)
        action_type = str(node.config.get("action_type") or "")
        validator = self._validators.get(action_type)
        if not validator:
            if action_type in {
                AutomationActionType.SEND_EMAIL.value,
                AutomationActionType.WEBHOOK_CALL.value,
            }:
                raise AutomationValidationError(f"Action type '{action_type}' is not implemented yet")
            raise AutomationValidationError("Action node requires a supported action_type")
        validator.validate(
            node.config,
            ActionValidationContext(
                user_email=ctx.user_email,
                automation_id=ctx.automation_id,
            ),
        )


class InvokeAgentActionValidator:
    action_type = AutomationActionType.INVOKE_AGENT.value

    def __init__(self, agent_repo: AgentRepository):
        self.agent_repo = agent_repo

    def validate(self, config: dict, ctx: ActionValidationContext) -> None:
        agent_id = config.get("agent_id")
        prompt_template = config.get("prompt_template")
        if not agent_id or not isinstance(agent_id, str):
            raise AutomationValidationError("invoke_agent action requires agent_id")
        if not prompt_template or not isinstance(prompt_template, str):
            raise AutomationValidationError("invoke_agent action requires prompt_template")
        if not self.agent_repo.find_agent_by_id(agent_id, ctx.user_email):
            raise AutomationValidationError("invoke_agent action references an unknown agent")


class SkillActionValidator:
    action_type = AutomationActionType.SKILL_ACTION.value

    def __init__(
        self,
        skill_registry: SkillRegistry,
        connector_service: ConnectorService,
        resolve_skill: Callable[
            [str, str | None, str | None, str, bool],
            AutomationSkill | None,
        ],
    ):
        self.skill_registry = skill_registry
        self.connector_service = connector_service
        self.resolve_skill = resolve_skill

    def validate(self, config: dict, ctx: ActionValidationContext) -> None:
        try:
            skill_config = SkillActionConfig(**config)
        except Exception as exc:
            raise AutomationValidationError(
                "skill_action requires installed_skill_id or skill_id, action, and arguments"
            ) from exc
        enabled = self.resolve_skill(
            ctx.automation_id,
            skill_config.installed_skill_id,
            skill_config.skill_id,
            ctx.user_email,
            True,
        )
        if not enabled or not enabled.enabled:
            raise AutomationValidationError(
                "skill_action references a skill that is not enabled for this automation"
            )
        loaded = self.skill_registry.get(enabled.skill_id)
        if not loaded:
            raise AutomationValidationError("skill_action references an unavailable skill")
        if not loaded.manifest.automation.enabled:
            raise AutomationValidationError(
                "skill_action references a skill that is not available for automations"
            )
        missing = self.connector_service.missing_required_connectors(loaded.manifest, ctx.user_email)
        if missing:
            raise AutomationValidationError(
                "skill_action requires connected connectors: " + ", ".join(missing)
            )
        action = next(
            (
                item
                for item in loaded.manifest.actions
                if item.name == skill_config.action or skill_config.action in item.aliases
            ),
            None,
        )
        if not action:
            raise AutomationValidationError("skill_action references an unknown skill action")
        if not action.automation.enabled:
            raise AutomationValidationError(
                "skill_action references a skill action that is not available for automations"
            )
        if not isinstance(skill_config.arguments, dict):
            raise AutomationValidationError("skill_action arguments must be an object")
        for field_name in action.input_schema.get("required", []):
            if field_name not in skill_config.arguments:
                raise AutomationValidationError(
                    f"skill_action missing required action argument: {field_name}"
                )


class AutomationGraphValidator:
    def __init__(self, node_policies: list[NodeValidationPolicy]):
        self._node_policies = {policy.node_type: policy for policy in node_policies}

    def validate(
        self,
        nodes: list[AutomationNode],
        edges: list[AutomationEdge],
        triggers: list[AutomationTrigger],
        user_email: str,
        automation_id: str | None = None,
    ) -> None:
        node_by_id = self._validate_identity(nodes, edges, triggers)
        start_nodes = self._validate_required_boundaries(nodes)
        outgoing = self._validate_edges(edges, node_by_id)
        for trigger in triggers:
            self._validate_trigger(nodes, trigger)
        self._validate_start_trigger_coverage(start_nodes, triggers)
        entry_node_ids = {trigger.entry_node_id for trigger in triggers} or {
            node.node_id for node in start_nodes
        }
        self._validate_reachability(nodes, entry_node_ids, outgoing)
        self._reject_cycles(entry_node_ids, outgoing)
        ctx = GraphValidationContext(
            nodes=nodes,
            edges=edges,
            triggers=triggers,
            node_by_id=node_by_id,
            outgoing=outgoing,
            user_email=user_email,
            automation_id=automation_id or nodes[0].automation_id,
        )
        for node in nodes:
            policy = self._node_policies.get(node.type)
            if not policy:
                raise AutomationValidationError(f"Unsupported node type: {node.type}")
            policy.validate(node, ctx)

    def validate_trigger(
        self,
        nodes: list[AutomationNode],
        trigger: AutomationTrigger,
    ) -> None:
        self._validate_trigger(nodes, trigger)

    def _validate_identity(
        self,
        nodes: list[AutomationNode],
        edges: list[AutomationEdge],
        triggers: list[AutomationTrigger],
    ) -> dict[str, AutomationNode]:
        node_by_id = {node.node_id: node for node in nodes}
        if len(node_by_id) != len(nodes):
            raise AutomationValidationError("Node IDs must be unique")
        edge_ids = {edge.edge_id for edge in edges}
        if len(edge_ids) != len(edges):
            raise AutomationValidationError("Edge IDs must be unique")
        trigger_ids = {trigger.trigger_id for trigger in triggers}
        if len(trigger_ids) != len(triggers):
            raise AutomationValidationError("Trigger IDs must be unique")
        return node_by_id

    def _validate_required_boundaries(self, nodes: list[AutomationNode]) -> list[AutomationNode]:
        start_nodes = [node for node in nodes if node.type == AutomationNodeType.START]
        final_nodes = [node for node in nodes if node.type == AutomationNodeType.FINAL]
        if not start_nodes:
            raise AutomationValidationError("Graph must include at least one start node")
        if not final_nodes:
            raise AutomationValidationError("Graph must include at least one final node")
        return start_nodes

    def _validate_start_trigger_coverage(
        self,
        start_nodes: list[AutomationNode],
        triggers: list[AutomationTrigger],
    ) -> None:
        if len(start_nodes) <= 1:
            return
        start_ids = {node.node_id for node in start_nodes}
        trigger_entry_ids = {trigger.entry_node_id for trigger in triggers}
        if not start_ids.issubset(trigger_entry_ids):
            raise AutomationValidationError(
                "Multiple start nodes require distinct triggers for each start"
            )

    def _validate_edges(
        self,
        edges: list[AutomationEdge],
        node_by_id: dict[str, AutomationNode],
    ) -> dict[str, list[AutomationEdge]]:
        outgoing: dict[str, list[AutomationEdge]] = defaultdict(list)
        for edge in edges:
            if edge.source_node_id not in node_by_id:
                raise AutomationValidationError(f"Edge source node not found: {edge.source_node_id}")
            if edge.target_node_id not in node_by_id:
                raise AutomationValidationError(f"Edge target node not found: {edge.target_node_id}")
            outgoing[edge.source_node_id].append(edge)
        return outgoing

    def _validate_trigger(
        self,
        nodes: list[AutomationNode],
        trigger: AutomationTrigger,
    ) -> None:
        node_by_id = {node.node_id: node for node in nodes}
        node = node_by_id.get(trigger.entry_node_id)
        if not node:
            raise AutomationValidationError(
                f"Trigger entry node not found: {trigger.entry_node_id}"
            )
        if node.type != AutomationNodeType.START:
            raise AutomationValidationError("Triggers must reference a start node")
        if trigger.type == AutomationTriggerType.SCHEDULE:
            try:
                config = ScheduleTriggerConfig.model_validate(trigger.config)
                validate_schedule_expression(
                    ScheduleExpression(config.cron_expression, config.timezone)
                )
            except Exception as exc:
                raise AutomationValidationError(f"Invalid schedule trigger: {exc}") from exc

    def _validate_reachability(
        self,
        nodes: list[AutomationNode],
        entry_node_ids: set[str],
        outgoing: dict[str, list[AutomationEdge]],
    ) -> None:
        reachable = self._reachable_nodes(entry_node_ids, outgoing)
        orphaned = [node.node_id for node in nodes if node.node_id not in reachable]
        if orphaned:
            raise AutomationValidationError(f"Required nodes are unreachable: {', '.join(orphaned)}")

    def _reachable_nodes(
        self, entry_node_ids: set[str], outgoing: dict[str, list[AutomationEdge]]
    ) -> set[str]:
        visited: set[str] = set()
        stack = list(entry_node_ids)
        while stack:
            node_id = stack.pop()
            if node_id in visited:
                continue
            visited.add(node_id)
            stack.extend(edge.target_node_id for edge in outgoing.get(node_id, []))
        return visited

    def _reject_cycles(
        self, entry_node_ids: set[str], outgoing: dict[str, list[AutomationEdge]]
    ) -> None:
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node_id: str) -> None:
            if node_id in visiting:
                raise AutomationValidationError("Graph cycles are not supported yet")
            if node_id in visited:
                return
            visiting.add(node_id)
            for edge in outgoing.get(node_id, []):
                visit(edge.target_node_id)
            visiting.remove(node_id)
            visited.add(node_id)

        for entry_node_id in entry_node_ids:
            visit(entry_node_id)


def _require_outgoing(
    node: AutomationNode,
    ctx: GraphValidationContext,
) -> list[AutomationEdge]:
    node_edges = ctx.outgoing.get(node.node_id, [])
    if not node_edges:
        raise AutomationValidationError(f"Node '{node.node_id}' must have an outgoing edge")
    return node_edges
