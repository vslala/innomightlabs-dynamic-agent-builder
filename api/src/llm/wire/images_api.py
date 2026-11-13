"""OpenAI's images endpoint shape (`POST {base}/images/generations`), which xAI also serves: a prompt in, base64
images out. Not streamed."""

from __future__ import annotations

import base64
from typing import Any

import httpx

DRAW_TIMEOUT_SECONDS = 180.0


async def generate_images(url: str, api_key: str, body: dict[str, Any], *, label: str) -> list[dict[str, Any]]:
    """The `data` items of the response, each with its picture decoded into `bytes` under "image". Asks for
    `b64_json`: a hosted URL would expire, and the bytes are kept in our own storage anyway."""
    async with httpx.AsyncClient(timeout=DRAW_TIMEOUT_SECONDS) as client:
        response = await client.post(
            url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={**body, "response_format": "b64_json"},
        )
    if not response.is_success:
        raise RuntimeError(f"{label} image generation error ({response.status_code}): {response.text}")
    items = response.json().get("data")
    return [
        {**item, "image": base64.b64decode(item["b64_json"])}
        for item in (items if isinstance(items, list) else [])
        if isinstance(item, dict) and item.get("b64_json")
    ]
