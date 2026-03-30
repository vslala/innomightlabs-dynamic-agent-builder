"""Analytics API routes."""

from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, Request

from src.analytics.models import (
    AnalyticsOverviewResponse,
    AnalyticsSource,
    AnalyticsTimeseriesResponse,
    TimeseriesBucket,
    TimeseriesMetric,
)
from src.analytics.service import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["analytics"])


def get_analytics_service() -> AnalyticsService:
    return AnalyticsService()


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
    request: Request,
    agent_id: str,
    service: Annotated[AnalyticsService, Depends(get_analytics_service)],
    from_at: Annotated[Optional[datetime], Query(alias="from")] = None,
    to_at: Annotated[Optional[datetime], Query(alias="to")] = None,
    tz: str = Query(default="UTC"),
    sources: Optional[str] = Query(default=None),
) -> AnalyticsOverviewResponse:
    return service.get_overview(
        owner_email=request.state.user_email,
        agent_id=agent_id,
        from_at=from_at,
        to_at=to_at,
        tz_name=tz,
        sources=parse_sources(sources),
    )


@router.get("/agents/{agent_id}/timeseries", response_model=AnalyticsTimeseriesResponse)
async def get_agent_timeseries(
    request: Request,
    agent_id: str,
    metric: TimeseriesMetric,
    bucket: TimeseriesBucket,
    service: Annotated[AnalyticsService, Depends(get_analytics_service)],
    from_at: Annotated[Optional[datetime], Query(alias="from")] = None,
    to_at: Annotated[Optional[datetime], Query(alias="to")] = None,
    tz: str = Query(default="UTC"),
    sources: Optional[str] = Query(default=None),
) -> AnalyticsTimeseriesResponse:
    return service.get_timeseries(
        owner_email=request.state.user_email,
        agent_id=agent_id,
        metric=metric,
        bucket=bucket,
        from_at=from_at,
        to_at=to_at,
        tz_name=tz,
        sources=parse_sources(sources),
    )
