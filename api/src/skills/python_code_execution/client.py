from __future__ import annotations

from typing import Any
from uuid import uuid4

import httpx
from pydantic import ValidationError

from src.config import settings
from src.skills.python_code_execution.models import (
    RUNNER_MAX_STDERR_BYTES,
    RUNNER_MAX_STDOUT_BYTES,
    RunScriptRequest,
    RunnerExecutionResponse,
)


HTTP_TIMEOUT_GRACE_SECONDS = 5


class PythonRunnerClient:
    async def run_script(
        self,
        request: RunScriptRequest,
        context: dict[str, Any],
    ) -> RunnerExecutionResponse:
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
            "script": request.script,
            "requirements": request.requirements_txt,
            "commands": request.runner_commands(),
            "timeout_seconds": request.timeout_seconds,
            "max_stdout_bytes": RUNNER_MAX_STDOUT_BYTES,
            "max_stderr_bytes": RUNNER_MAX_STDERR_BYTES,
        }
        headers = {"Authorization": f"Bearer {settings.cli_runner_shared_token}"}
        total_timeout = max(
            settings.cli_runner_timeout_seconds,
            request.timeout_seconds + HTTP_TIMEOUT_GRACE_SECONDS,
        )
        timeout = httpx.Timeout(total_timeout, connect=min(5, total_timeout))

        try:
            async with httpx.AsyncClient(timeout=timeout) as http_client:
                response = await http_client.post(
                    f"{settings.cli_runner_base_url.rstrip('/')}/v1/python/executions",
                    json=payload,
                    headers=headers,
                )
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Python runner request failed: {exc}") from exc

        if response.status_code >= 400:
            raise RuntimeError(
                f"Python runner rejected request: HTTP {response.status_code} {_bounded(response.text)}"
            )
        try:
            return RunnerExecutionResponse.model_validate(response.json())
        except (ValueError, ValidationError) as exc:
            raise RuntimeError("Python runner returned an invalid response") from exc


def get_python_runner_client() -> PythonRunnerClient:
    return PythonRunnerClient()


def _bounded(value: str, max_chars: int = 1000) -> str:
    if len(value) <= max_chars:
        return value
    return value[:max_chars] + "...[truncated]"
