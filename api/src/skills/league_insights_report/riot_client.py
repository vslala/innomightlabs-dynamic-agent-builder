from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx


class RiotApiError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class RiotAccount:
    puuid: str
    game_name: str
    tag_line: str


class RiotClient:
    def __init__(
        self,
        api_key: str,
        *,
        http_client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 20.0,
    ):
        self.api_key = api_key
        self.http_client = http_client
        self.timeout_seconds = timeout_seconds

    async def get_account_by_riot_id(
        self,
        *,
        routing_region: str,
        game_name: str,
        tag_line: str,
    ) -> RiotAccount:
        data = await self._get_json(
            routing_region=routing_region,
            path=(
                "/riot/account/v1/accounts/by-riot-id/"
                f"{_path_segment(game_name)}/{_path_segment(tag_line)}"
            ),
        )
        return RiotAccount(
            puuid=str(data.get("puuid") or ""),
            game_name=str(data.get("gameName") or game_name),
            tag_line=str(data.get("tagLine") or tag_line),
        )

    async def get_match_ids(
        self,
        *,
        routing_region: str,
        puuid: str,
        count: int,
        queue: int | None = None,
    ) -> list[str]:
        params: dict[str, int] = {"start": 0, "count": count}
        if queue is not None:
            params["queue"] = queue
        data = await self._get_json(
            routing_region=routing_region,
            path=f"/lol/match/v5/matches/by-puuid/{_path_segment(puuid)}/ids",
            params=params,
        )
        if not isinstance(data, list):
            raise RiotApiError("Riot returned an unexpected match id response")
        return [str(item) for item in data if str(item)]

    async def get_match(self, *, routing_region: str, match_id: str) -> dict[str, Any]:
        data = await self._get_json(
            routing_region=routing_region,
            path=f"/lol/match/v5/matches/{_path_segment(match_id)}",
        )
        if not isinstance(data, dict):
            raise RiotApiError("Riot returned an unexpected match response")
        return data

    async def _get_json(
        self,
        *,
        routing_region: str,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        url = f"https://{routing_region}.api.riotgames.com{path}"
        if self.http_client:
            response = await self.http_client.get(url, params=params, headers=self._headers())
            return self._parse_response(response)

        async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True) as client:
            response = await client.get(url, params=params, headers=self._headers())
            return self._parse_response(response)

    def _headers(self) -> dict[str, str]:
        return {"X-Riot-Token": self.api_key}

    def _parse_response(self, response: httpx.Response) -> Any:
        if response.status_code >= 400:
            raise RiotApiError(_riot_error_message(response), status_code=response.status_code)
        try:
            return response.json()
        except ValueError as exc:
            raise RiotApiError("Riot returned an invalid JSON response") from exc


def _riot_error_message(response: httpx.Response) -> str:
    status = response.status_code
    if status in {401, 403}:
        return "Riot API rejected the configured API key. Check that the key is valid and not expired."
    if status == 404:
        return "Riot could not find the requested player or match."
    if status == 429:
        return "Riot API rate limit was reached. Try again later or reduce the match count."
    if status >= 500:
        return "Riot API is temporarily unavailable. Try again later."
    return f"Riot API request failed with HTTP {status}."


def _path_segment(value: str) -> str:
    return quote(value, safe="")
