from __future__ import annotations

import asyncio
from types import SimpleNamespace

import httpx
import pytest

from src.agents.architectures.base import AgentInvocationResult
from src.agents.models import Agent
from src.skills.league_insights_report.actions import generate_match_report
from src.skills.league_insights_report.html_safety import (
    UnsafeHtmlError,
    extract_html_document,
    validate_safe_report_html,
)
from src.skills.league_insights_report.models import (
    MAX_MATCH_COUNT,
    GenerateMatchReportRequest,
    LeagueReportConfig,
)
from src.skills.league_insights_report.report_agent import generate_report_html_with_agent
from src.skills.league_insights_report.report_data import build_report_payload
from src.skills.league_insights_report.riot_client import RiotClient, RiotAccount, RiotApiError
from src.skills.registry import SkillRegistry
from tests.mock_data import TEST_USER_EMAIL


SAFE_HTML = """<!doctype html>
<html>
<head><title>Report</title><style>body{font-family:sans-serif}</style></head>
<body><main><h1>League Report</h1></main></body>
</html>"""


def test_manifest_marks_riot_key_secret_and_filters_krishna_mini_agents():
    manifest = SkillRegistry().get("league_insights_report").manifest

    secret_input = next(item for item in manifest.form if item.name == "riot_api_key")
    agent_input = next(item for item in manifest.form if item.name == "report_agent_id")

    assert secret_input.attr["secret"] == "true"
    assert agent_input.options_source.type == "krishna_mini_agents"


def test_league_report_config_requires_riot_key():
    with pytest.raises(ValueError, match="riot_api_key"):
        LeagueReportConfig.model_validate(
            {
                "report_agent_id": "agent-1",
                "riot_api_key": "",
                "default_routing_region": "europe",
            }
        )


def test_generate_match_report_request_normalizes_match_ids_and_clamps_count():
    request = GenerateMatchReportRequest.model_validate(
        {
            "game_name": "Player",
            "tag_line": "#EUW",
            "report_scope": "multi_match",
            "match_ids": "EUW1_1, EUW1_2",
            "match_count": "999",
        }
    )

    assert request.tag_line == "EUW"
    assert request.match_ids == ["EUW1_1", "EUW1_2"]
    assert request.match_count == MAX_MATCH_COUNT


def test_html_extraction_and_safety_validation():
    html = extract_html_document(f"```html\n{SAFE_HTML}\n```")

    validate_safe_report_html(html)

    with pytest.raises(UnsafeHtmlError, match="script"):
        validate_safe_report_html("<!doctype html><html><body><script>alert(1)</script></body></html>")

    with pytest.raises(UnsafeHtmlError, match="event handler"):
        validate_safe_report_html("<!doctype html><html><body><div onclick='x()'></div></body></html>")

    with pytest.raises(UnsafeHtmlError, match="CSS"):
        validate_safe_report_html("<!doctype html><html><head><style>@import url(x);</style></head><body></body></html>")


def test_riot_client_sends_token_and_translates_auth_error():
    class FakeHttpClient:
        def __init__(self):
            self.calls = []

        async def get(self, url, **kwargs):
            self.calls.append({"url": url, **kwargs})
            return httpx.Response(403, json={"status": {"message": "Forbidden"}}, request=httpx.Request("GET", url))

    fake = FakeHttpClient()
    client = RiotClient("RGAPI-secret", http_client=fake)

    with pytest.raises(RiotApiError, match="API key") as exc:
        asyncio.run(
            client.get_account_by_riot_id(
                routing_region="europe",
                game_name="The Player",
                tag_line="EUW",
            )
        )

    assert exc.value.status_code == 403
    assert fake.calls[0]["headers"]["X-Riot-Token"] == "RGAPI-secret"
    assert "The%20Player" in fake.calls[0]["url"]
    assert "RGAPI-secret" not in str(exc.value)


def test_report_data_builds_multi_match_trends():
    account = RiotAccount(puuid="puuid-1", game_name="Player", tag_line="EUW")
    payload = build_report_payload(
        account=account,
        matches=[_match("EUW1_1", True, champion="Ahri"), _match("EUW1_2", False, champion="Lux")],
        report_scope="multi_match",
        routing_region="europe",
    )

    assert payload["trends"]["matches_analyzed"] == 2
    assert payload["trends"]["wins"] == 1
    assert payload["trends"]["win_rate"] == 0.5
    assert payload["matches"][0]["kill_participation"] == 0.75
    assert payload["matches"][0]["summoner_spells"] == {"spell1_id": 4, "spell2_id": 7}
    assert payload["matches"][0]["runes"]["keystone_id"] == 8369
    assert payload["matches"][0]["runes"]["primary_style_id"] == 8300
    assert payload["matches"][0]["items"]["completed_item_ids"] == [1056, 6655, 3020, 4645, 3089, 3135]
    assert payload["matches"][0]["items"]["trinket_item_id"] == 3363
    assert payload["matches"][0]["combat"]["double_kills"] == 2
    assert payload["matches"][0]["early_game"]["gold_per_minute"] == 420.5
    assert payload["trends"]["keystone_perks"] == [{"value": "8369", "games": 2}]


def test_report_agent_rejects_non_krishna_mini_agent():
    repo = _FakeAgentRepository(
        Agent(
            agent_id="agent-1",
            agent_name="Report Agent",
            agent_architecture="krishna-memgpt",
            agent_provider="OpenAI",
            agent_persona="Reporter",
            created_by=TEST_USER_EMAIL,
        )
    )

    with pytest.raises(ValueError, match="krishna-mini"):
        asyncio.run(
            generate_report_html_with_agent(
                agent_id="agent-1",
                owner_email=TEST_USER_EMAIL,
                actor_email=TEST_USER_EMAIL,
                actor_id=TEST_USER_EMAIL,
                prompt="Generate",
                agent_repository=repo,
            )
        )


def test_report_agent_uses_in_memory_repository(monkeypatch):
    captured = {}
    repo = _FakeAgentRepository(
        Agent(
            agent_id="agent-1",
            agent_name="Report Agent",
            agent_architecture="krishna-mini",
            agent_provider="OpenAI",
            agent_persona="Reporter",
            created_by=TEST_USER_EMAIL,
        )
    )

    class FakeArchitecture:
        async def handle_message_buffered(self, **kwargs):
            captured["kwargs"] = kwargs
            return AgentInvocationResult(response_text=SAFE_HTML)

    def fake_get_message_repository(name):
        captured["repository_name"] = name
        return object()

    def fake_get_agent_architecture(name, *, message_repository):
        captured["architecture_name"] = name
        captured["message_repository"] = message_repository
        return FakeArchitecture()

    monkeypatch.setattr("src.skills.league_insights_report.report_agent.get_message_repository", fake_get_message_repository)
    monkeypatch.setattr("src.skills.league_insights_report.report_agent.get_agent_architecture", fake_get_agent_architecture)

    result = asyncio.run(
        generate_report_html_with_agent(
            agent_id="agent-1",
            owner_email=TEST_USER_EMAIL,
            actor_email=TEST_USER_EMAIL,
            actor_id=TEST_USER_EMAIL,
            prompt="Generate",
            agent_repository=repo,
        )
    )

    assert result == SAFE_HTML
    assert captured["repository_name"] == "in_memory"
    assert captured["architecture_name"] == "krishna-mini"
    assert captured["kwargs"]["conversation"].created_by == TEST_USER_EMAIL


def test_generate_match_report_multi_match_creates_artifact(monkeypatch):
    fake_riot = _FakeRiotClient(
        match_ids=["EUW1_1", "EUW1_2", "EUW1_3"],
        matches={
            "EUW1_1": _match("EUW1_1", True),
            "EUW1_2": _match("EUW1_2", False),
            "EUW1_3": _match("EUW1_3", True),
        },
    )
    fake_artifacts = _FakeArtifactService()
    monkeypatch.setattr("src.skills.league_insights_report.actions.RiotClient", lambda api_key: fake_riot)
    monkeypatch.setattr("src.skills.league_insights_report.actions.ArtifactService", lambda: fake_artifacts)
    monkeypatch.setattr(
        "src.skills.league_insights_report.actions.generate_report_html_with_agent",
        _fake_report_agent,
    )

    result = asyncio.run(
        generate_match_report(
            {
                "game_name": "Player",
                "tag_line": "EUW",
                "report_scope": "multi_match",
                "match_count": 3,
            },
            {
                "report_agent_id": "agent-1",
                "riot_api_key": "RGAPI-secret",
                "default_routing_region": "europe",
            },
            {
                "owner_email": TEST_USER_EMAIL,
                "automation_id": "automation-1",
                "automation_run_id": "run-1",
                "automation_node_id": "node-1",
            },
        )
    )

    assert result["ok"] is True
    assert result["artifact_id"] == "artifact-1"
    assert result["url"] == "https://example.com/view"
    assert result["view_url"] == "https://example.com/view"
    assert result["download_url"] == "https://example.com/download"
    assert result["report_scope"] == "multi_match"
    assert result["match_ids"] == ["EUW1_1", "EUW1_2", "EUW1_3"]
    assert fake_riot.match_id_calls == [{"count": 3, "queue": None, "routing_region": "europe", "puuid": "puuid-1"}]
    assert fake_riot.match_calls == ["EUW1_1", "EUW1_2", "EUW1_3"]
    assert fake_artifacts.calls[0]["artifact_type"] == "html_report"
    assert fake_artifacts.calls[0]["source"].metadata["report_scope"] == "multi_match"


def test_generate_match_report_explicit_ids_skip_match_id_lookup(monkeypatch):
    fake_riot = _FakeRiotClient(
        matches={
            "EUW1_1": _match("EUW1_1", True),
            "EUW1_2": _match("EUW1_2", False),
        },
    )
    monkeypatch.setattr("src.skills.league_insights_report.actions.RiotClient", lambda api_key: fake_riot)
    monkeypatch.setattr("src.skills.league_insights_report.actions.ArtifactService", lambda: _FakeArtifactService())
    monkeypatch.setattr(
        "src.skills.league_insights_report.actions.generate_report_html_with_agent",
        _fake_report_agent,
    )

    result = asyncio.run(
        generate_match_report(
            {
                "game_name": "Player",
                "tag_line": "EUW",
                "report_scope": "multi_match",
                "match_ids": "EUW1_1, EUW1_2",
            },
            {
                "report_agent_id": "agent-1",
                "riot_api_key": "RGAPI-secret",
                "default_routing_region": "europe",
            },
            {"owner_email": TEST_USER_EMAIL},
        )
    )

    assert result["match_ids"] == ["EUW1_1", "EUW1_2"]
    assert fake_riot.match_id_calls == []
    assert fake_riot.match_calls == ["EUW1_1", "EUW1_2"]


def test_generate_match_report_riot_error_returns_branchable_payload(monkeypatch):
    fake_riot = _FakeRiotClient(error=RiotApiError("bad key", status_code=403))
    monkeypatch.setattr("src.skills.league_insights_report.actions.RiotClient", lambda api_key: fake_riot)

    result = asyncio.run(
        generate_match_report(
            {"game_name": "Player", "tag_line": "EUW"},
            {
                "report_agent_id": "agent-1",
                "riot_api_key": "RGAPI-secret",
                "default_routing_region": "europe",
            },
            {"owner_email": TEST_USER_EMAIL},
        )
    )

    assert result == {"ok": False, "status_code": 403, "error": "bad key"}


async def _fake_report_agent(**kwargs):
    return SAFE_HTML


class _FakeAgentRepository:
    def __init__(self, agent: Agent | None):
        self.agent = agent

    def find_agent_by_id(self, agent_id: str, owner_email: str) -> Agent | None:
        return self.agent


class _FakeRiotClient:
    def __init__(
        self,
        match_ids: list[str] | None = None,
        matches: dict[str, dict] | None = None,
        error: Exception | None = None,
    ):
        self.match_ids = match_ids or []
        self.matches = matches or {}
        self.error = error
        self.match_id_calls = []
        self.match_calls = []

    async def get_account_by_riot_id(self, **kwargs):
        if self.error:
            raise self.error
        return RiotAccount(puuid="puuid-1", game_name=kwargs["game_name"], tag_line=kwargs["tag_line"])

    async def get_match_ids(self, **kwargs):
        self.match_id_calls.append(kwargs)
        return self.match_ids[: kwargs["count"]]

    async def get_match(self, **kwargs):
        self.match_calls.append(kwargs["match_id"])
        return self.matches[kwargs["match_id"]]


class _FakeArtifactService:
    def __init__(self):
        self.calls = []

    def create_artifact(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            artifact_id="artifact-1",
            title=kwargs["title"],
            filename=kwargs["filename"],
            url="https://example.com/download",
            view_url="https://example.com/view",
        )


def _match(match_id: str, win: bool, *, champion: str = "Ahri") -> dict:
    return {
        "metadata": {"matchId": match_id},
        "info": {
            "queueId": 420,
            "gameCreation": 1710000000000,
            "gameDuration": 1800,
            "gameMode": "CLASSIC",
            "participants": [
                {
                    "puuid": "puuid-1",
                    "teamId": 100,
                    "win": win,
                    "championName": champion,
                    "teamPosition": "MIDDLE",
                    "summonerName": "Player",
                    "summoner1Id": 4,
                    "summoner2Id": 7,
                    "kills": 5,
                    "deaths": 2,
                    "assists": 1,
                    "totalDamageDealtToChampions": 12000,
                    "totalDamageTaken": 18000,
                    "damageSelfMitigated": 9000,
                    "goldEarned": 11000,
                    "goldSpent": 10300,
                    "totalMinionsKilled": 180,
                    "neutralMinionsKilled": 12,
                    "visionScore": 24,
                    "wardsPlaced": 9,
                    "wardsKilled": 3,
                    "visionWardsBoughtInGame": 2,
                    "summonerLevel": 300,
                    "item0": 1056,
                    "item1": 6655,
                    "item2": 3020,
                    "item3": 4645,
                    "item4": 3089,
                    "item5": 3135,
                    "item6": 3363,
                    "itemsPurchased": 24,
                    "consumablesPurchased": 6,
                    "doubleKills": 2,
                    "tripleKills": 1,
                    "largestKillingSpree": 4,
                    "largestMultiKill": 3,
                    "firstBloodKill": True,
                    "perks": {
                        "statPerks": {"offense": 5008, "flex": 5008, "defense": 5002},
                        "styles": [
                            {
                                "style": 8300,
                                "selections": [
                                    {"perk": 8369},
                                    {"perk": 8304},
                                    {"perk": 8345},
                                    {"perk": 8347},
                                ],
                            },
                            {
                                "style": 8100,
                                "selections": [{"perk": 8139}, {"perk": 8135}],
                            },
                        ],
                    },
                    "challenges": {
                        "goldPerMinute": 420.5,
                        "damagePerMinute": 650.1,
                        "kdaAt10": 2.0,
                        "controlWardsPlaced": 2,
                        "skillshotsDodged": 12,
                        "skillshotsHit": 55,
                        "soloKills": 1,
                    },
                },
                {
                    "puuid": "ally",
                    "teamId": 100,
                    "kills": 3,
                    "totalDamageDealtToChampions": 8000,
                    "goldEarned": 9000,
                },
                {
                    "puuid": "enemy",
                    "teamId": 200,
                    "kills": 4,
                    "totalDamageDealtToChampions": 10000,
                    "goldEarned": 10000,
                },
            ],
            "teams": [
                {
                    "teamId": 100,
                    "win": win,
                    "objectives": {
                        "baron": {"kills": 1},
                        "champion": {"kills": 8},
                        "dragon": {"kills": 3},
                        "inhibitor": {"kills": 1},
                        "riftHerald": {"kills": 1},
                        "tower": {"kills": 7},
                    },
                },
                {"teamId": 200, "win": not win, "objectives": {}},
            ],
        },
    }
