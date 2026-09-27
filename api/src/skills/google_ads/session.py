"""One Google Ads action's view of the account: install limits, the API, and how writes happen."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import partial
from typing import Any, Optional

from pydantic import BaseModel, ValidationError

from src.skills.google_ads import confirmation
from src.skills.google_ads.client import GoogleAdsClient, compact
from src.skills.google_ads.models import GoogleAdsConfig, WriteRequest

#: Sends a change; the flag is validate_only.
Send = Callable[[bool], Awaitable[dict[str, Any]]]


def parse(model: type[BaseModel], arguments: dict[str, Any]) -> Any:
    # Automation action forms send "" for every field left blank; blank means "not given".
    given = {key: value for key, value in arguments.items() if value != ""}
    try:
        return model.model_validate(given)
    except ValidationError as exc:
        raise ValueError(f"Invalid Google Ads arguments: {exc}") from exc


@dataclass
class AdsSession:
    config: GoogleAdsConfig
    client: GoogleAdsClient
    context: dict[str, Any]

    @classmethod
    async def open(cls, config: dict[str, Any], context: dict[str, Any], *, writes: bool = False) -> "AdsSession":
        ads_config = parse(GoogleAdsConfig, config)
        if writes:
            # Before touching Google: a read-only install fails fast, with no network call.
            ads_config.require_writes()
        return cls(config=ads_config, client=await GoogleAdsClient.connect(ads_config, context), context=context)

    def customer(self, requested: Optional[str]) -> str:
        return self.config.customer(requested)

    async def rows(self, customer_id: str, query: str, **options: Any) -> list[dict[str, Any]]:
        return [compact(row, **options) for row in await self.client.search(customer_id, query)]

    async def change(
        self,
        request: WriteRequest,
        customer_id: str,
        operations: list[dict[str, Any]],
        summary: list[str],
        *,
        send: Optional[Send] = None,
        validates: bool = True,
    ) -> dict[str, Any]:
        """Preview a change, or apply one that was previewed.

        Agents preview first and get a token over the exact operations; apply
        re-checks the token against the operations rebuilt from the same
        arguments, so what runs is what the user was shown. Automation runs apply
        directly: the user authored the node, and nobody is there to confirm.
        """
        sender: Send = send or partial(self._mutate, customer_id, operations)
        in_automation = bool(self.context.get("automation_run_id"))

        if in_automation or request.mode == "apply":
            if not in_automation:
                confirmation.verify(request.confirmation_token, self._token_scope(), customer_id, operations)
            response = await sender(False)
            return {"status": "applied", "customer_id": customer_id, "summary": summary, "results": _results(response)}

        if validates:
            await sender(True)
        return {
            "status": "preview",
            "customer_id": customer_id,
            "summary": summary,
            "operation_count": len(operations),
            "confirmation_token": confirmation.sign(self._token_scope(), customer_id, operations),
            "next_step": (
                "Show this summary to the user and ask them to confirm. Only after they agree, call the same "
                "action with the same arguments plus mode=apply and this confirmation_token."
            ),
        }

    async def _mutate(self, customer_id: str, operations: list[dict[str, Any]], validate_only: bool) -> dict[str, Any]:
        return await self.client.mutate(customer_id, operations, validate_only=validate_only)

    def _token_scope(self) -> str:
        return str(self.context.get("installed_skill_id") or self.context.get("skill_id") or "google_ads")


def _results(response: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for item in response.get("mutateOperationResponses") or response.get("results") or []:
        if "resourceName" in item:
            names.append(item["resourceName"])
            continue
        for result in item.values():
            if isinstance(result, dict) and result.get("resourceName"):
                names.append(result["resourceName"])
    return names
