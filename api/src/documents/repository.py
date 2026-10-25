"""DynamoDB access for Document rows.

    - List an owner's documents: Query pk=DocumentOwner#{kind}#{owner_id}, sk begins_with Document#
    - Get one: GetItem pk, sk=Document#{document_id}
    - Claim for processing: UpdateItem, if in flight and no worker's lease is live
    - Save progress: UpdateItem of the worker's fields, if still in flight (a delete in between wins)
    - Renew the lease while working: UpdateItem lease_expires_at, if still in flight
    - Mark sent with a message: UpdateItem attached_at, if it was waiting to be sent
    - In flight, for the reaper: Scan entity_type=Document, status in flight (few at any time, like crawl jobs)
    - Waiting to be sent, for the unsent sweep: Scan entity_type=Document, owner_kind, attached_at = 0
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from boto3.dynamodb.conditions import Attr, Key
from botocore.exceptions import ClientError

from src.config import settings
from src.db import get_dynamodb_resource
from src.documents.models import IN_FLIGHT, Document, DocumentOwner, DocumentStatus, OwnerKind

log = logging.getLogger(__name__)

IN_FLIGHT_VALUES = [status.value for status in IN_FLIGHT]
#: Fields a worker never writes: the owner sets them while the worker reads the file, and a worker's save from its
#: copy at claim time would otherwise undo them (a document sent with a message while it was still being read).
NOT_THE_WORKERS = {"pk", "sk", "attached_at"}


def _conditional_failed(exc: ClientError) -> bool:
    return exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException"


class DocumentRepository:
    def __init__(self) -> None:
        self.table = get_dynamodb_resource().Table(settings.dynamodb_table)

    def save(self, document: Document) -> Document:
        self.table.put_item(Item=document.to_dynamo_item())
        return document

    def save_in_flight(self, document: Document) -> Optional[Document]:
        """Save a worker's progress, unless the document stopped being in flight (it is being deleted)."""
        fields = [(key, value) for key, value in document.to_dynamo_item().items() if key not in NOT_THE_WORKERS]
        # `#w`/`:w`: boto3 names the condition's own placeholders `#n0`, `:v0`...
        try:
            self.table.update_item(
                Key={"pk": document.pk, "sk": document.sk},
                UpdateExpression="SET " + ", ".join(f"#w{n} = :w{n}" for n in range(len(fields))),
                ConditionExpression=Attr("status").is_in(IN_FLIGHT_VALUES),
                ExpressionAttributeNames={f"#w{n}": key for n, (key, _) in enumerate(fields)},
                ExpressionAttributeValues={f":w{n}": value for n, (_, value) in enumerate(fields)},
            )
        except ClientError as exc:
            if _conditional_failed(exc):
                return None
            raise
        return document

    def get(self, owner: DocumentOwner, document_id: str) -> Optional[Document]:
        item = self.table.get_item(Key={"pk": owner.pk, "sk": f"Document#{document_id}"}).get("Item")
        if not item or item.get("account_id") != owner.account_id:
            return None
        return Document.from_dynamo_item(item)

    def list_by_owner(self, owner: DocumentOwner) -> list[Document]:
        query: dict[str, Any] = {"KeyConditionExpression": Key("pk").eq(owner.pk) & Key("sk").begins_with("Document#")}
        documents: list[Document] = []
        while True:
            response = self.table.query(**query)
            documents.extend(
                Document.from_dynamo_item(item) for item in response.get("Items", []) if item.get("account_id") == owner.account_id
            )
            if "LastEvaluatedKey" not in response:
                return sorted(documents, key=lambda document: document.created_at)
            query["ExclusiveStartKey"] = response["LastEvaluatedKey"]

    def find_by_filename(self, owner: DocumentOwner, filename: str) -> Optional[Document]:
        return next((document for document in self.list_by_owner(owner) if document.filename == filename), None)

    def claim(self, owner: DocumentOwner, document_id: str, *, lease_seconds: int, now: int) -> Optional[Document]:
        """Take the document for processing: in flight and no live lease. None when another worker holds it, or it is
        done or gone."""
        try:
            response = self.table.update_item(
                Key={"pk": owner.pk, "sk": f"Document#{document_id}"},
                UpdateExpression="SET #status = :parsing, lease_expires_at = :lease, attempts = attempts + :one, updated_at = :at",
                ConditionExpression=Attr("status").is_in(IN_FLIGHT_VALUES) & Attr("lease_expires_at").lte(now),
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={
                    ":parsing": DocumentStatus.PARSING.value,
                    ":lease": now + lease_seconds,
                    ":one": 1,
                    ":at": datetime.now(timezone.utc).isoformat(),
                },
                ReturnValues="ALL_NEW",
            )
        except ClientError as exc:
            if _conditional_failed(exc):
                return None
            raise
        return Document.from_dynamo_item(response["Attributes"])

    def renew(self, document: Document, *, lease_seconds: int, now: int) -> bool:
        """Extend a worker's lease while it is still working on the document: False once it is no longer in flight."""
        try:
            self.table.update_item(
                Key={"pk": document.pk, "sk": document.sk},
                UpdateExpression="SET lease_expires_at = :lease",
                ConditionExpression=Attr("status").is_in(IN_FLIGHT_VALUES),
                ExpressionAttributeValues={":lease": now + lease_seconds},
            )
        except ClientError as exc:
            if _conditional_failed(exc):
                return False
            raise
        return True

    def mark_attached(self, document: Document, *, now: int) -> None:
        """Record that the document went out with a message; one already sent keeps when it first was."""
        try:
            self.table.update_item(
                Key={"pk": document.pk, "sk": document.sk},
                UpdateExpression="SET attached_at = :now",
                ConditionExpression=Attr("attached_at").eq(0),
                ExpressionAttributeValues={":now": now},
            )
        except ClientError as exc:
            if not _conditional_failed(exc):
                raise

    def delete(self, document: Document) -> None:
        self.table.delete_item(Key={"pk": document.pk, "sk": document.sk})

    def in_flight(self) -> list[Document]:
        return self._scan(Attr("status").is_in(IN_FLIGHT_VALUES))

    def unsent(self, kind: OwnerKind) -> list[Document]:
        return self._scan(Attr("owner_kind").eq(kind.value) & Attr("attached_at").eq(0))

    def _scan(self, condition: Any) -> list[Document]:
        scan: dict[str, Any] = {"FilterExpression": Attr("entity_type").eq("Document") & condition}
        documents: list[Document] = []
        while True:
            response = self.table.scan(**scan)
            documents.extend(Document.from_dynamo_item(item) for item in response.get("Items", []))
            if "LastEvaluatedKey" not in response:
                return documents
            scan["ExclusiveStartKey"] = response["LastEvaluatedKey"]
