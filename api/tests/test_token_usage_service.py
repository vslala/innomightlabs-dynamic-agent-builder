from datetime import datetime, timezone

from fastapi import HTTPException

from src.token_usage.models import TokenUsagePeriod
from src.token_usage.service import TokenUsageService
from tests.mock_data import TEST_USER_EMAIL, TEST_USER_EMAIL_2
from tests.test_analytics_router import create_agent as _create_agent


def test_get_usage_raises_404_for_unowned_agent(dynamodb_table):
    _create_agent("agent-1", owner_email=TEST_USER_EMAIL_2)
    service = TokenUsageService()

    try:
        service.get_usage(
            owner_email=TEST_USER_EMAIL,
            agent_id="agent-1",
            period=TokenUsagePeriod.DAY,
            from_at=None,
            to_at=None,
        )
        assert False, "Expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 404


def test_get_usage_raises_404_for_missing_agent(dynamodb_table):
    service = TokenUsageService()

    try:
        service.get_usage(
            owner_email=TEST_USER_EMAIL,
            agent_id="does-not-exist",
            period=TokenUsagePeriod.DAY,
            from_at=None,
            to_at=None,
        )
        assert False, "Expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 404


def test_get_usage_returns_range_and_respects_boundaries(dynamodb_table):
    _create_agent("agent-2")
    service = TokenUsageService()

    service.record_usage(
        owner_email=TEST_USER_EMAIL,
        agent_id="agent-2",
        llm_model="claude-sonnet-4-5",
        prompt_tokens=10,
        completion_tokens=5,
    )

    response = service.get_usage(
        owner_email=TEST_USER_EMAIL,
        agent_id="agent-2",
        period=TokenUsagePeriod.DAY,
        from_at=datetime.now(timezone.utc).replace(day=1),
        to_at=datetime.now(timezone.utc),
    )

    assert response.agent_id == "agent-2"
    assert response.period == TokenUsagePeriod.DAY
    assert len(response.series) == 1
    point = response.series[0]
    assert point.llm_model == "claude-sonnet-4-5"
    assert point.prompt_tokens == 10
    assert point.completion_tokens == 5
    assert point.total_tokens == 15
    assert point.call_count == 1


def test_get_usage_llm_model_filter_narrows_results(dynamodb_table):
    _create_agent("agent-3")
    service = TokenUsageService()

    service.record_usage(
        owner_email=TEST_USER_EMAIL,
        agent_id="agent-3",
        llm_model="claude-sonnet-4-5",
        prompt_tokens=10,
        completion_tokens=5,
    )
    service.record_usage(
        owner_email=TEST_USER_EMAIL,
        agent_id="agent-3",
        llm_model="gpt-5.5",
        prompt_tokens=100,
        completion_tokens=50,
    )

    response = service.get_usage(
        owner_email=TEST_USER_EMAIL,
        agent_id="agent-3",
        period=TokenUsagePeriod.DAY,
        from_at=None,
        to_at=None,
        llm_model="gpt-5.5",
    )

    assert len(response.series) == 1
    assert response.series[0].llm_model == "gpt-5.5"
    assert response.llm_model_filter == "gpt-5.5"


def test_model_switch_preserves_historical_buckets_per_model(dynamodb_table):
    """The AC-critical model-switch test: recording usage for model-b after
    model-a must never mutate model-a's historical buckets, and no live
    agent-model lookup should be involved (record_usage takes llm_model
    explicitly from the caller's per-call state, not from the agent record).
    """
    _create_agent("agent-4")
    service = TokenUsageService()

    service.record_usage(
        owner_email=TEST_USER_EMAIL,
        agent_id="agent-4",
        llm_model="model-a",
        prompt_tokens=10,
        completion_tokens=5,
    )

    response_before_switch = service.get_usage(
        owner_email=TEST_USER_EMAIL,
        agent_id="agent-4",
        period=TokenUsagePeriod.DAY,
        from_at=None,
        to_at=None,
    )
    model_a_point_before = next(
        point for point in response_before_switch.series if point.llm_model == "model-a"
    )
    assert model_a_point_before.total_tokens == 15
    assert model_a_point_before.call_count == 1

    # Simulate the agent's configured model being switched, then a new call.
    service.record_usage(
        owner_email=TEST_USER_EMAIL,
        agent_id="agent-4",
        llm_model="model-b",
        prompt_tokens=20,
        completion_tokens=10,
    )

    response_after_switch = service.get_usage(
        owner_email=TEST_USER_EMAIL,
        agent_id="agent-4",
        period=TokenUsagePeriod.DAY,
        from_at=None,
        to_at=None,
    )

    by_model = {point.llm_model: point for point in response_after_switch.series}
    assert by_model["model-a"].total_tokens == 15
    assert by_model["model-a"].call_count == 1
    assert by_model["model-b"].total_tokens == 30
    assert by_model["model-b"].call_count == 1


def test_get_usage_range_spans_month_and_year_boundary(dynamodb_table):
    _create_agent("agent-5")
    service = TokenUsageService()
    repo = service.token_usage_repository

    repo.increment_usage(
        agent_id="agent-5",
        llm_model="claude-sonnet-4-5",
        prompt_tokens=1,
        completion_tokens=1,
        occurred_at=datetime(2025, 12, 31, tzinfo=timezone.utc),
    )
    repo.increment_usage(
        agent_id="agent-5",
        llm_model="claude-sonnet-4-5",
        prompt_tokens=2,
        completion_tokens=2,
        occurred_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    response = service.get_usage(
        owner_email=TEST_USER_EMAIL,
        agent_id="agent-5",
        period=TokenUsagePeriod.MONTH,
        from_at=datetime(2025, 12, 1, tzinfo=timezone.utc),
        to_at=datetime(2026, 1, 31, tzinfo=timezone.utc),
    )

    assert sorted(point.period_key for point in response.series) == ["2025-12", "2026-01"]

    year_response = service.get_usage(
        owner_email=TEST_USER_EMAIL,
        agent_id="agent-5",
        period=TokenUsagePeriod.YEAR,
        from_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        to_at=datetime(2026, 12, 31, tzinfo=timezone.utc),
    )

    assert sorted(point.period_key for point in year_response.series) == ["2025", "2026"]
