"""Schedule target executors."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from src.agents.architectures.factory import get_agent_architecture
from src.agents.repository import AgentRepository
from src.automations.models import AutomationStatus, AutomationTriggerType
from src.automations.runner import AutomationRunner
from src.automations.service import AutomationService
from src.conversations.repository import ConversationRepository
from src.scheduler.models import Schedule


class ScheduleTargetExecutor(Protocol):
    async def execute(self, schedule: Schedule, scheduled_for: datetime) -> dict[str, Any]: ...


class PhaseOneTargetExecutor:
    """Foundation executor used until target-specific execution lands."""

    async def execute(self, schedule: Schedule, scheduled_for: datetime) -> dict[str, Any]:
        return {
            "scheduled_for": scheduled_for.isoformat(),
            "target_type": schedule.target_type.value,
            "message": "Schedule dispatch recorded. Target execution is implemented in later phases.",
        }


class AgentScheduledMessageExecutor:
    """Wakes an agent by sending the scheduled message into an existing conversation."""

    def __init__(
        self,
        agent_repository: AgentRepository | None = None,
        conversation_repository: ConversationRepository | None = None,
    ):
        self.agent_repository = agent_repository or AgentRepository()
        self.conversation_repository = conversation_repository or ConversationRepository()

    async def execute(self, schedule: Schedule, scheduled_for: datetime) -> dict[str, Any]:
        agent_id = self._required_target(schedule, "agent_id")
        conversation_id = self._required_target(schedule, "conversation_id")
        message = self._required_target(schedule, "message")
        actor_email = str(schedule.target.get("actor_email") or schedule.owner_email)
        actor_id = str(schedule.target.get("actor_id") or actor_email)

        agent = self.agent_repository.find_agent_by_id(agent_id, schedule.owner_email)
        if not agent:
            raise ValueError("Scheduled agent was not found")

        conversation = self.conversation_repository.find_by_id(conversation_id, schedule.owner_email)
        if not conversation:
            raise ValueError("Scheduled conversation was not found")
        if conversation.agent_id != agent.agent_id:
            raise ValueError("Scheduled conversation does not belong to the scheduled agent")

        architecture = get_agent_architecture(agent.agent_architecture)
        result = await architecture.handle_message_buffered(
            agent=agent,
            conversation=conversation,
            user_message=message,
            owner_email=schedule.owner_email,
            actor_email=actor_email,
            actor_id=actor_id,
        )
        if not result.success:
            raise RuntimeError(result.error or "Scheduled agent invocation failed")

        return {
            "scheduled_for": scheduled_for.isoformat(),
            "agent_id": agent.agent_id,
            "conversation_id": conversation.conversation_id,
            "response_text": result.response_text,
            "message_ids": {
                "user_message_id": result.user_message_id,
                "assistant_message_id": result.assistant_message_id,
            },
        }

    def _required_target(self, schedule: Schedule, key: str) -> str:
        value = str(schedule.target.get(key) or "").strip()
        if not value:
            raise ValueError(f"Agent message schedule is missing {key}")
        return value


class AutomationScheduledRunExecutor:
    """Starts an automation run with the input stored on the schedule target."""

    def __init__(
        self,
        runner: AutomationRunner | None = None,
        service: AutomationService | None = None,
    ):
        self.runner = runner or AutomationRunner()
        self.service = service or AutomationService(repo=self.runner.automation_repo)

    async def execute(self, schedule: Schedule, scheduled_for: datetime) -> dict[str, Any]:
        automation_id = self._required_target(schedule, "automation_id")
        input_data = schedule.target.get("input") or {}
        if not isinstance(input_data, dict):
            raise ValueError("Automation schedule input must be an object")

        graph = self.service.get_graph(automation_id, schedule.owner_email)
        if graph.automation.status != AutomationStatus.ACTIVE:
            return {
                "scheduled_for": scheduled_for.isoformat(),
                "automation_id": automation_id,
                "status": "skipped",
                "reason": f"automation_{graph.automation.status.value}",
            }
        trigger_id = str(schedule.target.get("trigger_id") or "").strip() or None
        if trigger_id:
            trigger = next((item for item in graph.triggers if item.trigger_id == trigger_id), None)
            if not trigger:
                return {
                    "scheduled_for": scheduled_for.isoformat(),
                    "automation_id": automation_id,
                    "trigger_id": trigger_id,
                    "status": "skipped",
                    "reason": "trigger_missing",
                }
            if trigger.type != AutomationTriggerType.SCHEDULE or not trigger.enabled:
                return {
                    "scheduled_for": scheduled_for.isoformat(),
                    "automation_id": automation_id,
                    "trigger_id": trigger_id,
                    "status": "skipped",
                    "reason": "trigger_disabled",
                }
        self.service.validate_graph(
            graph.nodes,
            graph.edges,
            graph.triggers,
            schedule.owner_email,
        )
        run = self.runner.create_scheduled_run(
            graph=graph,
            input_data=input_data,
            user_email=schedule.owner_email,
            schedule_id=schedule.schedule_id,
            trigger_id=trigger_id,
        )
        completed = await self.runner.execute_run_graph(graph, run, schedule.owner_email)

        return {
            "scheduled_for": scheduled_for.isoformat(),
            "automation_id": automation_id,
            "automation_run_id": completed.run_id,
            "status": completed.status.value,
            "error": completed.error,
        }

    def _required_target(self, schedule: Schedule, key: str) -> str:
        value = str(schedule.target.get(key) or "").strip()
        if not value:
            raise ValueError(f"Automation schedule is missing {key}")
        return value
