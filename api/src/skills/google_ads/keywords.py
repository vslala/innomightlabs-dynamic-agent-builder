"""Keywords and negative keywords."""

from __future__ import annotations

from typing import Any

from src.skills.google_ads import operations as ops
from src.skills.google_ads.models import (
    AddKeywordsRequest,
    AddNegativeKeywordsRequest,
    ListRequest,
    RemoveKeywordsRequest,
    UpdateKeywordsRequest,
    id_of,
    to_micros,
)
from src.skills.google_ads.session import AdsSession, parse


async def list_keywords(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    request = parse(ListRequest, arguments)
    ads = await AdsSession.open(config, context)
    customer_id = ads.customer(request.customer_id)
    where = ["ad_group_criterion.type = 'KEYWORD'", "ad_group_criterion.negative = FALSE"]
    if not request.include_removed:
        where.append("ad_group_criterion.status != 'REMOVED'")
    if request.campaign_id:
        where.append(f"campaign.id = {id_of(request.campaign_id, 'campaign_id')}")
    if request.ad_group_id:
        where.append(f"ad_group.id = {id_of(request.ad_group_id, 'ad_group_id')}")
    gaql = (
        "SELECT campaign.name, ad_group.id, ad_group.name, ad_group_criterion.criterion_id, "
        "ad_group_criterion.keyword.text, ad_group_criterion.keyword.match_type, ad_group_criterion.status, "
        "ad_group_criterion.cpc_bid_micros, ad_group_criterion.quality_info.quality_score "
        f"FROM keyword_view WHERE {' AND '.join(where)} "
        f"ORDER BY ad_group_criterion.keyword.text LIMIT {request.limit}"
    )
    rows = await ads.rows(customer_id, gaql)
    return {"customer_id": customer_id, "row_count": len(rows), "keywords": rows}


async def add_keywords(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    request = parse(AddKeywordsRequest, arguments)
    ads = await AdsSession.open(config, context, writes=True)
    customer_id = ads.customer(request.customer_id)
    batch = [ops.create_keyword(customer_id, request.ad_group_id, keyword) for keyword in request.keywords]
    summary = [f"Add {len(batch)} keyword(s) to ad group {request.ad_group_id}"] + [
        f"[{keyword.match_type}] {keyword.text}" + (f" (max CPC {keyword.max_cpc:g})" if keyword.max_cpc else "")
        for keyword in request.keywords
    ]
    return await ads.change(request, customer_id, batch, summary)


async def update_keywords(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    request = parse(UpdateKeywordsRequest, arguments)
    ads = await AdsSession.open(config, context, writes=True)
    customer_id = ads.customer(request.customer_id)

    batch = []
    summary = []
    for keyword in request.keywords:
        fields: dict[str, Any] = {}
        mask: list[str] = []
        if keyword.status is not None:
            fields["status"] = keyword.status
            mask.append("status")
        if keyword.max_cpc is not None:
            fields["cpcBidMicros"] = str(to_micros(keyword.max_cpc))
            mask.append("cpc_bid_micros")
        batch.append(ops.update_keyword(customer_id, keyword.ad_group_id, keyword.criterion_id, fields, mask))
        summary.append(
            f"Keyword {keyword.criterion_id} in ad group {keyword.ad_group_id}: "
            + ", ".join(
                part
                for part in [
                    f"status {keyword.status}" if keyword.status else "",
                    f"max CPC {keyword.max_cpc:g}" if keyword.max_cpc else "",
                ]
                if part
            )
        )
    return await ads.change(request, customer_id, batch, summary)


async def remove_keywords(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    request = parse(RemoveKeywordsRequest, arguments)
    ads = await AdsSession.open(config, context, writes=True)
    customer_id = ads.customer(request.customer_id)
    batch = [ops.remove_keyword(customer_id, keyword.ad_group_id, keyword.criterion_id) for keyword in request.keywords]
    summary = [
        f"Remove keyword {keyword.criterion_id} from ad group {keyword.ad_group_id} (pausing is reversible, removing is not)"
        for keyword in request.keywords
    ]
    return await ads.change(request, customer_id, batch, summary)


async def add_negative_keywords(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    request = parse(AddNegativeKeywordsRequest, arguments)
    ads = await AdsSession.open(config, context, writes=True)
    customer_id = ads.customer(request.customer_id)
    if request.campaign_id:
        batch = [ops.negative_keyword_for_campaign(customer_id, request.campaign_id, keyword) for keyword in request.keywords]
        target = f"campaign {request.campaign_id}"
    else:
        assert request.ad_group_id is not None  # the model requires exactly one of the two
        batch = [ops.negative_keyword_for_ad_group(customer_id, request.ad_group_id, keyword) for keyword in request.keywords]
        target = f"ad group {request.ad_group_id}"
    summary = [f"Add {len(batch)} negative keyword(s) to {target}"] + [
        f"-[{keyword.match_type}] {keyword.text}" for keyword in request.keywords
    ]
    return await ads.change(request, customer_id, batch, summary)
