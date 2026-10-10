from typing import Any, Iterable, Optional

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from ..config import settings
from ..db import get_dynamodb_resource
from .models import Account, Member


class AccountExists(Exception):
    """An account with this id already exists."""


class AccountRepository:
    """
    Accounts and memberships. Groups, policies and attachments, and removing members, belong to
    `iam.service`, the only writer of permissions.

    Key structure:
        Account#{account_id} / Account#Metadata                     the account
        Account#{account_id} / Member#{user_id}                     a membership
            gsi2: Identity#{user_id} / Membership#{account_id}      a person's accounts
        Account#{account_id} / Attachment#member#{user_id}#{policy} policies attached to the member
        Identity#{user_id} / OwnedAccountCount                      accounts the person created, `n`
    """

    GSI2_NAME = "gsi2"

    def __init__(self) -> None:
        self.dynamodb = get_dynamodb_resource()
        self.table = self.dynamodb.Table(settings.dynamodb_table)

    def create(self, account: Account, owner: Member) -> None:
        """The account, its owner's membership and the owned-account count, all or nothing. The owner
        needs no attachment: owning the account makes them its admin."""
        try:
            self.table.meta.client.transact_write_items(TransactItems=[
                {"Put": {"TableName": self.table.name, "Item": account.to_dynamo_item(),
                         "ConditionExpression": "attribute_not_exists(pk)"}},
                {"Put": {"TableName": self.table.name, "Item": owner.to_dynamo_item()}},
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

    def members(self, account_id: str) -> list[Member]:
        items = self._query(
            KeyConditionExpression=Key("pk").eq(f"Account#{account_id}") & Key("sk").begins_with("Member#"),
        )
        # The same prefix holds each member's group links (Member#{uid}#Group#{gid})
        return [Member.from_dynamo_item(item) for item in items if "#Group#" not in item["sk"]]

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

    def _query(self, **kwargs: Any) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        while True:
            response = self.table.query(**kwargs)
            items.extend(response.get("Items", []))
            if "LastEvaluatedKey" not in response:
                return items
            kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]

