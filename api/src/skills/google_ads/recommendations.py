"""Google's own optimisation recommendations: list, apply, dismiss."""

from __future__ import annotations

from functools import partial
from typing import Any

from src.skills.google_ads.models import ListRecommendationsRequest, RecommendationsRequest, id_of
from src.skills.google_ads.session import AdsSession, parse


async def list_recommendations(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    request = parse(ListRecommendationsRequest, arguments)
    ads = await AdsSession.open(config, context)
    customer_id = ads.customer(request.customer_id)
    where = []
    if request.types:
        types = ", ".join(f"'{kind.strip().upper()}'" for kind in request.types if kind.strip().replace("_", "").isalnum())
        where.append(f"recommendation.type IN ({types})")
    if request.campaign_id:
        where.append(f"recommendation.campaign = 'customers/{customer_id}/campaigns/{id_of(request.campaign_id, 'campaign_id')}'")
    gaql = (
        "SELECT recommendation.resource_name, recommendation.type, recommendation.campaign, "
        "recommendation.impact.base_metrics.clicks, recommendation.impact.potential_metrics.clicks, "
        "recommendation.impact.base_metrics.cost_micros, recommendation.impact.potential_metrics.cost_micros "
        "FROM recommendation"
        + (f" WHERE {' AND '.join(where)}" if where else "")
        + f" LIMIT {max(1, min(100, request.limit))}"
    )
    # Resource names are how apply/dismiss refer to a recommendation, so they stay.
    rows = await ads.rows(customer_id, gaql, keep_resource_names=True)
    return {"customer_id": customer_id, "row_count": len(rows), "recommendations": rows}


async def apply_recommendations(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    return await _decide(arguments, config, context, "apply")


async def dismiss_recommendations(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    return await _decide(arguments, config, context, "dismiss")


async def _decide(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any], verb: str) -> dict[str, Any]:
    request = parse(RecommendationsRequest, arguments)
    ads = await AdsSession.open(config, context, writes=True)
    customer_id = ads.customer(request.customer_id)
    for name in request.resource_names:
        if not name.startswith(f"customers/{customer_id}/recommendations/"):
            raise ValueError(f"'{name}' is not a recommendation of account {customer_id}")

    # The token signs what will be sent; there is one "operation" per recommendation.
    batch = [{"recommendation": {verb: name}} for name in request.resource_names]
    summary = [f"{verb.capitalize()} recommendation {name}" for name in request.resource_names]
    if verb == "apply":
        summary.append("Applying a recommendation changes the account as Google describes it (budgets, bids, keywords, or ads).")
    return await ads.change(
        request,
        customer_id,
        batch,
        summary,
        send=partial(_send, ads, customer_id, verb, request.resource_names),
        # The recommendations endpoints have no validate-only mode.
        validates=False,
    )


async def _send(ads: AdsSession, customer_id: str, verb: str, resource_names: list[str], validate_only: bool) -> dict[str, Any]:
    return await ads.client.recommendations(customer_id, verb, resource_names)
