"""Scheduler backend factory."""

from __future__ import annotations

from src.config import settings
from src.scheduler.backends.base import SchedulerBackend
from src.scheduler.backends.in_app import InAppSchedulerBackend


def get_scheduler_backend(name: str | None = None) -> SchedulerBackend:
    backend_name = (name or settings.scheduler_backend).strip().lower()
    if backend_name == "in_app":
        return InAppSchedulerBackend()
    raise ValueError(f"Unsupported scheduler backend: {backend_name}")
