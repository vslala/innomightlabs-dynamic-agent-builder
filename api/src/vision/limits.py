"""How many images the public surfaces accept: per widget visitor and key, and per API key.

Guests and signed-in widget visitors share the limits. Dashboard members have none of their own: their sends
count against the account's subscription like any message.
"""

from __future__ import annotations

from contextlib import AbstractContextManager

from src.config import settings
from src.rate_limits.policy import RateLimitPolicy
from src.rate_limits.slots import Limit, limit_slot

_HOUR = 3600
_DAY = 86400
LIMITED = {"code": "image_upload_limited", "message": "Too many images. Try again in a moment."}

def widget_upload_limits(*, visitor_id: str, key_id: str) -> list[Limit]:
    """The visitor's own uploads, then every upload through the widget key."""
    return [
        (
            RateLimitPolicy.sliding_window(
                "WIDGET_IMAGE_UPLOADS", limit=settings.widget_image_uploads_per_visitor_hour, seconds=_HOUR,
                fail_open=False,
            ),
            visitor_id,
        ),
        (
            RateLimitPolicy.fixed_window(
                "WIDGET_IMAGE_UPLOADS_KEY_DAILY", limit=settings.widget_image_uploads_per_key_day, seconds=_DAY,
                fail_open=False,
            ),
            key_id,
        ),
    ]


def api_upload_limits(*, key_id: str) -> list[Limit]:
    return [
        (
            RateLimitPolicy.fixed_window(
                "API_IMAGE_UPLOADS_KEY_DAILY", limit=settings.api_image_uploads_per_key_day, seconds=_DAY,
                fail_open=False,
            ),
            key_id,
        )
    ]


def image_upload_slot(limits: list[Limit]) -> AbstractContextManager[None]:
    """Fails closed (every policy here has fail_open=False): uploads spend the owner's money once an agent reads them."""
    return limit_slot(limits, refusal=LIMITED)
