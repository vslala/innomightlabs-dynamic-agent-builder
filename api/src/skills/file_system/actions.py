from __future__ import annotations

import logging
from typing import Any

from src.skills.file_system.client import get_file_system_runner_client
from src.skills.file_system.models import FileSystemActionName
from src.skills.workspaces import workspace_id_from_context


logger = logging.getLogger(__name__)


async def list_dir(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    return await _execute("list_dir", arguments, config, context)


async def stat(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    return await _execute("stat", arguments, config, context)


async def search(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    return await _execute("search", arguments, config, context)


async def read_chunk(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    return await _execute("read_chunk", arguments, config, context)


async def write_file(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    return await _execute("write_file", arguments, config, context)


async def patch_file(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    return await _execute("patch_file", arguments, config, context)


async def preview_diff(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    return await _execute("preview_diff", arguments, config, context)


async def mkdir(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    return await _execute("mkdir", arguments, config, context)


async def copy(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    return await _execute("copy", arguments, config, context)


async def move(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    return await _execute("move", arguments, config, context)


async def delete(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    return await _execute("delete", arguments, config, context)


async def batch(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    return await _execute("batch", arguments, config, context)


async def _execute(
    action: FileSystemActionName,
    arguments: dict[str, Any],
    config: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    del config
    result_status = "error"
    error_code: str | None = None
    try:
        result = await get_file_system_runner_client().execute(
            action=action,
            arguments=arguments,
            context=context,
        )
        result_status = result.status
        error_code = result.error_code
        return result.model_dump(mode="json")
    finally:
        logger.info(
            "filesystem_action_audit",
            extra={
                "filesystem_audit": {
                    "action": action,
                    "paths": _audit_paths(arguments),
                    "workspace": workspace_id_from_context(context),
                    "agent_id": str(context.get("agent_id") or ""),
                    "actor": str(context.get("actor_email") or context.get("owner_email") or ""),
                    "session": str(context.get("conversation_id") or context.get("automation_run_id") or ""),
                    "policy_decision": "not_enforced",
                    "status": result_status,
                    "error_code": error_code,
                }
            },
        )
def _audit_paths(arguments: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for key in ("path", "source", "destination"):
        value = arguments.get(key)
        if isinstance(value, str):
            paths.append(value)
    if isinstance(arguments.get("operations"), list):
        for operation in arguments["operations"]:
            if isinstance(operation, dict) and isinstance(operation.get("arguments"), dict):
                paths.extend(_audit_paths(operation["arguments"]))
    return paths[:100]
