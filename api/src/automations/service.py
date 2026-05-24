"""Automation business logic and graph validation."""

import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from src.agents.repository import AgentRepository
from src.automations.models import (
    Automation,
    AutomationActionType,
    AutomationActionCatalogItemResponse,
    AutomationActionCatalogResponse,
    AutomationEdge,
    AutomationGraphResponse,
    AutomationNode,
    AutomationNodeType,
    AutomationSkill,
    AutomationSkillConnectorResponse,
    AutomationSkillResponse,
    AutomationStatus,
    AutomationTrigger,
    AutomationTriggerType,
    EnableAutomationSkillRequest,
    SkillActionConfig,
    CreateAutomationEdgeRequest,
    CreateAutomationNodeRequest,
    CreateAutomationRequest,
    CreateAutomationTriggerRequest,
    SaveAutomationGraphRequest,
    UpdateAutomationEdgeRequest,
    UpdateAutomationSkillRequest,
    UpdateAutomationNodeRequest,
    UpdateAutomationRequest,
    UpdateAutomationTriggerRequest,
)
from src.automations.repository import AutomationRepository
from src.connectors.service import ConnectorService, get_connector_service
from src.crypto import encrypt
from src.skills.registry import SkillRegistry, get_skill_registry


class AutomationNotFoundError(Exception):
    """Raised when an automation does not exist or is not owned by the user."""


class AutomationValidationError(Exception):
    """Raised when an automation graph or state transition is invalid."""


@dataclass
class AutomationGraph:
    automation: Automation
    nodes: list[AutomationNode]
    edges: list[AutomationEdge]
    triggers: list[AutomationTrigger]

    def to_response(self) -> AutomationGraphResponse:
        return AutomationGraphResponse(
            automation=self.automation.to_response(),
            nodes=[node.to_response() for node in self.nodes],
            edges=[edge.to_response() for edge in self.edges],
            triggers=[trigger.to_response() for trigger in self.triggers],
        )


class AutomationService:
    """Owns automation authorization, graph semantics, and validation."""

    def __init__(
        self,
        repo: AutomationRepository | None = None,
        agent_repo: AgentRepository | None = None,
        skill_registry: SkillRegistry | None = None,
        connector_service: ConnectorService | None = None,
    ):
        self.repo = repo or AutomationRepository()
        self.agent_repo = agent_repo or AgentRepository()
        self.skill_registry = skill_registry or get_skill_registry()
        self.connector_service = connector_service or get_connector_service()

    def create_automation(self, body: CreateAutomationRequest, user_email: str) -> AutomationGraph:
        automation = Automation(
            title=body.title,
            description=body.description,
            status=body.status,
            created_by=user_email,
        )
        saved = self.repo.save_automation(automation)
        start = AutomationNode(
            automation_id=saved.automation_id,
            type=AutomationNodeType.START,
            name="Start",
            position={"x": 0, "y": 0},
        )
        final = AutomationNode(
            automation_id=saved.automation_id,
            type=AutomationNodeType.FINAL,
            name="Done",
            position={"x": 400, "y": 0},
        )
        edge = AutomationEdge(
            automation_id=saved.automation_id,
            source_node_id=start.node_id,
            target_node_id=final.node_id,
            label="next",
        )
        trigger = AutomationTrigger(
            automation_id=saved.automation_id,
            type=AutomationTriggerType.MANUAL,
            name="Manual",
            enabled=True,
            entry_node_id=start.node_id,
        )
        self.repo.save_graph(saved.automation_id, [start, final], [edge], [trigger])
        self._enable_builtin_skill(saved.automation_id, "agent_invocation", user_email)
        return AutomationGraph(saved, [start, final], [edge], [trigger])

    def get_automation(self, automation_id: str, user_email: str) -> Automation:
        automation = self.repo.find_automation_by_id(automation_id, user_email)
        if not automation or automation.status == AutomationStatus.DELETED:
            raise AutomationNotFoundError("Automation not found")
        return automation

    def list_automations(self, user_email: str) -> list[Automation]:
        return self.repo.find_automations_by_user(user_email)

    def update_automation(
        self, automation_id: str, body: UpdateAutomationRequest, user_email: str
    ) -> Automation:
        automation = self.get_automation(automation_id, user_email)
        if body.title is not None:
            automation.title = body.title
        if body.description is not None:
            automation.description = body.description
        if body.status is not None:
            if body.status == AutomationStatus.ACTIVE:
                graph = self.get_graph(automation_id, user_email)
                self.validate_graph(graph.nodes, graph.edges, graph.triggers, user_email, automation_id)
            automation.status = body.status
        return self.repo.save_automation(automation)

    def delete_automation(self, automation_id: str, user_email: str) -> None:
        self.get_automation(automation_id, user_email)
        if not self.repo.soft_delete_automation(automation_id, user_email):
            raise AutomationValidationError("Failed to delete automation")

    def get_graph(self, automation_id: str, user_email: str) -> AutomationGraph:
        automation = self.get_automation(automation_id, user_email)
        self._enable_builtin_skill(automation_id, "agent_invocation", user_email)
        nodes, edges, triggers = self.repo.get_graph(automation_id)
        return AutomationGraph(automation, nodes, edges, triggers)

    def save_graph(
        self, automation_id: str, body: SaveAutomationGraphRequest, user_email: str
    ) -> AutomationGraph:
        automation = self.get_automation(automation_id, user_email)
        nodes = [
            AutomationNode(
                node_id=item.node_id or "",
                automation_id=automation_id,
                type=item.type,
                name=item.name,
                description=item.description,
                position=item.position,
                config=item.config,
            )
            for item in body.nodes
        ]
        for node in nodes:
            if not node.node_id:
                node.node_id = AutomationNode(automation_id=automation_id, type=node.type, name=node.name).node_id
        edges = [
            AutomationEdge(
                edge_id=item.edge_id or "",
                automation_id=automation_id,
                source_node_id=item.source_node_id,
                target_node_id=item.target_node_id,
                label=item.label,
                condition=item.condition,
            )
            for item in body.edges
        ]
        for edge in edges:
            if not edge.edge_id:
                edge.edge_id = AutomationEdge(
                    automation_id=automation_id,
                    source_node_id=edge.source_node_id,
                    target_node_id=edge.target_node_id,
                ).edge_id
        triggers = [
            AutomationTrigger(
                trigger_id=item.trigger_id or "",
                automation_id=automation_id,
                type=item.type,
                name=item.name,
                enabled=item.enabled,
                entry_node_id=item.entry_node_id,
                config=item.config,
            )
            for item in body.triggers
        ]
        for trigger in triggers:
            if not trigger.trigger_id:
                trigger.trigger_id = AutomationTrigger(
                    automation_id=automation_id,
                    type=trigger.type,
                    name=trigger.name,
                    entry_node_id=trigger.entry_node_id,
                ).trigger_id
        self.validate_graph(nodes, edges, triggers, user_email, automation_id)
        self.repo.save_graph(automation_id, nodes, edges, triggers)
        return AutomationGraph(automation, nodes, edges, triggers)

    def add_node(
        self, automation_id: str, body: CreateAutomationNodeRequest, user_email: str
    ) -> AutomationNode:
        graph = self.get_graph(automation_id, user_email)
        node = AutomationNode(
            node_id=body.node_id or "",
            automation_id=automation_id,
            type=body.type,
            name=body.name,
            description=body.description,
            position=body.position,
            config=body.config,
        )
        if not node.node_id:
            node.node_id = AutomationNode(automation_id=automation_id, type=body.type, name=body.name).node_id
        self.validate_graph([*graph.nodes, node], graph.edges, graph.triggers, user_email, automation_id)
        return self.repo.save_node(node)

    def update_node(
        self,
        automation_id: str,
        node_id: str,
        body: UpdateAutomationNodeRequest,
        user_email: str,
    ) -> AutomationNode:
        graph = self.get_graph(automation_id, user_email)
        node = next((item for item in graph.nodes if item.node_id == node_id), None)
        if not node:
            raise AutomationNotFoundError("Node not found")
        if body.type is not None:
            node.type = body.type
        if body.name is not None:
            node.name = body.name
        if body.description is not None:
            node.description = body.description
        if body.position is not None:
            node.position = body.position
        if body.config is not None:
            node.config = body.config
        updated_nodes = [node if item.node_id == node_id else item for item in graph.nodes]
        self.validate_graph(updated_nodes, graph.edges, graph.triggers, user_email, automation_id)
        return self.repo.save_node(node)

    def delete_node(self, automation_id: str, node_id: str, user_email: str) -> None:
        graph = self.get_graph(automation_id, user_email)
        nodes = [node for node in graph.nodes if node.node_id != node_id]
        if len(nodes) == len(graph.nodes):
            raise AutomationNotFoundError("Node not found")
        edges = [
            edge
            for edge in graph.edges
            if edge.source_node_id != node_id and edge.target_node_id != node_id
        ]
        triggers = [trigger for trigger in graph.triggers if trigger.entry_node_id != node_id]
        self.validate_graph(nodes, edges, triggers, user_email, automation_id)
        self.repo.delete_node(automation_id, node_id)
        for edge in graph.edges:
            if edge.source_node_id == node_id or edge.target_node_id == node_id:
                self.repo.delete_edge(automation_id, edge.edge_id)
        for trigger in graph.triggers:
            if trigger.entry_node_id == node_id:
                self.repo.delete_trigger(automation_id, trigger.trigger_id)

    def add_edge(
        self, automation_id: str, body: CreateAutomationEdgeRequest, user_email: str
    ) -> AutomationEdge:
        graph = self.get_graph(automation_id, user_email)
        edge = AutomationEdge(
            edge_id=body.edge_id or "",
            automation_id=automation_id,
            source_node_id=body.source_node_id,
            target_node_id=body.target_node_id,
            label=body.label,
            condition=body.condition,
        )
        if not edge.edge_id:
            edge.edge_id = AutomationEdge(
                automation_id=automation_id,
                source_node_id=edge.source_node_id,
                target_node_id=edge.target_node_id,
            ).edge_id
        self.validate_graph(graph.nodes, [*graph.edges, edge], graph.triggers, user_email, automation_id)
        return self.repo.save_edge(edge)

    def update_edge(
        self,
        automation_id: str,
        edge_id: str,
        body: UpdateAutomationEdgeRequest,
        user_email: str,
    ) -> AutomationEdge:
        graph = self.get_graph(automation_id, user_email)
        edge = next((item for item in graph.edges if item.edge_id == edge_id), None)
        if not edge:
            raise AutomationNotFoundError("Edge not found")
        if body.source_node_id is not None:
            edge.source_node_id = body.source_node_id
        if body.target_node_id is not None:
            edge.target_node_id = body.target_node_id
        if body.label is not None:
            edge.label = body.label
        if body.condition is not None:
            edge.condition = body.condition
        updated_edges = [edge if item.edge_id == edge_id else item for item in graph.edges]
        self.validate_graph(graph.nodes, updated_edges, graph.triggers, user_email, automation_id)
        return self.repo.save_edge(edge)

    def delete_edge(self, automation_id: str, edge_id: str, user_email: str) -> None:
        graph = self.get_graph(automation_id, user_email)
        edges = [edge for edge in graph.edges if edge.edge_id != edge_id]
        if len(edges) == len(graph.edges):
            raise AutomationNotFoundError("Edge not found")
        self.validate_graph(graph.nodes, edges, graph.triggers, user_email, automation_id)
        self.repo.delete_edge(automation_id, edge_id)

    def add_trigger(
        self, automation_id: str, body: CreateAutomationTriggerRequest, user_email: str
    ) -> AutomationTrigger:
        graph = self.get_graph(automation_id, user_email)
        trigger = AutomationTrigger(
            trigger_id=body.trigger_id or "",
            automation_id=automation_id,
            type=body.type,
            name=body.name,
            enabled=body.enabled,
            entry_node_id=body.entry_node_id,
            config=body.config,
        )
        if not trigger.trigger_id:
            trigger.trigger_id = AutomationTrigger(
                automation_id=automation_id,
                type=trigger.type,
                name=trigger.name,
                entry_node_id=trigger.entry_node_id,
            ).trigger_id
        self.validate_graph(graph.nodes, graph.edges, [*graph.triggers, trigger], user_email, automation_id)
        return self.repo.save_trigger(trigger)

    def update_trigger(
        self,
        automation_id: str,
        trigger_id: str,
        body: UpdateAutomationTriggerRequest,
        user_email: str,
    ) -> AutomationTrigger:
        graph = self.get_graph(automation_id, user_email)
        trigger = next((item for item in graph.triggers if item.trigger_id == trigger_id), None)
        if not trigger:
            raise AutomationNotFoundError("Trigger not found")
        if body.type is not None:
            trigger.type = body.type
        if body.name is not None:
            trigger.name = body.name
        if body.enabled is not None:
            trigger.enabled = body.enabled
        if body.entry_node_id is not None:
            trigger.entry_node_id = body.entry_node_id
        if body.config is not None:
            trigger.config = body.config
        updated_triggers = [
            trigger if item.trigger_id == trigger_id else item for item in graph.triggers
        ]
        self.validate_graph(graph.nodes, graph.edges, updated_triggers, user_email, automation_id)
        return self.repo.save_trigger(trigger)

    def delete_trigger(self, automation_id: str, trigger_id: str, user_email: str) -> None:
        graph = self.get_graph(automation_id, user_email)
        triggers = [trigger for trigger in graph.triggers if trigger.trigger_id != trigger_id]
        if len(triggers) == len(graph.triggers):
            raise AutomationNotFoundError("Trigger not found")
        self.validate_graph(graph.nodes, graph.edges, triggers, user_email, automation_id)
        self.repo.delete_trigger(automation_id, trigger_id)

    def validate_graph(
        self,
        nodes: list[AutomationNode],
        edges: list[AutomationEdge],
        triggers: list[AutomationTrigger],
        user_email: str,
        automation_id: str | None = None,
    ) -> None:
        node_by_id = {node.node_id: node for node in nodes}
        if len(node_by_id) != len(nodes):
            raise AutomationValidationError("Node IDs must be unique")
        edge_ids = {edge.edge_id for edge in edges}
        if len(edge_ids) != len(edges):
            raise AutomationValidationError("Edge IDs must be unique")
        trigger_ids = {trigger.trigger_id for trigger in triggers}
        if len(trigger_ids) != len(triggers):
            raise AutomationValidationError("Trigger IDs must be unique")

        start_nodes = [node for node in nodes if node.type == AutomationNodeType.START]
        final_nodes = [node for node in nodes if node.type == AutomationNodeType.FINAL]
        if not start_nodes:
            raise AutomationValidationError("Graph must include at least one start node")
        if not final_nodes:
            raise AutomationValidationError("Graph must include at least one final node")

        start_ids = {node.node_id for node in start_nodes}
        if len(start_nodes) > 1:
            trigger_entry_ids = {trigger.entry_node_id for trigger in triggers}
            if not start_ids.issubset(trigger_entry_ids):
                raise AutomationValidationError(
                    "Multiple start nodes require distinct triggers for each start"
                )

        outgoing: dict[str, list[AutomationEdge]] = defaultdict(list)
        for edge in edges:
            if edge.source_node_id not in node_by_id:
                raise AutomationValidationError(f"Edge source node not found: {edge.source_node_id}")
            if edge.target_node_id not in node_by_id:
                raise AutomationValidationError(f"Edge target node not found: {edge.target_node_id}")
            outgoing[edge.source_node_id].append(edge)

        for trigger in triggers:
            node = node_by_id.get(trigger.entry_node_id)
            if not node:
                raise AutomationValidationError(
                    f"Trigger entry node not found: {trigger.entry_node_id}"
                )
            if node.type != AutomationNodeType.START:
                raise AutomationValidationError("Triggers must reference a start node")

        entry_node_ids = {trigger.entry_node_id for trigger in triggers} or {
            node.node_id for node in start_nodes
        }
        reachable = self._reachable_nodes(entry_node_ids, outgoing)
        orphaned = [node.node_id for node in nodes if node.node_id not in reachable]
        if orphaned:
            raise AutomationValidationError(f"Required nodes are unreachable: {', '.join(orphaned)}")

        self._reject_cycles(entry_node_ids, outgoing)

        for node in nodes:
            node_edges = outgoing.get(node.node_id, [])
            if node.type == AutomationNodeType.FINAL:
                if node_edges:
                    raise AutomationValidationError("Final nodes cannot have outgoing edges")
                continue
            if not node_edges:
                raise AutomationValidationError(f"Node '{node.node_id}' must have an outgoing edge")
            if node.type == AutomationNodeType.CONDITION:
                config = ConditionNodeConfigAdapter.validate(node.config)
                labels = {edge.label for edge in node_edges}
                if config.true_label not in labels or config.false_label not in labels:
                    raise AutomationValidationError(
                        "Condition nodes must have valid true and false outgoing branches"
                    )
            elif node.type == AutomationNodeType.ACTION:
                self._validate_action_config(node.config, user_email, automation_id or node.automation_id)

    def _validate_action_config(self, config: dict[str, Any], user_email: str, automation_id: str) -> None:
        action_type = config.get("action_type")
        if action_type == AutomationActionType.INVOKE_AGENT.value:
            agent_id = config.get("agent_id")
            prompt_template = config.get("prompt_template")
            if not agent_id or not isinstance(agent_id, str):
                raise AutomationValidationError("invoke_agent action requires agent_id")
            if not prompt_template or not isinstance(prompt_template, str):
                raise AutomationValidationError("invoke_agent action requires prompt_template")
            if not self.agent_repo.find_agent_by_id(agent_id, user_email):
                raise AutomationValidationError("invoke_agent action references an unknown agent")
            return
        if action_type == AutomationActionType.SKILL_ACTION.value:
            try:
                skill_config = SkillActionConfig(**config)
            except Exception as exc:
                raise AutomationValidationError("skill_action requires skill_id, action, and arguments") from exc
            enabled = self._find_or_enable_default_skill(automation_id, skill_config.skill_id, user_email)
            if not enabled or not enabled.enabled:
                raise AutomationValidationError(
                    "skill_action references a skill that is not enabled for this automation"
                )
            loaded = self.skill_registry.get(skill_config.skill_id)
            if not loaded:
                raise AutomationValidationError("skill_action references an unavailable skill")
            missing = self.connector_service.missing_required_connectors(loaded.manifest, user_email)
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
            if not isinstance(skill_config.arguments, dict):
                raise AutomationValidationError("skill_action arguments must be an object")
            for field_name in action.input_schema.get("required", []):
                if field_name not in skill_config.arguments:
                    raise AutomationValidationError(
                        f"skill_action missing required action argument: {field_name}"
                    )
            return
        if action_type in {
            AutomationActionType.SEND_EMAIL.value,
            AutomationActionType.WEBHOOK_CALL.value,
        }:
            raise AutomationValidationError(f"Action type '{action_type}' is not implemented yet")
        raise AutomationValidationError("Action node requires a supported action_type")

    def list_skills(self, automation_id: str, user_email: str) -> list[AutomationSkillResponse]:
        self.get_automation(automation_id, user_email)
        return [self._skill_response(item, user_email) for item in self.repo.list_skills(automation_id)]

    def enable_skill(
        self,
        automation_id: str,
        skill_id: str,
        body: EnableAutomationSkillRequest,
        user_email: str,
    ) -> AutomationSkillResponse:
        self.get_automation(automation_id, user_email)
        loaded = self.skill_registry.get(skill_id)
        if not loaded:
            raise AutomationValidationError(f"Unknown skill: {skill_id}")
        missing = self.connector_service.missing_required_connectors(loaded.manifest, user_email)
        if missing:
            raise AutomationValidationError(
                f"{loaded.manifest.name} requires connected connectors: {', '.join(missing)}"
            )
        plain_config, encrypted_secrets, secret_fields = self._split_skill_config(
            skill_id,
            self.skill_registry.validate_config(skill_id, body.config),
        )
        skill = AutomationSkill(
            automation_id=automation_id,
            skill_id=skill_id,
            namespace=loaded.manifest.namespace,
            skill_name=loaded.manifest.name,
            skill_description=loaded.manifest.description,
            enabled=True,
            config=plain_config,
            encrypted_secrets=encrypted_secrets,
            secret_fields=secret_fields,
            enabled_by=user_email,
        )
        return self._skill_response(self.repo.save_skill(skill), user_email)

    def update_skill(
        self,
        automation_id: str,
        skill_id: str,
        body: UpdateAutomationSkillRequest,
        user_email: str,
    ) -> AutomationSkillResponse:
        self.get_automation(automation_id, user_email)
        existing = self.repo.find_skill(automation_id, skill_id)
        if not existing:
            raise AutomationNotFoundError("Automation skill not found")
        loaded = self.skill_registry.get(skill_id)
        if not loaded:
            raise AutomationValidationError("Skill not available")
        if body.enabled is not None:
            existing.enabled = body.enabled
        if body.config is not None:
            merged = self.repo.get_skill_runtime_config(existing)
            merged.update(body.config)
            plain_config, encrypted_secrets, secret_fields = self._split_skill_config(
                skill_id,
                self.skill_registry.validate_config(skill_id, merged),
            )
            existing.config = plain_config
            existing.encrypted_secrets = encrypted_secrets
            existing.secret_fields = secret_fields
        return self._skill_response(self.repo.save_skill(existing), user_email)

    def delete_skill(self, automation_id: str, skill_id: str, user_email: str) -> None:
        self.get_automation(automation_id, user_email)
        if not self.repo.delete_skill(automation_id, skill_id):
            raise AutomationValidationError("Failed to delete automation skill")

    def list_action_catalog(
        self,
        automation_id: str,
        user_email: str,
    ) -> AutomationActionCatalogResponse:
        self.get_automation(automation_id, user_email)
        self._enable_default_available_skills(automation_id, user_email)
        actions: list[AutomationActionCatalogItemResponse] = []
        for enabled in self.repo.list_skills(automation_id):
            if not enabled.enabled:
                continue
            loaded = self.skill_registry.get(enabled.skill_id)
            if not loaded:
                continue
            if self.connector_service.missing_required_connectors(loaded.manifest, user_email):
                continue
            for action in loaded.manifest.actions:
                actions.append(
                    AutomationActionCatalogItemResponse(
                        skill_id=enabled.skill_id,
                        skill_name=enabled.skill_name,
                        action=action.name,
                        label=f"{enabled.skill_name}: {action.name}",
                        description=action.description,
                        input_schema=action.input_schema,
                        action_form=(
                            action.action_form.model_dump(mode="json", exclude_none=True)
                            if action.action_form
                            else None
                        ),
                    )
                )
        return AutomationActionCatalogResponse(actions=actions)

    def _skill_response(self, item: AutomationSkill, user_email: str) -> AutomationSkillResponse:
        loaded = self.skill_registry.get(item.skill_id)
        connectors = []
        if loaded:
            connectors = [
                AutomationSkillConnectorResponse(**status.model_dump())
                for status in self.connector_service.statuses_for_manifest(loaded.manifest, user_email)
            ]
        return AutomationSkillResponse(
            skill_id=item.skill_id,
            namespace=item.namespace,
            name=item.skill_name,
            description=item.skill_description,
            enabled=item.enabled,
            enabled_at=item.enabled_at,
            updated_at=item.updated_at,
            config=item.config,
            connectors=connectors,
        )

    def _split_skill_config(self, skill_id: str, config: dict[str, Any]) -> tuple[dict[str, Any], str, list[str]]:
        secret_fields = sorted(self.skill_registry.secret_fields(skill_id))
        plain_config = {key: value for key, value in config.items() if key not in secret_fields}
        secret_config = {key: value for key, value in config.items() if key in secret_fields}
        encrypted_secrets = encrypt(json.dumps(secret_config, ensure_ascii=True)) if secret_config else ""
        return plain_config, encrypted_secrets, secret_fields

    def _enable_builtin_skill(self, automation_id: str, skill_id: str, user_email: str) -> None:
        if self.repo.find_skill(automation_id, skill_id):
            return
        loaded = self.skill_registry.get(skill_id)
        if not loaded:
            return
        self.repo.save_skill(
            AutomationSkill(
                automation_id=automation_id,
                skill_id=skill_id,
                namespace=loaded.manifest.namespace,
                skill_name=loaded.manifest.name,
                skill_description=loaded.manifest.description,
                enabled=True,
                config={},
                enabled_by=user_email,
            )
        )

    def _enable_default_available_skills(self, automation_id: str, user_email: str) -> None:
        for loaded in self.skill_registry.list():
            self._find_or_enable_default_skill(automation_id, loaded.manifest.id, user_email)

    def _find_or_enable_default_skill(
        self,
        automation_id: str,
        skill_id: str,
        user_email: str,
    ) -> AutomationSkill | None:
        existing = self.repo.find_skill(automation_id, skill_id)
        if existing:
            return existing

        loaded = self.skill_registry.get(skill_id)
        if not loaded:
            return None
        if loaded.manifest.form:
            return None
        if self.connector_service.missing_required_connectors(loaded.manifest, user_email):
            return None

        return self.repo.save_skill(
            AutomationSkill(
                automation_id=automation_id,
                skill_id=skill_id,
                namespace=loaded.manifest.namespace,
                skill_name=loaded.manifest.name,
                skill_description=loaded.manifest.description,
                enabled=True,
                config={},
                encrypted_secrets="",
                secret_fields=[],
                enabled_by=user_email,
            )
        )

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


class ConditionNodeConfigAdapter:
    @staticmethod
    def validate(config: dict[str, Any]) -> Any:
        from src.automations.models import ConditionNodeConfig

        try:
            return ConditionNodeConfig(**config)
        except Exception as exc:
            raise AutomationValidationError("Condition node requires a valid expression") from exc
