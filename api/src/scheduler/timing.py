"""When a schedule runs: on a cron expression, or once at a moment.

A 5-field cron expression has no year, so it can't say "once": `34 22 31 5 *` is every 31 May, and a reminder
written that way comes back every year. A one-time schedule names its moment instead (`run_at`), runs once, and is
marked completed. Each timing is a strategy; `timing_for` picks the one a schedule uses, so the service, the
in-process runtime and the dispatcher don't branch on it.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Protocol

from apscheduler.triggers.base import BaseTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from src.scheduler.cron import (
    ScheduleExpression,
    ScheduleExpressionError,
    next_run_at,
    validate_schedule_expression,
    zone,
)

if TYPE_CHECKING:
    from src.scheduler.models import Schedule

#: How far in the past a new one-time `run_at` may be and still count as "now" (a slow request, clock skew).
RUN_AT_PAST_TOLERANCE = timedelta(minutes=1)


class ScheduleTiming(Protocol):
    #: A one-time schedule is done after its run; a recurring one carries on.
    finishes_after_run: bool

    def applies(self, schedule: "Schedule") -> bool: ...

    def validate(self, schedule: "Schedule", now: datetime) -> None: ...

    def next_run(self, schedule: "Schedule", after: datetime) -> datetime | None: ...

    def trigger(self, schedule: "Schedule", now: datetime) -> BaseTrigger: ...


class OneTime:
    finishes_after_run = True

    def applies(self, schedule: "Schedule") -> bool:
        return schedule.run_at is not None

    def validate(self, schedule: "Schedule", now: datetime) -> None:
        if schedule.cron_expression:
            raise ScheduleExpressionError("Give either cron_expression or run_at, not both")
        zone(schedule.timezone)
        if moment(schedule) < now - RUN_AT_PAST_TOLERANCE:
            raise ScheduleExpressionError("run_at is in the past")

    def next_run(self, schedule: "Schedule", after: datetime) -> datetime | None:
        run_at = moment(schedule)
        return run_at if run_at > after - RUN_AT_PAST_TOLERANCE else None

    def trigger(self, schedule: "Schedule", now: datetime) -> BaseTrigger:
        # Missed while the server was down: run as soon as it's back, rather than lose the reminder.
        return DateTrigger(run_date=max(moment(schedule), now + timedelta(seconds=1)), timezone=timezone.utc)


class Recurring:
    finishes_after_run = False

    def applies(self, schedule: "Schedule") -> bool:
        return schedule.run_at is None

    def validate(self, schedule: "Schedule", now: datetime) -> None:
        if not schedule.cron_expression:
            raise ScheduleExpressionError("Give a cron_expression for a recurring schedule, or run_at to run once")
        validate_schedule_expression(_expression(schedule))

    def next_run(self, schedule: "Schedule", after: datetime) -> datetime | None:
        return next_run_at(_expression(schedule), now=after)

    def trigger(self, schedule: "Schedule", now: datetime) -> BaseTrigger:
        return CronTrigger.from_crontab(schedule.cron_expression, timezone=schedule.timezone)


TIMINGS: tuple[ScheduleTiming, ...] = (OneTime(), Recurring())


def timing_for(schedule: "Schedule") -> ScheduleTiming:
    return next(timing for timing in TIMINGS if timing.applies(schedule))


def moment(schedule: "Schedule") -> datetime:
    """`run_at` in UTC. A time without an offset is read in the schedule's own timezone."""
    assert schedule.run_at is not None
    run_at = schedule.run_at
    if run_at.tzinfo is None:
        run_at = run_at.replace(tzinfo=zone(schedule.timezone))
    return run_at.astimezone(timezone.utc)


def _expression(schedule: "Schedule") -> ScheduleExpression:
    return ScheduleExpression(schedule.cron_expression, schedule.timezone)
