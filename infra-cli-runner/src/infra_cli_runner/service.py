from __future__ import annotations

import asyncio
import os
import shutil
import signal
import sys
import tempfile
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from src.infra_cli_runner.models import (
    ALLOWED_ENV_KEYS,
    CommandRequest,
    CommandResponse,
    InstallRequirementsCommand,
    PythonCommandResult,
    PythonExecutionRequest,
    PythonExecutionResponse,
    RunScriptCommand,
)


TOOL_EXECUTABLES = {"aws": "aws"}

BASE_ENV = {
    "AWS_CLI_AUTO_PROMPT": "off",
    "AWS_EC2_METADATA_DISABLED": "true",
    "AWS_PAGER": "",
    "HOME": "/tmp",
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "PATH": "/usr/local/bin:/usr/bin:/bin",
}

TMP_ROOT = Path("/tmp").resolve()
DEFAULT_PYTHON_WORK_ROOT = Path("/tmp/infra-cli-runner")
SCRIPT_FILENAME = "script.py"
REQUIREMENTS_FILENAME = "requirements.txt"
DEPENDENCIES_DIRECTORY = "dependencies"
PYTHON_POLICY_DIRECTORY = Path(__file__).with_name("python_policy")


class CommandExecutionError(Exception):
    pass


@dataclass(frozen=True)
class ProcessOutcome:
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    stdout_truncated: bool
    stderr_truncated: bool
    timed_out: bool


class CliRunnerService:
    def __init__(
        self,
        *,
        python_work_root: Path = DEFAULT_PYTHON_WORK_ROOT,
        python_executable: str = sys.executable,
        uv_executable: str | None = None,
    ) -> None:
        self._python_work_root = python_work_root
        self._python_executable = python_executable
        self._uv_executable = uv_executable or shutil.which("uv") or "uv"

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

        outcome = await self._execute_process(
            [executable, *request.argv],
            env=self._build_process_env(request.env),
            timeout_seconds=request.timeout_seconds,
            max_stdout_bytes=request.max_stdout_bytes,
            max_stderr_bytes=request.max_stderr_bytes,
        )
        return CommandResponse(
            ok=outcome.exit_code == 0 and not outcome.timed_out,
            request_id=request.request_id,
            tool=request.tool,
            exit_code=outcome.exit_code,
            stdout=outcome.stdout,
            stderr=outcome.stderr,
            duration_ms=outcome.duration_ms,
            stdout_truncated=outcome.stdout_truncated,
            stderr_truncated=outcome.stderr_truncated,
            timed_out=outcome.timed_out,
        )

    async def run_python(self, request: PythonExecutionRequest) -> PythonExecutionResponse:
        started = time.monotonic()
        work_dir = self._create_python_work_dir()
        try:
            script_path = self._managed_path(work_dir, SCRIPT_FILENAME)
            requirements_path = self._managed_path(work_dir, REQUIREMENTS_FILENAME)
            dependencies_path = self._managed_path(work_dir, DEPENDENCIES_DIRECTORY)
            dependencies_path.mkdir(mode=0o700)
            script_path.write_text(request.script, encoding="utf-8")
            requirements_path.write_text(request.requirements, encoding="utf-8")

            env = self._build_python_env(work_dir, dependencies_path)
            deadline = started + request.timeout_seconds
            results: list[PythonCommandResult] = []
            failed_index: int | None = None

            for index, command in enumerate(request.commands):
                if failed_index is not None:
                    results.append(
                        PythonCommandResult(
                            index=index,
                            operation=command.operation,
                            status="skipped",
                        )
                    )
                    continue

                remaining_seconds = deadline - time.monotonic()
                if remaining_seconds <= 0:
                    outcome = ProcessOutcome(
                        exit_code=-1,
                        stdout="",
                        stderr="Execution timed out before this command started.",
                        duration_ms=0,
                        stdout_truncated=False,
                        stderr_truncated=False,
                        timed_out=True,
                    )
                else:
                    argv = self._python_command_argv(
                        command,
                        script_path=script_path,
                        requirements_path=requirements_path,
                        dependencies_path=dependencies_path,
                    )
                    outcome = await self._execute_process(
                        argv,
                        cwd=work_dir,
                        env=env,
                        timeout_seconds=remaining_seconds,
                        max_stdout_bytes=request.max_stdout_bytes,
                        max_stderr_bytes=request.max_stderr_bytes,
                    )

                status = "timed_out" if outcome.timed_out else (
                    "succeeded" if outcome.exit_code == 0 else "failed"
                )
                results.append(
                    PythonCommandResult(
                        index=index,
                        operation=command.operation,
                        status=status,
                        exit_code=outcome.exit_code,
                        stdout=outcome.stdout,
                        stderr=outcome.stderr,
                        duration_ms=outcome.duration_ms,
                        stdout_truncated=outcome.stdout_truncated,
                        stderr_truncated=outcome.stderr_truncated,
                        timed_out=outcome.timed_out,
                    )
                )
                if status != "succeeded":
                    failed_index = index

            stdout, stdout_truncated = self._combine_output(
                [result.stdout for result in results], request.max_stdout_bytes
            )
            stderr, stderr_truncated = self._combine_output(
                [result.stderr for result in results], request.max_stderr_bytes
            )
            executed = [result for result in results if result.status != "skipped"]
            last_executed = executed[-1]
            return PythonExecutionResponse(
                ok=failed_index is None,
                request_id=request.request_id,
                exit_code=last_executed.exit_code if last_executed.exit_code is not None else -1,
                stdout=stdout,
                stderr=stderr,
                duration_ms=int((time.monotonic() - started) * 1000),
                stdout_truncated=stdout_truncated or any(result.stdout_truncated for result in results),
                stderr_truncated=stderr_truncated or any(result.stderr_truncated for result in results),
                timed_out=any(result.timed_out for result in results),
                failed_command_index=failed_index,
                commands=results,
            )
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    def _create_python_work_dir(self) -> Path:
        root = self._python_work_root.resolve()
        try:
            root.relative_to(TMP_ROOT)
        except ValueError as exc:
            raise CommandExecutionError("Python work root must resolve under /tmp") from exc
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        work_dir = Path(tempfile.mkdtemp(prefix="run-", dir=root)).resolve()
        self._require_under(work_dir, root)
        return work_dir

    def _managed_path(self, work_dir: Path, relative_name: str) -> Path:
        if Path(relative_name).is_absolute():
            raise CommandExecutionError("Managed paths must be relative")
        path = (work_dir / relative_name).resolve()
        self._require_under(path, work_dir.resolve())
        return path

    def _require_under(self, path: Path, parent: Path) -> None:
        try:
            path.relative_to(parent)
            path.relative_to(TMP_ROOT)
        except ValueError as exc:
            raise CommandExecutionError("Managed path escaped the /tmp work directory") from exc

    def _python_command_argv(
        self,
        command: InstallRequirementsCommand | RunScriptCommand,
        *,
        script_path: Path,
        requirements_path: Path,
        dependencies_path: Path,
    ) -> list[str]:
        if isinstance(command, InstallRequirementsCommand):
            return [
                self._uv_executable,
                "pip",
                "install",
                "--target",
                str(dependencies_path),
                "--requirements",
                str(requirements_path),
                "--only-binary",
                ":all:",
                "--no-config",
            ]
        if isinstance(command, RunScriptCommand):
            return [self._python_executable, str(script_path), *command.args]
        raise ValueError(f"Unsupported Python command: {command.operation}")

    def _build_process_env(self, supplied: Mapping[str, str]) -> dict[str, str]:
        env = dict(BASE_ENV)
        for key in ALLOWED_ENV_KEYS:
            value = supplied.get(key)
            if value:
                env[key] = value
        return env

    def _build_python_env(self, work_dir: Path, dependencies_path: Path) -> dict[str, str]:
        env = dict(BASE_ENV)
        env.update(
            {
                "HOME": str(work_dir),
                "TMPDIR": str(work_dir),
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONNOUSERSITE": "1",
                "PYTHONPATH": os.pathsep.join(
                    [str(PYTHON_POLICY_DIRECTORY), str(dependencies_path)]
                ),
                "INFRA_CLI_RUNNER_WRITE_ROOT": str(work_dir),
                "UV_CACHE_DIR": str(self._managed_path(work_dir, "uv-cache")),
                "UV_NO_PROGRESS": "1",
            }
        )
        return env

    async def _execute_process(
        self,
        argv: Sequence[str],
        *,
        env: Mapping[str, str],
        timeout_seconds: float,
        max_stdout_bytes: int,
        max_stderr_bytes: int,
        cwd: Path | None = None,
    ) -> ProcessOutcome:
        started = time.monotonic()
        process = await asyncio.create_subprocess_exec(
            *argv,
            cwd=cwd,
            env=dict(env),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )

        timed_out = False
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError:
            timed_out = True
            stdout_bytes, stderr_bytes = await self._terminate_and_collect(process)

        stdout, stdout_truncated = self._decode_and_truncate(stdout_bytes, max_stdout_bytes)
        stderr, stderr_truncated = self._decode_and_truncate(stderr_bytes, max_stderr_bytes)
        return ProcessOutcome(
            exit_code=process.returncode if process.returncode is not None else -1,
            stdout=stdout,
            stderr=stderr,
            duration_ms=int((time.monotonic() - started) * 1000),
            stdout_truncated=stdout_truncated,
            stderr_truncated=stderr_truncated,
            timed_out=timed_out,
        )

    async def _terminate_and_collect(
        self, process: asyncio.subprocess.Process
    ) -> tuple[bytes, bytes]:
        self._signal_process_group(process, signal.SIGTERM)
        try:
            return await asyncio.wait_for(process.communicate(), timeout=1.0)
        except asyncio.TimeoutError:
            self._signal_process_group(process, signal.SIGKILL)
            return await process.communicate()

    def _signal_process_group(self, process: asyncio.subprocess.Process, sig: signal.Signals) -> None:
        if process.returncode is not None:
            return
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            return
        except Exception:
            if sig == signal.SIGKILL:
                process.kill()
            else:
                process.terminate()

    def _decode_and_truncate(self, data: bytes, max_bytes: int) -> tuple[str, bool]:
        truncated = len(data) > max_bytes
        if truncated:
            data = data[:max_bytes]
        return data.decode("utf-8", errors="replace"), truncated

    def _combine_output(self, values: Sequence[str], max_bytes: int) -> tuple[str, bool]:
        data = "".join(values).encode("utf-8")
        return self._decode_and_truncate(data, max_bytes)


def get_cli_runner_service() -> CliRunnerService:
    return CliRunnerService()
