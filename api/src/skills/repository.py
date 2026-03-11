from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from boto3.dynamodb.conditions import Key

from src.config import settings
from src.crypto import decrypt, encrypt
from src.db import get_dynamodb_resource
from src.skills.models import AgentSkill

log = logging.getLogger(__name__)


class AgentSkillRepository:
    def __init__(self):
        self.dynamodb = get_dynamodb_resource()
        self.table = self.dynamodb.Table(settings.dynamodb_table)

    def save(self, skill: AgentSkill) -> AgentSkill:
        existing = self.find_by_id(skill.agent_id, skill.skill_id)
        if existing:
            skill.installed_at = existing.installed_at
            skill.updated_at = datetime.now(timezone.utc)

        self.table.put_item(Item=skill.to_dynamo_item())
        return skill

    def find_by_id(self, agent_id: str, skill_id: str) -> Optional[AgentSkill]:
        response = self.table.get_item(
            Key={
                "pk": f"Agent#{agent_id}",
                "sk": f"Skill#{skill_id}",
            }
        )
        item = response.get("Item")
        if not item:
            return None
        return AgentSkill.from_dynamo_item(item)

    def list_by_agent(self, agent_id: str) -> list[AgentSkill]:
        response = self.table.query(
            KeyConditionExpression=Key("pk").eq(f"Agent#{agent_id}") & Key("sk").begins_with("Skill#")
        )
        items = response.get("Items", [])
        return [AgentSkill.from_dynamo_item(item) for item in items]

    def delete(self, agent_id: str, skill_id: str) -> bool:
        try:
            self.table.delete_item(
                Key={
                    "pk": f"Agent#{agent_id}",
                    "sk": f"Skill#{skill_id}",
                }
            )
            return True
        except Exception as e:
            log.error("Failed deleting AgentSkill %s/%s: %s", agent_id, skill_id, e, exc_info=True)
            return False

    def upsert_with_config(
        self,
        *,
        agent_id: str,
        skill_id: str,
        namespace: str,
        skill_name: str,
        skill_description: str,
        enabled: bool,
        installed_by: str,
        plain_config: dict[str, Any],
        secret_config: dict[str, Any],
        secret_fields: list[str],
    ) -> AgentSkill:
        encrypted_secrets = encrypt(json.dumps(secret_config, ensure_ascii=True)) if secret_config else ""
        item = AgentSkill(
            agent_id=agent_id,
            skill_id=skill_id,
            namespace=namespace,
            skill_name=skill_name,
            skill_description=skill_description,
            enabled=enabled,
            installed_by=installed_by,
            config=plain_config,
            encrypted_secrets=encrypted_secrets,
            secret_fields=secret_fields,
        )
        return self.save(item)

    def get_runtime_config(self, installed_skill: AgentSkill) -> dict[str, Any]:
        config = dict(installed_skill.config)
        if installed_skill.encrypted_secrets:
            try:
                secrets_map = json.loads(decrypt(installed_skill.encrypted_secrets))
                if isinstance(secrets_map, dict):
                    config.update(secrets_map)
            except Exception as e:
                log.error(
                    "Failed decrypting secrets for skill %s/%s: %s",
                    installed_skill.agent_id,
                    installed_skill.skill_id,
                    e,
                    exc_info=True,
                )
                raise
        return config


def get_agent_skill_repository() -> AgentSkillRepository:
    return AgentSkillRepository()
