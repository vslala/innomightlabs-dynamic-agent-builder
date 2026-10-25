"""The HTTP side of uploading a document, shared by every owner's upload route: the size cap and the rate limit."""

from fastapi import HTTPException, UploadFile

from src.config import settings
from src.rate_limits.limiter import RateLimiter, RateLimitPolicy

#: Uploads per account per hour, across knowledge bases and conversations. Reading is the expensive part.
DOCUMENT_UPLOAD_RATE_LIMIT = RateLimitPolicy.sliding_window("DOCUMENT_UPLOAD", limit=200, seconds=3600)


def take_upload_slot(account_id: str) -> None:
    decision = RateLimiter(DOCUMENT_UPLOAD_RATE_LIMIT).acquire(account_id)
    if not decision.allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Too many uploads this hour. Try again in {decision.retry_after_seconds} seconds.",
            headers={"Retry-After": str(decision.retry_after_seconds)},
        )


async def read_upload(upload: UploadFile) -> bytes:
    """The file's bytes, refusing it as soon as it is over the cap rather than after reading all of it."""
    limit = settings.document_max_bytes
    data = await upload.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(status_code=413, detail=f"File exceeds the {limit // (1024 * 1024)} MB limit")
    return data
