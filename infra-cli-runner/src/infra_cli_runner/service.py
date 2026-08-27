from __future__ import annotations

import asyncio
import os
import signal
import time
from collections.abc import Mapping

from src.infra_cli_runner.models import ALLOWED_ENV_KEYS, CommandRequest, CommandResponse


TOOL_EXECUTABLES = {
    "aws": "aws",
}

BASE_ENV = {
    "AWS_CLI_AUTO_PROMPT": "off",
    "AWS_EC2_METADATA_DISABLED": "true",
    "AWS_PAGER": "",
    "HOME": "/tmp",
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "PATH": "/usr/local/bin:/usr/bin:/bin",
}


class CommandExecutionError(Exception):
    pass


class CliRunnerService:
    def validate_token(self, token: str) -> None:
        expected = os.getenv("CLI_RUNNER_SHARED_TOKEN", "").strip()
        if not expected:
            raise CommandExecutionError("CLI runner shared token is not configured")
        if token != expected:
            raise PermissionError("Invalid bearer token")

    async def run(self, request: CommandRequest) -> CommandResponse:
        executable = TOOL_EXECUTABLES.get(request.tool)
        if not executable:
            raise ValueError(f"Unsupported tool: {request.tool}")

        started = time.monotonic()
        env = self._build_process_env(request.env)
        process = await asyncio.create_subprocess_exec(
            executable,
            *request.argv,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )

        timed_out = False
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=request.timeout_seconds,
            )
        except asyncio.TimeoutError:
            timed_out = True
            self._terminate_process_group(process)
            stdout_bytes, stderr_bytes = await process.communicate()

        duration_ms = int((time.monotonic() - started) * 1000)
        stdout, stdout_truncated = self._decode_and_truncate(stdout_bytes, request.max_stdout_bytes)
        stderr, stderr_truncated = self._decode_and_truncate(stderr_bytes, request.max_stderr_bytes)

        return CommandResponse(
            ok=process.returncode == 0 and not timed_out,
            request_id=request.request_id,
            tool=request.tool,
            exit_code=process.returncode if process.returncode is not None else -1,
            stdout=stdout,
            stderr=stderr,
            duration_ms=duration_ms,
            stdout_truncated=stdout_truncated,
            stderr_truncated=stderr_truncated,
            timed_out=timed_out,
        )

    def _build_process_env(self, supplied: Mapping[str, str]) -> dict[str, str]:
        env = dict(BASE_ENV)
        for key in ALLOWED_ENV_KEYS:
            value = supplied.get(key)
            if value:
                env[key] = value
        return env

    def _terminate_process_group(self, process: asyncio.subprocess.Process) -> None:
        if process.returncode is not None:
            return
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        except Exception:
            process.terminate()

    def _decode_and_truncate(self, data: bytes, max_bytes: int) -> tuple[str, bool]:
        truncated = len(data) > max_bytes
        if truncated:
            data = data[:max_bytes]
        return data.decode("utf-8", errors="replace"), truncated


def get_cli_runner_service() -> CliRunnerService:
    return CliRunnerService()
