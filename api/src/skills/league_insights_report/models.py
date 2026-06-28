from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

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
    game_name: str
    tag_line: str
    report_scope: str = "single_match"
    match_id: str | None = None
    match_ids: list[str] | str = Field(default_factory=list)
    match_count: int | str = DEFAULT_MATCH_COUNT
    routing_region: str | None = None
    queue: int | str | None = None
    report_title: str | None = None

    @model_validator(mode="after")
    def normalize(self) -> "GenerateMatchReportRequest":
        self.game_name = self.game_name.strip()
        self.tag_line = self.tag_line.strip().lstrip("#")
        self.report_scope = self.report_scope.strip().lower()
        self.match_id = self.match_id.strip() if self.match_id else None
        self.match_ids = _normalize_match_ids(self.match_ids)
        self.match_count = _clamped_int(self.match_count, DEFAULT_MATCH_COUNT, 1, MAX_MATCH_COUNT)
        self.queue = _optional_int(self.queue)
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


def _normalize_match_ids(value: list[str] | str) -> list[str]:
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
