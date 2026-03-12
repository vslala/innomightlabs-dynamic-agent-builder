"""Request ID propagation for logging.

We want each log line for a request to be traceable.

Approach:
- store request_id in a contextvar (so it flows through awaits)
- a logging.Filter injects request_id into LogRecord
- a middleware sets/clears request_id per request and echoes it back
"""

from __future__ import annotations

import logging
import uuid
from contextvars import ContextVar

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def new_request_id() -> str:
    return uuid.uuid4().hex


def set_request_id(value: str | None) -> None:
    _request_id.set(value)


def get_request_id() -> str | None:
    return _request_id.get()


class RequestIdFilter(logging.Filter):
    """Inject request_id into each log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id() or "-"
        return True
