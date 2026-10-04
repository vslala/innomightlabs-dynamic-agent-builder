"""Agent-scoped secret keys for the public /v1 API.

A secret key lets its holder chat with one agent as that agent's owner, so
only the SHA-256 of a secret is stored; the plaintext exists once, in the
create response. See docs/LLD-public-api-and-embeddable-widget.md.
"""

import hashlib
import logging
import secrets
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from pydantic import BaseModel, Field

from src.config import settings
from src.db import get_dynamodb_resource

log = logging.getLogger(__name__)

SECRET_KEY_PREFIX = "sk_live_"


def generate_secret() -> str:
    return f"{SECRET_KEY_PREFIX}{secrets.token_urlsafe(32)}"


def hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


class CreateSecretKeyRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Human-readable name for this key")


class UpdateSecretKeyRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    is_active: Optional[bool] = None


class SecretKeyResponse(BaseModel):
    key_id: str
    agent_id: str
    name: str
    key_hint: str
    is_active: bool
    created_at: datetime
    last_used_at: Optional[datetime] = None
    request_count: int = 0


class CreatedSecretKeyResponse(SecretKeyResponse):
    """Returned once, at creation: the only response that carries the secret."""

    secret: str


class AgentSecretKey(BaseModel):
    """
    DynamoDB Schema:
    - pk: Agent#{agent_id}
    - sk: SecretKey#{key_id}
    - GSI (gsi2): gsi2_pk=SecretKey#{sha256(secret)}, gsi2_sk=Agent#{agent_id}
    """

    key_id: str = Field(default_factory=lambda: str(uuid4()))
    agent_id: str
    name: str
    key_hash: str
    key_hint: str
    is_active: bool = True
    created_by: str  # Owner email; the key acts as this user
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_used_at: Optional[datetime] = None
    request_count: int = 0

    @classmethod
    def issue(cls, *, agent_id: str, name: str, created_by: str) -> tuple["AgentSecretKey", str]:
        """Create a key and return it with its one-time plaintext secret."""
        secret = generate_secret()
        key = cls(
            agent_id=agent_id,
            name=name,
            created_by=created_by,
            key_hash=hash_secret(secret),
            key_hint=f"{SECRET_KEY_PREFIX}…{secret[-4:]}",
        )
        return key, secret

    @property
    def pk(self) -> str:
        return f"Agent#{self.agent_id}"

    @property
    def sk(self) -> str:
        return f"SecretKey#{self.key_id}"

    def to_dynamo_item(self) -> dict[str, Any]:
        return {
            "pk": self.pk,
            "sk": self.sk,
            "gsi2_pk": f"SecretKey#{self.key_hash}",
            "gsi2_sk": f"Agent#{self.agent_id}",
            "key_id": self.key_id,
            "agent_id": self.agent_id,
            "name": self.name,
            "key_hash": self.key_hash,
            "key_hint": self.key_hint,
            "is_active": self.is_active,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat(),
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "request_count": self.request_count,
            "entity_type": "AgentSecretKey",
        }

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "AgentSecretKey":
        return cls(
            key_id=item["key_id"],
            agent_id=item["agent_id"],
            name=item["name"],
            key_hash=item["key_hash"],
            key_hint=item["key_hint"],
            is_active=item.get("is_active", True),
            created_by=item["created_by"],
            created_at=datetime.fromisoformat(item["created_at"]),
            last_used_at=datetime.fromisoformat(item["last_used_at"]) if item.get("last_used_at") else None,
            request_count=int(item.get("request_count", 0)),
        )

    def to_response(self) -> SecretKeyResponse:
        return SecretKeyResponse(**self.model_dump(exclude={"key_hash", "created_by"}))


class SecretKeyRepository:
    """
    Access Patterns:
        - create: PutItem
        - find_by_id: GetItem by pk + sk
        - find_by_hash: Query GSI2 by gsi2_pk
        - find_all_by_agent: Query by pk with sk prefix "SecretKey#"
        - update: UpdateItem of name / is_active only, so counters are never overwritten
        - record_request: atomic UpdateItem of request_count / last_used_at
        - delete_by_id: DeleteItem by pk + sk
    """

    GSI2_NAME = "gsi2"

    def __init__(self) -> None:
        self.table = get_dynamodb_resource().Table(settings.dynamodb_table)

    def create(self, key: AgentSecretKey) -> AgentSecretKey:
        self.table.put_item(Item=key.to_dynamo_item(), ConditionExpression="attribute_not_exists(pk)")
        log.info(f"Created secret key {key.key_id} for agent {key.agent_id}")
        return key

    def find_by_id(self, agent_id: str, key_id: str) -> Optional[AgentSecretKey]:
        item = self.table.get_item(Key=self._key(agent_id, key_id)).get("Item")
        return AgentSecretKey.from_dynamo_item(item) if item else None

    def find_by_hash(self, key_hash: str) -> Optional[AgentSecretKey]:
        response = self.table.query(
            IndexName=self.GSI2_NAME,
            KeyConditionExpression=Key("gsi2_pk").eq(f"SecretKey#{key_hash}"),
        )
        items = response.get("Items", [])
        return AgentSecretKey.from_dynamo_item(items[0]) if items else None

    def find_all_by_agent(self, agent_id: str) -> list[AgentSecretKey]:
        query_kwargs: dict[str, Any] = {
            "KeyConditionExpression": Key("pk").eq(f"Agent#{agent_id}") & Key("sk").begins_with("SecretKey#"),
        }
        items: list[dict[str, Any]] = []
        while True:
            response = self.table.query(**query_kwargs)
            items.extend(response.get("Items", []))
            if "LastEvaluatedKey" not in response:
                break
            query_kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
        return [AgentSecretKey.from_dynamo_item(item) for item in items]

    def update(
        self,
        agent_id: str,
        key_id: str,
        *,
        name: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> Optional[AgentSecretKey]:
        """Update only the provided fields. Returns None when the key does not exist."""
        changes = {field: value for field, value in {"name": name, "is_active": is_active}.items() if value is not None}
        if not changes:
            return self.find_by_id(agent_id, key_id)

        try:
            response = self.table.update_item(
                Key=self._key(agent_id, key_id),
                UpdateExpression="SET " + ", ".join(f"#{field} = :{field}" for field in changes),
                ConditionExpression="attribute_exists(pk)",
                ExpressionAttributeNames={f"#{field}": field for field in changes},
                ExpressionAttributeValues={f":{field}": value for field, value in changes.items()},
                ReturnValues="ALL_NEW",
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return None
            raise
        return AgentSecretKey.from_dynamo_item(response["Attributes"])

    def record_request(self, agent_id: str, key_id: str) -> None:
        """Count one request against the key. Never creates an item for an unknown key."""
        self.table.update_item(
            Key=self._key(agent_id, key_id),
            UpdateExpression="SET request_count = if_not_exists(request_count, :zero) + :one, last_used_at = :now",
            ConditionExpression="attribute_exists(pk)",
            ExpressionAttributeValues={":zero": 0, ":one": 1, ":now": datetime.now(timezone.utc).isoformat()},
        )

    def delete_by_id(self, agent_id: str, key_id: str) -> None:
        self.table.delete_item(Key=self._key(agent_id, key_id))
        log.info(f"Deleted secret key {key_id} for agent {agent_id}")

    def delete_all_by_agent(self, agent_id: str) -> None:
        for key in self.find_all_by_agent(agent_id):
            self.delete_by_id(agent_id, key.key_id)

    @staticmethod
    def _key(agent_id: str, key_id: str) -> dict[str, str]:
        return {"pk": f"Agent#{agent_id}", "sk": f"SecretKey#{key_id}"}
