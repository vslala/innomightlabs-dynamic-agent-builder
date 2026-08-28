from __future__ import annotations

import json

from src.agents.async_jobs import AsyncJobSupervisor, extract_async_job_status


def test_extract_async_job_status_ignores_non_async_payloads():
    assert extract_async_job_status("not json") is None
    assert extract_async_job_status(json.dumps({"ok": True})) is None
    assert extract_async_job_status(json.dumps(["not", "a", "dict"])) is None


def test_extract_async_job_status_returns_named_job_status():
    status = extract_async_job_status(
        json.dumps(
            {
                "async": True,
                "job_id": "tooljob_1",
                "status": "queued",
                "result": {"ok": True},
            }
        )
    )

    assert status is not None
    assert status.job_id == "tooljob_1"
    assert status.status == "queued"
    assert status.payload["result"] == {"ok": True}


def test_supervisor_tracks_running_jobs_and_builds_synthetic_events():
    supervisor = AsyncJobSupervisor(max_wait_seconds=600)

    tracked = supervisor.track_tool_result(
        json.dumps({"async": True, "job_id": "tooljob_1", "status": "running"})
    )
    wait_event = supervisor.next_wait_event()
    check_events = supervisor.check_events_after_wait()

    assert tracked is not None
    assert tracked.job_id == "tooljob_1"
    assert supervisor.has_active_jobs is True
    assert supervisor.deadline_at is not None
    assert wait_event.tool_name == "wait"
    assert wait_event.tool_use_id == "auto_wait_1"
    assert check_events[0].tool_name == "check_tool_job"
    assert check_events[0].tool_input == {"job_id": "tooljob_1"}
    assert check_events[0].tool_use_id == "auto_check_tooljob_1_1"


def test_supervisor_removes_terminal_jobs_only():
    supervisor = AsyncJobSupervisor(max_wait_seconds=600)
    supervisor.track_tool_result(
        json.dumps({"async": True, "job_id": "tooljob_1", "status": "queued"})
    )

    still_active = supervisor.mark_checked(
        "tooljob_1",
        json.dumps({"async": True, "job_id": "tooljob_1", "status": "running"}),
    )
    completed = supervisor.mark_checked(
        "tooljob_1",
        json.dumps({"async": True, "job_id": "tooljob_1", "status": "succeeded"}),
    )

    assert still_active is False
    assert completed is True
    assert supervisor.has_active_jobs is False
