"""DynamoDB persistence for consent requests and standing consents.

Requests live in the conversation's partition under `CONSENT#`, beside its messages and turns, and are found by id
through `gsi2`. Every status change is a conditional write on the status it moves from, so a second click on a card
can never run the action twice.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from src.artifacts.storage import ArtifactStorage, member_prefix
from src.config import settings
from src.consent.models import (
    ConsentRequest,
    ConsentStatus,
    StandingConsent,
    TurnCheckpoint,
    decode_exchange,
    encode_exchange,
)
from src.db import get_dynamodb_resource

#: A checkpoint up to this size stays on the request's item; a bigger one goes to S3 (DynamoDB refuses items over
#: 400 KB), the same rule as big tool-job results.
INLINE_CHECKPOINT_MAX_BYTES = 200_000


class ConsentStateChanged(Exception):
    """The request was no longer in the state the caller expected: someone decided first, or it moved on."""


class ConsentRepository:
    def __init__(self, storage: ArtifactStorage | None = None):
        self.table = get_dynamodb_resource().Table(settings.dynamodb_table)
        self._storage = storage

    @property
    def storage(self) -> ArtifactStorage:
        # Made on first use: most checkpoints are small and never need S3.
        if self._storage is None:
            self._storage = ArtifactStorage()
        return self._storage

    def open(self, request: ConsentRequest) -> ConsentRequest:
        """Save a new request, retiring any pending one for the same action in this conversation."""
        for older in self.list_for_conversation(request.conversation_id):
            if older.key == request.key and older.status is ConsentStatus.PENDING:
                try:
                    self._replace(older.model_copy(update={"status": ConsentStatus.SUPERSEDED}), ConsentStatus.PENDING)
                except ConsentStateChanged:
                    pass
        self.table.put_item(
            Item=request.to_dynamo_item(),
            ConditionExpression="attribute_not_exists(pk) AND attribute_not_exists(sk)",
        )
        return request

    def get(self, consent_id: str) -> ConsentRequest | None:
        response = self.table.query(
            IndexName="gsi2",
            KeyConditionExpression=Key("gsi2_pk").eq(f"Consent#{consent_id}") & Key("gsi2_sk").eq(f"Consent#{consent_id}"),
            Limit=1,
        )
        items = response.get("Items", [])
        return ConsentRequest.from_dynamo_item(items[0]) if items else None

    def list_for_conversation(self, conversation_id: str) -> list[ConsentRequest]:
        """Every request in the conversation, newest first."""
        items: list[dict[str, Any]] = []
        query: dict[str, Any] = {
            "KeyConditionExpression": Key("pk").eq(f"CONVERSATION#{conversation_id}") & Key("sk").begins_with("CONSENT#"),
            "ScanIndexForward": False,
        }
        while True:
            response = self.table.query(**query)
            items.extend(response.get("Items", []))
            if "LastEvaluatedKey" not in response:
                break
            query["ExclusiveStartKey"] = response["LastEvaluatedKey"]
        return [ConsentRequest.from_dynamo_item(item) for item in items]

    def decide(
        self,
        request: ConsentRequest,
        *,
        approve: bool,
        by: str,
        edits: dict[str, Any] | None = None,
        always: bool = False,
        reason: str | None = None,
    ) -> ConsentRequest:
        decided = request.model_copy(
            update={
                "status": ConsentStatus.APPROVED if approve else ConsentStatus.REJECTED,
                "edits": edits or {},
                "always": always and approve,
                "reason": reason,
                "decided_by": by,
                "decided_at": datetime.now(timezone.utc),
            }
        )
        return self._replace(decided, ConsentStatus.PENDING)

    def mark_running(self, request: ConsentRequest) -> ConsentRequest:
        running = request.model_copy(update={"status": ConsentStatus.RUNNING, "started_at": datetime.now(timezone.utc)})
        return self._replace(running, ConsentStatus.APPROVED)

    def finish(self, request: ConsentRequest, *, succeeded: bool, result: str) -> ConsentRequest:
        finished = request.model_copy(
            update={
                "status": ConsentStatus.SUCCEEDED if succeeded else ConsentStatus.FAILED,
                "result": result,
                "completed_at": datetime.now(timezone.utc),
            }
        )
        return self._replace(finished, ConsentStatus.RUNNING)

    def keep_checkpoint(self, request: ConsentRequest, checkpoint: TurnCheckpoint) -> ConsentRequest:
        """Save the paused turn's exchange on its request, in S3 when it is too big for the item."""
        body = json.dumps(encode_exchange(checkpoint.exchange), ensure_ascii=False).encode("utf-8")
        if len(body) > INLINE_CHECKPOINT_MAX_BYTES:
            key = f"{member_prefix(request.account_id, request.owner_id)}/consents/{request.consent_id}/checkpoint.json"
            self.storage.put_artifact(key=key, body=body, content_type="application/json")
            checkpoint = checkpoint.model_copy(update={"exchange": None, "exchange_ref": key})
        kept = request.model_copy(update={"checkpoint": checkpoint})
        self.table.put_item(Item=kept.to_dynamo_item())
        return kept

    def exchange_of(self, checkpoint: TurnCheckpoint) -> list[dict[str, Any]] | None:
        if checkpoint.exchange is not None:
            return checkpoint.exchange
        if checkpoint.exchange_ref:
            try:
                exchange: list[dict[str, Any]] = decode_exchange(json.loads(self.storage.get_object_body(checkpoint.exchange_ref)))
            except Exception:
                return None
            return exchange
        return None

    def image_url(self, s3_key: str) -> str:
        return self.storage.presign_get_url(s3_key, disposition="inline")

    def _replace(self, request: ConsentRequest, expected: ConsentStatus) -> ConsentRequest:
        try:
            self.table.put_item(
                Item=request.to_dynamo_item(),
                ConditionExpression="#status = :expected",
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={":expected": expected.value},
            )
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                raise ConsentStateChanged(request.consent_id) from exc
            raise
        return request

    # Standing consents: Agent#{agent_id} / StandingConsent#{key}

    def standing(self, agent_id: str, key: str) -> StandingConsent | None:
        item = self.table.get_item(Key={"pk": f"Agent#{agent_id}", "sk": f"StandingConsent#{key}"}).get("Item")
        return StandingConsent.from_dynamo_item(item) if item else None

    def list_standing(self, agent_id: str) -> list[StandingConsent]:
        response = self.table.query(
            KeyConditionExpression=Key("pk").eq(f"Agent#{agent_id}") & Key("sk").begins_with("StandingConsent#"),
        )
        return [StandingConsent.from_dynamo_item(item) for item in response.get("Items", [])]

    def save_standing(self, consent: StandingConsent) -> StandingConsent:
        self.table.put_item(Item=consent.to_dynamo_item())
        return consent

    def forget_standing(self, agent_id: str, key: str) -> None:
        self.table.delete_item(Key={"pk": f"Agent#{agent_id}", "sk": f"StandingConsent#{key}"})

    def forget_standing_starting(self, agent_id: str, key_prefix: str) -> None:
        """Drop the agent's standing consents for a skill install or MCP connection it no longer has."""
        for consent in self.list_standing(agent_id):
            if consent.key.startswith(key_prefix):
                self.forget_standing(agent_id, consent.key)
