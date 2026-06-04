"""Automation runner for manual/test execution."""

import json
import re
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from src.agents.architectures import get_agent_architecture
from src.agents.repository import AgentRepository
from src.automations.models import (
    Automation,
    AutomationActionType,
    AutomationEdge,
    AutomationNode,
    AutomationNodeRunStatus,
    AutomationNodeType,
    AutomationRun,
    AutomationRunStatus,
    AutomationRunNodeResult,
    AutomationSkill,
    AutomationTrigger,
    AutomationTriggerType,
)
from src.automations.repository import AutomationRepository
from src.automations.service import AutomationGraph, AutomationService, AutomationValidationError
from src.conversations.models import AutomationConversation
from src.conversations.repository import ConversationRepository
from src.connectors.service import ConnectorService, get_connector_service
from src.skills.service import SkillService
from src.skills.service import get_skill_service


class AutomationRunner:
    """Executes an automation graph in-process for manual/test runs."""

    def __init__(
        self,
        automation_repo: AutomationRepository | None = None,
        agent_repo: AgentRepository | None = None,
        conversation_repo: ConversationRepository | None = None,
        skill_service: SkillService | None = None,
        connector_service: ConnectorService | None = None,
    ):
        self.automation_repo = automation_repo or AutomationRepository()
        self.agent_repo = agent_repo or AgentRepository()
        self.conversation_repo = conversation_repo or ConversationRepository()
        self.skill_service = skill_service or get_skill_service()
        self.connector_service = connector_service or get_connector_service()

    async def run_test(
        self,
        graph: AutomationGraph,
        trigger_id: str | None,
        input_data: dict[str, Any],
        user_email: str,
    ) -> AutomationRun:
        run = self.create_test_run(graph, trigger_id, input_data, user_email)
        return await self.execute_run_graph(graph, run, user_email)

    def create_test_run(
        self,
        graph: AutomationGraph,
        trigger_id: str | None,
        input_data: dict[str, Any],
        user_email: str,
    ) -> AutomationRun:
        trigger = self._select_trigger(graph.triggers, trigger_id)
        first_agent_id = self._first_agent_id(graph.nodes)
        run = AutomationRun(
            automation_id=graph.automation.automation_id,
            trigger_id=trigger.trigger_id if trigger else None,
            status=AutomationRunStatus.PENDING,
            context={
                "input": input_data,
                "trigger": {
                    "type": trigger.type.value if trigger else AutomationTriggerType.MANUAL.value,
                    "trigger_id": trigger.trigger_id if trigger else None,
                },
                "nodes": {},
            },
            created_by=user_email,
        )
        conversation = AutomationConversation(
            title=f"Automation Run: {graph.automation.title}",
            description="Workflow execution",
            agent_id=first_agent_id,
            created_by=user_email,
            automation_id=graph.automation.automation_id,
            automation_run_id=run.run_id,
        )
        saved_conversation = self.conversation_repo.save(conversation)
        run.conversation_id = saved_conversation.conversation_id
        return self.automation_repo.save_run(run)

    def create_scheduled_run(
        self,
        graph: AutomationGraph,
        input_data: dict[str, Any],
        user_email: str,
        schedule_id: str,
        trigger_id: str | None = None,
    ) -> AutomationRun:
        first_agent_id = self._first_agent_id(graph.nodes)
        run = AutomationRun(
            automation_id=graph.automation.automation_id,
            status=AutomationRunStatus.PENDING,
            context={
                "input": input_data,
                "trigger": {
                    "type": AutomationTriggerType.SCHEDULE.value,
                    "trigger_id": trigger_id,
                    "schedule_id": schedule_id,
                },
                "nodes": {},
            },
            created_by=user_email,
        )
        conversation = AutomationConversation(
            title=f"Scheduled Automation Run: {graph.automation.title}",
            description="Scheduled workflow execution",
            agent_id=first_agent_id,
            created_by=user_email,
            automation_id=graph.automation.automation_id,
            automation_run_id=run.run_id,
        )
        saved_conversation = self.conversation_repo.save(conversation)
        run.conversation_id = saved_conversation.conversation_id
        return self.automation_repo.save_run(run)

    async def execute_run(self, run_id: str, user_email: str) -> AutomationRun:
        run = self.automation_repo.find_run_by_id(run_id, user_email)
        if not run:
            raise AutomationValidationError("Run not found")
        if run.status in {
            AutomationRunStatus.SUCCEEDED,
            AutomationRunStatus.FAILED,
            AutomationRunStatus.CANCELLED,
        }:
            return run

        service = AutomationService(repo=self.automation_repo)
        graph = service.get_graph(run.automation_id, user_email)
        service.validate_graph(graph.nodes, graph.edges, graph.triggers, user_email)
        return await self.execute_run_graph(graph, run, user_email)

    async def execute_run_graph(
        self,
        graph: AutomationGraph,
        run: AutomationRun,
        user_email: str,
    ) -> AutomationRun:
        trigger = self._select_trigger(graph.triggers, run.trigger_id)
        if not run.conversation_id:
            raise AutomationValidationError("Run is missing conversation")

        conversation = self.conversation_repo.find_by_id(run.conversation_id, user_email)
        if not isinstance(conversation, AutomationConversation):
            raise AutomationValidationError("Run conversation not found")

        if run.status == AutomationRunStatus.PENDING:
            run.status = AutomationRunStatus.RUNNING
            run.started_at = datetime.now(timezone.utc)
            self.automation_repo.save_run(run)

        try:
            current_node_id = trigger.entry_node_id if trigger else self._default_start_node(graph.nodes).node_id
            node_by_id = {node.node_id: node for node in graph.nodes}
            outgoing = self._outgoing_edges(graph.edges)

            while True:
                node = node_by_id[current_node_id]
                if node.type == AutomationNodeType.FINAL:
                    self._store_context_node(run, node.node_id, "succeeded", {}, {})
                    run.status = AutomationRunStatus.SUCCEEDED
                    run.completed_at = datetime.now(timezone.utc)
                    self.automation_repo.save_run(run)
                    return run

                result = await self._execute_node(
                    automation=graph.automation,
                    node=node,
                    run=run,
                    conversation=conversation,
                    user_email=user_email,
                )
                self.automation_repo.save_node_result(result)

                self._store_context_node(
                    run,
                    node.node_id,
                    result.status,
                    result.output,
                    result.message_ids,
                    result.error,
                )
                self.automation_repo.save_run(run)

                if result.status == AutomationNodeRunStatus.FAILED:
                    error_edge = self._edge_for_label(outgoing.get(node.node_id, []), "error")
                    if error_edge:
                        current_node_id = error_edge.target_node_id
                        continue
                    run.status = AutomationRunStatus.FAILED
                    run.error = result.error
                    run.completed_at = datetime.now(timezone.utc)
                    self.automation_repo.save_run(run)
                    return run

                next_label = self._next_label(node, run.context)
                edge = self._edge_for_label(outgoing.get(node.node_id, []), next_label)
                if not edge:
                    raise AutomationValidationError(
                        f"Node '{node.node_id}' has no '{next_label}' outgoing edge"
                    )
                current_node_id = edge.target_node_id
        except Exception as exc:
            run.status = AutomationRunStatus.FAILED
            run.error = str(exc)
            run.completed_at = datetime.now(timezone.utc)
            self.automation_repo.save_run(run)
            return run

    async def _execute_node(
        self,
        automation: Automation,
        node: AutomationNode,
        run: AutomationRun,
        conversation: AutomationConversation,
        user_email: str,
    ) -> AutomationRunNodeResult:
        started_at = datetime.now(timezone.utc)
        if node.type == AutomationNodeType.START:
            return AutomationRunNodeResult(
                run_id=run.run_id,
                automation_id=automation.automation_id,
                node_id=node.node_id,
                status=AutomationNodeRunStatus.SUCCEEDED,
                input=deepcopy(run.context.get("input", {})),
                output=deepcopy(run.context.get("input", {})),
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
            )

        if node.type == AutomationNodeType.CONDITION:
            value = self._evaluate_condition(node.config.get("expression", ""), run.context)
            return AutomationRunNodeResult(
                run_id=run.run_id,
                automation_id=automation.automation_id,
                node_id=node.node_id,
                status=AutomationNodeRunStatus.SUCCEEDED,
                input={"expression": node.config.get("expression")},
                output={"result": value},
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
            )

        if node.type != AutomationNodeType.ACTION:
            raise AutomationValidationError(f"Unsupported node type: {node.type}")

        action_type = node.config.get("action_type")
        if action_type != AutomationActionType.INVOKE_AGENT.value:
            if action_type == AutomationActionType.SKILL_ACTION.value:
                return await self._execute_skill_action(
                    automation=automation,
                    node=node,
                    run=run,
                    conversation=conversation,
                    user_email=user_email,
                    started_at=started_at,
                )
            return AutomationRunNodeResult(
                run_id=run.run_id,
                automation_id=automation.automation_id,
                node_id=node.node_id,
                status=AutomationNodeRunStatus.FAILED,
                input=node.config,
                error=f"Action type '{action_type}' is not implemented",
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
            )

        agent_id = node.config["agent_id"]
        agent = self.agent_repo.find_agent_by_id(agent_id, user_email)
        if not agent:
            return AutomationRunNodeResult(
                run_id=run.run_id,
                automation_id=automation.automation_id,
                node_id=node.node_id,
                status=AutomationNodeRunStatus.FAILED,
                input={"agent_id": agent_id},
                error="Agent not found",
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
            )

        prompt = self._render_template(node.config["prompt_template"], run.context)
        architecture = get_agent_architecture(agent.agent_architecture)
        invocation = await architecture.handle_message_buffered(
            agent=agent,
            conversation=conversation,
            user_message=prompt,
            owner_email=user_email,
            actor_email=user_email,
            actor_id=user_email,
        )
        return AutomationRunNodeResult(
            run_id=run.run_id,
            automation_id=automation.automation_id,
            node_id=node.node_id,
            status=(
                AutomationNodeRunStatus.SUCCEEDED
                if invocation.success
                else AutomationNodeRunStatus.FAILED
            ),
            input={"agent_id": agent_id, "prompt": prompt},
            output={
                "response_text": invocation.response_text,
                "events": [
                    event.model_dump(mode="json", exclude_none=True)
                    for event in invocation.events
                ],
            },
            error=invocation.error,
            message_ids={
                key: value
                for key, value in {
                    "user_message_id": invocation.user_message_id,
                    "assistant_message_id": invocation.assistant_message_id,
                }.items()
                if value
            },
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
        )

    async def _execute_skill_action(
        self,
        automation: Automation,
        node: AutomationNode,
        run: AutomationRun,
        conversation: AutomationConversation,
        user_email: str,
        started_at: datetime,
    ) -> AutomationRunNodeResult:
        installed_skill_id = str(node.config.get("installed_skill_id", "")).strip()
        skill_id = str(node.config.get("skill_id", "")).strip()
        action_name = str(node.config.get("action", "")).strip()
        raw_arguments = node.config.get("arguments", {})
        if not isinstance(raw_arguments, dict):
            return AutomationRunNodeResult(
                run_id=run.run_id,
                automation_id=automation.automation_id,
                node_id=node.node_id,
                status=AutomationNodeRunStatus.FAILED,
                input=node.config,
                error="skill_action arguments must be an object",
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
            )
        if not (installed_skill_id or skill_id) or not action_name:
            return AutomationRunNodeResult(
                run_id=run.run_id,
                automation_id=automation.automation_id,
                node_id=node.node_id,
                status=AutomationNodeRunStatus.FAILED,
                input=node.config,
                error="skill_action requires installed_skill_id or skill_id and action",
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
            )

        try:
            enabled = self._resolve_automation_skill(
                automation.automation_id,
                installed_skill_id=installed_skill_id,
                skill_id=skill_id,
            )
        except ValueError as exc:
            return AutomationRunNodeResult(
                run_id=run.run_id,
                automation_id=automation.automation_id,
                node_id=node.node_id,
                status=AutomationNodeRunStatus.FAILED,
                input={"installed_skill_id": installed_skill_id, "skill_id": skill_id, "action": action_name},
                error=str(exc),
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
            )
        if not enabled or not enabled.enabled:
            return AutomationRunNodeResult(
                run_id=run.run_id,
                automation_id=automation.automation_id,
                node_id=node.node_id,
                status=AutomationNodeRunStatus.FAILED,
                input={"installed_skill_id": installed_skill_id, "skill_id": skill_id, "action": action_name},
                error="Skill is not enabled for this automation",
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
            )

        loaded = self.skill_service.registry.get(enabled.skill_id)
        if not loaded:
            return AutomationRunNodeResult(
                run_id=run.run_id,
                automation_id=automation.automation_id,
                node_id=node.node_id,
                status=AutomationNodeRunStatus.FAILED,
                input={"installed_skill_id": installed_skill_id, "skill_id": skill_id, "action": action_name},
                error="Skill is not available",
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
            )
        missing = self.connector_service.missing_required_connectors(loaded.manifest, user_email)
        if missing:
            return AutomationRunNodeResult(
                run_id=run.run_id,
                automation_id=automation.automation_id,
                node_id=node.node_id,
                status=AutomationNodeRunStatus.FAILED,
                input={"installed_skill_id": installed_skill_id, "skill_id": skill_id, "action": action_name},
                error="Missing connected connectors: " + ", ".join(missing),
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
            )

        arguments = self._render_smart_values(deepcopy(raw_arguments), run.context)
        try:
            result = await self.skill_service.registry.execute_action(
                skill_id=enabled.skill_id,
                action_name=action_name,
                arguments=arguments,
                config=self.automation_repo.get_skill_runtime_config(enabled),
                context={
                    "owner_email": user_email,
                    "actor_email": user_email,
                    "actor_id": user_email,
                    "conversation_id": conversation.conversation_id,
                    "automation_id": automation.automation_id,
                    "automation_run_id": run.run_id,
                    "automation_node_id": node.node_id,
                    "orchestrator_type": "automation",
                    "orchestrator_id": automation.automation_id,
                },
            )
        except Exception as exc:
            return AutomationRunNodeResult(
                run_id=run.run_id,
                automation_id=automation.automation_id,
                node_id=node.node_id,
                status=AutomationNodeRunStatus.FAILED,
                input={
                    "installed_skill_id": enabled.installed_skill_id or enabled.skill_id,
                    "skill_id": enabled.skill_id,
                    "action": action_name,
                    "arguments": arguments,
                },
                error=str(exc),
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
            )

        return AutomationRunNodeResult(
            run_id=run.run_id,
            automation_id=automation.automation_id,
            node_id=node.node_id,
            status=AutomationNodeRunStatus.SUCCEEDED,
            input={
                "installed_skill_id": enabled.installed_skill_id or enabled.skill_id,
                "skill_id": enabled.skill_id,
                "action": action_name,
                "arguments": arguments,
            },
            output={
                "installed_skill_id": enabled.installed_skill_id or enabled.skill_id,
                "skill_id": enabled.skill_id,
                "action": action_name,
                "arguments": arguments,
                "result": result,
            },
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
        )

    def _resolve_automation_skill(
        self,
        automation_id: str,
        *,
        installed_skill_id: str,
        skill_id: str,
    ) -> AutomationSkill | None:
        if installed_skill_id:
            installed = self.automation_repo.find_skill(automation_id, installed_skill_id)
            if installed:
                return installed

        if not skill_id:
            return None

        installed = self.automation_repo.find_skill(automation_id, skill_id)
        if installed:
            return installed

        matches = [
            item
            for item in self.automation_repo.list_skills(automation_id)
            if item.skill_id == skill_id
        ]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise ValueError(
                f"Skill '{skill_id}' has multiple installed instances. Use installed_skill_id."
            )
        return None

    def _select_trigger(
        self, triggers: list[AutomationTrigger], trigger_id: str | None
    ) -> AutomationTrigger | None:
        if trigger_id:
            for trigger in triggers:
                if trigger.trigger_id == trigger_id:
                    return trigger
            raise AutomationValidationError("Trigger not found")
        manual = [
            trigger
            for trigger in triggers
            if trigger.type == AutomationTriggerType.MANUAL and trigger.enabled
        ]
        if manual:
            return manual[0]
        return triggers[0] if triggers else None

    def _default_start_node(self, nodes: list[AutomationNode]) -> AutomationNode:
        for node in nodes:
            if node.type == AutomationNodeType.START:
                return node
        raise AutomationValidationError("No start node found")

    def _first_agent_id(self, nodes: list[AutomationNode]) -> str:
        for node in nodes:
            if (
                node.type == AutomationNodeType.ACTION
                and node.config.get("action_type") == AutomationActionType.INVOKE_AGENT.value
            ):
                return str(node.config.get("agent_id", ""))
            if (
                node.type == AutomationNodeType.ACTION
                and node.config.get("action_type") == AutomationActionType.SKILL_ACTION.value
                and node.config.get("skill_id") == "agent_invocation"
            ):
                arguments = node.config.get("arguments")
                if isinstance(arguments, dict):
                    return str(arguments.get("agent_id", ""))
        return ""

    def _outgoing_edges(self, edges: list[AutomationEdge]) -> dict[str, list[AutomationEdge]]:
        outgoing: dict[str, list[AutomationEdge]] = {}
        for edge in edges:
            outgoing.setdefault(edge.source_node_id, []).append(edge)
        return outgoing

    def _edge_for_label(
        self, edges: list[AutomationEdge], label: str
    ) -> AutomationEdge | None:
        for edge in edges:
            if edge.label == label:
                return edge
        return None

    def _next_label(self, node: AutomationNode, context: dict[str, Any]) -> str:
        if node.type == AutomationNodeType.CONDITION:
            result = context.get("nodes", {}).get(node.node_id, {}).get("output", {}).get("result")
            label = node.config.get("true_label", "true") if result else node.config.get("false_label", "false")
            return str(label)
        return "next"

    def _store_context_node(
        self,
        run: AutomationRun,
        node_id: str,
        status: AutomationNodeRunStatus | str,
        output: dict[str, Any],
        message_ids: dict[str, str],
        error: str | None = None,
    ) -> None:
        run.context.setdefault("nodes", {})[node_id] = {
            "status": status.value if isinstance(status, AutomationNodeRunStatus) else status,
            "output": output,
            "message_ids": message_ids,
            "error": error,
        }

    def _render_template(self, template: str, context: dict[str, Any]) -> str:
        def replace(match: re.Match[str]) -> str:
            value = self._resolve_json_path(match.group(1).strip(), context)
            if isinstance(value, (dict, list)):
                return json.dumps(value)
            return "" if value is None else str(value)

        return re.sub(r"\{\{\s*(\$\.[^}]+)\s*\}\}", replace, template)

    def _render_smart_values(self, value: Any, context: dict[str, Any]) -> Any:
        if isinstance(value, dict):
            return {key: self._render_smart_values(item, context) for key, item in value.items()}
        if isinstance(value, list):
            return [self._render_smart_values(item, context) for item in value]
        if isinstance(value, str):
            return self._render_smart_string(value, context)
        return value

    def _render_smart_string(self, value: str, context: dict[str, Any]) -> Any:
        whole_match = re.fullmatch(r"\s*\{\{\s*(\$\.[^}]+|\$)\s*\}\}\s*", value)
        if whole_match:
            return self._resolve_json_path(whole_match.group(1).strip(), context)

        def replace(match: re.Match[str]) -> str:
            resolved = self._resolve_json_path(match.group(1).strip(), context)
            if isinstance(resolved, (dict, list)):
                return json.dumps(resolved)
            return "" if resolved is None else str(resolved)

        return re.sub(r"\{\{\s*(\$\.[^}]+|\$)\s*\}\}", replace, value)

    def _resolve_json_path(self, path: str, context: dict[str, Any]) -> Any:
        if path == "$":
            return context
        if not path.startswith("$."):
            return None
        current: Any = context
        for part in path[2:].split("."):
            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, list) and part.isdigit():
                current = current[int(part)]
            else:
                return None
        return current

    def _evaluate_condition(self, expression: str, context: dict[str, Any]) -> bool:
        expression = expression.strip()
        if "==" in expression:
            left, right = expression.split("==", 1)
            return bool(self._resolve_json_path(left.strip(), context) == self._literal_value(right.strip()))
        if "!=" in expression:
            left, right = expression.split("!=", 1)
            return bool(self._resolve_json_path(left.strip(), context) != self._literal_value(right.strip()))
        return bool(self._resolve_json_path(expression, context))

    def _literal_value(self, value: str) -> Any:
        value = value.strip()
        if value in {"true", "false"}:
            return value == "true"
        if value in {"null", "None"}:
            return None
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            return value[1:-1]
        try:
            return int(value)
        except ValueError:
            return value
