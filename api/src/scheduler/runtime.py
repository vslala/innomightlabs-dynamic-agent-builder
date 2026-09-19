"""In-process scheduler runtime.

APScheduler owns only the process-local clock. DynamoDB remains the source of
truth for schedules, run records, and duplicate dispatch protection.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone
from threading import Lock

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from src.agents.tool_runtime.jobs.repository import ToolJobRepository
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
TOOL_JOB_REAPER_ID = "internal:stale-tool-job-reaper"


class SchedulerRuntime:
    """Keeps active DynamoDB schedules registered in the current app process."""

    def __init__(
        self,
        repository: SchedulerRepository | None = None,
        crawl_job_state_service: CrawlJobStateService | None = None,
        dream_repository: DreamRepository | None = None,
        chat_turn_repository: ConversationTurnRepository | None = None,
        tool_job_repository: ToolJobRepository | None = None,
    ):
        self.repository = repository or SchedulerRepository()
        self.crawl_job_state_service = crawl_job_state_service or CrawlJobStateService()
        self.dream_repository = dream_repository or DreamRepository()
        self.chat_turn_repository = chat_turn_repository or ConversationTurnRepository()
        self.tool_job_repository = tool_job_repository or ToolJobRepository()
        self.scheduler = AsyncIOScheduler(timezone=timezone.utc)
        self._started = False

    async def start(self) -> None:
        if self._started or not settings.scheduler_runtime_enabled:
            return
        for schedule in self.repository.list_active_schedules():
            self.upsert(schedule)
        for reaper, interval_seconds, reaper_id in (
            (self._reap_stale_crawl_jobs, settings.crawl_job_reaper_interval_seconds, CRAWL_JOB_REAPER_ID),
            (self._reap_stale_dream_runs, settings.dream_run_reaper_interval_seconds, DREAM_RUN_REAPER_ID),
            (self._reap_stale_chat_turns, settings.chat_turn_reaper_interval_seconds, CHAT_TURN_REAPER_ID),
            (self._reap_stale_tool_jobs, settings.tool_job_reaper_interval_seconds, TOOL_JOB_REAPER_ID),
        ):
            self.scheduler.add_job(
                reaper,
                trigger=IntervalTrigger(seconds=interval_seconds, timezone=timezone.utc),
                id=reaper_id,
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
        self._reap("crawl job", self.crawl_job_state_service.fail_stale_jobs)

    async def _reap_stale_dream_runs(self) -> None:
        self._reap("dream run", self.dream_repository.fail_stale_runs)

    async def _reap_stale_chat_turns(self) -> None:
        self._reap("chat turn", self.chat_turn_repository.fail_stale_turns)

    async def _reap_stale_tool_jobs(self) -> None:
        self._reap("tool job", self.tool_job_repository.fail_stale_jobs)

    @staticmethod
    def _reap(label: str, fail_stale: Callable[[], int]) -> None:
        """Never let a reaper's failure stop the scheduler."""
        try:
            failed_count = fail_stale()
            if failed_count:
                log.warning("Marked %s stale %s(s) as failed", failed_count, label)
        except Exception:
            log.exception("Failed to reap stale %ss", label)


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
