"""Raw googleAds:mutate, for any change the curated actions do not cover.

Off unless the installer allows it, and it runs through the same preview/apply,
read-only, and budget-cap rules as every other write.
"""

from __future__ import annotations

from typing import Any

from src.skills.google_ads.models import MutateRequest
from src.skills.google_ads.operations import budget_amounts
from src.skills.google_ads.session import AdsSession, parse


async def mutate(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    request = parse(MutateRequest, arguments)
    ads = await AdsSession.open(config, context, writes=True)
    if not ads.config.allow_advanced_mutate:
        raise ValueError(
            "Raw mutate is turned off for this Google Ads skill. Use a curated action, or ask the user to "
            "allow raw mutate operations in the skill settings."
        )
    for amount in budget_amounts(request.operations):
        ads.config.check_daily_budget(amount)

    customer_id = ads.customer(request.customer_id)
    summary = [_describe(operation) for operation in request.operations]
    return await ads.change(request, customer_id, request.operations, summary)


def _describe(operation: dict[str, Any]) -> str:
    """'campaignOperation.update customers/1/campaigns/2 (status)' - enough for a human to check."""
    for kind, body in operation.items():
        if not isinstance(body, dict):
            return f"{kind}: {body}"
        for verb in ("create", "update", "remove"):
            if verb not in body:
                continue
            target = body[verb] if verb == "remove" else (body[verb] or {}).get("resourceName", "(new)")
            mask = f" ({body['updateMask']})" if body.get("updateMask") else ""
            return f"{kind}.{verb} {target}{mask}"
    return str(operation)[:200]
