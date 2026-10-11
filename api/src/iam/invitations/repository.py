from typing import Any, cast

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from ...accounts.models import Member
from ..repository import IamRepository
from .models import DeliveryStatus, Invite


class InvitationRepository:
    def __init__(self, iam: IamRepository | None = None) -> None:
        self.iam = iam or IamRepository()
        self.table = self.iam.table

    def get_item(self, key: dict[str, str]) -> dict[str, Any] | None:
        return cast(dict[str, Any] | None, self.table.get_item(Key=key, ConsistentRead=True).get("Item"))

    def account(self, account_id: str) -> dict[str, Any] | None:
        return self.get_item({"pk": f"Account#{account_id}", "sk": "Account#Metadata"})

    def get(self, account_id: str, invite_id: str) -> Invite | None:
        item = self.get_item({"pk": f"Account#{account_id}", "sk": f"Invite#{invite_id}"})
        return Invite.from_item(item) if item else None

    def query(self, **kwargs: Any) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        while True:
            response = self.table.query(**kwargs)
            items.extend(response.get("Items", []))
            if not response.get("LastEvaluatedKey"):
                return items
            kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]

    def prefix(self, account_id: str, prefix: str) -> list[dict[str, Any]]:
        return self.query(ConsistentRead=True, KeyConditionExpression=
                          Key("pk").eq(f"Account#{account_id}") & Key("sk").begins_with(prefix))

    def invites(self, account_id: str) -> list[Invite]:
        return [Invite.from_item(item) for item in self.prefix(account_id, "Invite#")]

    def by_hash(self, token_hash: str) -> Invite | None:
        token_key = f"InviteToken#{token_hash}"
        candidates = self.query(IndexName="gsi2", KeyConditionExpression=
                                Key("gsi2_pk").eq(token_key) & Key("gsi2_sk").eq(token_key))
        for candidate in candidates:
            # GSIs can retain the old hash after rotation/revocation; never trust their payload.
            item = self.get_item({"pk": candidate["pk"], "sk": candidate["sk"]})
            if item and item.get("token_hash") == token_hash:
                return Invite.from_item(item)
        return None

    def mark_delivery(self, invite: Invite, status: DeliveryStatus) -> bool:
        try:
            self.table.update_item(
                Key=invite.key, UpdateExpression="SET delivery_status = :delivery",
                ConditionExpression="token_hash = :hash AND #status = :pending AND delivery_status = :pending",
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={":hash": invite.token_hash, ":pending": "pending", ":delivery": status},
            )
            return True
        except ClientError as error:
            if error.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise

    # Operations for IamRepository.commit. Each carries the condition that makes its transaction fail
    # if what the service read has changed since.

    @staticmethod
    def put_invite(invite: Invite, previous: Invite | None = None) -> dict[str, Any]:
        """Create the invitation, or replace `previous` only while it still has the token and status read."""
        operation: dict[str, Any] = {"Item": invite.item(), "ConditionExpression": "attribute_not_exists(pk)"}
        if previous:
            operation.update(ConditionExpression="token_hash = :hash AND #status = :status",
                             ExpressionAttributeNames={"#status": "status"},
                             ExpressionAttributeValues={":hash": previous.token_hash, ":status": previous.status})
        return {"Put": operation}

    @classmethod
    def put_accepted_invite(cls, accepted: Invite, previous: Invite, now: float) -> dict[str, Any]:
        """As `put_invite`, and only while the invitation has not expired."""
        operation = cls.put_invite(accepted, previous)
        operation["Put"]["ConditionExpression"] += " AND #ttl > :time"
        operation["Put"]["ExpressionAttributeNames"]["#ttl"] = "ttl"
        operation["Put"]["ExpressionAttributeValues"][":time"] = int(now)
        return operation

    @staticmethod
    def put_member(member: Member) -> dict[str, Any]:
        return {"Put": {"Item": member.to_dynamo_item(), "ConditionExpression": "attribute_not_exists(pk)"}}

    @staticmethod
    def identity_unchanged(identity_item: dict[str, Any]) -> dict[str, Any]:
        """Guard the exact current stored email, not a normalized copy; change_email can race the read."""
        return {"ConditionCheck": {
            "Key": {"pk": identity_item["pk"], "sk": identity_item["sk"]},
            "ConditionExpression": "#status = :active AND email_verified = :verified AND email = :email",
            "ExpressionAttributeNames": {"#status": "status"},
            "ExpressionAttributeValues": {":active": "active", ":verified": True, ":email": identity_item["email"]},
        }}

    @staticmethod
    def member_active(member_item: dict[str, Any]) -> dict[str, Any]:
        return {"ConditionCheck": {
            "Key": {"pk": member_item["pk"], "sk": member_item["sk"]},
            "ConditionExpression": "#status = :active", "ExpressionAttributeNames": {"#status": "status"},
            "ExpressionAttributeValues": {":active": "active"},
        }}

    @staticmethod
    def accepted_by(invite: Invite, token_hash: str, user_id: str) -> dict[str, Any]:
        return {"ConditionCheck": {
            "Key": invite.key,
            "ConditionExpression": "token_hash = :hash AND #status = :accepted AND accepted_by = :user",
            "ExpressionAttributeNames": {"#status": "status"},
            "ExpressionAttributeValues": {":hash": token_hash, ":accepted": "accepted", ":user": user_id},
        }}
