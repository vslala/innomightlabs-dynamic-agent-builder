"""
Generic pagination models for API responses.
"""

import base64
import json
from typing import Any, Generic, Iterable, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginationParams(BaseModel):
    """Query parameters for pagination."""

    limit: int = Field(default=10, ge=1, le=100, description="Number of items per page")
    cursor: Optional[str] = Field(
        default=None, description="Cursor for next page (base64 encoded last evaluated key)"
    )


class Paginated(BaseModel, Generic[T]):
    """
    Generic paginated response wrapper.

    Usage:
        Paginated[AgentResponse](items=[...], next_cursor="...", has_more=True)
    """

    items: list[T] = Field(description="List of items for the current page")
    next_cursor: Optional[str] = Field(
        default=None, description="Cursor to fetch the next page. None if no more pages."
    )
    has_more: bool = Field(description="Whether there are more items to fetch")
    total_count: Optional[int] = Field(
        default=None, description="Total count of items (if available)"
    )


class InvalidCursor(ValueError):
    """A page cursor we did not issue. Clients get a 400, not a confused database error."""


def encode_cursor(start_key: Optional[dict[str, Any]]) -> Optional[str]:
    if not start_key:
        return None
    return base64.b64encode(json.dumps(start_key).encode("utf-8")).decode("utf-8")


def decode_cursor(cursor: Optional[str], *, key_names: Iterable[str] = ("pk", "sk")) -> Optional[dict[str, Any]]:
    """The DynamoDB start key in a cursor: exactly the table's key attributes, all strings."""
    if not cursor:
        return None
    try:
        start_key = json.loads(base64.b64decode(cursor, validate=True).decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise InvalidCursor("Invalid pagination cursor") from exc
    if (
        not isinstance(start_key, dict)
        or set(start_key) != set(key_names)
        or not all(isinstance(value, str) for value in start_key.values())
    ):
        raise InvalidCursor("Invalid pagination cursor")
    return start_key
