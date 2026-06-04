"""Cron parsing helpers for scheduler."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import croniter  # type: ignore[import-untyped]


class ScheduleExpressionError(ValueError):
    """Raised when a schedule expression is invalid."""


@dataclass(frozen=True)
class ScheduleExpression:
    cron_expression: str
    timezone: str = "UTC"


def validate_schedule_expression(value: ScheduleExpression) -> None:
    expression = value.cron_expression.strip()
    if len(expression.split()) != 5:
        raise ScheduleExpressionError("Cron expression must use 5 fields: minute hour day month weekday")
    _zone(value.timezone)
    if not croniter.is_valid(expression):
        raise ScheduleExpressionError("Invalid cron expression")


def next_run_at(value: ScheduleExpression, now: datetime | None = None) -> datetime:
    validate_schedule_expression(value)
    base = now or datetime.now(timezone.utc)
    zone = _zone(value.timezone)
    localized = base.astimezone(zone)
    next_local = croniter(value.cron_expression.strip(), localized).get_next(datetime)
    return cast(datetime, next_local).astimezone(timezone.utc)


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except ZoneInfoNotFoundError as exc:
        raise ScheduleExpressionError(f"Invalid timezone: {name}") from exc
