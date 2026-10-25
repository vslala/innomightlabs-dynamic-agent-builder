"""Asking a table questions: describe, page, filter, group, total."""

import pytest

from src.documents.outline import outline_from_markdown, weak_pages
from src.documents.models import ParsedPage
from src.documents.tables import Aggregation, Condition, OrderBy, TableQuery, TableQueryError, describe_table, page_table, query_table, to_number

ROWS = [
    ["Player", "Team", "Runs", "Date"],
    ["Madawa", "A", "1,200", "2026-01-01"],
    ["Kasun", "B", "$75.50", "2026-02-01"],
    ["Madawa", "B", "(30)", "2026-03-01"],
    ["Nimal", "A", "", "2026-04-01"],
]


@pytest.mark.parametrize("cell,number", [("1,234.50", 1234.5), ("$12", 12), ("(40)", -40), ("-7", -7), ("12%", 12), ("abc", None), ("", None)])
def test_numbers_are_read_however_they_are_written(cell, number):
    assert to_number(cell) == (None if number is None else pytest.approx(number))


def test_describe_gives_each_columns_type_and_the_totals():
    shape = describe_table(ROWS, 1)

    assert shape["total_rows"] == 4 and len(shape["sample"]) == 3
    runs = shape["columns"][2]
    assert (runs["type"], runs["filled"], runs["min"], runs["max"]) == ("number", 3, -30, 1200)
    assert shape["columns"][1]["distinct"] == 2 and shape["columns"][1]["type"] == "text"


def test_paging_reports_where_the_next_page_starts_and_can_pick_columns():
    first = page_table(ROWS, max_rows=3, columns=["player", "Runs"])
    last = page_table(ROWS, from_row=first["next_row"], max_rows=3)

    assert first["columns"] == ["Player", "Runs"] and first["rows"][0] == ["Madawa", "1,200"] and first["next_row"] == 4
    assert [r[0] for r in last["rows"]] == ["Nimal"] and last["next_row"] is None and last["total_rows"] == 4


def test_where_filters_text_and_numbers():
    result = query_table(ROWS, TableQuery(where=[Condition(column="Player", value="madawa"), Condition(column="Runs", op="gt", value=0)]))
    assert result["rows"] == [ROWS[1]] and result["matched_rows"] == 1 and result["total_rows"] == 4

    between = query_table(ROWS, TableQuery(where=[Condition(column="Runs", op="between", value=[50, 100])], select=["Player"]))
    assert between["rows"] == [["Kasun"]]


def test_group_and_aggregate_without_reading_the_rows():
    result = query_table(
        ROWS,
        TableQuery(group_by=["Player"], aggregate=[Aggregation(fn="sum", column="Runs", name="total"), Aggregation(fn="count")],
                   order_by=OrderBy(column="total", descending=True)),
    )

    assert result["columns"] == ["Player", "total", "count"]
    assert result["rows"] == [["Madawa", 1170, 2], ["Kasun", 75.5, 1], ["Nimal", None, 1]]
    assert result["skipped"] == 1, "the empty cell was left out of the sum"


def test_ordering_and_the_row_cap():
    result = query_table(ROWS, TableQuery(order_by=OrderBy(column="Runs", descending=True), limit=2))
    assert [r[0] for r in result["rows"]] == ["Madawa", "Kasun"] and result["truncated"] is True
    assert query_table(ROWS, TableQuery(limit=10_000))["truncated"] is False


def test_an_unknown_column_says_which_exist():
    with pytest.raises(TableQueryError, match="'Player', 'Team'"):
        query_table(ROWS, TableQuery(where=[Condition(column="Name", value="x")]))
    with pytest.raises(TableQueryError, match="needs a column"):
        query_table(ROWS, TableQuery(aggregate=[Aggregation(fn="sum")]))


def test_a_reply_never_holds_more_characters_than_the_cap():
    big = [["Text"], *[["x" * 200] for _ in range(200)]]
    assert len(page_table(big, max_rows=200)["rows"]) < 200


def test_headings_are_found_with_their_offsets_pages_and_not_inside_code():
    markdown = "# One\ntext\n```\n# not a heading\n```\n## Two\n"
    pages = [ParsedPage(1, "# One\ntext"), ParsedPage(2, "## Two")]

    entries = outline_from_markdown(markdown, pages)

    assert [(e.title, e.level, e.page) for e in entries] == [("One", 1, 1), ("Two", 2, 2)]
    assert markdown[entries[1].offset:].startswith("## Two")


def test_pages_with_hardly_any_text_are_weak():
    assert weak_pages([ParsedPage(1, "word " * 30), ParsedPage(2, "![img](x.png)"), ParsedPage(3, "")]) == [2, 3]
