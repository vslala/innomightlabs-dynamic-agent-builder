from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from src.config import settings
from src.connectors.social.models import SocialAccount, SocialAccountStatus, external_key
from src.db import get_dynamodb_resource

log = logging.getLogger(__name__)


class SocialAccountRepository:
    """
    Key structure (single table):
        pk: Account#{account_id}   sk: SocialAccount#{social_account_id}
        pk: Account#{account_id}   sk: SocialAccountExternal#{network}#{external_id}  -> social_account_id

    The second item is a uniqueness guard: an identity is connected once per account, and connecting it again
    (to refresh a token) updates the account it names instead of making a duplicate.
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
                ])
                return account
            except ClientError as error:
                # Two connects of one identity raced: the loser refreshes the winner's account
                if error.response["Error"]["Code"] != "TransactionCanceledException":
                    raise
        raise RuntimeError("Could not save the social account")

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
        ])

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
            "connected_by": connected.connected_by,
            "updated_at": datetime.now(timezone.utc),
        })
        self.table.put_item(Item=refreshed.to_dynamo_item())
        return refreshed
