"""Scheduler backend interface."""

from __future__ import annotations

from typing import Protocol

from src.scheduler.models import Schedule


class SchedulerBackend(Protocol):
    def upsert(self, schedule: Schedule) -> None: ...
    def delete(self, schedule: Schedule) -> None: ...
    def pause(self, schedule: Schedule) -> None: ...
    def resume(self, schedule: Schedule) -> None: ...
