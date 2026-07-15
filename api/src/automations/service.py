"""Automation business logic and graph orchestration."""

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
from src.automations.errors import AutomationNotFoundError, AutomationValidationError
from src.automations.repository import AutomationRepository
from src.automations.validation import (
    ActionNodeValidationPolicy,
    AutomationGraphValidator,
    ConditionNodeValidationPolicy,
    FinalNodeValidationPolicy,
    InvokeAgentActionValidator,
    SkillActionValidator,
    StartNodeValidationPolicy,
)
from src.connectors.service import ConnectorService, get_connector_service
from src.crypto import encrypt
from src.form_options import FormOptionsContext, hydrate_form_options
from src.skills.identity import installed_skill_id_for
from src.skills.lifecycle import SkillLifecycleRunner
from src.skills.registry import SkillRegistry, get_skill_registry
from src.automations.triggers.service import AutomationTriggerLifecycleService


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
        lifecycle_runner: SkillLifecycleRunner | None = None,
        trigger_lifecycle: AutomationTriggerLifecycleService | None = None,
    ):
        self.repo = repo or AutomationRepository()
        self.agent_repo = agent_repo or AgentRepository()
        self.skill_registry = skill_registry or get_skill_registry()
        self.connector_service = connector_service or get_connector_service()
        self.lifecycle_runner = lifecycle_runner or SkillLifecycleRunner(self.skill_registry)
        self.trigger_lifecycle = trigger_lifecycle or AutomationTriggerLifecycleService()
        action_validators = [
            InvokeAgentActionValidator(self.agent_repo),
            SkillActionValidator(
                skill_registry=self.skill_registry,
                connector_service=self.connector_service,
                resolve_skill=self._resolve_automation_skill_for_validation,
            ),
        ]
        self.graph_validator = AutomationGraphValidator(
            node_policies=[
                StartNodeValidationPolicy(),
                FinalNodeValidationPolicy(),
                ConditionNodeValidationPolicy(),
                ActionNodeValidationPolicy(action_validators),
            ]
        )

    def create_automation(self, body: CreateAutomationRequest, user_email: str) -> AutomationGraph:
        automation = Automation(
            title=body.title,
            description=body.description,
            status=body.status,
            created_by=user_email,
        )
        saved = self.repo.save_automation(automation)
        start, final, edge, trigger = self._default_graph_entities(saved.automation_id)
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
        previous_status = automation.status
        if body.title is not None:
            automation.title = body.title
        if body.description is not None:
            automation.description = body.description
        if body.status is not None:
            self._apply_status_update(automation, previous_status, body.status, user_email)
        return self.repo.save_automation(automation)

    def delete_automation(self, automation_id: str, user_email: str) -> None:
        graph = self.get_graph(automation_id, user_email)
        for trigger in graph.triggers:
            self.trigger_lifecycle.delete_trigger(automation_id, trigger.trigger_id, user_email)
        for node in graph.nodes:
            self._run_action_delete_lifecycle(
                automation_id,
                node,
                user_email,
                metadata={"automation_deleted": True},
            )
        if not self.repo.soft_delete_automation(automation_id, user_email):
            raise AutomationValidationError("Failed to delete automation")

    def get_graph(self, automation_id: str, user_email: str) -> AutomationGraph:
        automation = self.get_automation(automation_id, user_email)
        self._enable_builtin_skill(automation_id, "agent_invocation", user_email)
        nodes, edges, triggers = self.repo.get_graph(automation_id)
        return AutomationGraph(automation, nodes, edges, triggers)

    def list_triggers(self, automation_id: str, user_email: str) -> list[AutomationTrigger]:
        self.get_automation(automation_id, user_email)
        return self.repo.list_triggers(automation_id)

    def _default_graph_entities(
        self,
        automation_id: str,
    ) -> tuple[AutomationNode, AutomationNode, AutomationEdge, AutomationTrigger]:
        start = AutomationNode(
            automation_id=automation_id,
            type=AutomationNodeType.START,
            name="Start",
            position={"x": 0, "y": 0},
        )
        final = AutomationNode(
            automation_id=automation_id,
            type=AutomationNodeType.FINAL,
            name="Done",
            position={"x": 400, "y": 0},
        )
        edge = AutomationEdge(
            automation_id=automation_id,
            source_node_id=start.node_id,
            target_node_id=final.node_id,
            label="next",
        )
        trigger = AutomationTrigger(
            automation_id=automation_id,
            type=AutomationTriggerType.MANUAL,
            name="Manual",
            enabled=True,
            entry_node_id=start.node_id,
        )
        return start, final, edge, trigger

    def _apply_status_update(
        self,
        automation: Automation,
        previous_status: AutomationStatus,
        next_status: AutomationStatus,
        user_email: str,
    ) -> None:
        if next_status == AutomationStatus.ACTIVE:
            graph = self.get_graph(automation.automation_id, user_email)
            self.validate_graph(
                graph.nodes,
                graph.edges,
                graph.triggers,
                user_email,
                automation.automation_id,
            )
            automation.status = next_status
            if previous_status != AutomationStatus.ACTIVE:
                for trigger in graph.triggers:
                    self.trigger_lifecycle.sync_trigger(automation, trigger, user_email)
            return

        if previous_status == AutomationStatus.ACTIVE:
            graph = self.get_graph(automation.automation_id, user_email)
            self.trigger_lifecycle.pause_schedule_triggers(
                automation.automation_id,
                graph.triggers,
                user_email,
            )
        automation.status = next_status

    def _node_from_graph_item(self, automation_id: str, item: Any) -> AutomationNode:
        return self._ensure_node_id(
            AutomationNode(
                node_id=item.node_id or "",
                automation_id=automation_id,
                type=item.type,
                name=item.name,
                description=item.description,
                position=item.position,
                config=item.config,
            )
        )

    def _node_from_create_request(
        self,
        automation_id: str,
        body: CreateAutomationNodeRequest,
    ) -> AutomationNode:
        return self._ensure_node_id(
            AutomationNode(
                node_id=body.node_id or "",
                automation_id=automation_id,
                type=body.type,
                name=body.name,
                description=body.description,
                position=body.position,
                config=body.config,
            )
        )

    def _ensure_node_id(self, node: AutomationNode) -> AutomationNode:
        if not node.node_id:
            node.node_id = AutomationNode(
                automation_id=node.automation_id,
                type=node.type,
                name=node.name,
            ).node_id
        return node

    def _edge_from_graph_item(self, automation_id: str, item: Any) -> AutomationEdge:
        return self._ensure_edge_id(
            AutomationEdge(
                edge_id=item.edge_id or "",
                automation_id=automation_id,
                source_node_id=item.source_node_id,
                target_node_id=item.target_node_id,
                label=item.label,
                condition=item.condition,
            )
        )

    def _edge_from_create_request(
        self,
        automation_id: str,
        body: CreateAutomationEdgeRequest,
    ) -> AutomationEdge:
        return self._ensure_edge_id(
            AutomationEdge(
                edge_id=body.edge_id or "",
                automation_id=automation_id,
                source_node_id=body.source_node_id,
                target_node_id=body.target_node_id,
                label=body.label,
                condition=body.condition,
            )
        )

    def _ensure_edge_id(self, edge: AutomationEdge) -> AutomationEdge:
        if not edge.edge_id:
            edge.edge_id = AutomationEdge(
                automation_id=edge.automation_id,
                source_node_id=edge.source_node_id,
                target_node_id=edge.target_node_id,
            ).edge_id
        return edge

    def _run_removed_node_lifecycle(
        self,
        automation_id: str,
        existing_nodes: list[AutomationNode],
        next_nodes: list[AutomationNode],
        user_email: str,
    ) -> None:
        next_node_ids = {node.node_id for node in next_nodes}
        for removed_node in existing_nodes:
            if removed_node.node_id not in next_node_ids:
                self._run_action_delete_lifecycle(
                    automation_id,
                    removed_node,
                    user_email,
                    metadata={"automation_deleted": False, "graph_replaced": True},
                )

    def save_graph(
        self, automation_id: str, body: SaveAutomationGraphRequest, user_email: str
    ) -> AutomationGraph:
        automation = self.get_automation(automation_id, user_email)
        nodes = [self._node_from_graph_item(automation_id, item) for item in body.nodes]
        edges = [self._edge_from_graph_item(automation_id, item) for item in body.edges]
        existing_nodes, _, existing_triggers = self.repo.get_graph(automation_id)
        self.validate_graph(nodes, edges, existing_triggers, user_email, automation_id)
        self._run_removed_node_lifecycle(automation_id, existing_nodes, nodes, user_email)
        self.repo.save_graph(automation_id, nodes, edges, existing_triggers)
        return AutomationGraph(automation, nodes, edges, existing_triggers)

    def add_node(
        self, automation_id: str, body: CreateAutomationNodeRequest, user_email: str
    ) -> AutomationNode:
        graph = self.get_graph(automation_id, user_email)
        node = self._node_from_create_request(automation_id, body)
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
        deleted_node = next(node for node in graph.nodes if node.node_id == node_id)
        self._run_action_delete_lifecycle(
            automation_id,
            deleted_node,
            user_email,
            metadata={"automation_deleted": False},
        )
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
        edge = self._edge_from_create_request(automation_id, body)
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
        if any(item.trigger_id == trigger.trigger_id for item in graph.triggers):
            raise AutomationValidationError("Trigger IDs must be unique")
        self.graph_validator.validate_trigger(graph.nodes, trigger)
        saved = self.repo.save_trigger(trigger)
        self.trigger_lifecycle.sync_trigger(graph.automation, saved, user_email)
        return saved

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
        trigger_ids = {item.trigger_id for item in updated_triggers}
        if len(trigger_ids) != len(updated_triggers):
            raise AutomationValidationError("Trigger IDs must be unique")
        self.graph_validator.validate_trigger(graph.nodes, trigger)
        saved = self.repo.save_trigger(trigger)
        self.trigger_lifecycle.sync_trigger(graph.automation, saved, user_email)
        return saved

    def delete_trigger(self, automation_id: str, trigger_id: str, user_email: str) -> None:
        graph = self.get_graph(automation_id, user_email)
        triggers = [trigger for trigger in graph.triggers if trigger.trigger_id != trigger_id]
        if len(triggers) == len(graph.triggers):
            raise AutomationNotFoundError("Trigger not found")
        self.trigger_lifecycle.delete_trigger(automation_id, trigger_id, user_email)
        self.repo.delete_trigger(automation_id, trigger_id)

    def validate_graph(
        self,
        nodes: list[AutomationNode],
        edges: list[AutomationEdge],
        triggers: list[AutomationTrigger],
        user_email: str,
        automation_id: str | None = None,
    ) -> None:
        self.graph_validator.validate(nodes, edges, triggers, user_email, automation_id)

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
        skill = self.install_skill(
            automation_id=automation_id,
            skill_id=skill_id,
            raw_config=body.config,
            user_email=user_email,
        )
        return self._skill_response(skill, user_email)

    def validate_skill_config(
        self,
        *,
        skill_id: str,
        raw_config: dict[str, Any],
        user_email: str,
        validate_connectors: bool = True,
    ) -> dict[str, Any]:
        loaded = self.skill_registry.get(skill_id)
        if not loaded:
            raise AutomationValidationError(f"Unknown skill: {skill_id}")
        if not loaded.manifest.automation.enabled:
            raise AutomationValidationError(f"{loaded.manifest.name} is not available for automations")
        if validate_connectors:
            missing = self.connector_service.missing_required_connectors(loaded.manifest, user_email)
            if missing:
                raise AutomationValidationError(
                    f"{loaded.manifest.name} requires connected connectors: {', '.join(missing)}"
                )
        return self.skill_registry.validate_config(skill_id, raw_config)

    def install_skill(
        self,
        *,
        automation_id: str,
        skill_id: str,
        raw_config: dict[str, Any],
        user_email: str,
        enabled: bool = True,
        validate_connectors: bool = True,
    ) -> AutomationSkill:
        self.get_automation(automation_id, user_email)
        loaded = self.skill_registry.get(skill_id)
        if not loaded:
            raise AutomationValidationError(f"Unknown skill: {skill_id}")
        normalized_config = self.validate_skill_config(
            skill_id=skill_id,
            raw_config=raw_config,
            user_email=user_email,
            validate_connectors=validate_connectors,
        )
        installed_skill_id = installed_skill_id_for(loaded.manifest, normalized_config)
        plain_config, encrypted_secrets, secret_fields = self._split_skill_config(skill_id, normalized_config)
        skill = AutomationSkill(
            automation_id=automation_id,
            installed_skill_id=installed_skill_id,
            skill_id=skill_id,
            namespace=loaded.manifest.namespace,
            skill_name=loaded.manifest.name,
            skill_description=loaded.manifest.description,
            enabled=enabled,
            config=plain_config,
            encrypted_secrets=encrypted_secrets,
            secret_fields=secret_fields,
            enabled_by=user_email,
        )
        return self.repo.save_skill(skill)

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
            normalized = self.skill_registry.validate_config(existing.skill_id, merged)
            next_installed_skill_id = installed_skill_id_for(loaded.manifest, normalized)
            if next_installed_skill_id != (existing.installed_skill_id or existing.skill_id):
                raise AutomationValidationError("Repeatable skill identity fields cannot be changed")
            plain_config, encrypted_secrets, secret_fields = self._split_skill_config(existing.skill_id, normalized)
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
        installed_by_base_id: dict[str, list[AutomationSkill]] = defaultdict(list)
        for enabled in self.repo.list_skills(automation_id):
            installed_by_base_id[enabled.skill_id].append(enabled)
            loaded = self.skill_registry.get(enabled.skill_id)
            if not loaded:
                continue
            connector_statuses = [
                AutomationSkillConnectorResponse(**status.model_dump())
                for status in self.connector_service.statuses_for_manifest(loaded.manifest, user_email)
            ]
            missing = self.connector_service.missing_required_connectors(loaded.manifest, user_email)
            disabled_reason = None
            available = enabled.enabled and not missing and loaded.manifest.automation.enabled
            if not loaded.manifest.automation.enabled:
                disabled_reason = "Skill is not available for automations"
            elif not enabled.enabled:
                disabled_reason = "Skill is disabled for this automation"
            elif missing:
                disabled_reason = "Missing connected connectors: " + ", ".join(missing)
            for action in loaded.manifest.actions:
                if not action.automation.enabled:
                    continue
                actions.append(
                    AutomationActionCatalogItemResponse(
                        skill_id=enabled.skill_id,
                        installed_skill_id=enabled.installed_skill_id or enabled.skill_id,
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
                        available=available,
                        configured=True,
                        enabled=enabled.enabled,
                        disabled_reason=disabled_reason,
                        connectors=connector_statuses,
                    )
                )
        for loaded in self.skill_registry.list():
            if loaded.manifest.id in installed_by_base_id:
                continue
            if not loaded.manifest.automation.enabled:
                continue
            connector_statuses = [
                AutomationSkillConnectorResponse(**status.model_dump())
                for status in self.connector_service.statuses_for_manifest(loaded.manifest, user_email)
            ]
            missing = self.connector_service.missing_required_connectors(loaded.manifest, user_email)
            if missing:
                disabled_reason = "Missing connected connectors: " + ", ".join(missing)
            elif loaded.manifest.form:
                disabled_reason = "Skill requires configuration before use"
            else:
                continue
            install_form = None
            if loaded.manifest.form:
                form = hydrate_form_options(
                    self.skill_registry.install_form(
                        loaded.manifest.id,
                        f"/automations/{automation_id}/skills?skill_id={loaded.manifest.id}",
                    ),
                    FormOptionsContext(user_email=user_email),
                )
                install_form = form.model_dump(mode="json", exclude_none=True)
            for action in loaded.manifest.actions:
                if not action.automation.enabled:
                    continue
                actions.append(
                    AutomationActionCatalogItemResponse(
                        skill_id=loaded.manifest.id,
                        skill_name=loaded.manifest.name,
                        action=action.name,
                        label=f"{loaded.manifest.name}: {action.name}",
                        description=action.description,
                        input_schema=action.input_schema,
                        action_form=(
                            action.action_form.model_dump(mode="json", exclude_none=True)
                            if action.action_form
                            else None
                        ),
                        available=False,
                        configured=False,
                        enabled=False,
                        disabled_reason=disabled_reason,
                        install_schema=install_form,
                        connectors=connector_statuses,
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
            installed_skill_id=item.installed_skill_id or item.skill_id,
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

    def _run_action_delete_lifecycle(
        self,
        automation_id: str,
        node: AutomationNode,
        user_email: str,
        metadata: dict[str, Any],
    ) -> None:
        if node.type != AutomationNodeType.ACTION:
            return
        if node.config.get("action_type") != AutomationActionType.SKILL_ACTION.value:
            return
        try:
            skill_config = SkillActionConfig(**node.config)
        except Exception:
            return

        enabled = self._resolve_automation_skill(
            automation_id,
            installed_skill_id=skill_config.installed_skill_id,
            skill_id=skill_config.skill_id,
            user_email=user_email,
            allow_auto_enable=False,
        )
        skill_id = enabled.skill_id if enabled else skill_config.skill_id
        if not skill_id:
            return

        lifecycle_metadata = {
            **metadata,
            "automation_id": automation_id,
            "automation_node_id": node.node_id,
            "node": node.model_dump(mode="json"),
        }
        self.lifecycle_runner.run_action_delete(
            skill_id=skill_id,
            installed_skill_id=(
                enabled.installed_skill_id or enabled.skill_id
                if enabled
                else skill_config.installed_skill_id
            ),
            action_name=skill_config.action,
            owner_email=user_email,
            config=self.repo.get_skill_runtime_config(enabled) if enabled else {},
            arguments=skill_config.arguments,
            metadata=lifecycle_metadata,
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
                installed_skill_id=skill_id,
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
        if not loaded.manifest.automation.enabled:
            return None
        if loaded.manifest.form:
            return None
        if self.connector_service.missing_required_connectors(loaded.manifest, user_email):
            return None

        return self.repo.save_skill(
            AutomationSkill(
                automation_id=automation_id,
                installed_skill_id=skill_id,
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

    def _resolve_automation_skill(
        self,
        automation_id: str,
        *,
        installed_skill_id: str | None,
        skill_id: str | None,
        user_email: str,
        allow_auto_enable: bool,
    ) -> AutomationSkill | None:
        requested_installed_id = str(installed_skill_id or "").strip()
        requested_skill_id = str(skill_id or "").strip()
        if requested_installed_id:
            installed = self.repo.find_skill(automation_id, requested_installed_id)
            if installed:
                return installed

        if not requested_skill_id:
            return None

        if allow_auto_enable:
            auto_enabled = self._find_or_enable_default_skill(
                automation_id,
                requested_skill_id,
                user_email,
            )
            if auto_enabled:
                return auto_enabled

        matches = [
            item
            for item in self.repo.list_skills(automation_id)
            if item.skill_id == requested_skill_id
        ]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise AutomationValidationError(
                f"Skill '{requested_skill_id}' has multiple installed instances. Use installed_skill_id."
            )
        return None

    def _resolve_automation_skill_for_validation(
        self,
        automation_id: str,
        installed_skill_id: str | None,
        skill_id: str | None,
        user_email: str,
        allow_auto_enable: bool,
    ) -> AutomationSkill | None:
        return self._resolve_automation_skill(
            automation_id,
            installed_skill_id=installed_skill_id,
            skill_id=skill_id,
            user_email=user_email,
            allow_auto_enable=allow_auto_enable,
        )
