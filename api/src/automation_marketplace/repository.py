from __future__ import annotations

from datetime import datetime, timezone

from boto3.dynamodb.conditions import Attr, Key

from src.automation_marketplace.models import (
    MarketplaceAutomationImportSession,
    MarketplaceAutomationStatus,
    MarketplaceAutomationTemplate,
)
from src.config import settings
from src.db import get_dynamodb_resource


class AutomationMarketplaceRepository:
    def __init__(self):
        self.dynamodb = get_dynamodb_resource()
        self.table = self.dynamodb.Table(settings.dynamodb_table)

    def save(self, template: MarketplaceAutomationTemplate) -> MarketplaceAutomationTemplate:
        existing = self.find_by_id(template.template_id)
        if existing:
            template.created_at = existing.created_at
            template.updated_at = datetime.now(timezone.utc)
        self.table.put_item(Item=template.to_dynamo_item())
        return template

    def find_by_id(self, template_id: str) -> MarketplaceAutomationTemplate | None:
        response = self.table.get_item(
            Key={"pk": "MarketplaceAutomation", "sk": f"Template#{template_id}"}
        )
        item = response.get("Item")
        return MarketplaceAutomationTemplate.from_dynamo_item(item) if item else None

    def list_templates(
        self,
        *,
        status: MarketplaceAutomationStatus | None = MarketplaceAutomationStatus.PUBLISHED,
    ) -> list[MarketplaceAutomationTemplate]:
        response = self.table.query(
            KeyConditionExpression=Key("pk").eq("MarketplaceAutomation")
            & Key("sk").begins_with("Template#")
        )
        templates = [
            MarketplaceAutomationTemplate.from_dynamo_item(item)
            for item in response.get("Items", [])
            if item.get("entity_type") == "MarketplaceAutomationTemplate"
        ]
        if status:
            templates = [template for template in templates if template.status == status]
        return sorted(templates, key=_marketplace_rank_key)

    def list_latest_published(
        self,
        *,
        query: str | None = None,
        limit: int = 20,
    ) -> list[MarketplaceAutomationTemplate]:
        templates = self.list_templates(status=MarketplaceAutomationStatus.PUBLISHED)
        latest = [template for template in templates if template.latest_template_id == template.template_id]
        if query:
            normalized = query.strip().lower()
            latest = [template for template in latest if _matches_query(template, normalized)]
        return latest[: max(1, min(limit, 50))]

    def find_latest_for_source_automation(
        self,
        *,
        source_automation_id: str,
        publisher_user_email: str,
    ) -> MarketplaceAutomationTemplate | None:
        response = self.table.query(
            KeyConditionExpression=Key("pk").eq("MarketplaceAutomation")
            & Key("sk").begins_with("Template#"),
            FilterExpression=Attr("source_automation_id").eq(source_automation_id)
            & Attr("publisher_user_email").eq(publisher_user_email),
        )
        templates = [
            MarketplaceAutomationTemplate.from_dynamo_item(item)
            for item in response.get("Items", [])
            if item.get("entity_type") == "MarketplaceAutomationTemplate"
        ]
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

    def save_import_session(
        self,
        session: MarketplaceAutomationImportSession,
    ) -> MarketplaceAutomationImportSession:
        session.refresh_expiry()
        self.table.put_item(Item=session.to_dynamo_item())
        return session

    def find_import_session(
        self,
        *,
        owner_email: str,
        session_id: str,
    ) -> MarketplaceAutomationImportSession | None:
        response = self.table.get_item(
            Key={
                "pk": f"User#{owner_email}",
                "sk": f"AutomationMarketplaceImportSession#{session_id}",
            }
        )
        item = response.get("Item")
        return MarketplaceAutomationImportSession.from_dynamo_item(item) if item else None

    def delete_import_session(self, *, owner_email: str, session_id: str) -> None:
        self.table.delete_item(
            Key={
                "pk": f"User#{owner_email}",
                "sk": f"AutomationMarketplaceImportSession#{session_id}",
            }
        )


def get_automation_marketplace_repository() -> AutomationMarketplaceRepository:
    return AutomationMarketplaceRepository()


def _marketplace_rank_key(template: MarketplaceAutomationTemplate) -> tuple[int, float, str]:
    return (-template.import_count, -template.created_at.timestamp(), template.title.lower())


def _matches_query(template: MarketplaceAutomationTemplate, query: str) -> bool:
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
