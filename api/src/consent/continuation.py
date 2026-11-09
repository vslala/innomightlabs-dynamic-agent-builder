"""After the person decides: run exactly what they approved, then carry the paused turn on.

The continuation is the first part of a new turn (a `TurnPrelude`). It runs the stored call with the person's edits,
records the outcome on the request, and returns what the agent's part of the turn starts from: the paused turn's
exchange with the real result in place, or, when the turn can't be picked up exactly, the decision as a message.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Callable

from src.agents.agentic_loop import TurnResume
from src.agents.loop_context import with_tool_result
from src.agents.tool_display import derive_display_tool
from src.agents.turns.run import TurnInput
from src.accounts.owner import Owner
from src.automations.consent import AutomationConsentService
from src.automations.models import AutomationStatus, UpdateAutomationRequest
from src.automations.service import AutomationService
from src.consent.models import AutomationStepsSubject, ConsentRequest, ConsentStatus, SkillActionSubject
from src.consent.payloads import decision_result
from src.connectors.mcp.models import MCPCaller
from src.connectors.mcp.service import MCPConnectorService
from src.consent.repository import ConsentRepository
from src.llm.events import SSEEvent, SSEEventType
from src.messages.repositories import MessageRepository, get_message_repository
from src.skills.models import ActorKind
from src.skills.service import SkillRuntimeService

if TYPE_CHECKING:
    from src.agents.models import Agent

log = logging.getLogger(__name__)

#: As much of a result as the decision line keeps, the same cap as the tool-call audit.
MAX_DECISION_RESULT_CHARS = 12_000


class ConsentContinuation:
    def __init__(
        self,
        consent_id: str,
        agent: "Agent",
        *,
        repository: ConsentRepository | None = None,
        message_repo: MessageRepository | None = None,
        skill_runtime: SkillRuntimeService | None = None,
    ):
        self.consent_id = consent_id
        self.agent = agent
        self.repository = repository or ConsentRepository()
        self.message_repo = message_repo or get_message_repository("dynamodb")
        self.skill_runtime = skill_runtime or SkillRuntimeService()

    async def run(self, emit: Callable[[SSEEvent], None]) -> TurnInput:
        request = self.repository.get(self.consent_id)
        if request is None:
            raise ValueError("This approval no longer exists.")
        if request.status is ConsentStatus.APPROVED:
            request = await self._run_approved(request, emit)
        emit(
            SSEEvent(
                event_type=SSEEventType.CONSENT_UPDATED,
                content=request.title,
                consent=request.to_response(self.repository.image_url).model_dump(mode="json"),
            )
        )

        line = decision_line(request)
        exchange = self._resumable_exchange(request)
        if exchange is None:
            return TurnInput(user_message=line)
        assert request.checkpoint is not None and request.checkpoint.assistant_message_id is not None
        return TurnInput(
            user_message=line,
            resume=TurnResume(
                exchange=with_tool_result(exchange, request.tool_use_id, decision_result(request)),
                paused_reply_id=request.checkpoint.assistant_message_id,
            ),
        )

    async def _run_approved(self, request: ConsentRequest, emit: Callable[[SSEEvent], None]) -> ConsentRequest:
        tool_name, tool_args = _as_tool_call(request)
        display_name, display_args = derive_display_tool(tool_name, tool_args)
        emit(
            SSEEvent(
                event_type=SSEEventType.TOOL_CALL_START,
                content=f"Calling {tool_name}...",
                tool_call_id=request.tool_use_id,
                tool_name=tool_name,
                tool_args=tool_args,
                display_tool_name=display_name,
                display_tool_args=display_args,
            )
        )
        request = self.repository.mark_running(request)
        started_at = datetime.now(timezone.utc)
        try:
            result = await self._execute(request)
            request = self.repository.finish(request, succeeded=True, result=result)
        except Exception as exc:
            log.warning("Approved action %s failed", request.consent_id, exc_info=True)
            request = self.repository.finish(request, succeeded=False, result=f"Error: {exc}")
        emit(
            SSEEvent(
                event_type=SSEEventType.TOOL_CALL_RESULT,
                content=request.result or "",
                success=request.status is ConsentStatus.SUCCEEDED,
                tool_call_id=request.tool_use_id,
                tool_name=tool_name,
                display_tool_name=display_name,
                display_tool_args=display_args,
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
            )
        )
        return request

    async def _execute(self, request: ConsentRequest) -> str:
        subject = request.subject
        if isinstance(subject, SkillActionSubject):
            return await self.skill_runtime.run_consented(request)
        if isinstance(subject, AutomationStepsSubject):
            return json.dumps(_approve_steps(request, subject))
        result = await MCPConnectorService().call_runtime_tool(
            account_id=request.account_id,
            agent_id=request.agent_id,
            caller=MCPCaller(actor_kind=ActorKind.OWNER, actor_id=request.actor_id, actor_email=None,
                             conversation_id=request.conversation_id),
            mcp_id=subject.mcp_id,
            tool_name=subject.tool_name,
            arguments=request.arguments_to_run,
            consent_grant=f"consent:{request.consent_id}",
        )
        return json.dumps(result, ensure_ascii=False)

    def _resumable_exchange(self, request: ConsentRequest) -> list | None:
        """The paused turn's exchange, when the turn can be picked up exactly where it stopped.

        Not when the conversation has moved on (a message after the paused reply would come before the exchange), and
        not when the agent's model changed (thought signatures belong to the model that made them).
        """
        checkpoint = request.checkpoint
        if checkpoint is None or checkpoint.assistant_message_id is None:
            return None
        if (self.agent.agent_model or "") != checkpoint.model_name:
            return None
        newest, _, _ = self.message_repo.find_by_conversation_newest_first(request.conversation_id, limit=1)
        if not newest or newest[0].message_id != checkpoint.assistant_message_id:
            return None
        return self.repository.exchange_of(checkpoint)


def decision_line(request: ConsentRequest) -> str:
    """The person's decision as the user message: shown compactly in the chat, and read by later turns."""
    decision = "approved" if request.approved else "rejected"
    attributes = [f'consent_id="{request.consent_id}"', f'action="{_attribute(request.title)}"', f'decision="{decision}"']
    if request.edits:
        attributes.append(f'edited="{",".join(sorted(request.edits))}"')
    if request.always:
        attributes.append('always="true"')
    body = ""
    if request.approved:
        outcome = "Result" if request.status is ConsentStatus.SUCCEEDED else "It failed"
        body = f"{outcome}:\n{(request.result or '')[:MAX_DECISION_RESULT_CHARS]}\n"
    elif request.reason:
        body = f"Reason: {request.reason}\n"
    return f"<consent_decision {' '.join(attributes)}>\n{body}</consent_decision>"


def _approve_steps(request: ConsentRequest, subject: AutomationStepsSubject) -> dict:
    owner = Owner(account_id=request.account_id, user_id=request.owner_id, email=request.owner_email)
    automations = AutomationService()
    grants = {ref.node_id: request.arguments_to_run.get(f"grants:{ref.node_id}", []) for ref in subject.steps}
    return AutomationConsentService(repo=automations.repo).approve_from_card(
        subject,
        grants,
        owner,
        activate=lambda automation_id: automations.update_automation(
            automation_id, UpdateAutomationRequest(status=AutomationStatus.ACTIVE), owner
        ),
    )


def _as_tool_call(request: ConsentRequest) -> tuple[str, dict]:
    """The approved call as the tool call the agent made, so the chat's activity list shows it like any other."""
    subject = request.subject
    if isinstance(subject, SkillActionSubject):
        return "execute_skill_action", {
            "skill_id": subject.installed_skill_id,
            "action": subject.action,
            "arguments": request.arguments_to_run,
        }
    if isinstance(subject, AutomationStepsSubject):
        return "apply", {"approve_steps": [ref.model_dump() for ref in subject.steps], **request.arguments_to_run}
    return "call_mcp_tool", {"mcp_id": subject.mcp_id, "tool_name": subject.tool_name, "arguments": request.arguments_to_run}


def _attribute(value: str) -> str:
    return json.dumps(value)[1:-1]
