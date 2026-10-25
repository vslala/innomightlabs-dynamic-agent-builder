from __future__ import annotations

from typing import Annotated, Optional

from pydantic import BaseModel, Field, StringConstraints

from src.documents.tables import DEFAULT_ROWS, Aggregation, Condition, OrderBy

Id = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]

class OwnerArguments(BaseModel):
    knowledge_base_id: Optional[str] = None


class DocumentArguments(OwnerArguments):
    document_id: Id


class ReadDocument(DocumentArguments):
    offset: int = 0
    length: int = 8000


class ReadPages(DocumentArguments):
    from_page: int
    to_page: Optional[int] = None


class ReadSection(DocumentArguments):
    section: int
    offset: int = 0
    length: int = 8000


class TableArguments(DocumentArguments):
    table: int


class ReadTable(TableArguments):
    from_row: int = 1
    max_rows: int = DEFAULT_ROWS
    columns: list[str] = Field(default_factory=list)


class QueryTable(TableArguments):
    where: list[Condition] = Field(default_factory=list)
    select: list[str] = Field(default_factory=list)
    group_by: list[str] = Field(default_factory=list)
    aggregate: list[Aggregation] = Field(default_factory=list)
    order_by: Optional[OrderBy] = None
    limit: int = DEFAULT_ROWS


class ViewPage(DocumentArguments):
    page: int
    prompt: Optional[str] = None


class SearchDocument(DocumentArguments):
    query: Id
