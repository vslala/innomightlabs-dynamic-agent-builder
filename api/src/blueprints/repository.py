"""Blueprint deployments in the single table: pk=User#{email}, sk=BlueprintDeployment#{created_at}#{id}."""

from typing import Optional

from boto3.dynamodb.conditions import Attr, Key

from src.blueprints.models import Deployment
from src.config import settings
from src.db import get_dynamodb_resource
from src.utils.dynamodb import convert_decimals, convert_floats_to_decimals

SK_PREFIX = "BlueprintDeployment#"


class DeploymentRepository:
    def __init__(self) -> None:
        self.table = get_dynamodb_resource().Table(settings.dynamodb_table)

    def save(self, deployment: Deployment) -> Deployment:
        item = {
            "pk": deployment.pk,
            "sk": deployment.sk,
            "entity_type": "BlueprintDeployment",
            **deployment.model_dump(mode="json"),
        }
        self.table.put_item(Item=convert_floats_to_decimals(item))
        return deployment

    def list_by_user(self, user_email: str) -> list[Deployment]:
        """Newest first."""
        response = self.table.query(
            KeyConditionExpression=Key("pk").eq(f"User#{user_email}") & Key("sk").begins_with(SK_PREFIX),
            ScanIndexForward=False,
        )
        return [self._from_item(item) for item in response.get("Items", [])]

    def find_by_id(self, user_email: str, deployment_id: str) -> Optional[Deployment]:
        # A user's deployments are few, so a filtered query is enough without an index.
        kwargs = {
            "KeyConditionExpression": Key("pk").eq(f"User#{user_email}") & Key("sk").begins_with(SK_PREFIX),
            "FilterExpression": Attr("deployment_id").eq(deployment_id),
        }
        while True:
            response = self.table.query(**kwargs)
            for item in response.get("Items", []):
                return self._from_item(item)
            if "LastEvaluatedKey" not in response:
                return None
            kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]

    @staticmethod
    def _from_item(item: dict) -> Deployment:
        data = convert_decimals({k: v for k, v in item.items() if k not in ("pk", "sk", "entity_type")})
        return Deployment.model_validate(data)
