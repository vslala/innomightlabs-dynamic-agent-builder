import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException

from ..agents.repository import AgentRepository
from .models import TokenUsagePeriod, TokenUsagePoint, TokenUsageTimeseriesResponse, format_period_key
from .repository import TokenUsageRepository

log = logging.getLogger(__name__)

DEFAULT_RANGE_DAYS: dict[TokenUsagePeriod, int] = {
    TokenUsagePeriod.DAY: 30,
    TokenUsagePeriod.MONTH: 365,
    TokenUsagePeriod.YEAR: 365 * 5,
}


class TokenUsageService:
    def __init__(
        self,
        *,
        token_usage_repository: Optional[TokenUsageRepository] = None,
        agent_repository: Optional[AgentRepository] = None,
    ) -> None:
        self.token_usage_repository = token_usage_repository or TokenUsageRepository()
        self.agent_repository = agent_repository or AgentRepository()

    def record_usage(
        self,
        *,
        owner_email: str,
        agent_id: str,
        llm_model: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> None:
        """Record usage for one LLM call.

        No ownership check here -- this is called from the already-authorized
        conversation path (agentic_loop.py), unlike get_usage below which is
        reached directly from an API request.
        """
        self.token_usage_repository.increment_usage(
            agent_id=agent_id,
            llm_model=llm_model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

    def get_usage(
        self,
        *,
        owner_email: str,
        agent_id: str,
        period: TokenUsagePeriod,
        from_at: Optional[datetime],
        to_at: Optional[datetime],
        llm_model: Optional[str] = None,
    ) -> TokenUsageTimeseriesResponse:
        """Fetch a token usage time series for one agent.

        Must check agent ownership via AgentRepository.find_agent_by_id --
        this data is keyed by agent_id alone and doesn't get scoping "for
        free" the way analytics/service.py does by filtering conversations
        first.
        """
        if self.agent_repository.find_agent_by_id(agent_id, owner_email) is None:
            raise HTTPException(status_code=404, detail="Agent not found")

        normalized_from, normalized_to = self._normalize_range(period, from_at, to_at)
        from_key = format_period_key(period, normalized_from)
        to_key = format_period_key(period, normalized_to)

        records = self.token_usage_repository.get_usage_range(
            agent_id=agent_id,
            period=period,
            from_key=from_key,
            to_key=to_key,
            llm_model=llm_model,
        )

        series = [
            TokenUsagePoint(
                period_key=record.period_key,
                period_start=self._period_start(period, record.period_key),
                llm_model=record.llm_model,
                prompt_tokens=record.prompt_tokens,
                completion_tokens=record.completion_tokens,
                total_tokens=record.total_tokens,
                call_count=record.call_count,
            )
            for record in sorted(records, key=lambda record: (record.period_key, record.llm_model))
        ]

        return TokenUsageTimeseriesResponse(
            agent_id=agent_id,
            period=period,
            from_at=normalized_from,
            to_at=normalized_to,
            llm_model_filter=llm_model,
            series=series,
        )

    def _normalize_range(
        self,
        period: TokenUsagePeriod,
        from_at: Optional[datetime],
        to_at: Optional[datetime],
    ) -> tuple[datetime, datetime]:
        now = datetime.now(timezone.utc)
        normalized_to = self._ensure_utc(to_at) if to_at else now
        normalized_from = (
            self._ensure_utc(from_at)
            if from_at
            else normalized_to - timedelta(days=DEFAULT_RANGE_DAYS[period])
        )
        if normalized_from >= normalized_to:
            raise HTTPException(status_code=400, detail="'from' must be earlier than 'to'")
        return normalized_from, normalized_to

    @staticmethod
    def _ensure_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _period_start(period: TokenUsagePeriod, period_key: str) -> datetime:
        if period == TokenUsagePeriod.DAY:
            parsed = datetime.strptime(period_key, "%Y-%m-%d")
        elif period == TokenUsagePeriod.MONTH:
            parsed = datetime.strptime(period_key, "%Y-%m")
        else:
            parsed = datetime.strptime(period_key, "%Y")
        return parsed.replace(tzinfo=timezone.utc)
