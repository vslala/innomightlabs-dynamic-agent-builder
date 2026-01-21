from datetime import datetime
from typing import Optional

import boto3

from .models import Subscription
from ...config import settings


class SubscriptionRepository:
    def __init__(self) -> None:
        self.dynamodb = boto3.resource("dynamodb", region_name=settings.aws_region)
        self.table = self.dynamodb.Table(settings.dynamodb_table)

    def upsert(self, subscription: Subscription) -> Subscription:
        subscription.updated_at = datetime.utcnow().isoformat()
        self.table.put_item(Item=subscription.to_dynamo_item())
        return subscription

    def get_by_id(self, user_email: str, subscription_id: str) -> Optional[Subscription]:
        response = self.table.get_item(
            Key={
                "pk": f"User#{user_email}",
                "sk": f"Subscription#{subscription_id}",
            }
        )
        item = response.get("Item")
        if item:
            return Subscription.from_dynamo_item(item)
        return None
