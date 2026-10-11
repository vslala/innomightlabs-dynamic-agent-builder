from datetime import datetime, timezone
from typing import Optional

from boto3.dynamodb.conditions import Key

from src.builder.models import BuilderSession
from src.config import settings
from src.db import get_dynamodb_resource
from src.utils.dynamodb import convert_decimals, convert_floats_to_decimals

SK_PREFIX = "BuilderSession#"


class BuilderSessionRepository:
    def __init__(self) -> None:
        self.table = get_dynamodb_resource().Table(settings.dynamodb_table)

    def save(self, session: BuilderSession) -> BuilderSession:
        session.updated_at = datetime.now(timezone.utc)
        item = {"pk": session.pk, "sk": session.sk, "entity_type": "BuilderSession", **session.model_dump(mode="json")}
        self.table.put_item(Item=convert_floats_to_decimals(item))
        return session

    def find(self, partition: str, conversation_id: str) -> Optional[BuilderSession]:
        """The session in this member's partition (`Owner.member_pk`)."""
        item = self.table.get_item(Key={"pk": partition, "sk": f"{SK_PREFIX}{conversation_id}"}).get("Item")
        return self._from_item(item) if item else None

    def list_in(self, partition: str) -> list[BuilderSession]:
        """The member's sessions, newest first."""
        kwargs: dict = {"KeyConditionExpression": Key("pk").eq(partition) & Key("sk").begins_with(SK_PREFIX)}
        items: list[dict] = []
        while True:
            response = self.table.query(**kwargs)
            items += response.get("Items", [])
            if "LastEvaluatedKey" not in response:
                break
            kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
        sessions = [self._from_item(item) for item in items]
        return sorted(sessions, key=lambda session: session.created_at, reverse=True)

    @staticmethod
    def _from_item(item: dict) -> BuilderSession:
        return BuilderSession.model_validate(
            convert_decimals({k: v for k, v in item.items() if k not in ("pk", "sk", "entity_type")})
        )
