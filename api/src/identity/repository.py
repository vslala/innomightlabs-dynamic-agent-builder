from datetime import datetime, timezone
from typing import Any, Optional

from botocore.exceptions import ClientError

from ..config import settings
from ..db import get_dynamodb_resource
from .models import Identity, IdentityStatus, email_index_key


class EmailTaken(Exception):
    """Another identity already signs in with this email."""


class IdentityRepository:
    """
    Key structure:
        Identity#{user_id} / Identity#Metadata   the identity
        Email#{normalized_email} / Email#Identity  -> user_id, written in the same transaction
    """

    def __init__(self) -> None:
        self.table = get_dynamodb_resource().Table(settings.dynamodb_table)

    def get(self, user_id: str) -> Optional[Identity]:
        item = self.table.get_item(Key={"pk": f"Identity#{user_id}", "sk": "Identity#Metadata"}).get("Item")
        return Identity.from_dynamo_item(item) if item else None

    def find_by_email(self, email: str) -> Optional[Identity]:
        index = self.table.get_item(Key=email_index_key(email)).get("Item")
        return self.get(str(index["user_id"])) if index else None

    def create(self, identity: Identity) -> Identity:
        """Both items or neither: two sign-ups racing on one email produce one identity."""
        index_item: dict[str, Any] = {**email_index_key(identity.email), "user_id": identity.user_id}
        if identity.ttl is not None:
            index_item["ttl"] = identity.ttl
        try:
            self.table.meta.client.transact_write_items(TransactItems=[
                {"Put": {"TableName": self.table.name, "Item": index_item,
                         "ConditionExpression": "attribute_not_exists(pk)"}},
                {"Put": {"TableName": self.table.name, "Item": identity.to_dynamo_item(),
                         "ConditionExpression": "attribute_not_exists(pk)"}},
            ])
        except ClientError as error:
            if error.response["Error"]["Code"] == "TransactionCanceledException":
                raise EmailTaken(identity.email) from error
            raise
        return identity

    def find_or_create(self, email: str, name: str, **profile: Any) -> tuple[Identity, bool]:
        """The identity for this email and whether it was just created."""
        existing = self.find_by_email(email)
        if existing:
            return existing, False
        try:
            return self.create(Identity(email=email, name=name, **profile)), True
        except EmailTaken:
            winner = self.find_by_email(email)
            if winner is None:
                raise
            return winner, False

    def change_email(self, user_id: str, old_email: str, new_email: str) -> None:
        """Move the index entry and the identity's email together, refusing an email someone else has."""
        try:
            self.table.meta.client.transact_write_items(TransactItems=[
                {"Delete": {"TableName": self.table.name, "Key": email_index_key(old_email),
                            "ConditionExpression": "user_id = :uid",
                            "ExpressionAttributeValues": {":uid": user_id}}},
                {"Put": {"TableName": self.table.name, "Item": {**email_index_key(new_email), "user_id": user_id},
                         "ConditionExpression": "attribute_not_exists(pk)"}},
                {"Update": {"TableName": self.table.name,
                            "Key": {"pk": f"Identity#{user_id}", "sk": "Identity#Metadata"},
                            "UpdateExpression": "SET email = :email, email_verified = :verified, updated_at = :now",
                            "ConditionExpression": "attribute_exists(pk)",
                            "ExpressionAttributeValues": {":email": new_email, ":verified": False, ":now": _now()}}},
            ])
        except ClientError as error:
            if error.response["Error"]["Code"] == "TransactionCanceledException":
                raise EmailTaken(new_email) from error
            raise

    def update_profile(self, user_id: str, *, name: str, picture: Optional[str], email_verified: bool) -> None:
        self._set(user_id, name=name, picture=picture, email_verified=email_verified)

    def update_stripe_customer_id(self, user_id: str, customer_id: str) -> None:
        self._set(user_id, stripe_customer_id=customer_id)

    def set_last_account(self, user_id: str, account_id: str) -> None:
        self._set(user_id, last_account_id=account_id)

    def mark_inactive(self, user_id: str) -> None:
        self._set(user_id, status=IdentityStatus.INACTIVE.value, deletion_requested_at=_now())

    def _set(self, user_id: str, **fields: Any) -> None:
        fields["updated_at"] = _now()
        self.table.update_item(
            Key={"pk": f"Identity#{user_id}", "sk": "Identity#Metadata"},
            UpdateExpression="SET " + ", ".join(f"#{name} = :{name}" for name in fields),
            ConditionExpression="attribute_exists(pk)",
            ExpressionAttributeNames={f"#{name}": name for name in fields},
            ExpressionAttributeValues={f":{name}": value for name, value in fields.items()},
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
