"""What a skill action's runtime context says about where it runs."""

from __future__ import annotations

from typing import Any


def account_of(context: dict[str, Any]) -> str:
    """The account the action runs in: the agent's. Its connections (Google, A2A trust, ...) are this account's."""
    account_id = str(context.get("account_id") or "").strip()
    if not account_id:
        raise ValueError("Missing skill runtime account context")
    return account_id
