from __future__ import annotations

import hashlib
from typing import Any


def workspace_id_from_context(context: dict[str, Any]) -> str:
    """Return an opaque, stable workspace id shared by sidecar-backed skills."""
    owner = str(context.get("owner_email") or context.get("actor_email") or "").strip()
    agent = str(context.get("agent_id") or "").strip()
    conversation = str(
        context.get("conversation_id") or context.get("automation_run_id") or ""
    ).strip()
    if not owner:
        raise ValueError("Missing runtime context value: owner_email")
    if not conversation:
        raise ValueError("Missing runtime context value: conversation_id")
    scope = f"v1\0{owner}\0{agent}\0{conversation}".encode("utf-8")
    return hashlib.sha256(scope).hexdigest()[:48]
