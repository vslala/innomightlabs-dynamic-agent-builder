"""The Google Ads REST API, authenticated by the owner's OAuth connection alone.

REST keeps the JSON the agent writes as the JSON Google reads, so the generic
`mutate` action is a pass-through and no SDK or protobuf layer is needed.
"""

from __future__ import annotations

import re
from typing import Any, Optional

import httpx
from pydantic import ValidationError

from src.config import settings
from src.crypto import decrypt
from src.settings.models import ProviderSettings
from src.settings.repository import ProviderSettingsRepository
from src.skills.google_ads.models import MICROS, GoogleAdsConfig, GoogleAdsCredentials
from src.skills.google_ads.oauth import refresh_access_token, save_credentials

GOOGLE_ADS_PROVIDER_NAME = "GoogleAds"
REQUEST_TIMEOUT_SECONDS = 60.0
MAX_ERRORS_REPORTED = 3

#: Metrics Google reports in micros whose names do not end in "Micros".
MICROS_METRICS = {
    "averageCpc",
    "averageCpm",
    "averageCost",
    "costPerConversion",
    "costPerAllConversions",
}


class GoogleAdsError(RuntimeError):
    pass


def _http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS)


class GoogleAdsClient:
    def __init__(
        self,
        *,
        credentials: GoogleAdsCredentials,
        provider_settings: Optional[ProviderSettings],
        repo: Optional[ProviderSettingsRepository],
        login_customer_id: Optional[str],
    ):
        self._credentials = credentials
        self._provider_settings = provider_settings
        self._repo = repo
        self._login_customer_id = login_customer_id

    @classmethod
    async def connect(cls, config: GoogleAdsConfig, context: dict[str, Any]) -> "GoogleAdsClient":
        owner_email = str(context.get("owner_email") or "").strip()
        if not owner_email:
            raise ValueError("Missing skill runtime owner context")

        repo = ProviderSettingsRepository()
        provider_settings = repo.find_by_provider(owner_email, GOOGLE_ADS_PROVIDER_NAME)
        if not provider_settings:
            raise ValueError("Google Ads is not connected for the agent owner. Connect it from the Connectors page.")
        try:
            credentials = GoogleAdsCredentials.model_validate_json(decrypt(provider_settings.encrypted_credentials))
        except (ValidationError, Exception) as exc:
            raise GoogleAdsError("The stored Google Ads credentials are unreadable. Reconnect Google Ads.") from exc

        client = cls(
            credentials=credentials,
            provider_settings=provider_settings,
            repo=repo,
            login_customer_id=config.login_customer_id,
        )
        if credentials.refresh_token and credentials.is_expiring_soon():
            await client._refresh()
        return client

    # --- endpoints ------------------------------------------------------------------------------

    async def search(self, customer_id: str, query: str, *, login_customer_id: Optional[str] = None) -> list[dict[str, Any]]:
        payload = await self._request(
            "POST",
            f"customers/{customer_id}/googleAds:search",
            {"query": query},
            login_customer_id=login_customer_id,
        )
        return list(payload.get("results") or [])

    async def mutate(self, customer_id: str, operations: list[dict[str, Any]], *, validate_only: bool) -> dict[str, Any]:
        return await self._request(
            "POST",
            f"customers/{customer_id}/googleAds:mutate",
            {"mutateOperations": operations, "partialFailure": False, "validateOnly": validate_only},
        )

    async def list_accessible_customers(self) -> list[str]:
        payload = await self._request("GET", "customers:listAccessibleCustomers", None, login_customer_id="")
        return [name.split("/")[-1] for name in payload.get("resourceNames") or []]

    async def search_fields(self, query: str, page_size: int) -> list[dict[str, Any]]:
        payload = await self._request("POST", "googleAdsFields:search", {"query": query, "pageSize": page_size})
        return list(payload.get("results") or [])

    async def generate_keyword_ideas(self, customer_id: str, body: dict[str, Any]) -> list[dict[str, Any]]:
        payload = await self._request("POST", f"customers/{customer_id}:generateKeywordIdeas", body)
        return list(payload.get("results") or [])

    async def recommendations(self, customer_id: str, verb: str, resource_names: list[str]) -> dict[str, Any]:
        return await self._request(
            "POST",
            f"customers/{customer_id}/recommendations:{verb}",
            {"operations": [{"resourceName": name} for name in resource_names], "partialFailure": False},
        )

    # --- transport ------------------------------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        body: Optional[dict[str, Any]],
        *,
        login_customer_id: Optional[str] = None,
    ) -> dict[str, Any]:
        url = f"https://googleads.googleapis.com/{settings.google_ads_api_version}/{path}"
        response = await self._send(method, url, body, login_customer_id)
        if response.status_code == 401 and self._credentials.refresh_token:
            await self._refresh()
            response = await self._send(method, url, body, login_customer_id)

        if not response.is_success:
            raise GoogleAdsError(_failure_message(response))
        payload = response.json() if response.content else {}
        return payload if isinstance(payload, dict) else {}

    async def _send(
        self, method: str, url: str, body: Optional[dict[str, Any]], login_customer_id: Optional[str]
    ) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self._credentials.access_token}", "Accept": "application/json"}
        # An empty string means "send no login-customer-id" (calls that are not scoped to an account).
        login = self._login_customer_id if login_customer_id is None else login_customer_id
        if login:
            headers["login-customer-id"] = login
        async with _http_client() as client:
            return await client.request(method, url, json=body, headers=headers)

    async def _refresh(self) -> None:
        if not self._credentials.refresh_token:
            raise GoogleAdsError("Google Ads access expired and there is no refresh token. Reconnect Google Ads.")
        tokens = await refresh_access_token(self._credentials.refresh_token)
        self._credentials = self._credentials.with_token_response(tokens)
        if self._provider_settings and self._repo:
            self._provider_settings = save_credentials(self._provider_settings, self._repo, self._credentials)


def _failure_message(response: httpx.Response) -> str:
    """Google's error, cut to the first few GoogleAdsFailure entries the agent can act on."""
    try:
        error = response.json().get("error") or {}
    except Exception:
        return f"Google Ads API error {response.status_code}: {response.text[:300]}"

    problems: list[str] = []
    for detail in error.get("details") or []:
        for failure in detail.get("errors") or []:
            code = ".".join(f"{kind}={value}" for kind, value in (failure.get("errorCode") or {}).items())
            path = ".".join(
                element.get("fieldName", "") + (f"[{element['index']}]" if "index" in element else "")
                for element in (failure.get("location") or {}).get("fieldPathElements") or []
            )
            problems.append(" ".join(part for part in [code, f"at {path}" if path else "", "-", failure.get("message", "")] if part))
    summary = "; ".join(problems[:MAX_ERRORS_REPORTED]) or error.get("message") or response.text[:300]
    return f"Google Ads API error {response.status_code} ({error.get('status', 'UNKNOWN')}): {summary}"


# --- results -------------------------------------------------------------------------------------


def compact(row: dict[str, Any], *, keep_resource_names: bool = False) -> dict[str, Any]:
    """Flatten a result row to snake_case dotted keys, with money in currency units.

    Rows cost context on every turn they are shown, so resource names (the ids are
    already there) and micros go.
    """
    flat: dict[str, Any] = {}

    def walk(prefix: str, value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key == "resourceName" and not keep_resource_names and prefix:
                    continue
                walk(f"{prefix}.{key}" if prefix else key, child)
            return
        leaf = prefix.rsplit(".", 1)[-1]
        name = prefix
        if leaf.endswith("Micros") or leaf in MICROS_METRICS:
            value = round(float(value) / MICROS, 2) if value not in (None, "") else value
            name = prefix[: -len("Micros")] if leaf.endswith("Micros") else prefix
        elif isinstance(value, str) and value.lstrip("-").isdigit() and not leaf.endswith("Id") and leaf != "id":
            # int64 arrives as a string in JSON; counts read better as numbers. Ids stay strings.
            value = int(value)
        flat[_snake(name)] = value

    walk("", row)
    return flat


def _snake(name: str) -> str:
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name).lower()
