"""Async tool job supervision for the agentic loop."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SyntheticToolEvent:
    tool_name: str
    tool_input: dict[str, Any]
    tool_use_id: str


@dataclass(frozen=True)
class AsyncJobStatus:
    job_id: str
    status: str
    payload: dict[str, Any]


@dataclass
class AsyncJobSupervisor:
    max_wait_seconds: int
    wait_seconds: int = 20
    active_jobs: dict[str, AsyncJobStatus] = field(default_factory=dict)
    wait_cycles: int = 0
    deadline_at: float | None = None

    @property
    def has_active_jobs(self) -> bool:
        return bool(self.active_jobs)

    def track_tool_result(self, result: str) -> AsyncJobStatus | None:
        job_status = extract_async_job_status(result)
        if not job_status or job_status.status not in {"queued", "running"}:
            return None
        self.active_jobs[job_status.job_id] = job_status
        self.deadline_at = self.deadline_at or time.monotonic() + self.max_wait_seconds
        return job_status

    def mark_checked(self, job_id: str, result: str) -> bool:
        job_status = extract_async_job_status(result)
        if job_status and job_status.status in {"succeeded", "failed"}:
            self.active_jobs.pop(job_id, None)
            return True
        return False

    def deadline_expired(self) -> bool:
        return self.deadline_at is not None and time.monotonic() >= self.deadline_at

    def next_wait_event(self) -> SyntheticToolEvent:
        return SyntheticToolEvent(
            tool_name="wait",
            tool_input={
                "seconds": self.wait_seconds,
                "reason": "waiting for async tool job completion",
            },
            tool_use_id=f"auto_wait_{self.wait_cycles + 1}",
        )

    def check_events_after_wait(self) -> list[SyntheticToolEvent]:
        self.wait_cycles += 1
        return [
            SyntheticToolEvent(
                tool_name="check_tool_job",
                tool_input={"job_id": job_id},
                tool_use_id=f"auto_check_{job_id}_{self.wait_cycles}",
            )
            for job_id in list(self.active_jobs)
        ]


def extract_async_job_status(result: str) -> AsyncJobStatus | None:
    try:
        payload = json.loads(result)
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("async") is True and payload.get("status") and payload.get("job_id"):
        return AsyncJobStatus(
            job_id=str(payload["job_id"]),
            status=str(payload["status"]),
            payload=payload,
        )
    return None
