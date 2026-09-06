from datetime import datetime, timezone
from typing import Optional

from ..config import settings
from ..db import get_dynamodb_resource
from .models import TokenUsagePeriod, TokenUsageRecord, format_period_key


class TokenUsageRepository:
    def __init__(self) -> None:
        self.dynamodb = get_dynamodb_resource()
        self.table = self.dynamodb.Table(settings.dynamodb_table)

    def increment_usage(
        self,
        *,
        agent_id: str,
        llm_model: str,
        prompt_tokens: int,
        completion_tokens: int,
        occurred_at: Optional[datetime] = None,
    ) -> None:
        """Increment the day/month/year buckets for one LLM call.

        Three plain update_item calls (not TransactWriteItems): the three
        buckets are independent counters where a missed increment self-heals
        on the next call -- this is telemetry, not a billing ledger, so
        transactional cost isn't justified.
        """
        moment = occurred_at or datetime.now(timezone.utc)
        for period in (TokenUsagePeriod.DAY, TokenUsagePeriod.MONTH, TokenUsagePeriod.YEAR):
            self._increment_bucket(
                agent_id=agent_id,
                period=period,
                period_key=format_period_key(period, moment),
                llm_model=llm_model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )

    def _increment_bucket(
        self,
        *,
        agent_id: str,
        period: TokenUsagePeriod,
        period_key: str,
        llm_model: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> TokenUsageRecord:
        total_tokens = prompt_tokens + completion_tokens
        now = datetime.now(timezone.utc).isoformat()
        pk = f"Agent#{agent_id}"
        sk = f"TokenUsage#{period.value}#{period_key}#{llm_model}"
        response = self.table.update_item(
            Key={"pk": pk, "sk": sk},
            UpdateExpression=(
                "SET prompt_tokens = if_not_exists(prompt_tokens, :zero) + :prompt_tokens, "
                "completion_tokens = if_not_exists(completion_tokens, :zero) + :completion_tokens, "
                "total_tokens = if_not_exists(total_tokens, :zero) + :total_tokens, "
                "call_count = if_not_exists(call_count, :zero) + :one, "
                "updated_at = :updated_at, "
                "created_at = if_not_exists(created_at, :updated_at), "
                "agent_id = if_not_exists(agent_id, :agent_id), "
                "period = if_not_exists(period, :period), "
                "period_key = if_not_exists(period_key, :period_key), "
                "llm_model = if_not_exists(llm_model, :llm_model), "
                "entity_type = if_not_exists(entity_type, :entity_type)"
            ),
            ExpressionAttributeValues={
                ":zero": 0,
                ":one": 1,
                ":prompt_tokens": prompt_tokens,
                ":completion_tokens": completion_tokens,
                ":total_tokens": total_tokens,
                ":updated_at": now,
                ":agent_id": agent_id,
                ":period": period.value,
                ":period_key": period_key,
                ":llm_model": llm_model,
                ":entity_type": "TokenUsage",
            },
            ReturnValues="ALL_NEW",
        )
        return TokenUsageRecord.from_dynamo_item(response["Attributes"])

    def get_usage_range(
        self,
        *,
        agent_id: str,
        period: TokenUsagePeriod,
        from_key: str,
        to_key: str,
        llm_model: Optional[str] = None,
    ) -> list[TokenUsageRecord]:
        """One bounded Query (pk + sk BETWEEN) returning all models' buckets
        for the requested period/date range; the per-model split is a
        FilterExpression on that single result set, not a separate physical
        layout per model.
        """
        pk = f"Agent#{agent_id}"
        sk_prefix = f"TokenUsage#{period.value}#"
        # High sentinel character so the upper bound envelops every llm_model
        # suffix for `to_key` (sk = TokenUsage#{period}#{period_key}#{llm_model}).
        high_sentinel = chr(0x10FFFF)
        query_kwargs: dict = {
            "KeyConditionExpression": "pk = :pk AND sk BETWEEN :sk_from AND :sk_to",
            "ExpressionAttributeValues": {
                ":pk": pk,
                ":sk_from": f"{sk_prefix}{from_key}",
                ":sk_to": f"{sk_prefix}{to_key}#{high_sentinel}",
            },
        }
        if llm_model:
            query_kwargs["FilterExpression"] = "llm_model = :llm_model"
            query_kwargs["ExpressionAttributeValues"][":llm_model"] = llm_model

        items: list[dict] = []
        response = self.table.query(**query_kwargs)
        items.extend(response.get("Items", []))
        while "LastEvaluatedKey" in response:
            query_kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
            response = self.table.query(**query_kwargs)
            items.extend(response.get("Items", []))

        return [TokenUsageRecord.from_dynamo_item(item) for item in items]
