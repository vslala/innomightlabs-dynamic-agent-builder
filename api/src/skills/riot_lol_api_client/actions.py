from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from src.skills.riot_lol_api_client.client import RiotLolApiError, RiotLolClient, path_segment, riot_error_payload
from src.skills.riot_lol_api_client.models import (
    ChallengesRequest,
    ChampionMasteryRequest,
    ClashRequest,
    MatchRequest,
    PlatformRequest,
    RecentMatchesRequest,
    RiotLolConfig,
    TimelineRequest,
    PlayerLookup,
)
from src.skills.riot_lol_api_client.summary import (
    account_summary,
    champion_rotation_summary,
    challenges_summary,
    clash_players_summary,
    clash_team_summary,
    live_game_summary,
    mastery_summary,
    match_detail_summary,
    match_summary,
    ranked_entries_summary,
    status_summary,
    summoner_summary,
    timeline_summary,
)


async def lookup_player(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    del context
    request = _validate(PlayerLookup, arguments, "lookup_player")
    settings = _config(config)
    client = _client(settings)
    routing_region = request.routing_region or settings.default_routing_region
    platform_region = request.platform_region or settings.default_platform_region
    try:
        account = await _resolve_account(client, request, routing_region)
        summoner = await _get_summoner(client, platform_region, account["puuid"])
        return {
            "ok": True,
            "routing_region": routing_region,
            "platform_region": platform_region,
            "account": account_summary(account),
            "summoner": summoner_summary(summoner),
        }
    except RiotLolApiError as exc:
        return riot_error_payload(exc)


async def get_recent_match_summaries(
    arguments: dict[str, Any],
    config: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    del context
    request = _validate(RecentMatchesRequest, arguments, "get_recent_match_summaries")
    settings = _config(config)
    client = _client(settings)
    routing_region = request.routing_region or settings.default_routing_region
    try:
        account = await _resolve_account(client, request, routing_region)
        match_ids = await _get_match_ids(
            client,
            routing_region,
            account["puuid"],
            count=request.count,
            queue=request.queue,
        )
        matches = [await _get_match(client, routing_region, match_id) for match_id in match_ids]
        return {
            "ok": True,
            "routing_region": routing_region,
            "account": account_summary(account),
            "count": len(matches),
            "matches": [match_summary(match, puuid=account["puuid"]) for match in matches],
        }
    except RiotLolApiError as exc:
        return riot_error_payload(exc)


async def get_match_details(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    del context
    request = _validate(MatchRequest, arguments, "get_match_details")
    settings = _config(config)
    client = _client(settings)
    routing_region = request.routing_region or settings.default_routing_region
    try:
        puuid = await _resolve_optional_puuid(client, request, routing_region)
        match = await _get_match(client, routing_region, request.match_id)
        return {
            "ok": True,
            "routing_region": routing_region,
            "match": match_detail_summary(match, puuid=puuid),
        }
    except RiotLolApiError as exc:
        return riot_error_payload(exc)


async def get_match_timeline(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    del context
    request = _validate(TimelineRequest, arguments, "get_match_timeline")
    settings = _config(config)
    client = _client(settings)
    routing_region = request.routing_region or settings.default_routing_region
    try:
        data = await client.get_routing_json(
            routing_region,
            f"/lol/match/v5/matches/{path_segment(request.match_id)}/timeline",
        )
        return {
            "ok": True,
            "routing_region": routing_region,
            "timeline": timeline_summary(data, max_events=request.max_events),
        }
    except RiotLolApiError as exc:
        return riot_error_payload(exc)


async def get_ranked_profile(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    del context
    request = _validate(PlayerLookup, arguments, "get_ranked_profile")
    settings = _config(config)
    client = _client(settings)
    routing_region = request.routing_region or settings.default_routing_region
    platform_region = request.platform_region or settings.default_platform_region
    try:
        account = await _resolve_account(client, request, routing_region)
        entries = await client.get_platform_json(
            platform_region,
            f"/lol/league/v4/entries/by-puuid/{path_segment(account['puuid'])}",
        )
        return {
            "ok": True,
            "platform_region": platform_region,
            "account": account_summary(account),
            "ranked_entries": ranked_entries_summary(_list(entries)),
        }
    except RiotLolApiError as exc:
        return riot_error_payload(exc)


async def get_champion_mastery(
    arguments: dict[str, Any],
    config: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    del context
    request = _validate(ChampionMasteryRequest, arguments, "get_champion_mastery")
    settings = _config(config)
    client = _client(settings)
    routing_region = request.routing_region or settings.default_routing_region
    platform_region = request.platform_region or settings.default_platform_region
    try:
        account = await _resolve_account(client, request, routing_region)
        mastery = await _get_mastery(client, platform_region, account["puuid"], request)
        return {
            "ok": True,
            "platform_region": platform_region,
            "account": account_summary(account),
            "champion_mastery": mastery_summary(_list_or_single(mastery)),
        }
    except RiotLolApiError as exc:
        return riot_error_payload(exc)


async def get_live_game(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    del context
    request = _validate(PlayerLookup, arguments, "get_live_game")
    settings = _config(config)
    client = _client(settings)
    routing_region = request.routing_region or settings.default_routing_region
    platform_region = request.platform_region or settings.default_platform_region
    try:
        account = await _resolve_account(client, request, routing_region)
        data = await client.get_platform_json(
            platform_region,
            f"/lol/spectator/v5/active-games/by-summoner/{path_segment(account['puuid'])}",
        )
        return {
            "ok": True,
            "platform_region": platform_region,
            "account": account_summary(account),
            "live_game": live_game_summary(data),
        }
    except RiotLolApiError as exc:
        return riot_error_payload(exc)


async def get_champion_rotations(
    arguments: dict[str, Any],
    config: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    del context
    request = _validate(PlatformRequest, arguments, "get_champion_rotations")
    settings = _config(config)
    client = _client(settings)
    platform_region = request.platform_region or settings.default_platform_region
    try:
        data = await client.get_platform_json(platform_region, "/lol/platform/v3/champion-rotations")
        return {
            "ok": True,
            "platform_region": platform_region,
            "champion_rotations": champion_rotation_summary(data),
        }
    except RiotLolApiError as exc:
        return riot_error_payload(exc)


async def get_lol_status(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    del context
    request = _validate(PlatformRequest, arguments, "get_lol_status")
    settings = _config(config)
    client = _client(settings)
    platform_region = request.platform_region or settings.default_platform_region
    try:
        data = await client.get_platform_json(platform_region, "/lol/status/v4/platform-data")
        return {
            "ok": True,
            "platform_region": platform_region,
            "status": status_summary(data),
        }
    except RiotLolApiError as exc:
        return riot_error_payload(exc)


async def get_challenges(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    del context
    request = _validate(ChallengesRequest, arguments, "get_challenges")
    settings = _config(config)
    client = _client(settings)
    routing_region = request.routing_region or settings.default_routing_region
    platform_region = request.platform_region or settings.default_platform_region
    try:
        account = await _resolve_account(client, request, routing_region)
        data = await client.get_platform_json(
            platform_region,
            f"/lol/challenges/v1/player-data/{path_segment(account['puuid'])}",
        )
        response: dict[str, Any] = {
            "ok": True,
            "platform_region": platform_region,
            "account": account_summary(account),
            "challenges": challenges_summary(data),
        }
        if request.include_config:
            response["challenge_config"] = await client.get_platform_json(platform_region, "/lol/challenges/v1/challenges/config")
        return response
    except RiotLolApiError as exc:
        return riot_error_payload(exc)


async def get_clash(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    del context
    request = _validate(ClashRequest, arguments, "get_clash")
    settings = _config(config)
    client = _client(settings)
    routing_region = request.routing_region or settings.default_routing_region
    platform_region = request.platform_region or settings.default_platform_region
    try:
        account = await _resolve_account(client, request, routing_region)
        players = await client.get_platform_json(
            platform_region,
            f"/lol/clash/v1/players/by-puuid/{path_segment(account['puuid'])}",
        )
        teams = [
            clash_team_summary(await client.get_platform_json(platform_region, f"/lol/clash/v1/teams/{path_segment(player['teamId'])}"))
            for player in _list(players)
            if player.get("teamId")
        ]
        return {
            "ok": True,
            "platform_region": platform_region,
            "account": account_summary(account),
            "players": clash_players_summary(_list(players)),
            "teams": teams,
        }
    except RiotLolApiError as exc:
        return riot_error_payload(exc)


def _config(config: dict[str, Any]) -> RiotLolConfig:
    try:
        return RiotLolConfig.model_validate(config)
    except ValidationError as exc:
        raise ValueError(f"Invalid Riot LOL API Client configuration: {exc}") from exc


def _validate(model: type[Any], arguments: dict[str, Any], action_name: str) -> Any:
    try:
        return model.model_validate(arguments)
    except ValidationError as exc:
        raise ValueError(f"Invalid Riot LOL API Client {action_name} arguments: {exc}") from exc


def _client(config: RiotLolConfig) -> RiotLolClient:
    return RiotLolClient(config.riot_api_key)


async def _resolve_account(client: RiotLolClient, request: PlayerLookup, routing_region: str) -> dict[str, Any]:
    if request.puuid:
        return {"puuid": request.puuid, "gameName": request.game_name, "tagLine": request.tag_line}
    return await client.get_routing_json(
        routing_region,
        (
            "/riot/account/v1/accounts/by-riot-id/"
            f"{path_segment(request.game_name or '')}/{path_segment(request.tag_line or '')}"
        ),
    )


async def _resolve_optional_puuid(client: RiotLolClient, request: MatchRequest, routing_region: str) -> str | None:
    if request.puuid:
        return request.puuid
    if request.game_name and request.tag_line:
        account = await client.get_routing_json(
            routing_region,
            (
                "/riot/account/v1/accounts/by-riot-id/"
                f"{path_segment(request.game_name)}/{path_segment(request.tag_line)}"
            ),
        )
        return str(account.get("puuid") or "")
    return None


async def _get_summoner(client: RiotLolClient, platform_region: str, puuid: str) -> dict[str, Any]:
    return await client.get_platform_json(
        platform_region,
        f"/lol/summoner/v4/summoners/by-puuid/{path_segment(puuid)}",
    )


async def _get_match_ids(
    client: RiotLolClient,
    routing_region: str,
    puuid: str,
    *,
    count: int,
    queue: int | None,
) -> list[str]:
    params = {"start": 0, "count": count}
    if queue is not None:
        params["queue"] = queue
    data = await client.get_routing_json(
        routing_region,
        f"/lol/match/v5/matches/by-puuid/{path_segment(puuid)}/ids",
        params=params,
    )
    return [str(item) for item in _string_list(data)]


async def _get_match(client: RiotLolClient, routing_region: str, match_id: str) -> dict[str, Any]:
    return await client.get_routing_json(
        routing_region,
        f"/lol/match/v5/matches/{path_segment(match_id)}",
    )


async def _get_mastery(
    client: RiotLolClient,
    platform_region: str,
    puuid: str,
    request: ChampionMasteryRequest,
) -> Any:
    if request.champion_id is not None:
        return await client.get_platform_json(
            platform_region,
            (
                f"/lol/champion-mastery/v4/champion-masteries/by-puuid/{path_segment(puuid)}"
                f"/by-champion/{request.champion_id}"
            ),
        )
    return await client.get_platform_json(
        platform_region,
        f"/lol/champion-mastery/v4/champion-masteries/by-puuid/{path_segment(puuid)}/top",
        params={"count": request.limit},
    )


def _list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


def _list_or_single(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        return [value]
    return _list(value)
