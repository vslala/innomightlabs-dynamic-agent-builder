"""Server-Sent Events response helper shared by streaming routers."""

from typing import AsyncIterator

from fastapi.responses import StreamingResponse


def sse_response(events: AsyncIterator[str]) -> StreamingResponse:
    return StreamingResponse(
        events,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
