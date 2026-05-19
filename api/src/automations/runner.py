"""Synchronous automation runner for manual/test execution."""

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
    AutomationTrigger,
    AutomationTriggerType,
)
from src.automations.repository import AutomationRepository
from src.automations.service import AutomationGraph, AutomationValidationError
from src.conversations.models import AutomationConversation
from src.conversations.repository import ConversationRepository


class AutomationRunner:
    """Executes an automation graph in-process for manual/test runs."""

    def __init__(
        self,
        automation_repo: AutomationRepository | None = None,
        agent_repo: AgentRepository | None = None,
        conversation_repo: ConversationRepository | None = None,
    ):
        self.automation_repo = automation_repo or AutomationRepository()
        self.agent_repo = agent_repo or AgentRepository()
        self.conversation_repo = conversation_repo or ConversationRepository()

    async def run_test(
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
            status=AutomationRunStatus.RUNNING,
            context={
                "input": input_data,
                "trigger": {
                    "type": trigger.type.value if trigger else AutomationTriggerType.MANUAL.value,
                    "trigger_id": trigger.trigger_id if trigger else None,
                },
                "nodes": {},
            },
            created_by=user_email,
            started_at=datetime.now(timezone.utc),
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
                    conversation=saved_conversation,
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
                    {
                        "event_type": event.event_type.value,
                        "content": event.content,
                        "message_id": event.message_id,
                    }
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
            return node.config.get("true_label", "true") if result else node.config.get("false_label", "false")
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
            return self._resolve_json_path(left.strip(), context) == self._literal_value(right.strip())
        if "!=" in expression:
            left, right = expression.split("!=", 1)
            return self._resolve_json_path(left.strip(), context) != self._literal_value(right.strip())
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
