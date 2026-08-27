from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import uuid4

import boto3
import httpx
from pydantic import ValidationError

from src.config import settings
from src.skills.aws_cli.models import (
    AwsCliConfig,
    AwsCliReadRequest,
    ReadOutputPageRequest,
    parse_policy,
)
from src.skills.aws_cli.output_store import read_page, store_output


async def run_read(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    request = _validate(AwsCliReadRequest, arguments, "run_read")
    skill_config = _validate(AwsCliConfig, config, "install config")
    policy = parse_policy(skill_config.command_policy_yaml)
    policy.validate_read_argv(request.argv)

    temp_credentials = await _create_sts_session(skill_config, policy.sts_duration_seconds)
    runner_response = await _call_runner(
        request=request,
        skill_config=skill_config,
        temp_credentials=temp_credentials,
        timeout_seconds=policy.timeout_for(request.timeout_seconds),
        max_stdout_bytes=policy.max_stdout_bytes,
        max_stderr_bytes=policy.max_stderr_bytes,
        context=context,
    )
    return _shape_runner_response(
        request=request,
        runner_response=runner_response,
        context=context,
    )


async def read_output_page(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    del config
    request = _validate(ReadOutputPageRequest, arguments, "read_output_page")
    return read_page(
        output_id=request.output_id,
        owner_email=_context_value(context, "owner_email"),
        installed_skill_id=_context_value(context, "installed_skill_id"),
        page=request.page,
        page_size_chars=request.page_size_chars,
    )


def _validate(model: type[Any], payload: dict[str, Any], label: str) -> Any:
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"Invalid AWS CLI {label}: {exc}") from exc


async def _create_sts_session(config: AwsCliConfig, duration_seconds: int) -> dict[str, str]:
    def create() -> dict[str, str]:
        client = boto3.client(
            "sts",
            aws_access_key_id=config.aws_access_key_id,
            aws_secret_access_key=config.aws_secret_access_key,
            region_name=config.aws_region,
        )
        response = client.get_session_token(DurationSeconds=duration_seconds)
        credentials = response.get("Credentials") or {}
        return {
            "AWS_ACCESS_KEY_ID": str(credentials["AccessKeyId"]),
            "AWS_SECRET_ACCESS_KEY": str(credentials["SecretAccessKey"]),
            "AWS_SESSION_TOKEN": str(credentials["SessionToken"]),
        }

    try:
        return await asyncio.to_thread(create)
    except Exception as exc:
        raise RuntimeError(f"Failed to create temporary AWS STS credentials: {exc}") from exc


async def _call_runner(
    *,
    request: AwsCliReadRequest,
    skill_config: AwsCliConfig,
    temp_credentials: dict[str, str],
    timeout_seconds: int,
    max_stdout_bytes: int,
    max_stderr_bytes: int,
    context: dict[str, Any],
) -> dict[str, Any]:
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
        "tool": "aws",
        "argv": request.argv,
        "env": {
            **temp_credentials,
            "AWS_DEFAULT_REGION": skill_config.aws_region,
            "AWS_REGION": skill_config.aws_region,
        },
        "timeout_seconds": timeout_seconds,
        "max_stdout_bytes": max_stdout_bytes,
        "max_stderr_bytes": max_stderr_bytes,
    }
    headers = {"Authorization": f"Bearer {settings.cli_runner_shared_token}"}
    try:
        async with httpx.AsyncClient(timeout=settings.cli_runner_timeout_seconds) as client:
            response = await client.post(
                f"{settings.cli_runner_base_url.rstrip('/')}/v1/commands",
                json=payload,
                headers=headers,
            )
    except httpx.HTTPError as exc:
        raise RuntimeError(f"CLI runner request failed: {exc}") from exc

    if response.status_code >= 400:
        raise RuntimeError(f"CLI runner rejected request: HTTP {response.status_code} {_bounded(response.text)}")

    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(
            "AWS CLI command failed: "
            f"exit_code={data.get('exit_code')} timed_out={data.get('timed_out')} "
            f"stderr={_bounded(str(data.get('stderr') or ''))}"
        )
    return data


def _shape_runner_response(
    *,
    request: AwsCliReadRequest,
    runner_response: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    stdout = str(runner_response.get("stdout") or "")
    stderr = str(runner_response.get("stderr") or "")
    page_size = request.max_output_chars or request.page_size_chars
    parsed_json = _try_parse_json(stdout)

    result: dict[str, Any] = {
        "ok": True,
        "tool": "aws",
        "argv": request.argv,
        "exit_code": runner_response.get("exit_code"),
        "duration_ms": runner_response.get("duration_ms"),
        "stdout_truncated_by_runner": bool(runner_response.get("stdout_truncated")),
        "stderr_truncated_by_runner": bool(runner_response.get("stderr_truncated")),
        "stderr_preview": _bounded(stderr),
    }
    if parsed_json is not None and len(stdout) <= page_size:
        result["json"] = parsed_json

    if len(stdout) > page_size:
        stored = store_output(
            owner_email=_context_value(context, "owner_email"),
            installed_skill_id=_context_value(context, "installed_skill_id"),
            content=stdout,
        )
        page = read_page(
            output_id=stored.output_id,
            owner_email=stored.owner_email,
            installed_skill_id=stored.installed_skill_id,
            page=1,
            page_size_chars=page_size,
        )
        result.update(
            {
                "output_id": stored.output_id,
                "content": page["content"],
                "page": page["page"],
                "total_pages": page["total_pages"],
                "has_more": page["has_next"],
                "next_page": page["next_page"],
                "message": "More output is available. Call read_output_page with output_id and next_page to continue.",
            }
        )
    else:
        result.update(
            {
                "content": stdout,
                "has_more": False,
            }
        )
    return result


def _try_parse_json(value: str) -> Any | None:
    if not value.strip():
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def _bounded(value: str, max_chars: int = 1000) -> str:
    if len(value) <= max_chars:
        return value
    return value[:max_chars] + "...[truncated]"


def _context_value(context: dict[str, Any], key: str) -> str:
    value = str(context.get(key) or "").strip()
    if not value:
        raise ValueError(f"Missing runtime context value: {key}")
    return value
