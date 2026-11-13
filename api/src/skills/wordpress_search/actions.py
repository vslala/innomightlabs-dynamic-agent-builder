from __future__ import annotations

import base64
import html
from typing import Any

import httpx

from src.common import outbound
from src.skills.wordpress_search.models import ReadPostRequest, SearchRequest
from src.web_pages.content import fragment_to_markdown


def _site_url(config: dict[str, Any]) -> str:
    site_url = str(config.get("site_url", "")).strip().rstrip("/")
    if not site_url:
        raise ValueError("Skill configuration is incomplete: 'site_url' is required")
    if not site_url.startswith("http://") and not site_url.startswith("https://"):
        site_url = f"https://{site_url}"
    return site_url


def _build_headers(config: dict[str, Any]) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "User-Agent": "InnomightLabs-WordPressSkill/1.0",
    }
    username = str(config.get("username", "")).strip()
    app_password = str(config.get("app_password", "")).strip()
    if username and app_password:
        token = base64.b64encode(f"{username}:{app_password}".encode("utf-8")).decode("utf-8")
        headers["Authorization"] = f"Basic {token}"

    bypass_token = str(config.get("cf_bypass_token", "")).strip()
    if bypass_token:
        headers["X-Innomightlabs-Skill"] = bypass_token
    return headers


async def read_post(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    post_id = ReadPostRequest.model_validate(arguments).id
    endpoint = f"{_site_url(config)}/wp-json/wp/v2/posts/{post_id}"
    async with outbound.async_client(timeout=20.0, follow_redirects=False) as client:
        response = await client.get(endpoint, params={"_fields": "id,link,title,date,content"}, headers=_build_headers(config))

    if response.status_code >= 400:
        text = response.text[:400]
        raise RuntimeError(f"WordPress API error ({response.status_code}): {text}")

    post = response.json()
    markdown = fragment_to_markdown(post["content"]["rendered"])
    if not markdown:
        raise RuntimeError(f"WordPress post {post_id} has no readable content")
    return {
        "id": post["id"],
        "url": post["link"],
        "title": html.unescape(post["title"]["rendered"]),
        "date": post["date"],
        "markdown": markdown,
        "word_count": len(markdown.split()),
    }


def _safe_int(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except ValueError:
        return None


async def _lookup_id(client: httpx.AsyncClient, endpoint: str, headers: dict[str, str], value: str) -> int | None:
    """A user's or category's id from its number, slug or name: the exact slug first, then a search."""
    if (numeric := _safe_int(value)) is not None:
        return numeric
    for match_by in ("slug", "search"):
        response = await client.get(endpoint, params={match_by: value, "per_page": 1, "_fields": "id"}, headers=headers)
        payload = response.json() if response.is_success else None
        found = payload[0].get("id") if isinstance(payload, list) and payload else None
        if isinstance(found, int):
            return found
    return None


async def _category_ids(client: httpx.AsyncClient, base_url: str, headers: dict[str, str], categories: str) -> list[int]:
    endpoint = f"{base_url}/wp-json/wp/v2/categories"
    ids = [await _lookup_id(client, endpoint, headers, token.strip()) for token in categories.split(",") if token.strip()]
    return list(dict.fromkeys(category_id for category_id in ids if category_id is not None))


async def search(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> str:
    """Posts matching a query, or, without one, the posts the filters select, newest first."""
    request = SearchRequest.model_validate(arguments)
    base_url = _site_url(config)
    headers = _build_headers(config)
    params: dict[str, str | int] = {
        "per_page": request.per_page,
        "page": request.page,
        "status": request.status,
        "order": request.order,
        "orderby": request.sort,
        "_fields": "id,date,title,link,excerpt,author,categories",
    }
    for name in ("after", "before"):
        if value := getattr(request, name):
            params[name] = value
    if request.query:
        params["search"] = request.query

    async with outbound.async_client(timeout=20.0, follow_redirects=False) as client:
        if request.author:
            author_id = await _lookup_id(client, f"{base_url}/wp-json/wp/v2/users", headers, request.author)
            if author_id is None:
                raise ValueError(f"Author filter did not match any user: '{request.author}'")
            params["author"] = author_id

        if request.category:
            category_ids = await _category_ids(client, base_url, headers, request.category)
            if not category_ids:
                raise ValueError(f"Category filter did not match any categories: '{request.category}'")
            params["categories"] = ",".join(str(category_id) for category_id in category_ids)

        response = await client.get(f"{base_url}/wp-json/wp/v2/posts", params=params, headers=headers)

    if response.status_code >= 400:
        raise RuntimeError(f"WordPress API error ({response.status_code}): {response.text[:400]}")

    payload = response.json()
    if not isinstance(payload, list) or not payload:
        return "No WordPress posts matched."

    lines = ["WordPress results (read a post's content with read_post and its [id]):"]
    for item in payload:
        title_obj = item.get("title") or {}
        title = html.unescape(title_obj.get("rendered") or "") if isinstance(title_obj, dict) else ""
        lines.append(
            f"- [{item.get('id')}] {title or '(untitled)'} | date={item.get('date', '')} | author={item.get('author')}"
            f" | categories={item.get('categories') or []} -> {item.get('link', '')}"
        )
    return "\n".join(lines)
