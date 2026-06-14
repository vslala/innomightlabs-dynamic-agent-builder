"""Suggestion-type strategies for smart suggestions."""

from __future__ import annotations

import json
from typing import Protocol

from pydantic import BaseModel, Field, ValidationError

from src.scheduler.cron import ScheduleExpression, ScheduleExpressionError, validate_schedule_expression
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


class SmartSuggestionStrategyRegistry:
    def __init__(self, strategies: list[SmartSuggestionStrategy] | None = None):
        self._strategies = {
            strategy.suggestion_type: strategy
            for strategy in (strategies or [CronExpressionSuggestionStrategy()])
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

