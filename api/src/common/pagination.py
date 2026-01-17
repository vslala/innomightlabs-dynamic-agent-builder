"""
Generic pagination models for API responses.
"""

from typing import Generic, TypeVar, Optional
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
