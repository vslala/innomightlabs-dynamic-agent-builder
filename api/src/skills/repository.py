"""DynamoDB repository for tenant skills."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from boto3.dynamodb.conditions import Key

from src.config import settings
from src.db import get_dynamodb_resource

from .models import SkillDefinition, SkillStatus

log = logging.getLogger(__name__)


class SkillsRepository:
    def __init__(self):
        self.dynamodb = get_dynamodb_resource()
        self.table = self.dynamodb.Table(settings.dynamodb_table)

    def upsert(self, skill: SkillDefinition) -> SkillDefinition:
        existing = self.get(skill.owner_email, skill.skill_id, skill.version)
        if existing:
            skill.created_at = existing.created_at
            skill.updated_at = datetime.now(timezone.utc)
        self.table.put_item(Item=skill.to_dynamo_item())
        return skill

    def get(self, owner_email: str, skill_id: str, version: str) -> Optional[SkillDefinition]:
        resp = self.table.get_item(
            Key={
                "pk": f"Tenant#{owner_email}",
                "sk": f"Skill#{skill_id}#{version}",
            }
        )
        item = resp.get("Item")
        return SkillDefinition.from_dynamo_item(item) if item else None

    def list_by_owner(self, owner_email: str) -> list[SkillDefinition]:
        resp = self.table.query(
            KeyConditionExpression=Key("pk").eq(f"Tenant#{owner_email}")
            & Key("sk").begins_with("Skill#")
        )
        return [SkillDefinition.from_dynamo_item(i) for i in resp.get("Items", [])]

    def list_active(self, owner_email: str) -> list[SkillDefinition]:
        return [s for s in self.list_by_owner(owner_email) if s.status == SkillStatus.ACTIVE]

    def set_status(self, owner_email: str, skill_id: str, version: str, status: SkillStatus) -> SkillDefinition:
        skill = self.get(owner_email, skill_id, version)
        if not skill:
            raise ValueError("Skill not found")
        skill.status = status
        skill.updated_at = datetime.now(timezone.utc)
        self.upsert(skill)
        return skill
