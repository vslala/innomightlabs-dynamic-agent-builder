"""Durable guest close workflow: verified archive, bounded mail attempts, deletion.

Run sweep in a worker thread (it uses synchronous boto3 and Mailjet clients).
The session owns the lease and checkpoints; S3 owns the frozen deletion manifest.
"""

import asyncio
import gzip
import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from src.config import settings
from src.db import get_dynamodb_resource
from src.email.helpers import send_guest_transcript_email_safe
from src.memory.repository import MemoryRepository
from src.widget.transcript import GuestTranscriptEmail, build_transcript, is_visible_message

log = logging.getLogger(__name__)
LEASE_SECONDS = 600


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _json_default(value: object) -> object:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    raise TypeError(f"Cannot archive {type(value).__name__}")


class GuestSessionCloser:
    def __init__(self, *, table=None, s3=None, bucket: str | None = None):
        self.table = table if table is not None else get_dynamodb_resource().Table(settings.dynamodb_table)
        self.s3 = s3 if s3 is not None else boto3.client("s3", region_name=settings.conversation_media_region)
        self.bucket = bucket if bucket is not None else settings.conversation_media_bucket

    def sweep(self) -> int:
        """Process a bounded page of due sessions; isolate individual failures."""
        now = _now()
        limit = settings.widget_guest_sweep_batch
        query = {
            "IndexName": "gsi2",
            "KeyConditionExpression": Key("gsi2_pk").eq("WidgetGuestSessionEnd")
            & Key("gsi2_sk").lt(now.isoformat() + "~"),
            "Limit": limit,
        }
        closed = 0
        examined = 0
        while examined < limit:
            page = self.table.query(**query)
            for candidate in page.get("Items", []):
                examined += 1
                try:
                    closed += int(self.close(candidate))
                except Exception:
                    log.exception("Guest close failed for %s; checkpoint retained", candidate["pk"])
            if not page.get("LastEvaluatedKey"):
                break
            query["ExclusiveStartKey"] = page["LastEvaluatedKey"]
            query["Limit"] = limit - examined
        return closed

    def _claim(self, candidate: dict) -> dict | None:
        now = _now()
        # Compare the exact observed ISO value, not two potentially different UTC
        # encodings. A touch after the GSI read must invalidate this claim.
        if datetime.fromisoformat(candidate["session_ends_at"]) > now:
            return None
        try:
            claimed: dict = self.table.update_item(
                Key={"pk": candidate["pk"], "sk": "WidgetGuest#Metadata"},
                UpdateExpression="SET #status = :closing, lease_owner = :owner, lease_expires_at = :expires REMOVE #ttl",
                ConditionExpression="attribute_exists(pk) AND session_ends_at = :ends AND "
                "(#status = :active OR (#status = :closing AND lease_expires_at <= :epoch)) AND "
                                "(attribute_not_exists(turn_expires_at) OR turn_expires_at <= :epoch)",
                ExpressionAttributeNames={"#status": "status", "#ttl": "ttl"},
                ExpressionAttributeValues={
                    ":closing": "closing", ":active": "active", ":owner": uuid4().hex,
                    ":expires": int(now.timestamp()) + LEASE_SECONDS,
                    ":epoch": int(now.timestamp()), ":ends": candidate["session_ends_at"],
                }, ReturnValues="ALL_NEW",
            )["Attributes"]
            return claimed
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                return None
            raise

    def _checkpoint(self, session: dict, **fields: object) -> None:
        now = int(_now().timestamp())
        fields = {"lease_expires_at": now + LEASE_SECONDS, **fields}
        names = {f"#f{i}": key for i, key in enumerate(fields)}
        values = {f":v{i}": value for i, value in enumerate(fields.values())}
        self.table.update_item(
            Key={"pk": session["pk"], "sk": session["sk"]},
            UpdateExpression="SET " + ", ".join(f"#f{i} = :v{i}" for i in range(len(fields))),
            ConditionExpression="attribute_exists(pk) AND lease_owner = :owner AND lease_expires_at > :now",
            ExpressionAttributeNames=names,
            ExpressionAttributeValues={**values, ":owner": session["lease_owner"], ":now": now},
        )
        session.update(fields)

    def _query(self, **query: object) -> list[dict]:
        items = []
        while True:
            page = self.table.query(**query)
            items.extend(page.get("Items", []))
            if not page.get("LastEvaluatedKey"):
                return items
            query["ExclusiveStartKey"] = page["LastEvaluatedKey"]

    def _partition(self, pk: str) -> list[dict]:
        return self._query(KeyConditionExpression=Key("pk").eq(pk), ConsistentRead=True)

    def _collect(self, session: dict) -> dict:
        aid, vid = session["agent_id"], session["visitor_id"]
        # The session lists every conversation the guest created (written in the creating transaction),
        # so this is exact and strongly consistent without reading other visitors' conversations.
        entries = []
        for cid in sorted(session.get("conversation_ids") or ()):
            conversation = self.table.get_item(
                Key={"pk": f"Agent#{aid}#Widget", "sk": f"Conversation#{cid}"}, ConsistentRead=True,
            ).get("Item")
            if conversation is None:
                continue
            self._checkpoint(session)
            rows = self._partition(f"CONVERSATION#{conversation['conversation_id']}")
            if any(row["sk"].startswith("TURN#") and row.get("status") == "running" for row in rows):
                raise RuntimeError("Guest still has an in-flight turn; deferring cleanup")
            entries.append({"conversation": conversation, "messages": [
                row for row in rows if row["sk"].startswith(("MESSAGE#", "AUDIT#"))
            ], "rows": rows})
        end_reason = session.get("end_reason", "timeout")
        cap = datetime.fromisoformat(session["created_at"]) + timedelta(hours=settings.widget_guest_max_lifetime_hours)
        if end_reason == "timeout" and datetime.fromisoformat(session["session_ends_at"]) >= cap:
            end_reason = "max_lifetime"
        return {
            "schema_version": 1, "archived_at": _now().isoformat(),
            "end_reason": end_reason,
            "agent_id": aid, "key_id": session["key_id"],
            "guest": {key: session.get(key) for key in (
                "visitor_id", "email", "email_check", "origin", "created_at", "last_active_at", "session_timeout_minutes",
            )},
            "conversations": entries,
            "memory": self._partition(f"Agent#{aid}#User#{vid}"),
            "transcript": {"status": "pending", "attempts": 0},
        }

    def _archive_key(self, session: dict) -> str:
        date = datetime.fromisoformat(session["created_at"]).strftime("%Y/%m/%d")
        return f"agents/{session['agent_id']}/guest-sessions/{date}/{session['visitor_id']}.json.gz"

    def _write_archive(self, session: dict, archive: dict, key: str) -> None:
        body = gzip.compress(json.dumps(archive, default=_json_default).encode())
        digest = hashlib.sha256(body).hexdigest()
        self._checkpoint(session)
        self.s3.put_object(Bucket=self.bucket, Key=key, Body=body, ContentType="application/json",
                           ContentEncoding="gzip", Tagging="retention=guest-session", Metadata={"sha256": digest})
        head = self.s3.head_object(Bucket=self.bucket, Key=key)
        if head["ContentLength"] != len(body) or head.get("Metadata", {}).get("sha256") != digest:
            raise RuntimeError("Guest archive verification failed")

    def _copy_media(self, session: dict, archive: dict, key: str) -> None:
        mapping = {}
        for entry in archive["conversations"]:
            cid = entry["conversation"]["conversation_id"]
            prefix = f"agents/{session['agent_id']}/conversations/{cid}/"
            for page in self.s3.get_paginator("list_objects_v2").paginate(Bucket=self.bucket, Prefix=prefix):
                for obj in page.get("Contents", []):
                    self._checkpoint(session)
                    source = obj["Key"]
                    target = f"{key.removesuffix('.json.gz')}/media/{cid}/{source[len(prefix):]}"
                    self.s3.copy_object(Bucket=self.bucket, Key=target,
                        CopySource={"Bucket": self.bucket, "Key": source}, CopySourceIfMatch=obj["ETag"],
                        TaggingDirective="REPLACE", Tagging="retention=guest-session")
                    head = self.s3.head_object(Bucket=self.bucket, Key=target)
                    if head["ContentLength"] != obj["Size"] or head["ETag"] != obj["ETag"]:
                        raise RuntimeError("Guest media copy verification failed")
                    mapping[source] = target
            for message in entry["messages"]:
                for image in message.get("images", []):
                    if isinstance(image, dict) and image.get("s3_key"):
                        image["s3_key"] = mapping[image["s3_key"]]
        archive["media"] = mapping

    def _agent_name(self, session: dict) -> str:
        from src.agents.repository import AgentRepository

        key = self.table.get_item(Key={"pk": f"Agent#{session['agent_id']}", "sk": f"ApiKey#{session['key_id']}"}, ConsistentRead=True).get("Item", {})
        if key.get("created_by"):
            agent = AgentRepository().find_agent_by_id(session["agent_id"], key["created_by"])
            if agent:
                return agent.agent_name
        return session.get("agent_name") or "your assistant"

    def close(self, candidate: dict) -> bool:
        session = self._claim(candidate)
        if session is None:
            return False
        if session.get("archive_key"):
            key = session["archive_key"]
            head = self.s3.head_object(Bucket=self.bucket, Key=key)
            body = self.s3.get_object(Bucket=self.bucket, Key=key)["Body"].read()
            if hashlib.sha256(body).hexdigest() != head.get("Metadata", {}).get("sha256"):
                raise RuntimeError("Stored guest archive checksum mismatch")
            archive = json.loads(gzip.decompress(body))
        else:
            archive = self._collect(session)
            has_user_message = any(is_visible_message(row) and row["role"] == "user"
                for entry in archive["conversations"] for row in entry["messages"])
            if has_user_message:
                key = self._archive_key(session)
                archive["agent_name"] = self._agent_name(session)
                self._copy_media(session, archive, key)
                self._write_archive(session, archive, key)
                self._checkpoint(session, archive_key=key)
            else:
                self._checkpoint(session, transcript="skipped")

        if session.get("archive_key"):
            status = session.get("transcript", "pending")
            attempts = int(session.get("transcript_attempts", 0))
            if status not in {"sent", "failed"}:
                if attempts < settings.widget_guest_transcript_attempts:
                    attempts += 1
                    # Reserve before external I/O. A crash may consume an attempt;
                    # acceptance before checkpoint may cause a duplicate on retry.
                    self._checkpoint(session, transcript_attempts=attempts)
                    email = GuestTranscriptEmail(
                        agent_name=archive["agent_name"], origin=session.get("origin", ""),
                        started_at=session["created_at"],
                        transcript=build_transcript(archive["conversations"], archive["agent_name"],
                                                    settings.widget_guest_transcript_max_chars),
                    )
                    sent = asyncio.run(send_guest_transcript_email_safe(to_email=session["email"], email=email))
                    status = "sent" if sent else "pending"
                if status != "sent" and attempts >= settings.widget_guest_transcript_attempts:
                    status = "failed"
                    log.error("Guest transcript attempts exhausted; archive=%s", session["archive_key"])
                self._checkpoint(session, transcript=status, transcript_sent_at=_now().isoformat() if status == "sent" else "")
            archive["transcript"] = {"status": status, "attempts": attempts, "sent_at": session.get("transcript_sent_at")}
            self._write_archive(session, archive, session["archive_key"])
            if status == "pending":
                self._checkpoint(session, lease_expires_at=0)
                return False
        self._delete(session, archive)
        return True

    def _delete(self, session: dict, archive: dict) -> None:
        # Check all tracked turns even when resuming a frozen manifest.
        for entry in archive["conversations"]:
            cid = entry["conversation"]["conversation_id"]
            rows = self._partition(f"CONVERSATION#{cid}")
            if any(row["sk"].startswith("TURN#") and row.get("status") == "running" for row in rows):
                raise RuntimeError("Guest still has an in-flight turn; deferring cleanup")
        for entry in archive["conversations"]:
            cid = entry["conversation"]["conversation_id"]
            prefix = f"agents/{session['agent_id']}/conversations/{cid}/"
            for page in self.s3.get_paginator("list_objects_v2").paginate(Bucket=self.bucket, Prefix=prefix):
                objects = [{"Key": obj["Key"]} for obj in page.get("Contents", [])]
                if objects:
                    self._checkpoint(session)
                    result = self.s3.delete_objects(Bucket=self.bucket, Delete={"Objects": objects})
                    if result.get("Errors"):
                        raise RuntimeError("Guest media deletion failed")
            for row in self._partition(f"CONVERSATION#{cid}"):
                self._checkpoint(session)
                self.table.delete_item(Key={"pk": row["pk"], "sk": row["sk"]})
        memory = MemoryRepository()
        memory.table = self.table
        memory.delete_all_for_user(session["agent_id"], session["visitor_id"], before_delete=lambda: self._checkpoint(session))
        for entry in archive["conversations"]:
            self._checkpoint(session)
            row = entry["conversation"]
            self.table.delete_item(Key={"pk": row["pk"], "sk": row["sk"]})
        if session.get("refresh_hash"):
            self._checkpoint(session)
            self.table.delete_item(Key={"pk": f"WidgetRefresh#{session['refresh_hash']}", "sk": "WidgetRefresh#Metadata"})
        self._checkpoint(session)
        self.table.delete_item(Key={"pk": session["pk"], "sk": session["sk"]},
            ConditionExpression="lease_owner = :owner AND lease_expires_at > :now",
            ExpressionAttributeValues={":owner": session["lease_owner"], ":now": int(_now().timestamp())})
