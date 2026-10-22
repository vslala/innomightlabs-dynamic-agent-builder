from __future__ import annotations

import logging
from typing import Any

from src.skills.browser_studio.client import get_browser_studio_client
from src.skills.workspaces import workspace_id_from_context

logger = logging.getLogger(__name__)


async def inspect_page(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    return await _run("inspect_page", arguments, config, context)


async def record_walkthrough(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    return await _run("record_walkthrough", arguments, config, context)


async def render_scene(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    return await _run("render_scene", arguments, config, context)


async def compose_video(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    return await _run("compose_video", arguments, config, context)


async def probe_media(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    return await _run("probe_media", arguments, config, context)


async def _run(action: str, arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """The runner's answer, as it is: it is already as small as the agent needs it to be."""
    del config
    if not isinstance(arguments, dict):
        raise ValueError(f"Invalid Browser Studio {action} arguments: expected an object")
    outcome = "error"
    try:
        result = await get_browser_studio_client().call(action, arguments, context)
        outcome = str(result.get("status") or "success")
        return result
    finally:
        logger.info(
            "browser_studio_action_audit",
            extra={
                "browser_studio_audit": {
                    "action": action,
                    "url": str(arguments.get("url") or "")[:200],
                    "workspace": _workspace(context),
                    "agent_id": str(context.get("agent_id") or ""),
                    "actor": str(context.get("actor_email") or context.get("owner_email") or ""),
                    "session": str(context.get("conversation_id") or context.get("automation_run_id") or ""),
                    "status": outcome,
                }
            },
        )


def _workspace(context: dict[str, Any]) -> str:
    try:
        return workspace_id_from_context(context)
    except ValueError:
        return ""  # the call itself reports what the context is missing
