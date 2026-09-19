"""Recognising an async tool job in a tool result."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

#: Statuses that mean the job has not finished yet.
PENDING_JOB_STATUSES = frozenset({"queued", "running"})


@dataclass(frozen=True)
class AsyncJobStatus:
    job_id: str
    status: str
    payload: dict[str, Any]

    @property
    def pending(self) -> bool:
        return self.status in PENDING_JOB_STATUSES

    @property
    def progress_message(self) -> str | None:
        message = self.payload.get("progress_message")
        return message if isinstance(message, str) and message.strip() else None


def extract_async_job_status(result: str) -> AsyncJobStatus | None:
    """The job a tool result describes, if it describes one."""
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
