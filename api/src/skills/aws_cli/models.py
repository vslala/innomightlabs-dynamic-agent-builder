from __future__ import annotations

import json
import re
from typing import Any, Annotated

import yaml  # type: ignore[import-untyped,unused-ignore]
from pydantic import BaseModel, Field, StringConstraints, field_validator, model_validator


DEFAULT_PAGE_SIZE_CHARS = 12_000
MAX_PAGE_SIZE_CHARS = 40_000
MIN_PAGE_SIZE_CHARS = 1_000
DEFAULT_STS_DURATION_SECONDS = 900
MIN_STS_DURATION_SECONDS = 900
MAX_STS_DURATION_SECONDS = 3600

FORBIDDEN_ARG_FRAGMENTS = ("$(", "`", "\x00")
FORBIDDEN_ARG_VALUES = {"|", "||", "&", "&&", ";", ">", ">>", "<", "<<", "2>", "2>>"}
AWS_REGION_RE = re.compile(r"^[a-z]{2}-[a-z-]+-\d$|^us-gov-[a-z]+-\d$|^cn-[a-z-]+-\d$")


class AwsCliConfig(BaseModel):
    aws_access_key_id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    aws_secret_access_key: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    aws_region: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)] = "us-east-1"
    command_policy_yaml: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]

    @field_validator("aws_region")
    @classmethod
    def validate_region(cls, value: str) -> str:
        if not AWS_REGION_RE.match(value):
            raise ValueError("aws_region must look like an AWS region, for example us-east-1")
        return value


class AwsCliReadRequest(BaseModel):
    argv: list[str] | str = Field(min_length=1)
    timeout_seconds: int | None = None
    max_output_chars: int | None = None
    page_size_chars: int = DEFAULT_PAGE_SIZE_CHARS

    @model_validator(mode="after")
    def normalize(self) -> "AwsCliReadRequest":
        if isinstance(self.argv, str):
            try:
                parsed = json.loads(self.argv)
            except json.JSONDecodeError as exc:
                raise ValueError("argv string must be valid JSON array") from exc
            self.argv = parsed
        if not isinstance(self.argv, list) or not all(isinstance(item, str) for item in self.argv):
            raise ValueError("argv must be an array of strings")
        if not self.argv:
            raise ValueError("argv must not be empty")
        if self.argv[0] == "aws":
            raise ValueError('argv must not include the "aws" executable')
        for arg in self.argv:
            validate_argv_token(arg)
        self.page_size_chars = clamp_int(
            self.page_size_chars,
            minimum=MIN_PAGE_SIZE_CHARS,
            maximum=MAX_PAGE_SIZE_CHARS,
        )
        if self.timeout_seconds is not None:
            self.timeout_seconds = max(1, int(self.timeout_seconds))
        if self.max_output_chars is not None:
            self.max_output_chars = max(MIN_PAGE_SIZE_CHARS, int(self.max_output_chars))
        return self


class ReadOutputPageRequest(BaseModel):
    output_id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    page: int = 1
    page_size_chars: int = DEFAULT_PAGE_SIZE_CHARS

    @model_validator(mode="after")
    def normalize(self) -> "ReadOutputPageRequest":
        self.page = max(1, int(self.page))
        self.page_size_chars = clamp_int(
            self.page_size_chars,
            minimum=MIN_PAGE_SIZE_CHARS,
            maximum=MAX_PAGE_SIZE_CHARS,
        )
        return self


class AwsCliPolicy(BaseModel):
    default_timeout_seconds: int = 30
    max_timeout_seconds: int = 120
    max_stdout_bytes: int = 65_536
    max_stderr_bytes: int = 16_384
    sts_duration_seconds: int = DEFAULT_STS_DURATION_SECONDS
    services: dict[str, dict[str, list[list[str]]]]

    @model_validator(mode="after")
    def normalize(self) -> "AwsCliPolicy":
        self.default_timeout_seconds = clamp_int(self.default_timeout_seconds, minimum=1, maximum=120)
        self.max_timeout_seconds = clamp_int(self.max_timeout_seconds, minimum=1, maximum=300)
        self.max_stdout_bytes = clamp_int(self.max_stdout_bytes, minimum=1024, maximum=512 * 1024)
        self.max_stderr_bytes = clamp_int(self.max_stderr_bytes, minimum=1024, maximum=128 * 1024)
        self.sts_duration_seconds = clamp_int(
            self.sts_duration_seconds,
            minimum=MIN_STS_DURATION_SECONDS,
            maximum=MAX_STS_DURATION_SECONDS,
        )
        if not self.services:
            raise ValueError("policy must declare at least one service")
        for service_name, categories in self.services.items():
            if not service_name.strip():
                raise ValueError("policy service names must not be empty")
            for category_name, prefixes in categories.items():
                if category_name != "read":
                    raise ValueError("v1 supports only read command policy entries")
                if not prefixes:
                    raise ValueError(f"policy service {service_name} read list must not be empty")
                for prefix in prefixes:
                    if not prefix or not all(isinstance(item, str) and item for item in prefix):
                        raise ValueError("policy command prefixes must be non-empty string arrays")
                    for token in prefix:
                        validate_argv_token(token)
        return self

    def validate_read_argv(self, argv: list[str]) -> None:
        read_prefixes: list[list[str]] = []
        for categories in self.services.values():
            read_prefixes.extend(categories.get("read", []))
        if any(_matches_prefix(argv, prefix) for prefix in read_prefixes):
            return
        allowed = ", ".join(" ".join(prefix) for prefix in read_prefixes)
        raise ValueError(f"AWS CLI command is not allowed by installed policy. Allowed read prefixes: {allowed}")

    def timeout_for(self, requested: int | None) -> int:
        timeout = requested if requested is not None else self.default_timeout_seconds
        return clamp_int(timeout, minimum=1, maximum=self.max_timeout_seconds)


def parse_policy(policy_yaml: str) -> AwsCliPolicy:
    try:
        data = yaml.safe_load(policy_yaml)
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid command_policy_yaml: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("aws"), dict):
        raise ValueError("command_policy_yaml must contain an aws object")
    return AwsCliPolicy.model_validate(data["aws"])


def validate_argv_token(token: str) -> None:
    if not token:
        raise ValueError("argv entries must be non-empty strings")
    if token in FORBIDDEN_ARG_VALUES:
        raise ValueError(f"shell control token is not allowed in argv: {token}")
    if any(fragment in token for fragment in FORBIDDEN_ARG_FRAGMENTS):
        raise ValueError("shell substitution syntax is not allowed in argv")


def clamp_int(value: int, *, minimum: int, maximum: int) -> int:
    return max(minimum, min(int(value), maximum))


def _matches_prefix(argv: list[str], prefix: list[str]) -> bool:
    return len(argv) >= len(prefix) and argv[: len(prefix)] == prefix
