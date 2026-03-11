from __future__ import annotations

import base64
from typing import Any

import httpx


def _normalize_site_url(raw: str) -> str:
    value = raw.strip().rstrip("/")
    if not value.startswith("http://") and not value.startswith("https://"):
        value = f"https://{value}"
    return value


def _build_headers(config: dict[str, Any]) -> dict[str, str]:
    headers = {"Accept": "application/json"}
    username = str(config.get("username", "")).strip()
    app_password = str(config.get("app_password", "")).strip()
    if username and app_password:
        token = base64.b64encode(f"{username}:{app_password}".encode("utf-8")).decode("utf-8")
        headers["Authorization"] = f"Basic {token}"
    return headers


def _safe_int(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except Exception:
        return None


async def _resolve_author_id(
    client: httpx.AsyncClient,
    base_url: str,
    headers: dict[str, str],
    author_value: str,
) -> int | None:
    author_value = author_value.strip()
    if not author_value:
        return None

    numeric = _safe_int(author_value)
    if numeric is not None:
        return numeric

    users_endpoint = f"{base_url}/wp-json/wp/v2/users"

    # Try slug lookup first
    by_slug = await client.get(
        users_endpoint,
        params={"slug": author_value, "per_page": 1, "_fields": "id,slug,name"},
        headers=headers,
    )
    if by_slug.is_success:
        payload = by_slug.json()
        if isinstance(payload, list) and payload:
            user_id = payload[0].get("id")
            if isinstance(user_id, int):
                return user_id

    # Fall back to search lookup
    by_search = await client.get(
        users_endpoint,
        params={"search": author_value, "per_page": 1, "_fields": "id,slug,name"},
        headers=headers,
    )
    if by_search.is_success:
        payload = by_search.json()
        if isinstance(payload, list) and payload:
            user_id = payload[0].get("id")
            if isinstance(user_id, int):
                return user_id

    return None


async def _resolve_category_ids(
    client: httpx.AsyncClient,
    base_url: str,
    headers: dict[str, str],
    category_value: str,
) -> list[int]:
    raw_tokens = [token.strip() for token in category_value.split(",") if token.strip()]
    if not raw_tokens:
        return []

    categories_endpoint = f"{base_url}/wp-json/wp/v2/categories"
    ids: list[int] = []

    for token in raw_tokens:
        numeric = _safe_int(token)
        if numeric is not None:
            ids.append(numeric)
            continue

        by_slug = await client.get(
            categories_endpoint,
            params={"slug": token, "per_page": 1, "_fields": "id,slug,name"},
            headers=headers,
        )
        if by_slug.is_success:
            payload = by_slug.json()
            if isinstance(payload, list) and payload:
                category_id = payload[0].get("id")
                if isinstance(category_id, int):
                    ids.append(category_id)
                    continue

        by_search = await client.get(
            categories_endpoint,
            params={"search": token, "per_page": 1, "_fields": "id,slug,name"},
            headers=headers,
        )
        if by_search.is_success:
            payload = by_search.json()
            if isinstance(payload, list) and payload:
                category_id = payload[0].get("id")
                if isinstance(category_id, int):
                    ids.append(category_id)

    # Deduplicate while preserving order
    deduped: list[int] = []
    seen = set()
    for category_id in ids:
        if category_id not in seen:
            seen.add(category_id)
            deduped.append(category_id)
    return deduped


async def search(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> str:
    query = str(arguments.get("query", "")).strip()
    if not query:
        raise ValueError("Missing required argument: query")

    per_page_raw = arguments.get("per_page", 5)
    page_raw = arguments.get("page", 1)
    order = str(arguments.get("order", "desc")).strip().lower() or "desc"
    if order not in {"asc", "desc"}:
        order = "desc"

    orderby_default = "relevance" if query else "date"
    orderby = str(arguments.get("orderby", orderby_default)).strip().lower() or orderby_default
    if orderby not in {"date", "relevance", "title", "modified"}:
        orderby = orderby_default

    status = str(arguments.get("status", "publish")).strip().lower() or "publish"
    if status not in {"publish", "draft", "private", "future", "pending"}:
        status = "publish"

    after = str(arguments.get("after", "")).strip()
    before = str(arguments.get("before", "")).strip()
    author_input = str(arguments.get("author", "")).strip()
    category_input = str(arguments.get("category", "")).strip()

    per_page = 5
    page = 1
    try:
        per_page = max(1, min(20, int(per_page_raw)))
    except Exception:
        per_page = 5
    try:
        page = max(1, int(page_raw))
    except Exception:
        page = 1

    site_url = str(config.get("site_url", "")).strip()
    if not site_url:
        raise ValueError("Skill configuration is incomplete: 'site_url' is required")

    base_url = _normalize_site_url(site_url)
    endpoint = f"{base_url}/wp-json/wp/v2/posts"
    params = {
        "search": query,
        "per_page": per_page,
        "page": page,
        "status": status,
        "order": order,
        "orderby": orderby,
        "_fields": "id,date,title,link,excerpt,author,categories",
    }
    if after:
        params["after"] = after
    if before:
        params["before"] = before

    headers = _build_headers(config)

    async with httpx.AsyncClient(timeout=20.0) as client:
        if author_input:
            author_id = await _resolve_author_id(client, base_url, headers, author_input)
            if author_id is None:
                raise ValueError(f"Author filter did not match any user: '{author_input}'")
            params["author"] = author_id

        if category_input:
            category_ids = await _resolve_category_ids(client, base_url, headers, category_input)
            if not category_ids:
                raise ValueError(f"Category filter did not match any categories: '{category_input}'")
            params["categories"] = ",".join(str(cat_id) for cat_id in category_ids)

        response = await client.get(endpoint, params=params, headers=headers)

    if response.status_code >= 400:
        text = response.text[:400]
        raise RuntimeError(f"WordPress API error ({response.status_code}): {text}")

    payload = response.json()
    if not isinstance(payload, list) or not payload:
        return "No WordPress posts found for that query."

    lines = ["WordPress results:"]
    for item in payload:
        title_obj = item.get("title") or {}
        title = title_obj.get("rendered") if isinstance(title_obj, dict) else ""
        link = item.get("link", "")
        post_id = item.get("id")
        date = item.get("date", "")
        author_id = item.get("author")
        categories = item.get("categories") or []
        lines.append(
            f"- [{post_id}] {title or '(untitled)'} | date={date} | author={author_id} | categories={categories} -> {link}"
        )

    return "\n".join(lines)
