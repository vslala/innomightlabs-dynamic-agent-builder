from __future__ import annotations

import os
from typing import Annotated, Literal

from packaging.requirements import InvalidRequirement, Requirement
from pydantic import BaseModel, Field, StringConstraints, field_validator


DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_MAX_STDOUT_BYTES = 64 * 1024
DEFAULT_MAX_STDERR_BYTES = 16 * 1024
MAX_ARGV_ITEMS = 128
MAX_ARG_BYTES = 4096
MAX_ENV_VALUE_BYTES = 8192
MAX_PYTHON_COMMANDS = 16
MAX_SCRIPT_BYTES = 256 * 1024
MAX_REQUIREMENTS_BYTES = 64 * 1024

ALLOWED_ENV_KEYS = {
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "AWS_DEFAULT_REGION",
    "AWS_REGION",
}

FORBIDDEN_ARG_FRAGMENTS = ("$(", "`", "\x00")
FORBIDDEN_ARG_VALUES = {"|", "||", "&", "&&", ";", ">", ">>", "<", "<<", "2>", "2>>"}


class CommandRequest(BaseModel):
    request_id: str = Field(min_length=1, max_length=128)
    tool: Literal["aws"]
    argv: list[str] = Field(min_length=1, max_length=MAX_ARGV_ITEMS)
    env: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    max_stdout_bytes: int = DEFAULT_MAX_STDOUT_BYTES
    max_stderr_bytes: int = DEFAULT_MAX_STDERR_BYTES

    @field_validator("argv")
    @classmethod
    def validate_argv(cls, argv: list[str]) -> list[str]:
        for arg in argv:
            if not arg:
                raise ValueError("argv entries must be non-empty strings")
            if len(arg.encode("utf-8")) > MAX_ARG_BYTES:
                raise ValueError("argv entry is too large")
            if arg in FORBIDDEN_ARG_VALUES:
                raise ValueError(f"shell control token is not allowed in argv: {arg}")
            if any(fragment in arg for fragment in FORBIDDEN_ARG_FRAGMENTS):
                raise ValueError("shell substitution syntax is not allowed in argv")
        return argv

    @field_validator("env")
    @classmethod
    def validate_env(cls, env: dict[str, str]) -> dict[str, str]:
        for key, value in env.items():
            if key not in ALLOWED_ENV_KEYS:
                raise ValueError(f"environment variable is not allowed: {key}")
            if len(value.encode("utf-8")) > MAX_ENV_VALUE_BYTES:
                raise ValueError(f"environment variable value is too large: {key}")
        return env

    @field_validator("timeout_seconds")
    @classmethod
    def validate_timeout(cls, value: int) -> int:
        max_timeout = int(os.getenv("CLI_RUNNER_MAX_TIMEOUT_SECONDS", "120"))
        return max(1, min(value, max_timeout))

    @field_validator("max_stdout_bytes", "max_stderr_bytes")
    @classmethod
    def validate_byte_limit(cls, value: int) -> int:
        return max(1024, min(value, 512 * 1024))


class CommandResponse(BaseModel):
    ok: bool
    request_id: str
    tool: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    stdout_truncated: bool
    stderr_truncated: bool
    timed_out: bool = False


class InstallRequirementsCommand(BaseModel):
    operation: Literal["install_requirements"]


class RunScriptCommand(BaseModel):
    operation: Literal["run_script"]
    args: list[Annotated[str, StringConstraints(max_length=MAX_ARG_BYTES)]] = Field(
        default_factory=list,
        max_length=MAX_ARGV_ITEMS,
    )

    @field_validator("args")
    @classmethod
    def validate_args(cls, args: list[str]) -> list[str]:
        for arg in args:
            if "\x00" in arg:
                raise ValueError("script arguments must not contain null bytes")
        return args


PythonCommand = Annotated[
    InstallRequirementsCommand | RunScriptCommand,
    Field(discriminator="operation"),
]


class PythonExecutionRequest(BaseModel):
    request_id: str = Field(min_length=1, max_length=128)
    script: str
    requirements: str = ""
    commands: list[PythonCommand] = Field(min_length=1, max_length=MAX_PYTHON_COMMANDS)
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    max_stdout_bytes: int = DEFAULT_MAX_STDOUT_BYTES
    max_stderr_bytes: int = DEFAULT_MAX_STDERR_BYTES

    @field_validator("script")
    @classmethod
    def validate_script(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("script must not be empty")
        if len(value.encode("utf-8")) > MAX_SCRIPT_BYTES:
            raise ValueError("script is too large")
        return value

    @field_validator("requirements")
    @classmethod
    def validate_requirements(cls, value: str) -> str:
        if len(value.encode("utf-8")) > MAX_REQUIREMENTS_BYTES:
            raise ValueError("requirements are too large")
        for line_number, raw_line in enumerate(value.splitlines(), start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("-"):
                raise ValueError("requirements options and included files are not allowed")
            try:
                requirement = Requirement(line)
            except InvalidRequirement as exc:
                raise ValueError(f"invalid requirement on line {line_number}: {exc}") from exc
            if requirement.url is not None:
                raise ValueError("direct URL and local-path requirements are not allowed")
        return value

    @field_validator("timeout_seconds")
    @classmethod
    def validate_timeout(cls, value: int) -> int:
        max_timeout = int(os.getenv("CLI_RUNNER_MAX_TIMEOUT_SECONDS", "120"))
        return max(1, min(value, max_timeout))

    @field_validator("max_stdout_bytes", "max_stderr_bytes")
    @classmethod
    def validate_byte_limit(cls, value: int) -> int:
        return max(1024, min(value, 512 * 1024))


class PythonCommandResult(BaseModel):
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


class PythonExecutionResponse(BaseModel):
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
    commands: list[PythonCommandResult]
