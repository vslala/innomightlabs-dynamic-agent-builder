from typing import Any, Literal

from pydantic import BaseModel, PositiveInt, ValidationInfo, field_validator

MAX_PER_PAGE = 20


class ReadPostRequest(BaseModel):
    id: PositiveInt


class SearchRequest(BaseModel):
    """What `search` takes. Every field is optional: without a query it lists posts by the other filters, newest first.

    Blank values count as not given, as models often send every property with `""`.
    """

    query: str = ""
    per_page: int = 5
    page: int = 1
    author: str = ""
    category: str = ""
    after: str = ""
    before: str = ""
    order: Literal["asc", "desc"] = "desc"
    orderby: Literal["date", "relevance", "title", "modified"] | None = None
    status: Literal["publish", "draft", "private", "future", "pending"] = "publish"

    @field_validator("query", "author", "category", "after", "before", mode="before")
    @classmethod
    def _text(cls, value: Any) -> str:
        return str(value or "").strip()

    @field_validator("order", "orderby", "status", mode="before")
    @classmethod
    def _choice(cls, value: Any, info: ValidationInfo) -> Any:
        text = str(value or "").strip().lower()
        return text or cls.model_fields[str(info.field_name)].default

    @field_validator("per_page", mode="after")
    @classmethod
    def _per_page_in_range(cls, value: int) -> int:
        return max(1, min(MAX_PER_PAGE, value))

    @field_validator("page", mode="after")
    @classmethod
    def _page_from_one(cls, value: int) -> int:
        return max(1, value)

    @property
    def sort(self) -> str:
        """WordPress orders by relevance only for a search term, so without one the newest come first."""
        if self.orderby and (self.orderby != "relevance" or self.query):
            return self.orderby
        return "relevance" if self.query else "date"
