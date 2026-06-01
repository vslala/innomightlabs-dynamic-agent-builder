"""Scheduler application service."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from src.scheduler.backends import get_scheduler_backend
from src.scheduler.backends.base import SchedulerBackend
from src.scheduler.cron import ScheduleExpression, next_run_at, validate_schedule_expression
from src.scheduler.models import (
    CreateScheduleRequest,
    Schedule,
    ScheduleStatus,
    UpdateScheduleRequest,
)
from src.scheduler.repository import SchedulerRepository


class SchedulerValidationError(ValueError):
    """Raised when schedule input is invalid."""


class SchedulerService:
    """Coordinates schedule validation, persistence, and backend state."""

    def __init__(
        self,
        repository: SchedulerRepository | None = None,
        backend: SchedulerBackend | None = None,
    ):
        self.repository = repository or SchedulerRepository()
        self.backend = backend or get_scheduler_backend()

    def create_schedule(self, body: CreateScheduleRequest, owner_email: str, created_by: str) -> Schedule:
        self._validate_target(body.target_type.value, body.target)
        expression = ScheduleExpression(body.cron_expression, body.timezone)
        validate_schedule_expression(expression)
        status = ScheduleStatus.ACTIVE if body.enabled else ScheduleStatus.PAUSED
        schedule = Schedule(
            owner_email=owner_email,
            name=body.name,
            status=status,
            cron_expression=body.cron_expression.strip(),
            timezone=body.timezone or "UTC",
            target_type=body.target_type,
            target=body.target,
            source_type=body.source_type,
            source_ref=body.source_ref,
            next_run_at=next_run_at(expression) if status == ScheduleStatus.ACTIVE else None,
            created_by=created_by,
        )
        saved = self.repository.save_schedule(schedule)
        if saved.status == ScheduleStatus.ACTIVE:
            self.backend.upsert(saved)
        return saved

    def update_schedule(
        self,
        schedule_id: str,
        body: UpdateScheduleRequest,
        owner_email: str,
    ) -> Schedule:
        schedule = self.get_schedule(schedule_id, owner_email)
        if body.name is not None:
            schedule.name = body.name
        if body.cron_expression is not None:
            schedule.cron_expression = body.cron_expression.strip()
        if body.timezone is not None:
            schedule.timezone = body.timezone or "UTC"
        if body.target is not None:
            self._validate_target(schedule.target_type.value, body.target)
            schedule.target = body.target
        if body.source_ref is not None:
            schedule.source_ref = body.source_ref
        if body.enabled is not None:
            schedule.status = ScheduleStatus.ACTIVE if body.enabled else ScheduleStatus.PAUSED

        expression = ScheduleExpression(schedule.cron_expression, schedule.timezone)
        validate_schedule_expression(expression)
        schedule.next_run_at = (
            next_run_at(expression)
            if schedule.status == ScheduleStatus.ACTIVE
            else None
        )
        saved = self.repository.save_schedule(schedule)
        if saved.status == ScheduleStatus.ACTIVE:
            self.backend.upsert(saved)
        else:
            self.backend.pause(saved)
        return saved

    def pause_schedule(self, schedule_id: str, owner_email: str) -> Schedule:
        schedule = self.get_schedule(schedule_id, owner_email)
        schedule.status = ScheduleStatus.PAUSED
        schedule.next_run_at = None
        saved = self.repository.save_schedule(schedule)
        self.backend.pause(saved)
        return saved

    def resume_schedule(self, schedule_id: str, owner_email: str) -> Schedule:
        schedule = self.get_schedule(schedule_id, owner_email)
        expression = ScheduleExpression(schedule.cron_expression, schedule.timezone)
        schedule.status = ScheduleStatus.ACTIVE
        schedule.next_run_at = next_run_at(expression)
        saved = self.repository.save_schedule(schedule)
        self.backend.resume(saved)
        return saved

    def delete_schedule(self, schedule_id: str, owner_email: str) -> None:
        schedule = self.get_schedule(schedule_id, owner_email)
        schedule.status = ScheduleStatus.DELETED
        self.backend.delete(schedule)
        self.repository.delete_schedule(schedule)

    def get_schedule(self, schedule_id: str, owner_email: str) -> Schedule:
        schedule = self.repository.find_schedule(owner_email, schedule_id)
        if not schedule:
            raise SchedulerValidationError("Schedule not found")
        return schedule

    def list_schedules(self, owner_email: str) -> list[Schedule]:
        return self.repository.list_schedules(owner_email)

    def mark_dispatched(self, schedule: Schedule, scheduled_for: datetime) -> Schedule:
        schedule.last_run_at = datetime.now(timezone.utc)
        if schedule.status == ScheduleStatus.ACTIVE:
            schedule.next_run_at = next_run_at(
                ScheduleExpression(schedule.cron_expression, schedule.timezone),
                now=scheduled_for,
            )
        return self.repository.save_schedule(schedule)

    def _validate_target(self, target_type: str, target: dict) -> None:
        if target_type == "agent_message":
            if not str(target.get("agent_id") or "").strip():
                raise SchedulerValidationError("Agent message schedules require agent_id")
            if not str(target.get("message") or "").strip():
                raise SchedulerValidationError("Agent message schedules require message")
            return
        if target_type == "automation_run":
            if not str(target.get("automation_id") or "").strip():
                raise SchedulerValidationError("Automation schedules require automation_id")
            raw_input = target.get("input", {})
            if raw_input is not None and not isinstance(raw_input, dict):
                raise SchedulerValidationError("Automation schedule input must be an object")
            return
        raise SchedulerValidationError(f"Unsupported schedule target type: {target_type}")
