import boto3
from typing import Optional
from datetime import datetime

from .models import User
from ..config import settings


class UserRepository:
    def __init__(self):
        self.dynamodb = boto3.resource("dynamodb", region_name=settings.aws_region)
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
