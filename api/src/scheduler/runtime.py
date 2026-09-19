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
from apscheduler.triggers.interval import IntervalTrigger

from src.agents.turns.repository import ConversationTurnRepository
from src.config import settings
from src.dream.repository import DreamRepository
from src.knowledge.run_state import CrawlJobStateService
from src.scheduler.models import Schedule, ScheduleStatus
from src.scheduler.repository import SchedulerRepository

log = logging.getLogger(__name__)

CRAWL_JOB_REAPER_ID = "internal:stale-crawl-job-reaper"
DREAM_RUN_REAPER_ID = "internal:stale-dream-run-reaper"
CHAT_TURN_REAPER_ID = "internal:stale-chat-turn-reaper"


class SchedulerRuntime:
    """Keeps active DynamoDB schedules registered in the current app process."""

    def __init__(
        self,
        repository: SchedulerRepository | None = None,
        crawl_job_state_service: CrawlJobStateService | None = None,
        dream_repository: DreamRepository | None = None,
        chat_turn_repository: ConversationTurnRepository | None = None,
    ):
        self.repository = repository or SchedulerRepository()
        self.crawl_job_state_service = crawl_job_state_service or CrawlJobStateService()
        self.dream_repository = dream_repository or DreamRepository()
        self.chat_turn_repository = chat_turn_repository or ConversationTurnRepository()
        self.scheduler = AsyncIOScheduler(timezone=timezone.utc)
        self._started = False

    async def start(self) -> None:
        if self._started or not settings.scheduler_runtime_enabled:
            return
        for schedule in self.repository.list_active_schedules():
            self.upsert(schedule)
        self.scheduler.add_job(
            self._reap_stale_crawl_jobs,
            trigger=IntervalTrigger(
                seconds=settings.crawl_job_reaper_interval_seconds,
                timezone=timezone.utc,
            ),
            id=CRAWL_JOB_REAPER_ID,
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )
        self.scheduler.add_job(
            self._reap_stale_dream_runs,
            trigger=IntervalTrigger(
                seconds=settings.dream_run_reaper_interval_seconds,
                timezone=timezone.utc,
            ),
            id=DREAM_RUN_REAPER_ID,
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )
        self.scheduler.add_job(
            self._reap_stale_chat_turns,
            trigger=IntervalTrigger(
                seconds=settings.chat_turn_reaper_interval_seconds,
                timezone=timezone.utc,
            ),
            id=CHAT_TURN_REAPER_ID,
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )
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

        scheduled_for = _current_scheduler_tick()
        from src.scheduler.dispatcher import SchedulerDispatcher

        await SchedulerDispatcher(repository=self.repository).dispatch(
            schedule_id=schedule_id,
            owner_email=owner_email,
            scheduled_for=scheduled_for,
        )

    async def _reap_stale_crawl_jobs(self) -> None:
        try:
            failed_count = self.crawl_job_state_service.fail_stale_jobs()
            if failed_count:
                log.warning("Marked %s stale crawl job(s) as failed", failed_count)
        except Exception:
            log.exception("Failed to reap stale crawl jobs")

    async def _reap_stale_dream_runs(self) -> None:
        try:
            failed_count = self.dream_repository.fail_stale_runs()
            if failed_count:
                log.warning("Marked %s stale dream run(s) as failed", failed_count)
        except Exception:
            log.exception("Failed to reap stale dream runs")

    async def _reap_stale_chat_turns(self) -> None:
        try:
            failed_count = self.chat_turn_repository.fail_stale_turns()
            if failed_count:
                log.warning("Marked %s stale chat turn(s) as failed", failed_count)
        except Exception:
            log.exception("Failed to reap stale chat turns")


_runtime: SchedulerRuntime | None = None
_runtime_lock = Lock()


def get_scheduler_runtime() -> SchedulerRuntime:
    global _runtime
    if _runtime is None:
        with _runtime_lock:
            if _runtime is None:
                _runtime = SchedulerRuntime()
    return _runtime


def _current_scheduler_tick() -> datetime:
    return datetime.now(timezone.utc).replace(second=0, microsecond=0)
