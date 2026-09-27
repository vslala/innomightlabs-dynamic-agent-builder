"""Which accounts exist, and raw GAQL for anything the curated actions do not cover."""

from __future__ import annotations

import re
from typing import Any

from src.skills.google_ads.client import GoogleAdsError, compact
from src.skills.google_ads.models import (
    DescribeFieldsRequest,
    ListAccountsRequest,
    QueryRequest,
    customer_id_of,
)
from src.skills.google_ads.session import AdsSession, parse

MAX_ACCOUNTS = 25

CUSTOMER_QUERY = (
    "SELECT customer.id, customer.descriptive_name, customer.currency_code, customer.time_zone, "
    "customer.manager, customer.test_account FROM customer LIMIT 1"
)
CLIENTS_QUERY = (
    "SELECT customer_client.id, customer_client.descriptive_name, customer_client.currency_code, "
    "customer_client.manager, customer_client.level, customer_client.status "
    "FROM customer_client WHERE customer_client.level <= 1 LIMIT {limit}"
)


async def list_accounts(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    request = parse(ListAccountsRequest, arguments)
    ads = await AdsSession.open(config, context)

    if request.manager_id:
        manager = customer_id_of(request.manager_id)
        rows = await ads.client.search(manager, CLIENTS_QUERY.format(limit=MAX_ACCOUNTS * 4), login_customer_id=manager)
        return {"manager_id": manager, "accounts": [compact(row) for row in rows]}

    accounts: list[dict[str, Any]] = []
    unreadable: list[str] = []
    ids = await ads.client.list_accessible_customers()
    for customer_id in ids[:MAX_ACCOUNTS]:
        try:
            # Each directly accessible account can be its own login account.
            rows = await ads.client.search(customer_id, CUSTOMER_QUERY, login_customer_id=customer_id)
        except GoogleAdsError:
            unreadable.append(customer_id)
            continue
        if rows:
            accounts.append(compact(rows[0]))
    result: dict[str, Any] = {"accounts": accounts, "total_accessible": len(ids)}
    if unreadable:
        result["unreadable"] = unreadable
    if len(ids) > MAX_ACCOUNTS:
        result["truncated"] = True
    result["hint"] = "For manager accounts (customer.manager=true), pass manager_id to list the accounts under them."
    return result


async def query(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    request = parse(QueryRequest, arguments)
    ads = await AdsSession.open(config, context)
    customer_id = ads.customer(request.customer_id)
    gaql = _limited(request.query, request.limit)
    rows = await ads.rows(customer_id, gaql, keep_resource_names=True)
    return {"customer_id": customer_id, "query": gaql, "row_count": len(rows), "rows": rows}


async def describe_fields(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    request = parse(DescribeFieldsRequest, arguments)
    ads = await AdsSession.open(config, context)
    pattern = f"{request.resource}.%{request.contains or ''}%"
    gaql = (
        "SELECT name, category, data_type, selectable, filterable, sortable, is_repeated, enum_values "
        f"WHERE name LIKE '{pattern}'"
    )
    fields = [compact(row) for row in await ads.client.search_fields(gaql, max(1, min(200, request.limit)))]
    return {"resource": request.resource, "fields": fields}


def _limited(gaql: str, limit: int) -> str:
    """Cap rows: keep a smaller LIMIT the caller wrote, otherwise apply ours."""
    match = re.search(r"\bLIMIT\s+(\d+)\s*$", gaql.strip(), flags=re.IGNORECASE)
    if match:
        if int(match.group(1)) <= limit:
            return gaql.strip()
        return gaql.strip()[: match.start()].rstrip() + f" LIMIT {limit}"
    return f"{gaql.strip()} LIMIT {limit}"
