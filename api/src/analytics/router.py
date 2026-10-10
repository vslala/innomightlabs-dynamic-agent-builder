"""Analytics API routes."""

from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query

from src.agents.access import agent_with
from src.agents.models import Agent

from src.analytics.models import (
    AnalyticsOverviewResponse,
    AnalyticsSource,
    AnalyticsTimeseriesResponse,
    TimeseriesBucket,
    TimeseriesMetric,
)
from src.analytics.service import AnalyticsService
from src.token_usage.models import TokenUsagePeriod, TokenUsageTimeseriesResponse
from src.token_usage.service import TokenUsageService

router = APIRouter(prefix="/analytics", tags=["analytics"])

# Analytics count conversations and messages, including the owner's own chats: contents-level access
can_read_agent = agent_with("agents:Get")


def get_analytics_service() -> AnalyticsService:
    return AnalyticsService()


def get_token_usage_service() -> TokenUsageService:
    return TokenUsageService()


def parse_sources(sources: Optional[str]) -> Optional[list[AnalyticsSource]]:
    if sources is None or not sources.strip():
        return None

    parsed: list[AnalyticsSource] = []
    seen: set[AnalyticsSource] = set()
    for raw_value in sources.split(","):
        value = raw_value.strip()
        if not value:
            continue
        try:
            source = AnalyticsSource(value)
        except ValueError as exc:
            from fastapi import HTTPException

            raise HTTPException(status_code=400, detail=f"Invalid source '{value}'") from exc
        if source not in seen:
            parsed.append(source)
            seen.add(source)
    return parsed or None


@router.get("/agents/{agent_id}/overview", response_model=AnalyticsOverviewResponse)
async def get_agent_overview(
    agent: Annotated[Agent, Depends(can_read_agent)],
    service: Annotated[AnalyticsService, Depends(get_analytics_service)],
    from_at: Annotated[Optional[datetime], Query(alias="from")] = None,
    to_at: Annotated[Optional[datetime], Query(alias="to")] = None,
    tz: str = Query(default="UTC"),
    sources: Optional[str] = Query(default=None),
) -> AnalyticsOverviewResponse:
    return service.get_overview(
        partition=agent.owner_partition,
        agent_id=agent.agent_id,
        from_at=from_at,
        to_at=to_at,
        tz_name=tz,
        sources=parse_sources(sources),
    )


@router.get("/agents/{agent_id}/timeseries", response_model=AnalyticsTimeseriesResponse)
async def get_agent_timeseries(
    agent: Annotated[Agent, Depends(can_read_agent)],
    metric: TimeseriesMetric,
    bucket: TimeseriesBucket,
    service: Annotated[AnalyticsService, Depends(get_analytics_service)],
    from_at: Annotated[Optional[datetime], Query(alias="from")] = None,
    to_at: Annotated[Optional[datetime], Query(alias="to")] = None,
    tz: str = Query(default="UTC"),
    sources: Optional[str] = Query(default=None),
) -> AnalyticsTimeseriesResponse:
    return service.get_timeseries(
        partition=agent.owner_partition,
        agent_id=agent.agent_id,
        metric=metric,
        bucket=bucket,
        from_at=from_at,
        to_at=to_at,
        tz_name=tz,
        sources=parse_sources(sources),
    )


@router.get("/agents/{agent_id}/token-usage", response_model=TokenUsageTimeseriesResponse)
async def get_agent_token_usage(
    agent: Annotated[Agent, Depends(can_read_agent)],
    period: TokenUsagePeriod,
    service: Annotated[TokenUsageService, Depends(get_token_usage_service)],
    llm_model: Optional[str] = Query(default=None),
    from_at: Annotated[Optional[datetime], Query(alias="from")] = None,
    to_at: Annotated[Optional[datetime], Query(alias="to")] = None,
) -> TokenUsageTimeseriesResponse:
    return service.get_usage(
        agent=agent,
        period=period,
        from_at=from_at,
        to_at=to_at,
        llm_model=llm_model,
    )
