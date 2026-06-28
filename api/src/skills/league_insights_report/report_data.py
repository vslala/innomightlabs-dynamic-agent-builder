from __future__ import annotations

from collections import Counter
from typing import Any

from src.skills.league_insights_report.models import ReportScope
from src.skills.league_insights_report.riot_client import RiotAccount


def build_report_payload(
    *,
    account: RiotAccount,
    matches: list[dict[str, Any]],
    report_scope: ReportScope,
    routing_region: str,
) -> dict[str, Any]:
    summaries = [_match_summary(match, account.puuid) for match in matches]
    payload: dict[str, Any] = {
        "game": "league_of_legends",
        "riot_id": f"{account.game_name}#{account.tag_line}",
        "puuid": account.puuid,
        "routing_region": routing_region,
        "report_scope": report_scope,
        "matches": summaries,
    }
    if report_scope == "multi_match":
        payload["trends"] = _trend_summary(summaries)
    return payload


def _match_summary(match: dict[str, Any], puuid: str) -> dict[str, Any]:
    metadata = _dict(match.get("metadata"))
    info = _dict(match.get("info"))
    participants = [_dict(item) for item in info.get("participants", []) if isinstance(item, dict)]
    participant = _target_participant(participants, puuid)
    teams = [_dict(item) for item in info.get("teams", []) if isinstance(item, dict)]
    team = _team_for_participant(teams, participant)
    team_id = int(participant.get("teamId") or 0)

    kills = int(participant.get("kills") or 0)
    deaths = int(participant.get("deaths") or 0)
    assists = int(participant.get("assists") or 0)
    team_kills = sum(int(item.get("kills") or 0) for item in participants if int(item.get("teamId") or 0) == team_id)
    total_damage = int(participant.get("totalDamageDealtToChampions") or 0)
    team_damage = sum(
        int(item.get("totalDamageDealtToChampions") or 0)
        for item in participants
        if int(item.get("teamId") or 0) == team_id
    )
    gold = int(participant.get("goldEarned") or 0)
    team_gold = sum(int(item.get("goldEarned") or 0) for item in participants if int(item.get("teamId") or 0) == team_id)

    return {
        "match_id": str(metadata.get("matchId") or ""),
        "queue_id": int(info.get("queueId") or 0),
        "game_creation": int(info.get("gameCreation") or 0),
        "game_duration_seconds": int(info.get("gameDuration") or 0),
        "game_mode": str(info.get("gameMode") or ""),
        "win": bool(participant.get("win")),
        "champion": str(participant.get("championName") or ""),
        "role": str(participant.get("teamPosition") or participant.get("individualPosition") or ""),
        "summoner_name": str(participant.get("summonerName") or participant.get("riotIdGameName") or ""),
        "kills": kills,
        "deaths": deaths,
        "assists": assists,
        "kda": round((kills + assists) / max(1, deaths), 2),
        "kill_participation": _ratio(kills + assists, team_kills),
        "total_damage_to_champions": total_damage,
        "damage_share": _ratio(total_damage, team_damage),
        "gold_earned": gold,
        "gold_share": _ratio(gold, team_gold),
        "cs": int(participant.get("totalMinionsKilled") or 0) + int(participant.get("neutralMinionsKilled") or 0),
        "vision_score": int(participant.get("visionScore") or 0),
        "wards_placed": int(participant.get("wardsPlaced") or 0),
        "wards_killed": int(participant.get("wardsKilled") or 0),
        "summoner_level": int(participant.get("summonerLevel") or 0),
        "objectives": _objective_summary(team),
        "team_result": {"team_id": team_id, "win": bool(team.get("win"))},
    }


def _trend_summary(matches: list[dict[str, Any]]) -> dict[str, Any]:
    count = len(matches)
    wins = sum(1 for item in matches if item["win"])
    champions = Counter(str(item.get("champion") or "Unknown") for item in matches)
    roles = Counter(str(item.get("role") or "Unknown") for item in matches)
    return {
        "matches_analyzed": count,
        "wins": wins,
        "losses": count - wins,
        "win_rate": _ratio(wins, count),
        "champions": [{"champion": name, "games": games} for name, games in champions.most_common()],
        "roles": [{"role": name, "games": games} for name, games in roles.most_common()],
        "average_kda": _average(matches, "kda"),
        "average_deaths": _average(matches, "deaths"),
        "average_kill_participation": _average(matches, "kill_participation"),
        "average_damage_share": _average(matches, "damage_share"),
        "average_gold_share": _average(matches, "gold_share"),
        "average_cs": _average(matches, "cs"),
        "average_vision_score": _average(matches, "vision_score"),
    }


def _target_participant(participants: list[dict[str, Any]], puuid: str) -> dict[str, Any]:
    for participant in participants:
        if participant.get("puuid") == puuid:
            return participant
    raise ValueError("Requested player was not found in Riot match data")


def _team_for_participant(teams: list[dict[str, Any]], participant: dict[str, Any]) -> dict[str, Any]:
    team_id = int(participant.get("teamId") or 0)
    for team in teams:
        if int(team.get("teamId") or 0) == team_id:
            return team
    return {}


def _objective_summary(team: dict[str, Any]) -> dict[str, int]:
    objectives = _dict(team.get("objectives"))
    return {
        name: int(_dict(objectives.get(name)).get("kills") or 0)
        for name in ["baron", "champion", "dragon", "inhibitor", "riftHerald", "tower"]
    }


def _average(items: list[dict[str, Any]], key: str) -> float:
    if not items:
        return 0.0
    return round(sum(float(item.get(key) or 0) for item in items) / len(items), 2)


def _ratio(numerator: int | float, denominator: int | float) -> float:
    if not denominator:
        return 0.0
    return round(float(numerator) / float(denominator), 3)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
