"""Ads: responsive search ads and their status."""

from __future__ import annotations

from typing import Any

from src.skills.google_ads import operations as ops
from src.skills.google_ads.models import CreateResponsiveSearchAdRequest, ListRequest, SetAdStatusRequest, id_of
from src.skills.google_ads.session import AdsSession, parse


async def list_ads(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    request = parse(ListRequest, arguments)
    ads = await AdsSession.open(config, context)
    customer_id = ads.customer(request.customer_id)
    where = [] if request.include_removed else ["ad_group_ad.status != 'REMOVED'"]
    if request.campaign_id:
        where.append(f"campaign.id = {id_of(request.campaign_id, 'campaign_id')}")
    if request.ad_group_id:
        where.append(f"ad_group.id = {id_of(request.ad_group_id, 'ad_group_id')}")
    gaql = (
        "SELECT campaign.name, ad_group.id, ad_group.name, ad_group_ad.ad.id, ad_group_ad.ad.type, "
        "ad_group_ad.status, ad_group_ad.policy_summary.approval_status, ad_group_ad.ad.final_urls, "
        "ad_group_ad.ad.responsive_search_ad.headlines, ad_group_ad.ad.responsive_search_ad.descriptions "
        "FROM ad_group_ad"
        + (f" WHERE {' AND '.join(where)}" if where else "")
        + f" LIMIT {request.limit}"
    )
    rows = [_texts_only(row) for row in await ads.rows(customer_id, gaql)]
    return {"customer_id": customer_id, "row_count": len(rows), "ads": rows}


async def create_responsive_search_ad(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    request = parse(CreateResponsiveSearchAdRequest, arguments)
    ads = await AdsSession.open(config, context, writes=True)
    customer_id = ads.customer(request.customer_id)
    batch = [ops.create_responsive_search_ad(customer_id, request.ad_group_id, request)]
    summary = [
        f"Create a responsive search ad in ad group {request.ad_group_id} ({request.status}), landing on {request.final_url}",
        "Headlines: " + " | ".join(request.headlines),
        "Descriptions: " + " | ".join(request.descriptions),
    ]
    return await ads.change(request, customer_id, batch, summary)


async def set_ad_status(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    request = parse(SetAdStatusRequest, arguments)
    ads = await AdsSession.open(config, context, writes=True)
    customer_id = ads.customer(request.customer_id)
    batch = [ops.ad_status(customer_id, ad.ad_group_id, ad.ad_id, request.status) for ad in request.ads]
    summary = [f"Set ad {ad.ad_id} in ad group {ad.ad_group_id} to {request.status}" for ad in request.ads]
    return await ads.change(request, customer_id, batch, summary)


def _texts_only(row: dict[str, Any]) -> dict[str, Any]:
    """Headline/description assets arrive as [{text, pinnedField, ...}]; the texts are what matter."""
    for key in ("ad_group_ad.ad.responsive_search_ad.headlines", "ad_group_ad.ad.responsive_search_ad.descriptions"):
        if isinstance(row.get(key), list):
            row[key] = [item.get("text") for item in row[key] if isinstance(item, dict)]
    return row
