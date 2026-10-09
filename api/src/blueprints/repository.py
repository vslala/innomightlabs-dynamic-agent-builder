"""Blueprint deployments in the single table: pk=User#{email}, sk=BlueprintDeployment#{created_at}#{id}.

While one is applying it's also in gsi2 (gsi2_pk=BlueprintApplying, gsi2_sk=updated_at), so the reaper finds applies
that were interrupted without scanning the table. The entry goes when the item is saved with another status."""

from datetime import datetime, timezone
from typing import Optional

from boto3.dynamodb.conditions import Attr, Key

from src.blueprints.models import Deployment, DeploymentStatus
from src.config import settings
from src.db import get_dynamodb_resource
from src.utils.dynamodb import convert_decimals, convert_floats_to_decimals

SK_PREFIX = "BlueprintDeployment#"
APPLYING = "BlueprintApplying"


class DeploymentRepository:
    def __init__(self) -> None:
        self.table = get_dynamodb_resource().Table(settings.dynamodb_table)

    def save(self, deployment: Deployment) -> Deployment:
        deployment.updated_at = datetime.now(timezone.utc)
        item = {
            "pk": deployment.pk,
            "sk": deployment.sk,
            "entity_type": "BlueprintDeployment",
            **deployment.model_dump(mode="json"),
        }
        if deployment.status == DeploymentStatus.APPLYING:
            item["gsi2_pk"] = APPLYING
            item["gsi2_sk"] = deployment.updated_at.isoformat()
        self.table.put_item(Item=convert_floats_to_decimals(item))
        return deployment

    def list_applying(self, updated_before: datetime) -> list[Deployment]:
        """Applies still marked as running that haven't been saved since `updated_before`."""
        kwargs: dict = {
            "IndexName": "gsi2",
            "KeyConditionExpression": Key("gsi2_pk").eq(APPLYING) & Key("gsi2_sk").lt(updated_before.isoformat()),
        }
        found = []
        while True:
            response = self.table.query(**kwargs)
            found += [self._from_item(item) for item in response.get("Items", [])]
            if "LastEvaluatedKey" not in response:
                return found
            kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]

    def list_by_user(self, user_email: str) -> list[Deployment]:
        """Newest first."""
        kwargs: dict = {
            "KeyConditionExpression": Key("pk").eq(f"User#{user_email}") & Key("sk").begins_with(SK_PREFIX),
            "ScanIndexForward": False,
        }
        found = []
        while True:
            response = self.table.query(**kwargs)
            found += [self._from_item(item) for item in response.get("Items", [])]
            if "LastEvaluatedKey" not in response:
                return found
            kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]

    def list_for_kit(self, user_email: str, kit_id: str) -> list[Deployment]:
        """A kit's deployments, newest first."""
        return [deployment for deployment in self.list_by_user(user_email) if deployment.kit_id == kit_id]

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
        skip = ("pk", "sk", "entity_type", "gsi2_pk", "gsi2_sk")
        data = convert_decimals({k: v for k, v in item.items() if k not in skip})
        return Deployment.model_validate(data)
