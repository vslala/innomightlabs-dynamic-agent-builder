"""The tool-job reaper.

Job execution is an in-process asyncio task, so a restart orphans the row.
Before this reaper existed, an orphaned job sat RUNNING until its 7-day TTL:
the per-job stale check only fires when an agent happens to ask about that
exact job id. See api/docs/LLD-agent-runtime-refactor.md.
"""

from datetime import datetime, timedelta, timezone

import pytest

from src.agents.tool_runtime.jobs.models import (
    TOOL_JOB_STALE_AFTER_SECONDS,
    ToolJob,
    ToolJobStatus,
)
from src.agents.tool_runtime.jobs.repository import ToolJobRepository

OWNER = "owner@example.com"


@pytest.fixture
def job_repository(dynamodb_table):
    return ToolJobRepository()


def _job(*, status: ToolJobStatus, started_at: datetime | None) -> ToolJob:
    return ToolJob(
        owner_email=OWNER,
        actor_email=OWNER,
        actor_id=OWNER,
        agent_id="agent-1",
        conversation_id="conversation-1",
        tool_name="execute_skill_action",
        skill_id="some_skill",
        action="do_the_thing",
        status=status,
        started_at=started_at,
        created_at=started_at or datetime.now(timezone.utc),
    )


def test_reaper_fails_a_running_job_that_outlived_the_stale_window(job_repository):
    stale = _job(
        status=ToolJobStatus.RUNNING,
        started_at=datetime.now(timezone.utc)
        - timedelta(seconds=TOOL_JOB_STALE_AFTER_SECONDS + 60),
    )
    job_repository.create(stale)

    assert job_repository.fail_stale_jobs() == 1

    reaped = job_repository.find_by_id(stale.job_id)
    assert reaped is not None
    assert reaped.status == ToolJobStatus.FAILED
    assert "stale" in (reaped.error or "")
    assert reaped.completed_at is not None


def test_reaper_leaves_a_job_inside_the_stale_window_alone(job_repository):
    fresh = _job(status=ToolJobStatus.RUNNING, started_at=datetime.now(timezone.utc))
    job_repository.create(fresh)

    assert job_repository.fail_stale_jobs() == 0
    assert job_repository.find_by_id(fresh.job_id).status == ToolJobStatus.RUNNING


def test_reaper_fails_a_queued_job_that_was_never_picked_up(job_repository):
    """The P0.2 failure mode: a job whose task was collected before it ran."""
    orphaned = _job(
        status=ToolJobStatus.QUEUED,
        started_at=None,
    )
    orphaned.created_at = datetime.now(timezone.utc) - timedelta(
        seconds=TOOL_JOB_STALE_AFTER_SECONDS + 60
    )
    job_repository.create(orphaned)

    assert job_repository.fail_stale_jobs() == 1
    assert job_repository.find_by_id(orphaned.job_id).status == ToolJobStatus.FAILED


def test_reaper_ignores_jobs_that_already_finished(job_repository):
    long_ago = datetime.now(timezone.utc) - timedelta(days=1)
    for status in (ToolJobStatus.SUCCEEDED, ToolJobStatus.FAILED):
        job_repository.create(_job(status=status, started_at=long_ago))

    assert job_repository.fail_stale_jobs() == 0
