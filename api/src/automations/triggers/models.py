from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class ScheduleTriggerConfig(BaseModel):
    """When a schedule trigger starts the automation: repeatedly on a cron expression, or once at `run_at`.

    A 5-field cron has no year, so "once" can't be written as cron; see src/scheduler/timing.py."""

    cron_expression: str = ""
    #: Run once at this moment, then the trigger's schedule completes. Without an offset it's read in `timezone`.
    run_at: datetime | None = None
    timezone: str = "UTC"
    input: dict[str, Any] = Field(default_factory=dict)

    @field_validator("run_at", mode="before")
    @classmethod
    def _blank_is_unset(cls, value: Any) -> Any:
        # The dashboard form sends the field it didn't fill as "".
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("cron_expression", mode="before")
    @classmethod
    def _strip(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _once_or_repeating(self) -> "ScheduleTriggerConfig":
        if bool(self.cron_expression) == bool(self.run_at):
            raise ValueError("Set either a cron expression to repeat or a date and time to run once, not both")
        return self
