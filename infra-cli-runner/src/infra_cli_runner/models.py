from __future__ import annotations

import os
from typing import Literal

from pydantic import BaseModel, Field, field_validator


DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_MAX_STDOUT_BYTES = 64 * 1024
DEFAULT_MAX_STDERR_BYTES = 16 * 1024
MAX_ARGV_ITEMS = 128
MAX_ARG_BYTES = 4096
MAX_ENV_VALUE_BYTES = 8192

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
