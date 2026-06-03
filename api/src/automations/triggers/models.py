from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ScheduleTriggerConfig(BaseModel):
    cron_expression: str = Field(min_length=1)
    timezone: str = "UTC"
    input: dict[str, Any] = Field(default_factory=dict)
