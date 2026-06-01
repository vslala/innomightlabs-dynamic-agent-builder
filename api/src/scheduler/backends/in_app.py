"""Scheduler backend backed by the app process runtime."""

from __future__ import annotations

from src.scheduler.backends.base import SchedulerBackend
from src.scheduler.models import Schedule
from src.scheduler.runtime import get_scheduler_runtime


class InAppSchedulerBackend(SchedulerBackend):
    """Synchronizes persisted schedule changes into the in-process runtime."""

    def upsert(self, schedule: Schedule) -> None:
        get_scheduler_runtime().upsert(schedule)

    def delete(self, schedule: Schedule) -> None:
        get_scheduler_runtime().remove(schedule.schedule_id)

    def pause(self, schedule: Schedule) -> None:
        get_scheduler_runtime().remove(schedule.schedule_id)

    def resume(self, schedule: Schedule) -> None:
        get_scheduler_runtime().upsert(schedule)
