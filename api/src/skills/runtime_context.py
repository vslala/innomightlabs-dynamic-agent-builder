"""What a skill action's runtime context says about where it runs."""

from __future__ import annotations

import json
from typing import Any, Optional

from src.accounts.owner import Owner
from src.skills.models import ActorKind


def action_context(
    *,
    skill_id: str,
    installed_skill_id: str,
    agent_id: str,
    account_id: str,
    owner_id: str,
    owner_email: str,
    actor_email: str,
    actor_id: str,
    actor_kind: ActorKind,
    conversation_id: str,
    user_message_id: Optional[str],
    tool_call_id: Optional[str],
) -> dict[str, Any]:
    """The context every skill action runs with, installed or core: who it runs for, where, and for which call."""
    return {
        "agent_id": agent_id,
        "installed_skill_id": installed_skill_id,
        "skill_id": skill_id,
        "account_id": account_id,
        "owner_id": owner_id,
        "owner_email": owner_email,
        "actor_email": actor_email,
        "actor_id": actor_id,
        "actor_kind": actor_kind.value,
        "conversation_id": conversation_id,
        "user_message_id": user_message_id,
        # Kept on an async job's context too, so the action still knows its call when it runs later.
        "tool_call_id": tool_call_id,
    }


def as_tool_result(result: Any) -> str:
    """An action's return value as the text the model reads."""
    return result if isinstance(result, str) else json.dumps(result, ensure_ascii=True)


def account_of(context: dict[str, Any]) -> str:
    """The account the action runs in: the agent's. Its connections (Google, A2A trust, ...) are this account's."""
    account_id = str(context.get("account_id") or "").strip()
    if not account_id:
        raise ValueError("Missing skill runtime account context")
    return account_id


def run_owner(context: dict[str, Any]) -> Owner:
    """The member the action runs as: the agent's (or automation's) owner, in its account."""
    owner_id = str(context.get("owner_id") or "").strip()
    if not owner_id:
        raise ValueError("Missing skill runtime owner context")
    return Owner(account_id=account_of(context), user_id=owner_id, email=str(context.get("owner_email") or ""))
