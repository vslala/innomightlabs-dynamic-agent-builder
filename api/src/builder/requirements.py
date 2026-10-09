"""What the system asks the person for, rather than Ada: an account to connect, a skill's settings.

Each requirement reads what the draft still needs from the person, asks for the first of it in the chat, and takes
in the answer when it comes back as their next message. `REQUIREMENTS` is in the order the person is asked: sign in
first, then settings. A new kind of ask (the secure secrets panel, consent for another agent's domain) is one more
entry here, not a new branch in Ada's tools.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from src.blueprints.draft import Draft
from src.builder.connections import connect_request, missing_connections
from src.builder.models import BuilderSession, PendingInput
from src.builder.skill_inputs import absorb_submission, input_form, missing_inputs

if TYPE_CHECKING:
    from src.agents.runtime_state import AgentTurnState


class Requirement(Protocol):
    def missing(self, draft: Draft, session: BuilderSession, user_email: str) -> list[Any]:
        """What the draft still needs from the person, in the order to ask."""
        ...

    def settle(self, session: BuilderSession, missing: list[Any]) -> None:
        """Forget an ask that's no longer needed (the draft changed since)."""
        ...

    def ask(self, missing: list[Any], session: BuilderSession, state: "AgentTurnState") -> dict[str, Any]:
        """The tool result that asks for the first of `missing`: the chat shows it under Ada's message."""
        ...

    def absorb(self, session: BuilderSession, message: str) -> bool:
        """Take in the person's answer, if `message` is one. Returns whether it was."""
        ...


class AccountConnection:
    """An MCP connection the account hasn't signed in to. The person connects it from a card; the next plan finds
    it, so there's no answer to take in."""

    def missing(self, draft: Draft, session: BuilderSession, user_email: str) -> list[Any]:
        return list(missing_connections(draft, user_email))

    def settle(self, session: BuilderSession, missing: list[Any]) -> None:
        pass

    def ask(self, missing: list[Any], session: BuilderSession, state: "AgentTurnState") -> dict[str, Any]:
        need = missing[0]
        return {
            **connect_request(need, state.conversation_id),
            "ok": False,
            "needs_connection": {"provider": need.title, "connections_left": len(missing)},
            "next": (
                f"The system is asking the person to connect {need.title} with a card under your message. "
                "Say one short line about what it gives the agent, and stop. When they say it's connected, "
                "call plan_blueprint with no arguments."
            ),
        }

    def absorb(self, session: BuilderSession, message: str) -> bool:
        return False


class SkillSettings:
    """Settings only the person knows, asked one skill at a time in a form built from the skill's manifest."""

    def missing(self, draft: Draft, session: BuilderSession, user_email: str) -> list[Any]:
        return list(missing_inputs(draft, session.draft_params))

    def settle(self, session: BuilderSession, missing: list[Any]) -> None:
        pending = session.pending_input
        if pending is not None and all(item.key != pending.key for item in missing):
            # The form it waited on isn't needed any more (the draft changed, or the setting is Ada's to write).
            session.pending_input = None

    def ask(self, missing: list[Any], session: BuilderSession, state: "AgentTurnState") -> dict[str, Any]:
        item = missing[0]
        pending = session.pending_input
        error = pending.error if pending is not None and pending.key == item.key else None
        session.pending_input = PendingInput(key=item.key, label=item.label)
        context = {"agent_id": state.agent_id, "conversation_id": state.conversation_id}
        form = input_form(item, Draft(session.draft_yaml), session.draft_params, state.owner_email, context, error)
        return {
            **form,
            "ok": False,
            "needs_input": {"skill": item.skill_name, "agent": item.agent_name, "skills_left": len(missing)},
            "next": (
                f"The system is asking the person for {item.skill_name}'s settings in a form under your message. "
                "Say one short line, such as what the skill will do for them. Don't ask for these settings or "
                "fill them in yourself. When their message is that form, call plan_blueprint with no arguments."
            ),
        }

    def absorb(self, session: BuilderSession, message: str) -> bool:
        return absorb_submission(session, message)


REQUIREMENTS: tuple[Requirement, ...] = (AccountConnection(), SkillSettings())


def absorb_answers(session: BuilderSession, message: str) -> bool:
    """Takes in the person's answer to whatever the system asked them, before Ada sees the turn."""
    return any(requirement.absorb(session, message) for requirement in REQUIREMENTS)
