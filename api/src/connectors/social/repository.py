from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, List, Optional

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from src.config import settings
from src.connectors.social.models import SocialAccount, SocialAccountStatus, external_key, grant_key
from src.db import get_dynamodb_resource

log = logging.getLogger(__name__)


class SocialAccountRepository:
    """
    Key structure (single table):
        pk: Account#{account_id}   sk: SocialAccount#{social_account_id}
        pk: Account#{account_id}   sk: SocialAccountExternal#{network}#{external_id}  -> social_account_id
        pk: SocialGrant#{network}#{grant_id}   sk: Account#{account_id}#{social_account_id}

    The second item is a uniqueness guard: an identity is connected once per account, and connecting it again
    (to refresh a token) updates the account it names instead of making a duplicate. The third, written only for
    networks that name who granted access, finds the accounts of one grant across InnomightLabs accounts.
    """

    def __init__(self) -> None:
        self.table = get_dynamodb_resource().Table(settings.dynamodb_table)

    def list(self, account_id: str) -> list[SocialAccount]:
        response = self.table.query(
            KeyConditionExpression=Key("pk").eq(f"Account#{account_id}") & Key("sk").begins_with("SocialAccount#")
        )
        accounts = [SocialAccount.from_dynamo_item(item) for item in response.get("Items", [])]
        return sorted(accounts, key=lambda account: account.created_at)

    def get(self, account_id: str, social_account_id: str) -> Optional[SocialAccount]:
        item = self.table.get_item(
            Key={"pk": f"Account#{account_id}", "sk": f"SocialAccount#{social_account_id}"}
        ).get("Item")
        return SocialAccount.from_dynamo_item(item) if item else None

    def connect(self, account: SocialAccount) -> SocialAccount:
        """Save a newly connected identity: a new account, or the existing one for the same identity, refreshed."""
        for _ in range(2):
            existing = self._existing(account)
            if existing:
                return self._refresh(existing, account)
            try:
                self.table.meta.client.transact_write_items(TransactItems=[
                    {"Put": {"TableName": self.table.name, "Item": account.to_dynamo_item(),
                             "ConditionExpression": "attribute_not_exists(pk)"}},
                    {"Put": {"TableName": self.table.name,
                             "Item": {**external_key(account.account_id, account.network, account.external_id),
                                      "social_account_id": account.social_account_id},
                             "ConditionExpression": "attribute_not_exists(pk)"}},
                    *self._grant_puts(account),
                ])
                return account
            except ClientError as error:
                # Two connects of one identity raced: the loser refreshes the winner's account
                if error.response["Error"]["Code"] != "TransactionCanceledException":
                    raise
        raise RuntimeError("Could not save the social account")

    def update_credentials(self, account: SocialAccount, encrypted_credentials: str,
                           token_expires_at: Optional[datetime]) -> SocialAccount:
        """Save a renewed token and nothing else, and only while the account is still connected."""
        now = datetime.now(timezone.utc)
        self.table.update_item(
            Key={"pk": account.pk, "sk": account.sk},
            UpdateExpression="SET encrypted_credentials = :credentials, token_expires_at = :expires, updated_at = :now",
            ConditionExpression="attribute_exists(pk)",
            ExpressionAttributeValues={":credentials": encrypted_credentials, ":now": now.isoformat(),
                                       ":expires": token_expires_at.isoformat() if token_expires_at else None},
        )
        return account.model_copy(update={"encrypted_credentials": encrypted_credentials,
                                          "token_expires_at": token_expires_at, "updated_at": now})

    def mark_needs_reconnect(self, account: SocialAccount, reason: str) -> None:
        self.table.update_item(
            Key={"pk": account.pk, "sk": account.sk},
            UpdateExpression="SET #status = :status, last_error = :reason, updated_at = :now",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={":status": SocialAccountStatus.NEEDS_RECONNECT.value, ":reason": reason,
                                       ":now": datetime.now(timezone.utc).isoformat()},
        )

    def delete(self, account: SocialAccount) -> None:
        self.table.meta.client.transact_write_items(TransactItems=[
            {"Delete": {"TableName": self.table.name, "Key": {"pk": account.pk, "sk": account.sk}}},
            {"Delete": {"TableName": self.table.name,
                        "Key": external_key(account.account_id, account.network, account.external_id)}},
            *self._grant_deletes(account),
        ])

    def for_grant(self, network: str, grant_id: str) -> List[SocialAccount]:
        """Every account one person's grant connected, in any InnomightLabs account."""
        partition = grant_key(network, grant_id, "", "")["pk"]
        items: List[dict[str, Any]] = []
        query: dict[str, Any] = {"KeyConditionExpression": Key("pk").eq(partition)}
        while True:
            response = self.table.query(**query)
            items.extend(response.get("Items", []))
            if "LastEvaluatedKey" not in response:
                break
            query["ExclusiveStartKey"] = response["LastEvaluatedKey"]
        accounts = (self.get(str(item["account_id"]), str(item["social_account_id"])) for item in items)
        return [account for account in accounts if account is not None]

    def _existing(self, account: SocialAccount) -> Optional[SocialAccount]:
        reference = self.table.get_item(
            Key=external_key(account.account_id, account.network, account.external_id)
        ).get("Item")
        return self.get(account.account_id, str(reference["social_account_id"])) if reference else None

    def _refresh(self, existing: SocialAccount, connected: SocialAccount) -> SocialAccount:
        refreshed = existing.model_copy(update={
            "handle": connected.handle,
            "display_name": connected.display_name,
            "avatar_url": connected.avatar_url,
            "status": SocialAccountStatus.ACTIVE,
            "encrypted_credentials": connected.encrypted_credentials,
            "scopes": connected.scopes,
            "token_expires_at": connected.token_expires_at,
            "last_error": None,
            # Someone else may have reconnected the same Page: the grant is theirs now
            "grant_id": connected.grant_id or existing.grant_id,
            "connected_by": connected.connected_by,
            "updated_at": datetime.now(timezone.utc),
        })
        moved = existing.grant_id and existing.grant_key() != refreshed.grant_key()
        self.table.meta.client.transact_write_items(TransactItems=[
            {"Put": {"TableName": self.table.name, "Item": refreshed.to_dynamo_item()}},
            *(self._grant_deletes(existing) if moved else []),
            *self._grant_puts(refreshed),
        ])
        return refreshed

    def _grant_puts(self, account: SocialAccount) -> List[dict[str, Any]]:
        key = account.grant_key()
        if key is None:
            return []
        return [{"Put": {"TableName": self.table.name, "Item": {
            **key, "entity_type": "SocialGrant", "account_id": account.account_id,
            "social_account_id": account.social_account_id,
        }}}]

    def _grant_deletes(self, account: SocialAccount) -> List[dict[str, Any]]:
        key = account.grant_key()
        return [{"Delete": {"TableName": self.table.name, "Key": key}}] if key else []
