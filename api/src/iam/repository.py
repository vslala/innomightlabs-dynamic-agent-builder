from typing import Any, Iterable, Optional

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from ..config import settings
from ..db import get_dynamodb_resource
from .models import AccountIam, Attachment, CustomPolicy, Group, PolicyVersion, now

# A transaction holds at most 100 items; one is the account's version bump
MAX_CHANGE_ITEMS = 99


class ConcurrentChange(Exception):
    """The account's permissions changed after they were read; the change was not made."""


class IamRepository:
    """Reads an account's IAM state at one version, and writes changes only if it is still that version.

    Every write goes through `commit`, which bumps `Account.authz_version` in the same transaction,
    conditional on the version that was read. A change is therefore always judged (the caller's rights,
    the escalation guard) on the state it actually changes, never on one another admin has just changed.
    """

    def __init__(self) -> None:
        self.table = get_dynamodb_resource().Table(settings.dynamodb_table)

    def load(self, account_id: str) -> Optional[AccountIam]:
        account = self.table.get_item(Key={"pk": f"Account#{account_id}", "sk": "Account#Metadata"}).get("Item")
        if account is None:
            return None
        members: dict[str, str] = {}
        group_members: set[tuple[str, str]] = set()
        for item in self._prefix(account_id, "Member#"):
            if "#Group#" in item["sk"]:
                group_members.add((item["group_id"], item["user_id"]))
            else:
                members[item["user_id"]] = item.get("status", "active")
        groups = {item["group_id"]: Group.from_item(item) for item in self._prefix(account_id, "Group#")}
        attachments = {item["sk"]: Attachment.from_item(item) for item in self._prefix(account_id, "Attachment#")}
        return AccountIam(
            account_id=account_id,
            owner_id=account.get("owner_id", account["created_by"]),
            authz_version=int(account.get("authz_version", 1)),
            members=members,
            groups=groups,
            group_members=frozenset(group_members),
            attachments=attachments,
            policies=self._policies(account_id),
        )

    def commit(self, state: AccountIam, put: Iterable[dict[str, Any]] = (),
               delete: Iterable[dict[str, Any]] = ()) -> None:
        puts, deletes = list(put), [{"pk": key["pk"], "sk": key["sk"]} for key in delete]
        if len(puts) + len(deletes) > MAX_CHANGE_ITEMS:
            raise ValueError(f"A change can touch at most {MAX_CHANGE_ITEMS} items")
        name = self.table.name
        try:
            self.table.meta.client.transact_write_items(TransactItems=[
                *({"Put": {"TableName": name, "Item": item}} for item in puts),
                *({"Delete": {"TableName": name, "Key": key}} for key in deletes),
                {"Update": {
                    "TableName": name,
                    "Key": {"pk": f"Account#{state.account_id}", "sk": "Account#Metadata"},
                    "UpdateExpression": "SET authz_version = :next, updated_at = :now",
                    "ConditionExpression": "authz_version = :seen",
                    "ExpressionAttributeValues": {":seen": state.authz_version, ":next": state.authz_version + 1,
                                                  ":now": now()},
                }},
            ])
        except ClientError as error:
            if error.response["Error"]["Code"] == "TransactionCanceledException":
                raise ConcurrentChange(state.account_id) from error
            raise

    def _policies(self, account_id: str) -> dict[str, CustomPolicy]:
        metadata: dict[str, dict[str, Any]] = {}
        versions: dict[str, dict[int, PolicyVersion]] = {}
        for item in self._prefix(account_id, "Policy#"):
            if "#v" in item["sk"]:
                version = PolicyVersion.from_item(item)
                versions.setdefault(item["policy_id"], {})[version.version] = version
            else:
                metadata[item["policy_id"]] = item
        return {policy_id: CustomPolicy.from_item(item, versions.get(policy_id, {}))
                for policy_id, item in metadata.items()}

    def _prefix(self, account_id: str, prefix: str) -> list[dict[str, Any]]:
        query: dict[str, Any] = {
            "KeyConditionExpression": Key("pk").eq(f"Account#{account_id}") & Key("sk").begins_with(prefix),
        }
        items: list[dict[str, Any]] = []
        while True:
            response = self.table.query(**query)
            items.extend(response.get("Items", []))
            if "LastEvaluatedKey" not in response:
                return items
            query["ExclusiveStartKey"] = response["LastEvaluatedKey"]
