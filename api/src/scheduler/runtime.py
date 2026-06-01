"""In-process scheduler runtime.

APScheduler owns only the process-local clock. DynamoDB remains the source of
truth for schedules, run records, and duplicate dispatch protection.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from threading import Lock

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.config import settings
from src.scheduler.models import Schedule, ScheduleStatus
from src.scheduler.repository import SchedulerRepository

log = logging.getLogger(__name__)


class SchedulerRuntime:
    """Keeps active DynamoDB schedules registered in the current app process."""

    def __init__(self, repository: SchedulerRepository | None = None):
        self.repository = repository or SchedulerRepository()
        self.scheduler = AsyncIOScheduler(timezone=timezone.utc)
        self._started = False

    async def start(self) -> None:
        if self._started or not settings.scheduler_runtime_enabled:
            return
        for schedule in self.repository.list_active_schedules():
            self.upsert(schedule)
        self.scheduler.start()
        self._started = True
        log.info("Scheduler runtime started")

    async def stop(self) -> None:
        if not self._started:
            return
        self.scheduler.shutdown(wait=False)
        self._started = False
        log.info("Scheduler runtime stopped")

    def upsert(self, schedule: Schedule) -> None:
        if schedule.status != ScheduleStatus.ACTIVE:
            self.remove(schedule.schedule_id)
            return

        trigger = CronTrigger.from_crontab(schedule.cron_expression, timezone=schedule.timezone)
        self.scheduler.add_job(
            self._dispatch_job,
            trigger=trigger,
            id=schedule.schedule_id,
            args=[schedule.schedule_id, schedule.owner_email],
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=300,
        )

    def remove(self, schedule_id: str) -> None:
        if self.scheduler.get_job(schedule_id):
            self.scheduler.remove_job(schedule_id)

    async def _dispatch_job(self, schedule_id: str, owner_email: str) -> None:
        schedule = self.repository.find_schedule(owner_email, schedule_id)
        if not schedule:
            self.remove(schedule_id)
            return

        scheduled_for = schedule.next_run_at or datetime.now(timezone.utc).replace(second=0, microsecond=0)
        from src.scheduler.dispatcher import SchedulerDispatcher

        await SchedulerDispatcher(repository=self.repository).dispatch(
            schedule_id=schedule_id,
            owner_email=owner_email,
            scheduled_for=scheduled_for,
        )


_runtime: SchedulerRuntime | None = None
_runtime_lock = Lock()


def get_scheduler_runtime() -> SchedulerRuntime:
    global _runtime
    if _runtime is None:
        with _runtime_lock:
            if _runtime is None:
                _runtime = SchedulerRuntime()
    return _runtime
