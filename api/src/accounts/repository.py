from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from ..config import settings
from ..db import get_dynamodb_resource
from .models import ADMINISTRATOR_ACCESS, Account, Member, member_attachment_item


class AccountExists(Exception):
    """An account with this id already exists."""


class AccountRepository:
    """
    Key structure:
        Account#{account_id} / Account#Metadata                     the account
        Account#{account_id} / Member#{user_id}                     a membership
            gsi2: Identity#{user_id} / Membership#{account_id}      a person's accounts
        Account#{account_id} / Member#{user_id}#Group#{group_id}    the member's groups (KAN-77)
        Account#{account_id} / GroupMember#{group_id}#{user_id}     the same, read from the group
        Account#{account_id} / Attachment#member#{user_id}#{policy} policies attached to the member
        Identity#{user_id} / OwnedAccountCount                      accounts the person created, `n`
    """

    GSI2_NAME = "gsi2"

    def __init__(self) -> None:
        self.dynamodb = get_dynamodb_resource()
        self.table = self.dynamodb.Table(settings.dynamodb_table)

    def create(self, account: Account, admin: Member) -> None:
        """The account, its first admin and the owned-account count, all or nothing."""
        try:
            self.table.meta.client.transact_write_items(TransactItems=[
                {"Put": {"TableName": self.table.name, "Item": account.to_dynamo_item(),
                         "ConditionExpression": "attribute_not_exists(pk)"}},
                {"Put": {"TableName": self.table.name, "Item": admin.to_dynamo_item()}},
                {"Put": {"TableName": self.table.name,
                         "Item": member_attachment_item(account.account_id, admin.user_id,
                                                        ADMINISTRATOR_ACCESS, attached_by=admin.user_id)}},
                # KAN-85 adds the limit as a condition on this increment
                {"Update": {"TableName": self.table.name,
                            "Key": {"pk": f"Identity#{account.created_by}", "sk": "OwnedAccountCount"},
                            "UpdateExpression": "SET n = if_not_exists(n, :zero) + :one",
                            "ExpressionAttributeValues": {":zero": 0, ":one": 1}}},
            ])
        except ClientError as error:
            if error.response["Error"]["Code"] == "TransactionCanceledException":
                raise AccountExists(account.account_id) from error
            raise

    def get(self, account_id: str) -> Optional[Account]:
        item = self.table.get_item(Key={"pk": f"Account#{account_id}", "sk": "Account#Metadata"}).get("Item")
        return Account.from_dynamo_item(item) if item else None

    def get_many(self, account_ids: Iterable[str]) -> dict[str, Account]:
        ids = list(dict.fromkeys(account_ids))
        accounts: dict[str, Account] = {}
        for start in range(0, len(ids), 100):
            keys = [{"pk": f"Account#{aid}", "sk": "Account#Metadata"} for aid in ids[start:start + 100]]
            request: dict[str, Any] = {self.table.name: {"Keys": keys}}
            while request:
                response = self.dynamodb.batch_get_item(RequestItems=request)
                for item in response["Responses"].get(self.table.name, []):
                    account = Account.from_dynamo_item(item)
                    accounts[account.account_id] = account
                request = response.get("UnprocessedKeys") or {}
        return accounts

    def get_member(self, account_id: str, user_id: str) -> Optional[Member]:
        item = self.table.get_item(Key={"pk": f"Account#{account_id}", "sk": f"Member#{user_id}"}).get("Item")
        return Member.from_dynamo_item(item) if item else None

    def list_memberships(self, user_id: str) -> list[Member]:
        items = self._query(
            IndexName=self.GSI2_NAME,
            KeyConditionExpression=Key("gsi2_pk").eq(f"Identity#{user_id}")
            & Key("gsi2_sk").begins_with("Membership#"),
        )
        return [Member.from_dynamo_item(item) for item in items]

    def member_policies(self, account_id: str, user_id: str) -> list[str]:
        """Policies attached directly to the member (not through groups)."""
        items = self._query(
            KeyConditionExpression=Key("pk").eq(f"Account#{account_id}")
            & Key("sk").begins_with(f"Attachment#member#{user_id}#"),
        )
        return [str(item["policy"]) for item in items]

    def remove_member(self, account_id: str, user_id: str) -> None:
        """
        Delete the membership, the member's group memberships and attachments, and nothing else: the
        identity and its other accounts are untouched. The Member item goes last, so a failure part way
        leaves a member with fewer permissions, never stale permissions waiting for a re-invite.
        """
        pk = f"Account#{account_id}"
        attachments = self._query(
            KeyConditionExpression=Key("pk").eq(pk) & Key("sk").begins_with(f"Attachment#member#{user_id}#"),
        )
        groups = self._query(
            KeyConditionExpression=Key("pk").eq(pk) & Key("sk").begins_with(f"Member#{user_id}#Group#"),
        )
        keys = [{"pk": pk, "sk": item["sk"]} for item in attachments + groups]
        group_ids = [str(item["sk"]).split("#Group#", 1)[1] for item in groups]
        keys += [{"pk": pk, "sk": f"GroupMember#{group_id}#{user_id}"} for group_id in group_ids]
        with self.table.batch_writer() as batch:
            for key in keys:
                batch.delete_item(Key=key)
        self.table.delete_item(Key={"pk": pk, "sk": f"Member#{user_id}"})
        self.bump_authz_version(account_id)

    def bump_authz_version(self, account_id: str) -> None:
        self.table.update_item(
            Key={"pk": f"Account#{account_id}", "sk": "Account#Metadata"},
            UpdateExpression="SET authz_version = authz_version + :one, updated_at = :now",
            ConditionExpression="attribute_exists(pk)",
            ExpressionAttributeValues={":one": 1, ":now": datetime.now(timezone.utc).isoformat()},
        )

    def _query(self, **kwargs: Any) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        while True:
            response = self.table.query(**kwargs)
            items.extend(response.get("Items", []))
            if "LastEvaluatedKey" not in response:
                return items
            kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]

