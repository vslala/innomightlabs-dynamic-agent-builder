"""Server-sent events as the Responses API sends them: one JSON object per `data:` line."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx


async def sse_events(response: httpx.Response) -> AsyncIterator[dict[str, Any]]:
    """Each `data:` line's JSON object. Comments, `event:` lines, `[DONE]` and payloads that aren't a JSON object are
    skipped: they carry nothing a reader acts on."""
    async for raw_line in response.aiter_lines():
        line = raw_line.strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data or data == "[DONE]":
            continue
        try:
            event = json.loads(data)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            yield event
