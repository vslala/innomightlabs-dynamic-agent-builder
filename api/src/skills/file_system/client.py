from __future__ import annotations

from typing import Any
from uuid import uuid4

import httpx
from pydantic import ValidationError

from src.config import settings
from src.skills.file_system.models import FileSystemActionName, FileSystemResult
from src.skills.workspaces import workspace_id_from_context


class FileSystemRunnerClient:
    async def execute(
        self,
        *,
        action: FileSystemActionName,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> FileSystemResult:
        if not settings.cli_runner_base_url:
            raise RuntimeError("CLI runner is not configured. Set CLI_RUNNER_BASE_URL.")
        if not settings.cli_runner_shared_token:
            raise RuntimeError("CLI runner is not configured. Set CLI_RUNNER_SHARED_TOKEN.")

        request_id = str(
            context.get("user_message_id")
            or context.get("automation_run_id")
            or context.get("conversation_id")
            or uuid4()
        )
        payload = {
            "request_id": request_id,
            "workspace_id": workspace_id_from_context(context),
            "action": action,
            "arguments": arguments,
        }
        headers = {"Authorization": f"Bearer {settings.cli_runner_shared_token}"}
        try:
            async with httpx.AsyncClient(timeout=settings.cli_runner_timeout_seconds) as http_client:
                response = await http_client.post(
                    f"{settings.cli_runner_base_url.rstrip('/')}/v1/filesystem/actions",
                    json=payload,
                    headers=headers,
                )
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Filesystem runner request failed: {exc}") from exc

        if response.status_code >= 400:
            raise RuntimeError(
                f"Filesystem runner rejected request: HTTP {response.status_code} {_bounded(response.text)}"
            )
        try:
            return FileSystemResult.model_validate(response.json())
        except (ValueError, ValidationError) as exc:
            raise RuntimeError("Filesystem runner returned an invalid response") from exc

    async def put_file(self, *, path: str, data: bytes, context: dict[str, Any]) -> dict[str, Any]:
        """Writes `data` to `path` in this conversation's workspace, replacing a file already there."""
        if not settings.cli_runner_base_url or not settings.cli_runner_shared_token:
            raise RuntimeError("CLI runner is not configured. Set CLI_RUNNER_BASE_URL and CLI_RUNNER_SHARED_TOKEN.")
        # The workspace comes from the run's own identity, so an agent can only write into its own conversation's.
        query = {"workspace_id": workspace_id_from_context(context), "path": path}
        headers = {"Authorization": f"Bearer {settings.cli_runner_shared_token}"}
        try:
            async with httpx.AsyncClient(timeout=settings.cli_runner_timeout_seconds) as http_client:
                response = await http_client.put(f"{settings.cli_runner_base_url.rstrip('/')}/v1/filesystem/files",
                                                 params=query, content=data, headers=headers)
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Copying {path} into the workspace failed: the runner is unreachable.") from exc
        if response.status_code == 413:
            raise ValueError(f"{path} doesn't fit: the workspace is full. Delete files you no longer need.")
        if response.status_code == 404:
            raise RuntimeError("The runner can't receive files yet: it is older than this skill.")
        if response.status_code >= 400:
            raise RuntimeError(f"The runner refused {path}: HTTP {response.status_code} {_bounded(response.text, 300)}")
        result: dict[str, Any] = response.json()
        return result


def get_file_system_runner_client() -> FileSystemRunnerClient:
    return FileSystemRunnerClient()


def _bounded(value: str, max_chars: int = 1000) -> str:
    if len(value) <= max_chars:
        return value
    return value[:max_chars] + "...[truncated]"
