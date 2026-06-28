from __future__ import annotations

from boto3.dynamodb.conditions import Key

from src.artifacts.models import Artifact
from src.config import settings
from src.db import get_dynamodb_resource


class ArtifactRepository:
    def __init__(self):
        self.dynamodb = get_dynamodb_resource()
        self.table = self.dynamodb.Table(settings.dynamodb_table)

    def save(self, artifact: Artifact) -> Artifact:
        self.table.put_item(Item=artifact.to_dynamo_item())
        return artifact

    def find_by_id(self, owner_email: str, artifact_id: str) -> Artifact | None:
        response = self.table.query(
            IndexName="gsi2",
            KeyConditionExpression=Key("gsi2_pk").eq(f"Artifact#{artifact_id}")
            & Key("gsi2_sk").eq(f"User#{owner_email}"),
            Limit=1,
        )
        items = response.get("Items", [])
        return Artifact.from_dynamo_item(items[0]) if items else None

    def list_by_user(self, owner_email: str, limit: int = 50) -> list[Artifact]:
        response = self.table.query(
            KeyConditionExpression=Key("pk").eq(f"User#{owner_email}") & Key("sk").begins_with("Artifact#"),
            ScanIndexForward=False,
            Limit=max(1, min(100, limit)),
        )
        return [Artifact.from_dynamo_item(item) for item in response.get("Items", [])]
