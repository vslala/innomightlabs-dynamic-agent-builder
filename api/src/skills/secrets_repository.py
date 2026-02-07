"""DynamoDB repository for skill secrets."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from boto3.dynamodb.conditions import Key

from src.config import settings
from src.crypto import encrypt
from src.db import get_dynamodb_resource

from .secrets import SkillSecret

log = logging.getLogger(__name__)


class SkillSecretsRepository:
    def __init__(self):
        self.dynamodb = get_dynamodb_resource()
        self.table = self.dynamodb.Table(settings.dynamodb_table)

    def upsert_plaintext(
        self,
        *,
        owner_email: str,
        skill_id: str,
        name: str,
        value: str,
    ) -> SkillSecret:
        existing = self.get(owner_email, skill_id, name)
        secret = SkillSecret(
            owner_email=owner_email,
            skill_id=skill_id,
            name=name,
            encrypted_value=encrypt(value),
        )
        if existing:
            secret.created_at = existing.created_at
            secret.updated_at = datetime.now(timezone.utc)
        self.table.put_item(Item=secret.to_dynamo_item())
        return secret

    def get(self, owner_email: str, skill_id: str, name: str) -> Optional[SkillSecret]:
        resp = self.table.get_item(
            Key={
                "pk": f"Tenant#{owner_email}",
                "sk": f"SkillSecret#{skill_id}#{name}",
            }
        )
        item = resp.get("Item")
        return SkillSecret.from_dynamo_item(item) if item else None

    def list_for_skill(self, owner_email: str, skill_id: str) -> list[SkillSecret]:
        resp = self.table.query(
            KeyConditionExpression=Key("pk").eq(f"Tenant#{owner_email}")
            & Key("sk").begins_with(f"SkillSecret#{skill_id}#")
        )
        return [SkillSecret.from_dynamo_item(i) for i in resp.get("Items", [])]
