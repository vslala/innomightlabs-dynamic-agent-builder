"""Recognising an async tool job in a tool result.

The supervisor that used to drive a synthetic wait/check cycle is gone -- the
loop now waits for the job itself. See
api/docs/LLD-agent-runtime-refactor.md (P1.2).
"""

from __future__ import annotations

import json

from src.agents.async_jobs import extract_async_job_status


def test_extract_async_job_status_ignores_non_async_payloads():
    assert extract_async_job_status("not json") is None
    assert extract_async_job_status(json.dumps({"ok": True})) is None
    assert extract_async_job_status(json.dumps(["not", "a", "dict"])) is None
    assert extract_async_job_status(json.dumps({"async": True, "status": "queued"})) is None
    assert extract_async_job_status(json.dumps({"async": True, "job_id": "j1"})) is None


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


def test_pending_covers_exactly_the_non_terminal_statuses():
    def status_for(status: str):
        parsed = extract_async_job_status(
            json.dumps({"async": True, "job_id": "j1", "status": status})
        )
        assert parsed is not None
        return parsed

    assert status_for("queued").pending is True
    assert status_for("running").pending is True
    assert status_for("succeeded").pending is False
    assert status_for("failed").pending is False


def test_progress_message_is_reported_only_when_it_says_something():
    def message_for(payload: dict):
        parsed = extract_async_job_status(json.dumps({"async": True, "job_id": "j1", **payload}))
        assert parsed is not None
        return parsed.progress_message

    assert message_for({"status": "running", "progress_message": "Page 2 of 9"}) == "Page 2 of 9"
    assert message_for({"status": "running", "progress_message": "   "}) is None
    assert message_for({"status": "running"}) is None
