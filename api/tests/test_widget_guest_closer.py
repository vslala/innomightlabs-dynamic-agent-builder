"""Guest cleanup against real DynamoDB/S3 APIs (moto), including restart failures."""

import gzip
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import boto3
import pytest
from botocore.exceptions import ClientError

from src.widget import guest_closer
from src.widget.guest_closer import GuestSessionCloser

NOW = datetime(2026, 10, 7, 12, tzinfo=timezone.utc)
BUCKET = "guest-transcripts-test"
SESSION_KEY = {"pk": "WidgetGuest#guest_1", "sk": "WidgetGuest#Metadata"}
MEDIA = "agents/a/conversations/c/messages/m/image.png"


@pytest.fixture
def closer(dynamodb_table, monkeypatch):
    monkeypatch.setattr(guest_closer, "_now", lambda: NOW)
    monkeypatch.setattr(guest_closer, "settings", SimpleNamespace(
        widget_guest_sweep_batch=100, widget_guest_transcript_attempts=3,
        widget_guest_transcript_max_chars=100_000, widget_guest_max_lifetime_hours=24,
    ))
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket=BUCKET)
    sender = AsyncMock(return_value=True)
    monkeypatch.setattr(guest_closer, "send_guest_transcript_email_safe", sender)
    instance = GuestSessionCloser(table=dynamodb_table, s3=s3, bucket=BUCKET)
    return instance, sender


def seed(closer, *, user_message=True, ends=None):
    closer, _ = closer
    end = ends or (NOW - timedelta(minutes=1)).isoformat()
    session = {
        **SESSION_KEY, "visitor_id": "guest_1", "agent_id": "a", "key_id": "k",
        "email": "guest@example.com", "agent_name": "Mira", "status": "active",
        "created_at": (NOW - timedelta(hours=2)).isoformat(), "last_active_at": end,
        "session_timeout_minutes": 60, "session_ends_at": end, "origin": "https://example.com",
        "refresh_hash": "refresh", "transcript": "pending", "transcript_attempts": 0,
        "ttl": int(NOW.timestamp()) + 86400, "gsi2_pk": "WidgetGuestSessionEnd",
        "gsi2_sk": f"{end}#guest_1", "conversation_ids": {"c"},
    }
    rows = [session, {
        "pk": "Agent#a#Widget", "sk": "Conversation#c", "conversation_id": "c",
        "agent_id": "a", "visitor_id": "guest_1", "title": "Our chat", "created_at": end,
        "gsi2_pk": "Visitor#guest_1", "gsi2_sk": "Agent#a#Conversation#c",
    }, {
        "pk": "CONVERSATION#c", "sk": "MESSAGE#2", "role": "assistant", "kind": "chat",
        "content": "**Hi** <script>bad</script>", "images": [{"s3_key": MEDIA}],
    }, {"pk": "CONVERSATION#c", "sk": "AUDIT#1", "role": "assistant", "kind": "tool_audit", "content": "SECRET AUDIT"},
        {"pk": "CONVERSATION#c", "sk": "TURN#1", "status": "succeeded"},
        {"pk": "Agent#a#User#guest_1", "sk": "CoreMemory#1", "content": "memory"},
        {"pk": "Agent#a#User#guest_1", "sk": "MemoryBlockDef#1"},
        {"pk": "Agent#a#User#guest_1", "sk": "CapacityWarning#1"},
        {"pk": "Agent#a#User#guest_1", "sk": "Archival#date#mem", "memory_id": "mem", "content_hash": "hash", "content": "archive memory"},
        {"pk": "Agent#a#User#guest_1#Hash#hash", "sk": "Archival#mem"},
        {"pk": "WidgetRefresh#refresh", "sk": "WidgetRefresh#Metadata"},
    ]
    if user_message:
        rows.append({"pk": "CONVERSATION#c", "sk": "MESSAGE#1", "role": "user", "content": "Hello <img src=x>", "created_at": end})
    for row in rows:
        closer.table.put_item(Item=row)
    closer.s3.put_object(Bucket=BUCKET, Key=MEDIA, Body=b"image")
    return session, rows


def saved_session(closer):
    return closer.table.get_item(Key=SESSION_KEY, ConsistentRead=True).get("Item")


def archive(closer, session):
    body = closer.s3.get_object(Bucket=BUCKET, Key=closer._archive_key(session))["Body"].read()
    return json.loads(gzip.decompress(body))


def expire_lease(closer):
    closer.table.update_item(Key=SESSION_KEY, UpdateExpression="SET lease_expires_at = :zero", ExpressionAttributeValues={":zero": 0})


def assert_deleted(closer, rows):
    for row in rows:
        assert "Item" not in closer.table.get_item(Key={"pk": row["pk"], "sk": row["sk"]})
    assert not closer.s3.list_objects_v2(Bucket=BUCKET, Prefix="agents/a/conversations/").get("Contents")


def test_complete_close_archives_tags_escapes_and_deletes(closer):
    session, rows = seed(closer)
    worker, sender = closer
    worker.table.put_item(Item={"pk": "Owner#a", "sk": "MCPCall#keep"})
    assert worker.sweep() == 1
    assert_deleted(worker, rows)
    sender.assert_awaited_once()
    body = sender.call_args.kwargs["email"].html()
    assert "&lt;img" in body and "<strong>Hi</strong>" in body
    assert "SECRET AUDIT" not in body and "(image)" in body
    data = archive(worker, session)
    assert data["transcript"]["status"] == "sent"
    assert data["transcript"]["attempts"] == 1
    copied = data["media"][MEDIA]
    assert worker.s3.get_object(Bucket=BUCKET, Key=copied)["Body"].read() == b"image"
    for key in [copied, worker._archive_key(session)]:
        assert worker.s3.get_object_tagging(Bucket=BUCKET, Key=key)["TagSet"] == [{"Key": "retention", "Value": "guest-session"}]
    assert worker.table.get_item(Key={"pk": "Owner#a", "sk": "MCPCall#keep"}).get("Item")


def test_empty_session_still_deletes_all_media_memory_hashes_tokens(closer):
    _, rows = seed(closer, user_message=False)
    worker, sender = closer
    assert worker.sweep() == 1
    assert_deleted(worker, rows)
    sender.assert_not_awaited()
    assert not worker.s3.list_objects_v2(Bucket=BUCKET).get("Contents")


def test_guest_turn_lease_atomically_blocks_claim_then_allows_finished_turn(closer):
    session, rows = seed(closer)
    worker, sender = closer
    worker.table.update_item(Key=SESSION_KEY,
        UpdateExpression="SET turn_id = :turn, turn_expires_at = :expires",
        ExpressionAttributeValues={":turn": "in-flight", ":expires": int(NOW.timestamp()) + 300})
    assert worker._claim(session) is None
    assert worker.sweep() == 0
    assert saved_session(worker)["status"] == "active"
    sender.assert_not_awaited()
    worker.table.update_item(Key=SESSION_KEY, UpdateExpression="REMOVE turn_id, turn_expires_at")
    assert worker.sweep() == 1
    assert_deleted(worker, rows)


def test_expired_guest_turn_lease_allows_recovery(closer):
    session, _ = seed(closer)
    worker, _ = closer
    worker.table.update_item(Key=SESSION_KEY, UpdateExpression="SET turn_expires_at = :expires",
        ExpressionAttributeValues={":expires": int(NOW.timestamp()) - 1})
    assert worker._claim(session)


def test_paginated_inventory_and_sweep(closer, monkeypatch):
    _, rows = seed(closer)
    worker, _ = closer
    original = worker.table.query

    def small_pages(**kwargs):
        return original(**{**kwargs, "Limit": 1})

    monkeypatch.setattr(worker.table, "query", small_pages)
    assert worker.sweep() == 1
    assert_deleted(worker, rows)


def test_sweep_batch_is_bounded(closer):
    session, _ = seed(closer, user_message=False)
    worker, _ = closer
    guest_closer.settings.widget_guest_sweep_batch = 1
    second = {**session, "pk": "WidgetGuest#guest_2", "visitor_id": "guest_2", "refresh_hash": "other",
        "gsi2_sk": session["session_ends_at"] + "#guest_2"}
    worker.table.put_item(Item=second)
    assert worker.sweep() == 1
    assert worker.table.get_item(Key={"pk": second["pk"], "sk": second["sk"]}).get("Item")
    assert worker.sweep() == 1


def test_future_and_touched_sessions_are_not_claimed(closer):
    session, _ = seed(closer, ends=(NOW + timedelta(hours=1)).isoformat())
    worker, sender = closer
    assert worker.sweep() == 0
    assert worker._claim(session) is None
    session["session_ends_at"] = (NOW - timedelta(minutes=1)).isoformat()
    assert worker._claim(session) is None
    sender.assert_not_awaited()


def test_claim_lease_owner_fences_old_worker_and_removes_ttl(closer):
    session, _ = seed(closer)
    worker, _ = closer
    first = worker._claim(session)
    assert first and "ttl" not in first
    assert worker._claim(session) is None
    expire_lease(worker)
    second = worker._claim(session)
    assert second["lease_owner"] != first["lease_owner"]
    with pytest.raises(ClientError, match="ConditionalCheckFailedException"):
        worker._checkpoint(first, transcript="sent")
    worker._checkpoint(second)
    worker.table.delete_item(Key=SESSION_KEY)
    assert worker._claim(session) is None
    with pytest.raises(ClientError):
        worker._checkpoint(second)
    assert saved_session(worker) is None


def test_send_retries_three_times_then_archives_failure_and_deletes(closer):
    session, rows = seed(closer)
    worker, sender = closer
    sender.return_value = False
    for attempt in (1, 2):
        assert worker.sweep() == 0
        assert saved_session(worker)["transcript_attempts"] == attempt
        assert worker.table.get_item(Key={"pk": "CONVERSATION#c", "sk": "MESSAGE#1"}).get("Item")
    assert worker.sweep() == 1
    assert_deleted(worker, rows)
    assert sender.await_count == 3
    assert archive(worker, session)["transcript"]["status"] == "failed"


@pytest.mark.parametrize("failure_pk", ["CONVERSATION#c", "Agent#a#User#guest_1", "Agent#a#Widget", "WidgetRefresh#refresh"])
def test_resume_partial_delete_keeps_original_archive_and_does_not_resend(closer, monkeypatch, failure_pk):
    session, rows = seed(closer)
    worker, sender = closer
    original = worker.table.delete_item
    failed = False

    def fail_once(**kwargs):
        nonlocal failed
        if kwargs["Key"]["pk"] == failure_pk and not failed:
            failed = True
            original(**kwargs)
            raise RuntimeError("crash after deletion")
        return original(**kwargs)

    monkeypatch.setattr(worker.table, "delete_item", fail_once)
    assert worker.sweep() == 0
    before = archive(worker, session)
    assert saved_session(worker)["transcript"] == "sent"
    expire_lease(worker)
    assert worker.sweep() == 1
    assert archive(worker, session) == before
    assert_deleted(worker, rows)
    sender.assert_awaited_once()


def test_resume_after_archive_before_send(closer, monkeypatch):
    session, rows = seed(closer)
    worker, sender = closer
    original = worker._checkpoint

    def crash_before_attempt(session, **fields):
        if "transcript_attempts" in fields:
            raise RuntimeError("crash")
        return original(session, **fields)

    monkeypatch.setattr(worker, "_checkpoint", crash_before_attempt)
    assert worker.sweep() == 0
    assert saved_session(worker)["archive_key"]
    sender.assert_not_awaited()
    monkeypatch.setattr(worker, "_checkpoint", original)
    expire_lease(worker)
    assert worker.sweep() == 1
    assert_deleted(worker, rows)
    assert archive(worker, session)["transcript"]["status"] == "sent"


def test_running_turn_defers_archive_mail_and_cleanup_even_if_old(closer):
    seed(closer)
    worker, sender = closer
    worker.table.put_item(Item={"pk": "CONVERSATION#c", "sk": "TURN#0", "status": "running", "last_heartbeat_at": "2020-01-01T00:00:00Z"})
    assert worker.sweep() == 0
    assert saved_session(worker)
    assert worker.s3.get_object(Bucket=BUCKET, Key=MEDIA)
    sender.assert_not_awaited()
    assert not worker.s3.list_objects_v2(Bucket=BUCKET, Prefix="agents/a/guest-sessions/").get("Contents")


@pytest.mark.parametrize("target", ["media", "archive"])
def test_failed_head_verification_prevents_mail_and_delete(closer, monkeypatch, target):
    seed(closer)
    worker, sender = closer
    original = worker.s3.head_object

    def bad_head(**kwargs):
        result = original(**kwargs)
        if (target == "archive" and kwargs["Key"].endswith(".json.gz")) or (target == "media" and "/media/" in kwargs["Key"]):
            result["ContentLength"] += 1
        return result

    monkeypatch.setattr(worker.s3, "head_object", bad_head)
    assert worker.sweep() == 0
    sender.assert_not_awaited()
    assert worker.table.get_item(Key={"pk": "CONVERSATION#c", "sk": "MESSAGE#1"}).get("Item")
    assert worker.s3.get_object(Bucket=BUCKET, Key=MEDIA)


def test_s3_partial_delete_errors_keep_session_for_retry(closer, monkeypatch):
    session, rows = seed(closer)
    worker, sender = closer
    original = worker.s3.delete_objects
    monkeypatch.setattr(worker.s3, "delete_objects", lambda **kwargs: {"Errors": [{"Key": MEDIA, "Code": "AccessDenied"}]})
    assert worker.sweep() == 0
    assert saved_session(worker)
    monkeypatch.setattr(worker.s3, "delete_objects", original)
    expire_lease(worker)
    assert worker.sweep() == 1
    assert_deleted(worker, rows)
    sender.assert_awaited_once()


def test_memory_hash_delete_failure_preserves_source_for_retry(closer, monkeypatch):
    _, rows = seed(closer, user_message=False)
    worker, _ = closer
    original = worker.table.delete_item

    def fail_hash(**kwargs):
        if "#Hash#" in kwargs["Key"]["pk"]:
            raise RuntimeError("hash delete unavailable")
        return original(**kwargs)

    monkeypatch.setattr(worker.table, "delete_item", fail_hash)
    assert worker.sweep() == 0
    assert worker.table.get_item(Key={"pk": "Agent#a#User#guest_1", "sk": "Archival#date#mem"}).get("Item")
    monkeypatch.setattr(worker.table, "delete_item", original)
    expire_lease(worker)
    assert worker.sweep() == 1
    assert_deleted(worker, rows)


def test_only_the_guests_own_conversations_are_read_or_deleted(closer):
    session, rows = seed(closer)
    worker, _ = closer
    other = {"pk": "Agent#a#Widget", "sk": "Conversation#someone-else", "conversation_id": "someone-else",
             "agent_id": "a", "visitor_id": "google-visitor", "title": "Not the guest's"}
    worker.table.put_item(Item=other)
    worker.table.put_item(Item={"pk": "CONVERSATION#someone-else", "sk": "MESSAGE#1", "role": "user", "content": "keep"})

    assert worker.sweep() == 1

    assert_deleted(worker, rows)
    assert worker.table.get_item(Key={"pk": other["pk"], "sk": other["sk"]}).get("Item")
    assert worker.table.get_item(Key={"pk": "CONVERSATION#someone-else", "sk": "MESSAGE#1"}).get("Item")
    assert [entry["conversation"]["conversation_id"] for entry in archive(worker, session)["conversations"]] == ["c"]
