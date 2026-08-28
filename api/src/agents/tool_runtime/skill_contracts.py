"""Input contracts for built-in skill runtime tools."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LoadSkillInput(BaseModel):
    skill_id: str


class ExecuteSkillActionInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    skill_id: str
    action: str
    arguments: dict[str, Any]
    async_: bool = Field(default=False, alias="async")


class CheckToolJobInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
