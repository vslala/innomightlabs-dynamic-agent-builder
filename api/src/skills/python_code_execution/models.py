from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator


DEFAULT_TIMEOUT_SECONDS = 60
MAX_TIMEOUT_SECONDS = 120
MAX_SCRIPT_BYTES = 128 * 1024
MAX_REQUIREMENTS_BYTES = 32 * 1024
MAX_SCRIPT_ARGS = 128
MAX_ARG_BYTES = 4096
RUNNER_MAX_STDOUT_BYTES = 16 * 1024
RUNNER_MAX_STDERR_BYTES = 8 * 1024


class RunScriptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    script: str
    requirements_txt: str = ""
    args: list[Annotated[str, StringConstraints(max_length=MAX_ARG_BYTES)]] = Field(
        default_factory=list,
        max_length=MAX_SCRIPT_ARGS,
    )
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS

    @field_validator("script")
    @classmethod
    def validate_script(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("script must not be empty")
        if len(value.encode("utf-8")) > MAX_SCRIPT_BYTES:
            raise ValueError("script is too large")
        return value

    @field_validator("requirements_txt")
    @classmethod
    def validate_requirements(cls, value: str) -> str:
        if len(value.encode("utf-8")) > MAX_REQUIREMENTS_BYTES:
            raise ValueError("requirements_txt is too large")
        return value

    @field_validator("args")
    @classmethod
    def validate_args(cls, args: list[str]) -> list[str]:
        for arg in args:
            if "\x00" in arg:
                raise ValueError("script arguments must not contain null bytes")
            if len(arg.encode("utf-8")) > MAX_ARG_BYTES:
                raise ValueError("script argument is too large")
        return args

    @field_validator("timeout_seconds")
    @classmethod
    def validate_timeout(cls, value: int) -> int:
        return max(1, min(int(value), MAX_TIMEOUT_SECONDS))

    def runner_commands(self) -> list[dict[str, object]]:
        commands: list[dict[str, object]] = []
        if self.requirements_txt.strip():
            commands.append({"operation": "install_requirements"})
        commands.append({"operation": "run_script", "args": self.args})
        return commands


class RunnerCommandResult(BaseModel):
    index: int
    operation: str
    status: Literal["succeeded", "failed", "timed_out", "skipped"]
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    duration_ms: int = 0
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    timed_out: bool = False


class RunnerExecutionResponse(BaseModel):
    ok: bool
    request_id: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    stdout_truncated: bool
    stderr_truncated: bool
    timed_out: bool
    failed_command_index: int | None = None
    commands: list[RunnerCommandResult]

    @property
    def execution_status(self) -> Literal["succeeded", "failed", "timed_out"]:
        if self.timed_out:
            return "timed_out"
        return "succeeded" if self.ok else "failed"


class RunScriptResult(BaseModel):
    ok: bool
    execution_status: Literal["succeeded", "failed", "timed_out"]
    request_id: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    stdout_truncated: bool
    stderr_truncated: bool
    timed_out: bool
    failed_command_index: int | None = None
    commands: list[RunnerCommandResult]

    @classmethod
    def from_runner(cls, response: RunnerExecutionResponse) -> "RunScriptResult":
        return cls(
            execution_status=response.execution_status,
            **response.model_dump(),
        )
