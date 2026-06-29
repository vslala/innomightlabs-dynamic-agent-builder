from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx


class RiotLolApiError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class RiotLolClient:
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

    async def get_routing_json(
        self,
        routing_region: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> Any:
        return await self._get_json(f"https://{routing_region}.api.riotgames.com{path}", params=params)

    async def get_platform_json(
        self,
        platform_region: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> Any:
        return await self._get_json(f"https://{platform_region}.api.riotgames.com{path}", params=params)

    async def _get_json(self, url: str, *, params: dict[str, Any] | None = None) -> Any:
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
            raise RiotLolApiError(_riot_error_message(response), status_code=response.status_code)
        try:
            return response.json()
        except ValueError as exc:
            raise RiotLolApiError("Riot returned an invalid JSON response") from exc


def path_segment(value: str) -> str:
    return quote(value, safe="")


def riot_error_payload(error: RiotLolApiError) -> dict[str, Any]:
    return {
        "ok": False,
        "status_code": error.status_code,
        "error": str(error),
    }


def _riot_error_message(response: httpx.Response) -> str:
    status = response.status_code
    if status in {401, 403}:
        return "Riot API rejected the configured API key. Check that the key is valid and not expired."
    if status == 404:
        return "Riot could not find the requested player, match, or resource."
    if status == 429:
        return "Riot API rate limit was reached. Try again later or request fewer matches."
    if status >= 500:
        return "Riot API is temporarily unavailable. Try again later."
    return f"Riot API request failed with HTTP {status}."
