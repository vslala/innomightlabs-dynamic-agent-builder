from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml

from src.skills.registry import SkillRegistry
from src.skills.riot_lol_api_client.actions import get_recent_match_summaries, lookup_player
from src.skills.riot_lol_api_client.client import RiotLolClient
from src.skills.riot_lol_api_client.models import MAX_MATCH_COUNT, RecentMatchesRequest, RiotLolConfig


class FakeRiotClient:
    def __init__(self):
        self.routing_calls: list[dict[str, Any]] = []
        self.platform_calls: list[dict[str, Any]] = []

    async def get_routing_json(self, routing_region: str, path: str, *, params: dict[str, Any] | None = None):
        self.routing_calls.append({"routing_region": routing_region, "path": path, "params": params})
        if path.startswith("/riot/account/v1/accounts/by-riot-id/"):
            return {"puuid": "puuid-1", "gameName": "Demon Simon", "tagLine": "messi"}
        if path.endswith("/ids"):
            return ["EUW1_1"]
        if path == "/lol/match/v5/matches/EUW1_1":
            return _match_payload()
        raise AssertionError(f"Unexpected routing path {path}")

    async def get_platform_json(self, platform_region: str, path: str, *, params: dict[str, Any] | None = None):
        self.platform_calls.append({"platform_region": platform_region, "path": path, "params": params})
        if path.startswith("/lol/summoner/v4/summoners/by-puuid/"):
            return {"puuid": "puuid-1", "profileIconId": 6013, "revisionDate": 1782691414981, "summonerLevel": 70}
        raise AssertionError(f"Unexpected platform path {path}")


def test_manifest_declares_secret_key_and_expected_actions():
    with open("src/skills/riot_lol_api_client/manifest.yml") as handle:
        manifest = yaml.safe_load(handle)

    secret_field = next(item for item in manifest["form"] if item["name"] == "riot_api_key")
    action_names = {action["name"] for action in manifest["actions"]}

    assert manifest["id"] == "riot_lol_api_client"
    assert manifest["namespace"] == "games.league_of_legends"
    assert secret_field["attr"]["secret"] == "true"
    assert {
        "lookup_player",
        "get_recent_match_summaries",
        "get_match_details",
        "get_match_timeline",
        "get_ranked_profile",
        "get_champion_mastery",
        "get_live_game",
        "get_champion_rotations",
        "get_lol_status",
        "get_challenges",
        "get_clash",
    }.issubset(action_names)


def test_config_and_request_validation():
    config = RiotLolConfig.model_validate(
        {
            "riot_api_key": " RGAPI-test ",
            "default_routing_region": "Europe",
            "default_platform_region": "EUW1",
        }
    )
    request = RecentMatchesRequest.model_validate(
        {"game_name": "Demon Simon", "tag_line": "messi", "count": 99}
    )

    assert config.riot_api_key == "RGAPI-test"
    assert config.default_routing_region == "europe"
    assert config.default_platform_region == "euw1"
    assert request.count == MAX_MATCH_COUNT

    with pytest.raises(ValueError, match="Provide either puuid"):
        RecentMatchesRequest.model_validate({})


def test_riot_client_sends_token_and_humanizes_auth_error():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(403, json={"status": {"message": "Forbidden"}}, request=request)

    client = RiotLolClient("RGAPI-secret", http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))

    with pytest.raises(Exception, match="Riot API rejected"):
        asyncio.run(client.get_platform_json("euw1", "/lol/status/v4/platform-data"))

    assert requests[0].headers["X-Riot-Token"] == "RGAPI-secret"


def test_lookup_player_returns_compact_identity(monkeypatch):
    fake = FakeRiotClient()
    monkeypatch.setattr("src.skills.riot_lol_api_client.actions._client", lambda config: fake)

    result = asyncio.run(
        lookup_player(
            {"game_name": "Demon Simon", "tag_line": "messi"},
            {
                "riot_api_key": "RGAPI-test",
                "default_routing_region": "europe",
                "default_platform_region": "euw1",
            },
            {},
        )
    )

    assert result["ok"] is True
    assert result["account"] == {
        "puuid": "puuid-1",
        "game_name": "Demon Simon",
        "tag_line": "messi",
        "riot_id": "Demon Simon#messi",
    }
    assert result["summoner"]["summoner_level"] == 70
    assert fake.routing_calls[0]["path"] == "/riot/account/v1/accounts/by-riot-id/Demon%20Simon/messi"


def test_recent_match_summaries_are_compact(monkeypatch):
    fake = FakeRiotClient()
    monkeypatch.setattr("src.skills.riot_lol_api_client.actions._client", lambda config: fake)

    result = asyncio.run(
        get_recent_match_summaries(
            {"game_name": "Demon Simon", "tag_line": "messi", "count": 1},
            {
                "riot_api_key": "RGAPI-test",
                "default_routing_region": "europe",
                "default_platform_region": "euw1",
            },
            {},
        )
    )

    player = result["matches"][0]["player"]
    assert result["ok"] is True
    assert result["count"] == 1
    assert player["champion_name"] == "Ezreal"
    assert player["kda"] == 5.0
    assert player["cs"] == 210
    assert "metadata" not in result["matches"][0]


def test_registry_executes_riot_lol_alias(monkeypatch):
    fake = FakeRiotClient()
    monkeypatch.setattr("src.skills.riot_lol_api_client.actions._client", lambda config: fake)
    registry = SkillRegistry(Path("src/skills"))

    result = asyncio.run(
        registry.execute_action(
            "riot_lol_api_client",
            "lol_lookup_player",
            {"game_name": "Demon Simon", "tag_line": "messi"},
            {
                "riot_api_key": "RGAPI-test",
                "default_routing_region": "europe",
                "default_platform_region": "euw1",
            },
            {},
        )
    )

    assert result["ok"] is True
    assert result["account"]["riot_id"] == "Demon Simon#messi"


def _match_payload() -> dict[str, Any]:
    return {
        "metadata": {"matchId": "EUW1_1"},
        "info": {
            "gameCreation": 1782690000000,
            "gameEndTimestamp": 1782691800000,
            "gameDuration": 1800,
            "gameMode": "CLASSIC",
            "gameType": "MATCHED_GAME",
            "queueId": 420,
            "mapId": 11,
            "participants": [
                {
                    "puuid": "puuid-1",
                    "riotIdGameName": "Demon Simon",
                    "riotIdTagline": "messi",
                    "teamId": 100,
                    "teamPosition": "BOTTOM",
                    "championId": 81,
                    "championName": "Ezreal",
                    "win": True,
                    "kills": 8,
                    "deaths": 2,
                    "assists": 2,
                    "totalMinionsKilled": 190,
                    "neutralMinionsKilled": 20,
                    "goldEarned": 12000,
                    "totalDamageDealtToChampions": 25000,
                    "totalDamageTaken": 14000,
                    "visionScore": 22,
                    "wardsPlaced": 8,
                    "visionWardsBoughtInGame": 2,
                    "challenges": {"killParticipation": 0.625},
                }
            ],
            "teams": [
                {
                    "teamId": 100,
                    "win": True,
                    "objectives": {"dragon": {"kills": 3, "first": True}},
                    "bans": [{"championId": 122, "pickTurn": 1}],
                }
            ],
        },
    }
