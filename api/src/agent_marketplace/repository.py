from __future__ import annotations

from datetime import datetime, timezone

from boto3.dynamodb.conditions import Attr, Key

from src.agent_marketplace.models import MarketplaceAgentStatus, MarketplaceAgentTemplate
from src.config import settings
from src.db import get_dynamodb_resource


class AgentMarketplaceRepository:
    def __init__(self):
        self.dynamodb = get_dynamodb_resource()
        self.table = self.dynamodb.Table(settings.dynamodb_table)

    def save(self, template: MarketplaceAgentTemplate) -> MarketplaceAgentTemplate:
        existing = self.find_by_id(template.template_id)
        if existing:
            template.created_at = existing.created_at
            template.updated_at = datetime.now(timezone.utc)
        self.table.put_item(Item=template.to_dynamo_item())
        return template

    def find_by_id(self, template_id: str) -> MarketplaceAgentTemplate | None:
        response = self.table.get_item(
            Key={"pk": "MarketplaceAgent", "sk": f"Template#{template_id}"}
        )
        item = response.get("Item")
        return MarketplaceAgentTemplate.from_dynamo_item(item) if item else None

    def list_templates(
        self,
        *,
        status: MarketplaceAgentStatus | None = MarketplaceAgentStatus.PUBLISHED,
    ) -> list[MarketplaceAgentTemplate]:
        response = self.table.query(
            KeyConditionExpression=Key("pk").eq("MarketplaceAgent")
            & Key("sk").begins_with("Template#")
        )
        templates = [MarketplaceAgentTemplate.from_dynamo_item(item) for item in response.get("Items", [])]
        if status:
            templates = [template for template in templates if template.status == status]
        return sorted(templates, key=_marketplace_rank_key)

    def list_latest_published(
        self,
        *,
        query: str | None = None,
        limit: int = 20,
    ) -> list[MarketplaceAgentTemplate]:
        templates = self.list_templates(status=MarketplaceAgentStatus.PUBLISHED)
        latest = [
            template
            for template in templates
            if template.latest_template_id == template.template_id
        ]
        if query:
            normalized = query.strip().lower()
            latest = [template for template in latest if _matches_query(template, normalized)]
        return latest[: max(1, min(limit, 50))]

    def find_latest_for_source_agent(
        self,
        *,
        source_agent_id: str,
        publisher_user_email: str,
    ) -> MarketplaceAgentTemplate | None:
        response = self.table.query(
            KeyConditionExpression=Key("pk").eq("MarketplaceAgent")
            & Key("sk").begins_with("Template#"),
            FilterExpression=Attr("source_agent_id").eq(source_agent_id)
            & Attr("publisher_user_email").eq(publisher_user_email),
        )
        templates = [MarketplaceAgentTemplate.from_dynamo_item(item) for item in response.get("Items", [])]
        if not templates:
            return None
        return max(templates, key=lambda template: template.template_version)

    def increment_import_count(self, template_id: str) -> None:
        template = self.find_by_id(template_id)
        if not template:
            return
        template.import_count += 1
        template.updated_at = datetime.now(timezone.utc)
        self.table.put_item(Item=template.to_dynamo_item())


def get_agent_marketplace_repository() -> AgentMarketplaceRepository:
    return AgentMarketplaceRepository()


def _marketplace_rank_key(template: MarketplaceAgentTemplate) -> tuple[int, float, str]:
    return (
        -template.import_count,
        -template.created_at.timestamp(),
        template.title.lower(),
    )


def _matches_query(template: MarketplaceAgentTemplate, query: str) -> bool:
    haystack = " ".join(
        [
            template.title,
            template.short_description,
            template.full_description,
            template.publisher_display_name,
            " ".join(template.tags),
        ]
    ).lower()
    return query in haystack
