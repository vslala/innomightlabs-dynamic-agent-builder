from typing import Optional
from datetime import datetime

from .models import User, UserStatus
from ..config import settings
from ..db import get_dynamodb_resource


class UserRepository:
    def __init__(self):
        self.dynamodb = get_dynamodb_resource()
        self.table = self.dynamodb.Table(settings.dynamodb_table)

    def get_by_email(self, email: str) -> Optional[User]:
        response = self.table.get_item(
            Key={
                "pk": f"User#{email}",
                "sk": "User#Metadata",
            }
        )
        item = response.get("Item")
        if item:
            return User.from_dynamo_item(item)
        return None

    def create_or_update(self, user: User) -> User:
        existing = self.get_by_email(user.email)

        if existing:
            user.created_at = existing.created_at
            user.updated_at = datetime.utcnow().isoformat()
            if user.stripe_customer_id is None:
                user.stripe_customer_id = existing.stripe_customer_id
            if user.refresh_token is None:
                user.refresh_token = existing.refresh_token

        self.table.put_item(Item=user.to_dynamo_item())
        return user

    def update_refresh_token(self, email: str, refresh_token: str) -> bool:
        try:
            self.table.update_item(
                Key={
                    "pk": f"User#{email}",
                    "sk": "User#Metadata",
                },
                UpdateExpression="SET refresh_token = :rt, updated_at = :ua",
                ExpressionAttributeValues={
                    ":rt": refresh_token,
                    ":ua": datetime.utcnow().isoformat(),
                },
            )
            return True
        except Exception:
            return False

    def delete(self, email: str) -> bool:
        try:
            self.table.delete_item(
                Key={
                    "pk": f"User#{email}",
                    "sk": "User#Metadata",
                }
            )
            return True
        except Exception:
            return False

    def update_stripe_customer_id(self, email: str, customer_id: str) -> bool:
        try:
            self.table.update_item(
                Key={
                    "pk": f"User#{email}",
                    "sk": "User#Metadata",
                },
                UpdateExpression="SET stripe_customer_id = :cid, updated_at = :ua",
                ExpressionAttributeValues={
                    ":cid": customer_id,
                    ":ua": datetime.utcnow().isoformat(),
                },
            )
            return True
        except Exception:
            return False

    def mark_inactive(self, email: str) -> bool:
        try:
            self.table.update_item(
                Key={
                    "pk": f"User#{email}",
                    "sk": "User#Metadata",
                },
                UpdateExpression="SET #status = :status, deletion_requested_at = :timestamp, updated_at = :ua",
                ExpressionAttributeNames={
                    "#status": "status"
                },
                ExpressionAttributeValues={
                    ":status": UserStatus.INACTIVE.value,
                    ":timestamp": datetime.utcnow().isoformat(),
                    ":ua": datetime.utcnow().isoformat(),
                },
            )
            return True
        except Exception:
            return False
