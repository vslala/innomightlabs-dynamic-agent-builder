"""Suggestion-type strategies for smart suggestions."""

from __future__ import annotations

import json
from typing import Protocol

from pydantic import BaseModel, Field, ValidationError

from src.scheduler.cron import ScheduleExpression, ScheduleExpressionError, validate_schedule_expression
from src.skills.aws_cli.models import parse_policy
from src.smart_suggestions.models import (
    SmartSuggestionRequest,
    SmartSuggestionResponse,
    SmartSuggestionType,
)


class SmartSuggestionError(ValueError):
    """Raised when a smart suggestion cannot be generated or validated."""


class SmartSuggestionStrategy(Protocol):
    suggestion_type: str

    def build_messages(self, request: SmartSuggestionRequest) -> list[dict[str, str]]:
        ...

    def parse_response(self, raw_response: str, request: SmartSuggestionRequest) -> SmartSuggestionResponse:
        ...


class CronExpressionPayload(BaseModel):
    cron_expression: str = Field(min_length=1)
    explanation: str = Field(min_length=1)


class AgentInstructionsPayload(BaseModel):
    instructions: str = Field(min_length=1)
    summary: str = Field(min_length=1)


class AwsCliCommandPolicyPayload(BaseModel):
    command_policy_yaml: str = Field(min_length=1)
    summary: str = Field(min_length=1)


class CronExpressionSuggestionStrategy:
    suggestion_type = SmartSuggestionType.CRON_EXPRESSION

    def build_messages(self, request: SmartSuggestionRequest) -> list[dict[str, str]]:
        timezone = _context_string(request, "timezone", default="UTC")
        current_value = request.current_value or ""
        system_prompt = (
            "You convert natural language schedule requests into standard 5-field cron expressions.\n"
            "Return only valid JSON matching this exact shape:\n"
            '{"cron_expression":"string","explanation":"string"}\n'
            "Rules:\n"
            "- Use standard 5-field cron: minute hour day month weekday.\n"
            "- Do not include seconds.\n"
            "- Interpret the requested schedule in the provided timezone.\n"
            "- Do not convert the cron expression to UTC.\n"
            "- If the request is ambiguous, choose the most likely schedule and explain the assumption.\n"
            "- Do not return markdown, code fences, or extra keys."
        )
        user_payload = {
            "request": request.query,
            "current_value": current_value,
            "timezone": timezone,
        }
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=True)},
        ]

    def parse_response(self, raw_response: str, request: SmartSuggestionRequest) -> SmartSuggestionResponse:
        try:
            payload = CronExpressionPayload.model_validate_json(_extract_json_object(raw_response))
        except ValidationError as exc:
            raise SmartSuggestionError("Model returned an invalid cron suggestion") from exc

        timezone = _context_string(request, "timezone", default="UTC")
        cron_expression = payload.cron_expression.strip()
        try:
            validate_schedule_expression(ScheduleExpression(cron_expression, timezone))
        except ScheduleExpressionError as exc:
            raise SmartSuggestionError(str(exc)) from exc

        return SmartSuggestionResponse(
            suggestion_type=self.suggestion_type,
            value=cron_expression,
            display_text=payload.explanation.strip(),
            metadata={"timezone": timezone},
        )


class AgentInstructionsSuggestionStrategy:
    suggestion_type = SmartSuggestionType.AGENT_INSTRUCTIONS

    def build_messages(self, request: SmartSuggestionRequest) -> list[dict[str, str]]:
        current_value = request.current_value or ""
        user_payload = {
            "request": request.query,
            "current_instructions": current_value,
            "agent_name": _context_string(request, "agent_name", default=""),
            "agent_architecture": _context_string(request, "agent_architecture", default=""),
            "agent_description": _context_string(request, "agent_description", default=""),
        }
        system_prompt = (
            "You write clear, durable instructions for an AI agent configuration form.\n"
            "Return only valid JSON matching this exact shape:\n"
            '{"instructions":"string","summary":"string"}\n'
            "Rules:\n"
            "- Write in direct instruction style, not as a biography.\n"
            "- Include purpose, scope, behavior, tone, and any constraints implied by the request.\n"
            "- Preserve useful existing instructions when current_instructions are provided.\n"
            "- Use concise markdown bullets only when they improve scanability.\n"
            "- Do not include secrets, placeholders for secrets, markdown code fences, or extra keys."
        )
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=True)},
        ]

    def parse_response(self, raw_response: str, request: SmartSuggestionRequest) -> SmartSuggestionResponse:
        try:
            payload = AgentInstructionsPayload.model_validate_json(_extract_json_object(raw_response))
        except ValidationError as exc:
            raise SmartSuggestionError("Model returned invalid agent instructions") from exc

        instructions = payload.instructions.strip()
        if not instructions:
            raise SmartSuggestionError("Model returned empty agent instructions")

        return SmartSuggestionResponse(
            suggestion_type=self.suggestion_type,
            value=instructions,
            display_text=payload.summary.strip(),
            metadata={},
        )


class AwsCliCommandPolicySuggestionStrategy:
    suggestion_type = SmartSuggestionType.AWS_CLI_COMMAND_POLICY

    def build_messages(self, request: SmartSuggestionRequest) -> list[dict[str, str]]:
        current_value = request.current_value or ""
        user_payload = {
            "request": request.query,
            "current_command_policy_yaml": current_value,
        }
        system_prompt = (
            "You modify an AWS CLI command policy YAML for an installable skill.\n"
            "Return only valid JSON matching this exact shape:\n"
            '{"command_policy_yaml":"string","summary":"string"}\n'
            "Policy rules:\n"
            "- Return YAML with one top-level aws object.\n"
            "- Preserve these scalar keys when present: default_timeout_seconds, max_timeout_seconds, "
            "max_stdout_bytes, max_stderr_bytes, sts_duration_seconds.\n"
            "- Under aws.services, define service names with read command prefix lists only.\n"
            "- v1 supports only read entries. Do not add write, mutate, delete, put, update, create, or remove policies.\n"
            "- Command prefixes are arrays of argv tokens after the aws executable, for example "
            '["s3api","list-buckets"].\n'
            "- Do not include shell syntax, pipes, redirects, command separators, substitutions, or the aws executable token.\n"
            "- Keep the policy least-privilege and include only commands implied by the request.\n"
            "- Do not return markdown, code fences, or extra JSON keys."
        )
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=True)},
        ]

    def parse_response(self, raw_response: str, request: SmartSuggestionRequest) -> SmartSuggestionResponse:
        try:
            payload = AwsCliCommandPolicyPayload.model_validate_json(_extract_json_object(raw_response))
        except ValidationError as exc:
            raise SmartSuggestionError("Model returned an invalid AWS CLI policy suggestion") from exc

        command_policy_yaml = payload.command_policy_yaml.strip()
        if not command_policy_yaml:
            raise SmartSuggestionError("Model returned an empty AWS CLI policy")
        try:
            policy = parse_policy(command_policy_yaml)
        except ValueError as exc:
            raise SmartSuggestionError(str(exc)) from exc

        services = sorted(policy.services)
        return SmartSuggestionResponse(
            suggestion_type=self.suggestion_type,
            value=command_policy_yaml,
            display_text=payload.summary.strip(),
            metadata={"services": services},
        )


class SmartSuggestionStrategyRegistry:
    def __init__(self, strategies: list[SmartSuggestionStrategy] | None = None):
        self._strategies = {
            strategy.suggestion_type: strategy
            for strategy in (
                strategies
                or [
                    CronExpressionSuggestionStrategy(),
                    AgentInstructionsSuggestionStrategy(),
                    AwsCliCommandPolicySuggestionStrategy(),
                ]
            )
        }

    def get(self, suggestion_type: str) -> SmartSuggestionStrategy:
        strategy = self._strategies.get(suggestion_type)
        if not strategy:
            raise SmartSuggestionError(f"Unsupported smart suggestion type: {suggestion_type}")
        return strategy


def _context_string(request: SmartSuggestionRequest, key: str, *, default: str) -> str:
    value = request.context.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return default


def _extract_json_object(raw_response: str) -> str:
    stripped = raw_response.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        return stripped[start : end + 1]
    raise SmartSuggestionError("Model did not return a JSON object")
