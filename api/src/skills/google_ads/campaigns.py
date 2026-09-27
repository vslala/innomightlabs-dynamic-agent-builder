"""Campaigns and their budgets."""

from __future__ import annotations

from typing import Any

from src.skills.google_ads import operations as ops
from src.skills.google_ads.models import (
    MICROS,
    CampaignsRequest,
    CreateSearchCampaignRequest,
    ListRequest,
    RemoveCampaignRequest,
    UpdateBudgetRequest,
    UpdateCampaignRequest,
    id_of,
    to_micros,
)
from src.skills.google_ads.session import AdsSession, parse


async def list_campaigns(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    request = parse(ListRequest, arguments)
    ads = await AdsSession.open(config, context)
    customer_id = ads.customer(request.customer_id)
    where = "" if request.include_removed else " WHERE campaign.status != 'REMOVED'"
    gaql = (
        "SELECT campaign.id, campaign.name, campaign.status, campaign.advertising_channel_type, "
        "campaign.bidding_strategy_type, campaign.serving_status, campaign_budget.amount_micros, "
        "campaign_budget.explicitly_shared, customer.currency_code "
        f"FROM campaign{where} ORDER BY campaign.name LIMIT {request.limit}"
    )
    rows = await ads.rows(customer_id, gaql)
    return {"customer_id": customer_id, "row_count": len(rows), "campaigns": rows}


async def create_search_campaign(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    request = parse(CreateSearchCampaignRequest, arguments)
    ads = await AdsSession.open(config, context, writes=True)
    ads.config.check_daily_budget(to_micros(request.daily_budget))
    customer_id = ads.customer(request.customer_id)

    ids = ops.TemporaryIds()
    budget_id, campaign_id = ids.take(), ids.take()
    batch = [
        ops.create_budget(customer_id, budget_id, request.name, request.daily_budget),
        ops.create_search_campaign(
            customer_id,
            campaign_id,
            budget_id,
            name=request.name,
            bidding_strategy=request.bidding_strategy,
            max_cpc=request.max_cpc,
            include_search_partners=request.include_search_partners,
            enabled=request.start_enabled,
            contains_eu_political_advertising=request.contains_eu_political_advertising,
        ),
        *(ops.campaign_location(customer_id, campaign_id, location) for location in request.location_ids),
        *(ops.campaign_language(customer_id, campaign_id, language) for language in request.language_ids),
    ]
    for group in request.ad_groups:
        batch.extend(ops.ad_group_with_contents(customer_id, ids, campaign_id, group))

    summary = [
        f"Create Search campaign '{request.name}' ({'ENABLED - starts serving' if request.start_enabled else 'PAUSED'})",
        f"Daily budget {request.daily_budget:g}, bidding {request.bidding_strategy}"
        + (f", max CPC {request.max_cpc:g}" if request.max_cpc else ""),
        f"Targeting {len(request.location_ids) or 'all'} location(s), {len(request.language_ids) or 'all'} language(s)",
        *(
            f"Ad group '{group.name}': {len(group.keywords)} keyword(s), {len(group.ads)} ad(s)"
            for group in request.ad_groups
        ),
    ]
    return await ads.change(request, customer_id, batch, summary)


async def update_campaign(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    request = parse(UpdateCampaignRequest, arguments)
    ads = await AdsSession.open(config, context, writes=True)
    customer_id = ads.customer(request.customer_id)

    fields: dict[str, Any] = {}
    mask: list[str] = []
    summary = []
    if request.name is not None:
        fields["name"] = request.name
        mask.append("name")
        summary.append(f"Rename campaign {request.campaign_id} to '{request.name}'")
    if request.include_search_partners is not None:
        fields["networkSettings"] = {"targetSearchNetwork": request.include_search_partners}
        mask.append("network_settings.target_search_network")
        summary.append(
            f"{'Include' if request.include_search_partners else 'Exclude'} search partners on campaign {request.campaign_id}"
        )
    batch = [ops.update_campaign(customer_id, request.campaign_id, fields, mask)]
    return await ads.change(request, customer_id, batch, summary)


async def pause_campaigns(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    return await _set_status(arguments, config, context, "PAUSED")


async def enable_campaigns(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    return await _set_status(arguments, config, context, "ENABLED")


async def _set_status(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any], status: str) -> dict[str, Any]:
    request = parse(CampaignsRequest, arguments)
    ads = await AdsSession.open(config, context, writes=True)
    customer_id = ads.customer(request.customer_id)
    batch = [ops.update_campaign(customer_id, campaign_id, {"status": status}, ["status"]) for campaign_id in request.campaign_ids]
    verb = "Pause" if status == "PAUSED" else "Enable (starts serving)"
    return await ads.change(request, customer_id, batch, [f"{verb} campaign {campaign_id}" for campaign_id in request.campaign_ids])


async def update_budget(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    request = parse(UpdateBudgetRequest, arguments)
    ads = await AdsSession.open(config, context, writes=True)
    ads.config.check_daily_budget(to_micros(request.daily_budget))
    customer_id = ads.customer(request.customer_id)

    campaign_id = id_of(request.campaign_id, "campaign_id")
    rows = await ads.client.search(
        customer_id,
        "SELECT campaign.name, campaign_budget.resource_name, campaign_budget.amount_micros, "
        f"campaign_budget.explicitly_shared FROM campaign WHERE campaign.id = {campaign_id}",
    )
    if not rows:
        raise ValueError(f"Campaign {campaign_id} was not found in account {customer_id}")
    budget = rows[0].get("campaignBudget") or {}
    current = int(budget.get("amountMicros") or 0) / MICROS

    summary = [
        f"Change the daily budget of campaign '{rows[0].get('campaign', {}).get('name', campaign_id)}' "
        f"from {current:g} to {request.daily_budget:g}"
    ]
    if budget.get("explicitlyShared"):
        summary.append("This budget is shared: every campaign that uses it changes too")
    batch = [ops.update_budget(budget["resourceName"], request.daily_budget)]
    return await ads.change(request, customer_id, batch, summary)


async def remove_campaign(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    request = parse(RemoveCampaignRequest, arguments)
    ads = await AdsSession.open(config, context, writes=True)
    customer_id = ads.customer(request.customer_id)
    batch = [ops.remove_campaign(customer_id, request.campaign_id)]
    summary = [f"Permanently remove campaign {request.campaign_id}. This cannot be undone; pausing is reversible."]
    return await ads.change(request, customer_id, batch, summary)
