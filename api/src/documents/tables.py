"""Questions about a table, answered from its rows (the first row is the header): describe, page through, query.

Plain functions over `list[list[str]]`, so an agent can ask "what do the Madawa rows add up to" without the table, or
a page of it, entering its context. Numbers are read leniently (`1,234.50`, `$12`, `(40)`, `12%`); a cell that isn't a
number is left out of arithmetic and counted in `skipped`.
"""

import re
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, Field

from src.documents.models import DocumentReadError

DEFAULT_ROWS = 50
MAX_ROWS = 200
#: A cell longer than this is cut, and a reply holding more characters than the cap loses rows from its end.
MAX_CELL_CHARS = 200
MAX_REPLY_CHARS = 20000
SAMPLE_ROWS = 3
EXAMPLE_VALUES = 5

NUMBER = re.compile(r"^\(?[-+]?[$€£₹]?\s*[-+]?\d[\d,\s]*(\.\d+)?\s*%?\)?$")


class TableQueryError(DocumentReadError):
    """The question doesn't fit the table (a column it hasn't); the message says what does."""


class Condition(BaseModel):
    column: str
    op: Literal["eq", "ne", "contains", "gt", "gte", "lt", "lte", "between"] = "eq"
    #: One value; two for `between` (inclusive).
    value: Union[str, int, float, list[Union[str, int, float]]]


class Aggregation(BaseModel):
    fn: Literal["sum", "count", "avg", "min", "max"]
    #: Not needed for `count`, which counts rows.
    column: Optional[str] = None
    #: The result column's name; `fn(column)` when left out.
    name: Optional[str] = None


class OrderBy(BaseModel):
    #: A column of the result: one of `select`, `group_by`, or an aggregation's name.
    column: str
    descending: bool = False


class TableQuery(BaseModel):
    where: list[Condition] = Field(default_factory=list)
    select: list[str] = Field(default_factory=list)
    group_by: list[str] = Field(default_factory=list)
    aggregate: list[Aggregation] = Field(default_factory=list)
    order_by: Optional[OrderBy] = None
    limit: int = DEFAULT_ROWS


def to_number(cell: str) -> Optional[Decimal]:
    text = cell.strip()
    if not NUMBER.match(text):
        return None
    negative = text.startswith("(") or text.startswith("-") or text.startswith("-", 1)
    digits = re.sub(r"[^\d.]", "", text)
    try:
        value = Decimal(digits)
    except InvalidOperation:
        return None
    return -value if negative else value


def describe_table(rows: list[list[str]], number: int) -> dict[str, Any]:
    header, body = _split(rows)
    columns = []
    for index, name in enumerate(header):
        cells = [_cell(row, index) for row in body]
        filled = [cell for cell in cells if cell.strip()]
        numbers = [n for n in (to_number(cell) for cell in filled) if n is not None]
        column: dict[str, Any] = {"name": name, "filled": len(filled)}
        if filled and len(numbers) >= len(filled) * 0.8:
            column.update(type="number", min=_plain(min(numbers)), max=_plain(max(numbers)), sum=_plain(sum(numbers, Decimal(0))))
        else:
            distinct = list(dict.fromkeys(filled))
            column.update(type="text", distinct=len(distinct), examples=[cell[:MAX_CELL_CHARS] for cell in distinct[:EXAMPLE_VALUES]])
        columns.append(column)
    return {
        "table": number,
        "total_rows": len(body),
        "columns": columns,
        "sample": [[cell[:MAX_CELL_CHARS] for cell in row] for row in body[:SAMPLE_ROWS]],
    }


def page_table(
    rows: list[list[str]], *, from_row: int = 1, max_rows: int = DEFAULT_ROWS, columns: Optional[list[str]] = None
) -> dict[str, Any]:
    """Data rows `from_row` (from 1, not counting the header) on, at most `max_rows`, and `next_row` where the next
    page starts."""
    header, body = _split(rows)
    indexes = [_column(header, name) for name in columns] if columns else list(range(len(header)))
    start = max(from_row, 1) - 1
    count = max(1, min(max_rows, MAX_ROWS))
    chosen = [[_cell(row, i)[:MAX_CELL_CHARS] for i in indexes] for row in body[start:start + count]]
    chosen = _within_reply_cap(chosen)
    end = start + len(chosen)
    return {
        "columns": [header[i] for i in indexes],
        "rows": chosen,
        "from_row": start + 1,
        "total_rows": len(body),
        "next_row": end + 1 if end < len(body) else None,
    }


def query_table(rows: list[list[str]], query: TableQuery) -> dict[str, Any]:
    header, body = _split(rows)
    conditions = [(_column(header, c.column), c) for c in query.where]
    matched = [row for row in body if all(_holds(_cell(row, i), c) for i, c in conditions)]

    if query.aggregate or query.group_by:
        names, result, skipped = _grouped(header, matched, query)
    else:
        indexes = [_column(header, name) for name in query.select] if query.select else list(range(len(header)))
        names = [header[i] for i in indexes]
        result = [[_cell(row, i) for i in indexes] for row in matched]
        skipped = 0

    if query.order_by:
        position = _result_column(names, query.order_by.column)
        result = _ordered(result, position, query.order_by.descending)

    limit = max(1, min(query.limit, MAX_ROWS))
    shown = _within_reply_cap([[cell[:MAX_CELL_CHARS] if isinstance(cell, str) else cell for cell in row] for row in result[:limit]])
    reply: dict[str, Any] = {
        "columns": names,
        "rows": shown,
        "matched_rows": len(matched),
        "total_rows": len(body),
        "truncated": len(shown) < len(result),
    }
    if skipped:
        reply["skipped"] = skipped
    return reply


def _grouped(header: list[str], matched: list[list[str]], query: TableQuery) -> tuple[list[str], list[list[Any]], int]:
    group_indexes = [_column(header, name) for name in query.group_by]
    aggregations = query.aggregate or [Aggregation(fn="count")]
    sources = [(a, _column(header, a.column) if a.column else None) for a in aggregations]
    for aggregation, index in sources:
        if index is None and aggregation.fn != "count":
            raise TableQueryError(f"{aggregation.fn} needs a column")
    names = [header[i] for i in group_indexes] + [a.name or (f"{a.fn}({a.column})" if a.column else a.fn) for a in aggregations]

    groups: dict[tuple[str, ...], list[list[str]]] = {}
    for row in matched:
        groups.setdefault(tuple(_cell(row, i) for i in group_indexes), []).append(row)
    if not group_indexes:
        groups = {(): matched}

    skipped = 0
    result: list[list[Any]] = []
    for key, members in groups.items():
        values: list[Any] = []
        for aggregation, index in sources:
            value, missed = _aggregate(aggregation.fn, [_cell(m, index) for m in members] if index is not None else members)
            skipped += missed
            values.append(value)
        result.append([*key, *values])
    return names, result, skipped


def _aggregate(fn: str, cells: list[Any]) -> tuple[Any, int]:
    if fn == "count":
        return len(cells), 0
    numbers = [n for n in (to_number(cell) for cell in cells) if n is not None]
    skipped = len(cells) - len(numbers)
    if not numbers:
        return None, skipped
    value = {"sum": sum(numbers), "avg": sum(numbers) / len(numbers), "min": min(numbers), "max": max(numbers)}[fn]
    return _plain(Decimal(value)), skipped


def _holds(cell: str, condition: Condition) -> bool:
    op, wanted = condition.op, condition.value
    if op == "between":
        if not isinstance(wanted, list) or len(wanted) != 2:
            raise TableQueryError("between needs a value of two items: [low, high]")
        low, high = to_number(str(wanted[0])), to_number(str(wanted[1]))
        number = to_number(cell)
        return number is not None and low is not None and high is not None and low <= number <= high
    if isinstance(wanted, list):
        raise TableQueryError(f"{op} takes one value")
    text = str(wanted)
    if op == "contains":
        return text.lower() in cell.lower()
    number, target = to_number(cell), to_number(text)
    if op in ("eq", "ne"):
        same = number == target if number is not None and target is not None else cell.strip().lower() == text.strip().lower()
        return same if op == "eq" else not same
    if number is None or target is None:
        return False
    return {"gt": number > target, "gte": number >= target, "lt": number < target, "lte": number <= target}[op]


def _ordered(rows: list[list[Any]], position: int, descending: bool) -> list[list[Any]]:
    def key(row: list[Any]) -> tuple[int, Any]:
        value = row[position]
        number = value if isinstance(value, (int, float)) else to_number(str(value)) if value is not None else None
        # Numbers sort before text; empty values last either way
        if number is not None:
            return (0, float(number))
        return (1, str(value).lower()) if value not in (None, "") else (2, "")

    present = [row for row in rows if row[position] not in (None, "")]
    absent = [row for row in rows if row[position] in (None, "")]
    return sorted(present, key=key, reverse=descending) + absent


def _within_reply_cap(rows: list[list[Any]]) -> list[list[Any]]:
    total = 0
    for count, row in enumerate(rows):
        total += sum(len(str(cell)) for cell in row)
        if total > MAX_REPLY_CHARS and count > 0:
            return rows[:count]
    return rows


def _split(rows: list[list[str]]) -> tuple[list[str], list[list[str]]]:
    return (rows[0], rows[1:]) if rows else ([], [])


def _cell(row: list[str], index: int) -> str:
    return row[index] if index < len(row) else ""


def _column(header: list[str], name: str) -> int:
    wanted = name.strip().lower()
    for index, column in enumerate(header):
        if column.strip().lower() == wanted:
            return index
    raise TableQueryError(f"No column '{name}'. The columns are: {', '.join(repr(c) for c in header)}")


def _result_column(names: list[str], name: str) -> int:
    wanted = name.strip().lower()
    for index, column in enumerate(names):
        if column.strip().lower() == wanted:
            return index
    raise TableQueryError(f"Can't order by '{name}'. The result's columns are: {', '.join(repr(c) for c in names)}")


def _plain(value: Decimal) -> Union[int, float]:
    """12.50 → 12.5, 12.0 → 12: the number as it would be written, without Decimal's trailing zeros."""
    rounded = round(value, 4)
    return int(rounded) if rounded == rounded.to_integral_value() else float(rounded)
