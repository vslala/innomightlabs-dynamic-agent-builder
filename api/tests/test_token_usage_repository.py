from src.token_usage.models import TokenUsagePeriod
from src.token_usage.repository import TokenUsageRepository


def test_increment_usage_accumulates_across_day_month_year_buckets(dynamodb_table):
    repo = TokenUsageRepository()
    occurred_at = _dt("2026-03-15")

    repo.increment_usage(
        agent_id="agent-1",
        llm_model="claude-sonnet-4-5",
        prompt_tokens=10,
        completion_tokens=5,
        occurred_at=occurred_at,
    )
    repo.increment_usage(
        agent_id="agent-1",
        llm_model="claude-sonnet-4-5",
        prompt_tokens=20,
        completion_tokens=8,
        occurred_at=occurred_at,
    )

    day_records = repo.get_usage_range(
        agent_id="agent-1", period=TokenUsagePeriod.DAY, from_key="2026-03-15", to_key="2026-03-15"
    )
    month_records = repo.get_usage_range(
        agent_id="agent-1", period=TokenUsagePeriod.MONTH, from_key="2026-03", to_key="2026-03"
    )
    year_records = repo.get_usage_range(
        agent_id="agent-1", period=TokenUsagePeriod.YEAR, from_key="2026", to_key="2026"
    )

    for records in (day_records, month_records, year_records):
        assert len(records) == 1
        record = records[0]
        assert record.prompt_tokens == 30
        assert record.completion_tokens == 13
        assert record.total_tokens == 43
        assert record.call_count == 2


def test_increment_usage_keeps_independent_items_per_model(dynamodb_table):
    repo = TokenUsageRepository()
    occurred_at = _dt("2026-03-15")

    repo.increment_usage(
        agent_id="agent-1",
        llm_model="claude-sonnet-4-5",
        prompt_tokens=10,
        completion_tokens=5,
        occurred_at=occurred_at,
    )
    repo.increment_usage(
        agent_id="agent-1",
        llm_model="gpt-5.5",
        prompt_tokens=100,
        completion_tokens=50,
        occurred_at=occurred_at,
    )

    day_records = repo.get_usage_range(
        agent_id="agent-1", period=TokenUsagePeriod.DAY, from_key="2026-03-15", to_key="2026-03-15"
    )

    assert len(day_records) == 2
    by_model = {record.llm_model: record for record in day_records}
    assert by_model["claude-sonnet-4-5"].total_tokens == 15
    assert by_model["gpt-5.5"].total_tokens == 150


def test_get_usage_range_bounds_by_date_range(dynamodb_table):
    repo = TokenUsageRepository()

    repo.increment_usage(
        agent_id="agent-1",
        llm_model="claude-sonnet-4-5",
        prompt_tokens=1,
        completion_tokens=1,
        occurred_at=_dt("2026-01-01"),
    )
    repo.increment_usage(
        agent_id="agent-1",
        llm_model="claude-sonnet-4-5",
        prompt_tokens=2,
        completion_tokens=2,
        occurred_at=_dt("2026-06-15"),
    )
    repo.increment_usage(
        agent_id="agent-1",
        llm_model="claude-sonnet-4-5",
        prompt_tokens=3,
        completion_tokens=3,
        occurred_at=_dt("2026-12-31"),
    )

    day_records = repo.get_usage_range(
        agent_id="agent-1", period=TokenUsagePeriod.DAY, from_key="2026-03-01", to_key="2026-09-01"
    )
    assert [record.period_key for record in day_records] == ["2026-06-15"]

    month_records = repo.get_usage_range(
        agent_id="agent-1", period=TokenUsagePeriod.MONTH, from_key="2026-01", to_key="2026-06"
    )
    assert sorted(record.period_key for record in month_records) == ["2026-01", "2026-06"]


def test_get_usage_range_filters_by_llm_model(dynamodb_table):
    repo = TokenUsageRepository()
    occurred_at = _dt("2026-03-15")

    repo.increment_usage(
        agent_id="agent-1",
        llm_model="claude-sonnet-4-5",
        prompt_tokens=10,
        completion_tokens=5,
        occurred_at=occurred_at,
    )
    repo.increment_usage(
        agent_id="agent-1",
        llm_model="gpt-5.5",
        prompt_tokens=100,
        completion_tokens=50,
        occurred_at=occurred_at,
    )

    filtered = repo.get_usage_range(
        agent_id="agent-1",
        period=TokenUsagePeriod.DAY,
        from_key="2026-03-15",
        to_key="2026-03-15",
        llm_model="gpt-5.5",
    )

    assert len(filtered) == 1
    assert filtered[0].llm_model == "gpt-5.5"


def _dt(date_str: str):
    from datetime import datetime, timezone

    return datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
