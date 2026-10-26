"""The consent gate: before a tool call runs, does it need the person's yes, and do we have it?

Every chat tool call passes `ToolExecutionRouter.execute`, which asks the gate first. A subject kind recognises the
calls it covers (a skill action, an MCP tool); the first rule that decides says what happens: run it, ask the person
with a card, or refuse. See docs/LLD-action-consent.md.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Protocol

from src.consent.models import ConsentRequest, ConsentSubject, McpToolSubject, SkillActionSubject, mcp_key, skill_key
from src.consent.payloads import consent_request_payload, refusal
from src.consent.preview import ConsentPreview, WarningBlock, default_preview
from src.consent.repository import ConsentRepository
from src.skills.models import ActorKind
from src.skills.runtime_context import action_context

if TYPE_CHECKING:
    from src.agents.runtime_state import AgentTurnState
    from src.connectors.mcp.service import MCPConnectorService
    from src.skills.service import SkillRuntimeService

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class GatedCall:
    """A tool call that acts for the person, resolved to what it acts on and what they would be shown."""

    subject: ConsentSubject
    key: str
    title: str
    arguments: dict[str, Any]
    editable: list[str]
    preview: Callable[[], Awaitable[ConsentPreview]]


class SubjectKind(Protocol):
    def identify(self, tool_name: str, tool_input: dict[str, Any], state: "AgentTurnState") -> GatedCall | None:
        """The call as something consent covers, or None when it needs none."""
        ...


class SkillActions:
    """`execute_skill_action` naming an action whose manifest declares `consent`."""

    def __init__(self, skill_runtime: "SkillRuntimeService"):
        self.skill_runtime = skill_runtime

    def identify(self, tool_name: str, tool_input: dict[str, Any], state: "AgentTurnState") -> GatedCall | None:
        arguments = tool_input.get("arguments")
        if tool_name != "execute_skill_action" or not isinstance(arguments, dict):
            return None
        found = self.skill_runtime.action_needing_consent(
            state.agent_id, str(tool_input.get("skill_id") or "").strip(), str(tool_input.get("action") or "").strip(),
            state.actor_kind,
        )
        if found is None:
            return None
        installed, action = found
        consent = action.consent
        assert consent is not None
        installed_skill_id = installed.installed_skill_id or installed.skill_id

        async def preview() -> ConsentPreview:
            shown = default_preview(consent.title, arguments, action.input_schema)
            if consent.preview:
                context = action_context(
                    skill_id=installed.skill_id,
                    installed_skill_id=installed_skill_id,
                    agent_id=state.agent_id,
                    account_id=state.account_id,
                    owner_id=state.owner_id,
                    owner_email=state.owner_email,
                    actor_email=state.actor_email,
                    actor_id=state.actor_id,
                    actor_kind=state.actor_kind,
                    conversation_id=state.conversation_id,
                    user_message_id=state.user_message_id,
                    tool_call_id=None,
                )
                try:
                    built = await self.skill_runtime.preview_action(installed, action, arguments, context)
                    shown = built if isinstance(built, ConsentPreview) else ConsentPreview.model_validate({"title": consent.title, **built})
                except Exception:
                    # The default still shows every argument, so the person can decide all the same
                    log.warning("Consent preview failed for %s.%s", installed.skill_id, action.name, exc_info=True)
            if consent.warning and not any(isinstance(block, WarningBlock) for block in shown.blocks):
                shown.blocks.append(WarningBlock(text=consent.warning))
            return shown

        return GatedCall(
            subject=SkillActionSubject(skill_id=installed.skill_id, installed_skill_id=installed_skill_id, action=action.name),
            key=skill_key(installed_skill_id, action.name),
            title=consent.title,
            arguments=arguments,
            editable=list(consent.editable),
            preview=preview,
        )


class McpTools:
    """`call_mcp_tool` naming a tool its connection asks about first (the person's choice, or a destructive default)."""

    def __init__(self, mcp: "MCPConnectorService"):
        self.mcp = mcp

    def identify(self, tool_name: str, tool_input: dict[str, Any], state: "AgentTurnState") -> GatedCall | None:
        arguments = tool_input.get("arguments")
        mcp_id, name = str(tool_input.get("mcp_id") or ""), str(tool_input.get("tool_name") or "")
        if tool_name != "call_mcp_tool" or not isinstance(arguments, dict) or not mcp_id or not name:
            return None
        policy, catalog = self.mcp.tool_policy(state.account_id, mcp_id)
        # Someone the owner shared a tool with may use it as shared, unless the owner chose to be asked about it
        asks = policy.asks(name) if state.actor_kind == ActorKind.OWNER else policy.keeps_from_outsiders(name)
        if not asks:
            return None
        listed = next((tool for tool in catalog.tools if tool.name == name), None) if catalog else None
        title = (listed.title if listed else None) or name

        async def preview() -> ConsentPreview:
            return default_preview(title, arguments, {})

        return GatedCall(
            subject=McpToolSubject(mcp_id=mcp_id, tool_name=name),
            key=mcp_key(mcp_id, name),
            title=title,
            arguments=arguments,
            editable=[],
            preview=preview,
        )


@dataclass(frozen=True)
class Settled:
    """What a rule decided: run it under `grant`, ask the person, or refuse for `reason`."""

    run: bool = False
    ask: bool = False
    grant: str | None = None
    reason: str | None = None


#: A rule decides, or returns None to leave it to the next.
Rule = Callable[[GatedCall, "AgentTurnState", ConsentRepository], Settled | None]


def owner_only(call: GatedCall, state: "AgentTurnState", repository: ConsentRepository) -> Settled | None:
    # Tools run with the owner's accounts: nobody else may make them act, with or without a card
    if state.actor_kind != ActorKind.OWNER:
        return Settled(reason="This action isn't available here.")
    return None


def step_granted(call: GatedCall, state: "AgentTurnState", repository: ConsentRepository) -> Settled | None:
    scope = state.consent_scope
    return Settled(run=True, grant=scope.grant_ref) if call.key in scope.granted else None


def always_allowed(call: GatedCall, state: "AgentTurnState", repository: ConsentRepository) -> Settled | None:
    if repository.standing(state.agent_id, call.key) is None:
        return None
    return Settled(run=True, grant=f"standing:{state.agent_id}/{call.key}")


def ask_the_person(call: GatedCall, state: "AgentTurnState", repository: ConsentRepository) -> Settled | None:
    return Settled(ask=True) if state.consent_scope.can_ask else None


def nobody_to_ask(call: GatedCall, state: "AgentTurnState", repository: ConsentRepository) -> Settled | None:
    return Settled(
        reason=(
            f"'{call.title}' needs the person's approval, and nobody is here to give it. Tell them, so they can run "
            "it themselves or allow it for this agent."
        )
    )


RULES: list[Rule] = [owner_only, step_granted, always_allowed, ask_the_person, nobody_to_ask]


@dataclass(frozen=True)
class GateDecision:
    """Run the tool under `grant` (None when it needs no consent), or return `result` in its place."""

    result: str | None = None
    grant: str | None = None


class ConsentGate:
    def __init__(self, subjects: list[SubjectKind], repository: ConsentRepository | None = None):
        self.subjects = subjects
        self.repository = repository or ConsentRepository()

    async def check(
        self, *, tool_name: str, tool_input: dict[str, Any], tool_use_id: str, state: "AgentTurnState"
    ) -> GateDecision:
        """Whether the tool runs, and under which consent; or the card or refusal to return in its place."""
        call = next((found for kind in self.subjects if (found := kind.identify(tool_name, tool_input, state))), None)
        if call is None:
            return GateDecision()

        settled = next(decided for rule in RULES if (decided := rule(call, state, self.repository)))
        if settled.run:
            return GateDecision(grant=settled.grant)
        if not settled.ask:
            return GateDecision(result=refusal(settled.reason or ""))

        preview = await call.preview()
        request = self.repository.open(
            ConsentRequest(
                conversation_id=state.conversation_id,
                agent_id=state.agent_id,
                account_id=state.account_id,
                owner_id=state.owner_id,
                owner_email=state.owner_email,
                actor_email=state.actor_email,
                actor_id=state.actor_id,
                user_message_id=state.user_message_id,
                tool_use_id=tool_use_id,
                subject=call.subject,
                key=call.key,
                title=call.title,
                arguments=call.arguments,
                preview=preview,
                editable=preview.editable if preview.editable is not None else call.editable,
            )
        )
        return GateDecision(result=consent_request_payload(request, self.repository))
