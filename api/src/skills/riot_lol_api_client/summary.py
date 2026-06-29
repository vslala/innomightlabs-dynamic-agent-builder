from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

KEY_TIMELINE_EVENTS = {
    "CHAMPION_KILL",
    "ELITE_MONSTER_KILL",
    "BUILDING_KILL",
    "TURRET_PLATE_DESTROYED",
    "DRAGON_SOUL_GIVEN",
    "OBJECTIVE_BOUNTY_PRESTART",
}


def account_summary(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "puuid": _text(data.get("puuid")),
        "game_name": _text(data.get("gameName")),
        "tag_line": _text(data.get("tagLine")),
        "riot_id": _riot_id(data.get("gameName"), data.get("tagLine")),
    }


def summoner_summary(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "puuid": _text(data.get("puuid")),
        "summoner_level": data.get("summonerLevel"),
        "profile_icon_id": data.get("profileIconId"),
        "revision_date": _millis_to_iso(data.get("revisionDate")),
    }


def ranked_entries_summary(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "queue_type": entry.get("queueType"),
            "tier": entry.get("tier"),
            "rank": entry.get("rank"),
            "league_points": entry.get("leaguePoints"),
            "wins": entry.get("wins"),
            "losses": entry.get("losses"),
            "win_rate": _rate(entry.get("wins"), entry.get("losses")),
            "hot_streak": entry.get("hotStreak"),
            "veteran": entry.get("veteran"),
            "fresh_blood": entry.get("freshBlood"),
            "inactive": entry.get("inactive"),
        }
        for entry in entries
    ]


def mastery_summary(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "champion_id": item.get("championId"),
            "champion_level": item.get("championLevel"),
            "champion_points": item.get("championPoints"),
            "last_play_time": _millis_to_iso(item.get("lastPlayTime")),
            "chest_granted": item.get("chestGranted"),
            "tokens_earned": item.get("tokensEarned"),
        }
        for item in items
    ]


def match_summary(match: dict[str, Any], *, puuid: str | None = None) -> dict[str, Any]:
    info = _info(match)
    participants = _participants(info)
    player = _participant_for_puuid(participants, puuid)
    teams = info.get("teams") if isinstance(info.get("teams"), list) else []
    return {
        "match_id": _metadata(match).get("matchId"),
        "game_creation": _millis_to_iso(info.get("gameCreation")),
        "game_end": _millis_to_iso(info.get("gameEndTimestamp")),
        "game_duration_seconds": info.get("gameDuration"),
        "game_mode": info.get("gameMode"),
        "game_type": info.get("gameType"),
        "queue_id": info.get("queueId"),
        "map_id": info.get("mapId"),
        "player": participant_summary(player) if player else None,
        "teams": [team_summary(team) for team in teams],
    }


def match_detail_summary(match: dict[str, Any], *, puuid: str | None = None) -> dict[str, Any]:
    info = _info(match)
    participants = _participants(info)
    player = _participant_for_puuid(participants, puuid)
    return {
        **match_summary(match, puuid=puuid),
        "player_performance": participant_summary(player) if player else None,
        "participants": [participant_summary(participant) for participant in participants],
    }


def participant_summary(participant: dict[str, Any]) -> dict[str, Any]:
    challenges = participant.get("challenges") if isinstance(participant.get("challenges"), dict) else {}
    return {
        "puuid": participant.get("puuid"),
        "riot_id": _riot_id(participant.get("riotIdGameName"), participant.get("riotIdTagline")),
        "summoner_name": participant.get("summonerName"),
        "team_id": participant.get("teamId"),
        "team_position": participant.get("teamPosition"),
        "champion_id": participant.get("championId"),
        "champion_name": participant.get("championName"),
        "win": participant.get("win"),
        "kills": participant.get("kills"),
        "deaths": participant.get("deaths"),
        "assists": participant.get("assists"),
        "kda": _kda(participant.get("kills"), participant.get("deaths"), participant.get("assists")),
        "cs": _sum_numbers(participant.get("totalMinionsKilled"), participant.get("neutralMinionsKilled")),
        "gold_earned": participant.get("goldEarned"),
        "total_damage_to_champions": participant.get("totalDamageDealtToChampions"),
        "damage_taken": participant.get("totalDamageTaken"),
        "vision_score": participant.get("visionScore"),
        "wards_placed": participant.get("wardsPlaced"),
        "control_wards_bought": participant.get("visionWardsBoughtInGame"),
        "kill_participation": _round_float(challenges.get("killParticipation")),
    }


def team_summary(team: dict[str, Any]) -> dict[str, Any]:
    objectives = team.get("objectives") if isinstance(team.get("objectives"), dict) else {}
    return {
        "team_id": team.get("teamId"),
        "win": team.get("win"),
        "bans": [
            {"champion_id": ban.get("championId"), "pick_turn": ban.get("pickTurn")}
            for ban in team.get("bans", [])
            if isinstance(ban, dict)
        ],
        "objectives": {
            name: {
                "kills": value.get("kills"),
                "first": value.get("first"),
            }
            for name, value in objectives.items()
            if isinstance(value, dict)
        },
    }


def timeline_summary(timeline: dict[str, Any], *, max_events: int) -> dict[str, Any]:
    info = timeline.get("info") if isinstance(timeline.get("info"), dict) else {}
    frames = info.get("frames") if isinstance(info.get("frames"), list) else []
    events = [event_summary(event) for frame in frames for event in _frame_events(frame)]
    key_events = [event for event in events if event.get("type") in KEY_TIMELINE_EVENTS]
    return {
        "match_id": _metadata(timeline).get("matchId"),
        "frame_count": len(frames),
        "frame_interval_ms": info.get("frameInterval"),
        "key_events": key_events[:max_events],
        "truncated": len(key_events) > max_events,
    }


def event_summary(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "timestamp_ms": event.get("timestamp"),
        "type": event.get("type"),
        "participant_id": event.get("participantId"),
        "killer_id": event.get("killerId"),
        "victim_id": event.get("victimId"),
        "assisting_participant_ids": event.get("assistingParticipantIds"),
        "monster_type": event.get("monsterType"),
        "monster_sub_type": event.get("monsterSubType"),
        "building_type": event.get("buildingType"),
        "tower_type": event.get("towerType"),
        "team_id": event.get("teamId"),
        "lane_type": event.get("laneType"),
    }


def live_game_summary(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "game_id": data.get("gameId"),
        "game_type": data.get("gameType"),
        "game_mode": data.get("gameMode"),
        "map_id": data.get("mapId"),
        "game_length_seconds": data.get("gameLength"),
        "game_start_time": _millis_to_iso(data.get("gameStartTime")),
        "queue_id": data.get("gameQueueConfigId"),
        "participants": [
            {
                "puuid": item.get("puuid"),
                "riot_id": _riot_id(item.get("riotId"), item.get("riotIdTagline")),
                "summoner_name": item.get("summonerName"),
                "team_id": item.get("teamId"),
                "champion_id": item.get("championId"),
                "spell1_id": item.get("spell1Id"),
                "spell2_id": item.get("spell2Id"),
                "bot": item.get("bot"),
            }
            for item in data.get("participants", [])
            if isinstance(item, dict)
        ],
        "banned_champions": data.get("bannedChampions", []),
    }


def champion_rotation_summary(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "free_champion_ids": data.get("freeChampionIds", []),
        "free_champion_ids_for_new_players": data.get("freeChampionIdsForNewPlayers", []),
        "max_new_player_level": data.get("maxNewPlayerLevel"),
    }


def status_summary(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": data.get("id"),
        "name": data.get("name"),
        "maintenances": [
            _status_item(item)
            for item in data.get("maintenances", [])
            if isinstance(item, dict)
        ],
        "incidents": [
            _status_item(item)
            for item in data.get("incidents", [])
            if isinstance(item, dict)
        ],
    }


def challenges_summary(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "total_points": data.get("totalPoints"),
        "category_points": data.get("categoryPoints"),
        "preferences": data.get("preferences"),
        "challenges": [
            {
                "challenge_id": item.get("challengeId"),
                "percentile": item.get("percentile"),
                "level": item.get("level"),
                "value": item.get("value"),
                "achieved_time": _millis_to_iso(item.get("achievedTime")),
            }
            for item in data.get("challenges", [])
            if isinstance(item, dict)
        ][:20],
    }


def clash_players_summary(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "summoner_id": item.get("summonerId"),
            "team_id": item.get("teamId"),
            "position": item.get("position"),
            "role": item.get("role"),
        }
        for item in items
    ]


def clash_team_summary(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": data.get("id"),
        "tournament_id": data.get("tournamentId"),
        "name": data.get("name"),
        "icon_id": data.get("iconId"),
        "tier": data.get("tier"),
        "captain": data.get("captain"),
        "abbreviation": data.get("abbreviation"),
        "players": data.get("players", []),
    }


def _status_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id"),
        "maintenance_status": item.get("maintenance_status"),
        "incident_severity": item.get("incident_severity"),
        "titles": item.get("titles", []),
        "updates": item.get("updates", [])[:3],
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
    }


def _info(match: dict[str, Any]) -> dict[str, Any]:
    value = match.get("info")
    return value if isinstance(value, dict) else {}


def _metadata(match: dict[str, Any]) -> dict[str, Any]:
    value = match.get("metadata")
    return value if isinstance(value, dict) else {}


def _participants(info: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in info.get("participants", []) if isinstance(item, dict)]


def _participant_for_puuid(participants: list[dict[str, Any]], puuid: str | None) -> dict[str, Any] | None:
    if not puuid:
        return None
    return next((item for item in participants if item.get("puuid") == puuid), None)


def _frame_events(frame: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(frame, dict):
        return []
    return [event for event in frame.get("events", []) if isinstance(event, dict)]


def _riot_id(game_name: Any, tag_line: Any) -> str | None:
    game = _text(game_name)
    tag = _text(tag_line)
    if not game or not tag:
        return None
    return f"{game}#{tag}"


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None


def _millis_to_iso(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return None


def _kda(kills: Any, deaths: Any, assists: Any) -> float | None:
    kills_int = _int_or_none(kills)
    deaths_int = _int_or_none(deaths)
    assists_int = _int_or_none(assists)
    if kills_int is None or deaths_int is None or assists_int is None:
        return None
    return round((kills_int + assists_int) / max(1, deaths_int), 2)


def _rate(wins: Any, losses: Any) -> float | None:
    wins_int = _int_or_none(wins)
    losses_int = _int_or_none(losses)
    if wins_int is None or losses_int is None:
        return None
    total = wins_int + losses_int
    return round(wins_int / total, 3) if total else None


def _sum_numbers(*values: Any) -> int:
    return sum(value for value in (_int_or_none(item) for item in values) if value is not None)


def _round_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), 3)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
