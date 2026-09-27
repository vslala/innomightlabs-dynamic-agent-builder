"""Ad groups."""

from __future__ import annotations

from typing import Any

from src.skills.google_ads import operations as ops
from src.skills.google_ads.models import CreateAdGroupRequest, ListRequest, UpdateAdGroupRequest, id_of, to_micros
from src.skills.google_ads.session import AdsSession, parse


async def list_ad_groups(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    request = parse(ListRequest, arguments)
    ads = await AdsSession.open(config, context)
    customer_id = ads.customer(request.customer_id)
    where = [] if request.include_removed else ["ad_group.status != 'REMOVED'"]
    if request.campaign_id:
        where.append(f"campaign.id = {id_of(request.campaign_id, 'campaign_id')}")
    gaql = (
        "SELECT campaign.id, campaign.name, ad_group.id, ad_group.name, ad_group.status, ad_group.type, "
        "ad_group.cpc_bid_micros FROM ad_group"
        + (f" WHERE {' AND '.join(where)}" if where else "")
        + f" ORDER BY ad_group.name LIMIT {request.limit}"
    )
    rows = await ads.rows(customer_id, gaql)
    return {"customer_id": customer_id, "row_count": len(rows), "ad_groups": rows}


async def create_ad_group(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    request = parse(CreateAdGroupRequest, arguments)
    ads = await AdsSession.open(config, context, writes=True)
    customer_id = ads.customer(request.customer_id)
    batch = ops.ad_group_with_contents(customer_id, ops.TemporaryIds(), request.campaign_id, request, request.status)
    summary = [
        f"Create ad group '{request.name}' in campaign {request.campaign_id} ({request.status})"
        + (f", default max CPC {request.max_cpc:g}" if request.max_cpc else ""),
        f"With {len(request.keywords)} keyword(s) and {len(request.ads)} ad(s)",
    ]
    return await ads.change(request, customer_id, batch, summary)


async def update_ad_group(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    request = parse(UpdateAdGroupRequest, arguments)
    ads = await AdsSession.open(config, context, writes=True)
    customer_id = ads.customer(request.customer_id)

    fields: dict[str, Any] = {}
    mask: list[str] = []
    changes = []
    if request.name is not None:
        fields["name"] = request.name
        mask.append("name")
        changes.append(f"name '{request.name}'")
    if request.status is not None:
        fields["status"] = request.status
        mask.append("status")
        changes.append(f"status {request.status}")
    if request.max_cpc is not None:
        fields["cpcBidMicros"] = str(to_micros(request.max_cpc))
        mask.append("cpc_bid_micros")
        changes.append(f"max CPC {request.max_cpc:g}")
    batch = [ops.update_ad_group(customer_id, request.ad_group_id, fields, mask)]
    return await ads.change(request, customer_id, batch, [f"Set ad group {request.ad_group_id} {', '.join(changes)}"])
