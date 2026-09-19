from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

ROUTING_REGIONS = {"americas", "asia", "europe", "sea"}
REPORT_SCOPES = {"single_match", "multi_match"}
DEFAULT_MATCH_COUNT = 5
MAX_MATCH_COUNT = 10

ReportScope = Literal["single_match", "multi_match"]


class LeagueReportConfig(BaseModel):
    report_agent_id: str
    riot_api_key: str
    default_routing_region: str = "europe"

    @model_validator(mode="after")
    def normalize(self) -> "LeagueReportConfig":
        self.report_agent_id = self.report_agent_id.strip()
        self.riot_api_key = self.riot_api_key.strip()
        self.default_routing_region = self.default_routing_region.strip().lower()
        if not self.report_agent_id:
            raise ValueError("report_agent_id is required")
        if not self.riot_api_key:
            raise ValueError("riot_api_key is required")
        if self.default_routing_region not in ROUTING_REGIONS:
            raise ValueError("default_routing_region must be americas, asia, europe, or sea")
        return self


class GenerateMatchReportRequest(BaseModel):
    """Report request from a skill action call.

    The LLM caller may send match_ids/match_count/queue as either their native
    type or a numeric/comma-separated string, so those three fields coerce
    their raw input in a `mode="before"` validator. The field's declared type
    is the coerced type, not the accepted input shape, so downstream code
    reads a real list[str]/int/int|None instead of re-narrowing a lie.
    """

    game_name: str
    tag_line: str
    report_scope: str = "single_match"
    match_id: str | None = None
    match_ids: list[str] = Field(default_factory=list)
    match_count: int = DEFAULT_MATCH_COUNT
    routing_region: str | None = None
    queue: int | None = None
    report_title: str | None = None

    @field_validator("match_ids", mode="before")
    @classmethod
    def _coerce_match_ids(cls, value: Any) -> list[str]:
        return _normalize_match_ids(value)

    @field_validator("match_count", mode="before")
    @classmethod
    def _coerce_match_count(cls, value: Any) -> int:
        return _clamped_int(value, DEFAULT_MATCH_COUNT, 1, MAX_MATCH_COUNT)

    @field_validator("queue", mode="before")
    @classmethod
    def _coerce_queue(cls, value: Any) -> int | None:
        return _optional_int(value)

    @model_validator(mode="after")
    def normalize(self) -> "GenerateMatchReportRequest":
        self.game_name = self.game_name.strip()
        self.tag_line = self.tag_line.strip().lstrip("#")
        self.report_scope = self.report_scope.strip().lower()
        self.match_id = self.match_id.strip() if self.match_id else None
        self.routing_region = self.routing_region.strip().lower() if self.routing_region else None
        self.report_title = self.report_title.strip() if self.report_title else None
        if not self.game_name:
            raise ValueError("game_name is required")
        if not self.tag_line:
            raise ValueError("tag_line is required")
        if self.report_scope not in REPORT_SCOPES:
            raise ValueError("report_scope must be single_match or multi_match")
        if self.match_id and self.match_ids:
            raise ValueError("Provide either match_id or match_ids, not both")
        if self.report_scope == "single_match" and len(self.match_ids) > 1:
            raise ValueError("single_match report accepts at most one match id")
        if len(self.match_ids) > MAX_MATCH_COUNT:
            self.match_ids = self.match_ids[:MAX_MATCH_COUNT]
        if self.routing_region and self.routing_region not in ROUTING_REGIONS:
            raise ValueError("routing_region must be americas, asia, europe, or sea")
        return self

    @property
    def normalized_scope(self) -> ReportScope:
        return "multi_match" if self.report_scope == "multi_match" else "single_match"


def _normalize_match_ids(value: Any) -> list[str]:
    raw_items = value.split(",") if isinstance(value, str) else value
    return [str(item).strip() for item in raw_items if str(item).strip()]


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _clamped_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    if value is None or value == "":
        return default
    return max(minimum, min(maximum, int(value)))
