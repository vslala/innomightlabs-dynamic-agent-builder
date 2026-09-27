"""How campaigns are doing: performance, search terms, change history, and keyword ideas."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from src.skills.google_ads.client import compact
from src.skills.google_ads.models import (
    ChangeHistoryRequest,
    KeywordIdeasRequest,
    PerformanceRequest,
    SearchTermsRequest,
    id_of,
)
from src.skills.google_ads.session import AdsSession, parse

#: Report metric names the agent uses -> GAQL fields. Money fields come back in currency units.
METRICS = {
    "clicks": "metrics.clicks",
    "impressions": "metrics.impressions",
    "ctr": "metrics.ctr",
    "average_cpc": "metrics.average_cpc",
    "cost": "metrics.cost_micros",
    "conversions": "metrics.conversions",
    "conversions_value": "metrics.conversions_value",
    "cost_per_conversion": "metrics.cost_per_conversion",
    "conversion_rate": "metrics.conversions_from_interactions_rate",
    "all_conversions": "metrics.all_conversions",
    "search_impression_share": "metrics.search_impression_share",
}


@dataclass(frozen=True)
class Level:
    resource: str
    fields: list[str]
    status: str | None
    #: Which of campaign_id / ad_group_id this level can be filtered by.
    filters: set[str]


LEVELS = {
    "account": Level("customer", ["customer.id", "customer.descriptive_name"], None, set()),
    "campaign": Level("campaign", ["campaign.id", "campaign.name", "campaign.status"], "campaign.status", {"campaign_id"}),
    "ad_group": Level(
        "ad_group",
        ["campaign.id", "campaign.name", "ad_group.id", "ad_group.name", "ad_group.status"],
        "ad_group.status",
        {"campaign_id", "ad_group_id"},
    ),
    "ad": Level(
        "ad_group_ad",
        ["campaign.name", "ad_group.id", "ad_group.name", "ad_group_ad.ad.id", "ad_group_ad.ad.type", "ad_group_ad.status"],
        "ad_group_ad.status",
        {"campaign_id", "ad_group_id"},
    ),
    "keyword": Level(
        "keyword_view",
        [
            "campaign.name",
            "ad_group.id",
            "ad_group.name",
            "ad_group_criterion.criterion_id",
            "ad_group_criterion.keyword.text",
            "ad_group_criterion.keyword.match_type",
            "ad_group_criterion.status",
        ],
        "ad_group_criterion.status",
        {"campaign_id", "ad_group_id"},
    ),
}


async def get_performance(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    request = parse(PerformanceRequest, arguments)
    unknown = [name for name in request.metrics if name not in METRICS]
    if unknown:
        raise ValueError(f"Unknown metrics {unknown}. Use any of: {', '.join(METRICS)}")
    metrics = list(dict.fromkeys(request.metrics))
    order_by = request.order_by if request.order_by in metrics else ("cost" if "cost" in metrics else metrics[0])

    level = LEVELS[request.level]
    where = [request.during(), *_filters(level, request.campaign_id, request.ad_group_id)]
    if level.status:
        where.append(f"{level.status} = 'ENABLED'" if not request.include_paused else f"{level.status} != 'REMOVED'")

    ads = await AdsSession.open(config, context)
    customer_id = ads.customer(request.customer_id)
    gaql = (
        f"SELECT {', '.join([*level.fields, *(METRICS[name] for name in metrics), 'customer.currency_code'])} "
        f"FROM {level.resource} WHERE {' AND '.join(where)} "
        f"ORDER BY {METRICS[order_by]} DESC LIMIT {request.limit}"
    )
    return _report(customer_id, await ads.rows(customer_id, gaql), request.limit, level=request.level)


async def get_search_terms(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    request = parse(SearchTermsRequest, arguments)
    where = [request.during(), *_filters(LEVELS["ad_group"], request.campaign_id, request.ad_group_id)]
    if request.min_clicks > 0:
        where.append(f"metrics.clicks >= {int(request.min_clicks)}")
    if request.without_conversions:
        where.append("metrics.conversions = 0")

    ads = await AdsSession.open(config, context)
    customer_id = ads.customer(request.customer_id)
    gaql = (
        "SELECT search_term_view.search_term, search_term_view.status, campaign.id, campaign.name, "
        "ad_group.id, ad_group.name, metrics.impressions, metrics.clicks, metrics.cost_micros, "
        "metrics.conversions, customer.currency_code "
        f"FROM search_term_view WHERE {' AND '.join(where)} "
        f"ORDER BY metrics.cost_micros DESC LIMIT {request.limit}"
    )
    report = _report(customer_id, await ads.rows(customer_id, gaql), request.limit)
    report["hint"] = "Terms with cost and no conversions are negative-keyword candidates (add_negative_keywords)."
    return report


async def get_change_history(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    request = parse(ChangeHistoryRequest, arguments)
    ads = await AdsSession.open(config, context)
    customer_id = ads.customer(request.customer_id)
    since = (date.today() - timedelta(days=request.days)).isoformat()
    until = (date.today() + timedelta(days=1)).isoformat()
    gaql = (
        "SELECT change_event.change_date_time, change_event.change_resource_type, "
        "change_event.resource_change_operation, change_event.changed_fields, change_event.client_type, "
        "change_event.user_email, change_event.campaign, change_event.ad_group "
        f"FROM change_event WHERE change_event.change_date_time >= '{since}' "
        f"AND change_event.change_date_time <= '{until}' "
        f"ORDER BY change_event.change_date_time DESC LIMIT {request.limit}"
    )
    rows = await ads.rows(customer_id, gaql)
    return {"customer_id": customer_id, "since": since, "row_count": len(rows), "changes": rows}


async def generate_keyword_ideas(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    request = parse(KeywordIdeasRequest, arguments)
    ads = await AdsSession.open(config, context)
    customer_id = ads.customer(request.customer_id)

    body: dict[str, Any] = {
        "language": f"languageConstants/{request.language_id}",
        "geoTargetConstants": [f"geoTargetConstants/{location}" for location in request.location_ids],
        "keywordPlanNetwork": "GOOGLE_SEARCH",
        "includeAdultKeywords": False,
        "pageSize": request.limit,
    }
    if request.keywords and request.url:
        body["keywordAndUrlSeed"] = {"url": request.url, "keywords": request.keywords}
    elif request.url:
        body["urlSeed"] = {"url": request.url}
    else:
        body["keywordSeed"] = {"keywords": request.keywords}

    ideas = []
    for idea in (await ads.client.generate_keyword_ideas(customer_id, body))[: request.limit]:
        row = compact(idea)
        ideas.append({key.removeprefix("keyword_idea_metrics."): value for key, value in row.items()})
    return {"customer_id": customer_id, "idea_count": len(ideas), "ideas": ideas, "note": "Bids are in the account currency."}


def _filters(level: Level, campaign_id: str | None, ad_group_id: str | None) -> list[str]:
    where = []
    if campaign_id and "campaign_id" in level.filters:
        where.append(f"campaign.id = {id_of(campaign_id, 'campaign_id')}")
    if ad_group_id and "ad_group_id" in level.filters:
        where.append(f"ad_group.id = {id_of(ad_group_id, 'ad_group_id')}")
    return where


def _report(customer_id: str, rows: list[dict[str, Any]], limit: int, **extra: Any) -> dict[str, Any]:
    currency = next((row.get("customer.currency_code") for row in rows if row.get("customer.currency_code")), None)
    for row in rows:
        row.pop("customer.currency_code", None)
    return {
        "customer_id": customer_id,
        **extra,
        "currency": currency,
        "row_count": len(rows),
        "truncated": len(rows) >= limit,
        "rows": rows,
    }
