from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator

ROUTING_REGIONS = {"americas", "asia", "europe", "sea"}
PLATFORM_REGIONS = {
    "br1",
    "eun1",
    "euw1",
    "jp1",
    "kr",
    "la1",
    "la2",
    "me1",
    "na1",
    "oc1",
    "ph2",
    "ru",
    "sg2",
    "th2",
    "tr1",
    "tw2",
    "vn2",
}

DEFAULT_ROUTING_REGION = "europe"
DEFAULT_PLATFORM_REGION = "euw1"
MAX_MATCH_COUNT = 10
MAX_TIMELINE_EVENTS = 80


class RiotLolConfig(BaseModel):
    riot_api_key: str
    default_routing_region: str = DEFAULT_ROUTING_REGION
    default_platform_region: str = DEFAULT_PLATFORM_REGION

    @model_validator(mode="after")
    def normalize(self) -> "RiotLolConfig":
        self.riot_api_key = self.riot_api_key.strip()
        self.default_routing_region = _routing_region(self.default_routing_region, "default_routing_region")
        self.default_platform_region = _platform_region(self.default_platform_region, "default_platform_region")
        if not self.riot_api_key:
            raise ValueError("riot_api_key is required")
        return self


class PlayerLookup(BaseModel):
    game_name: str | None = None
    tag_line: str | None = None
    puuid: str | None = None
    routing_region: str | None = None
    platform_region: str | None = None

    @model_validator(mode="after")
    def normalize(self) -> "PlayerLookup":
        self.game_name = _optional_text(self.game_name)
        self.tag_line = _optional_text(self.tag_line)
        self.puuid = _optional_text(self.puuid)
        self.routing_region = _optional_routing_region(self.routing_region)
        self.platform_region = _optional_platform_region(self.platform_region)
        if not self.puuid and not (self.game_name and self.tag_line):
            raise ValueError("Provide either puuid or both game_name and tag_line")
        return self


class RecentMatchesRequest(PlayerLookup):
    count: int = 5
    queue: int | None = None

    @model_validator(mode="after")
    def normalize_recent(self) -> "RecentMatchesRequest":
        self.count = _clamp_int(self.count, 1, MAX_MATCH_COUNT)
        return self


class MatchRequest(BaseModel):
    match_id: str
    routing_region: str | None = None
    game_name: str | None = None
    tag_line: str | None = None
    puuid: str | None = None

    @model_validator(mode="after")
    def normalize(self) -> "MatchRequest":
        self.match_id = self.match_id.strip()
        self.routing_region = _optional_routing_region(self.routing_region)
        self.game_name = _optional_text(self.game_name)
        self.tag_line = _optional_text(self.tag_line)
        self.puuid = _optional_text(self.puuid)
        if not self.match_id:
            raise ValueError("match_id is required")
        if (self.game_name and not self.tag_line) or (self.tag_line and not self.game_name):
            raise ValueError("Provide both game_name and tag_line when resolving a player")
        return self


class TimelineRequest(MatchRequest):
    max_events: int = 40

    @model_validator(mode="after")
    def normalize_timeline(self) -> "TimelineRequest":
        self.max_events = _clamp_int(self.max_events, 1, MAX_TIMELINE_EVENTS)
        return self


class PlatformRequest(BaseModel):
    platform_region: str | None = None

    @model_validator(mode="after")
    def normalize(self) -> "PlatformRequest":
        self.platform_region = _optional_platform_region(self.platform_region)
        return self


class ChampionMasteryRequest(PlayerLookup):
    champion_id: int | None = None
    limit: int = 5

    @model_validator(mode="after")
    def normalize_mastery(self) -> "ChampionMasteryRequest":
        self.limit = _clamp_int(self.limit, 1, 20)
        return self


class ChallengesRequest(PlayerLookup):
    include_config: bool = False


class ClashRequest(PlayerLookup):
    pass


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_routing_region(value: str | None) -> str | None:
    if not value:
        return None
    return _routing_region(value, "routing_region")


def _optional_platform_region(value: str | None) -> str | None:
    if not value:
        return None
    return _platform_region(value, "platform_region")


def _routing_region(value: str, field_name: str) -> str:
    normalized = str(value).strip().lower()
    if normalized not in ROUTING_REGIONS:
        raise ValueError(f"{field_name} must be americas, asia, europe, or sea")
    return normalized


def _platform_region(value: str, field_name: str) -> str:
    normalized = str(value).strip().lower()
    if normalized not in PLATFORM_REGIONS:
        raise ValueError(f"{field_name} is not a supported League platform region")
    return normalized


def _clamp_int(value: Any, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, int(value)))
