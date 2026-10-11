"""What a skill action's runtime context says about where it runs."""

from __future__ import annotations

from typing import Any

from src.accounts.owner import Owner


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
