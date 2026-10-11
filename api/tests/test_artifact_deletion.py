"""Member-private cleanup across real moto S3 and DynamoDB, including retry boundaries."""
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import boto3
import jwt
import pytest
from botocore.exceptions import ClientError

from src.accounts import AccountService, Member
from src.accounts.owner import member_partition
from src.artifacts.router import get_artifact_service
from src.artifacts.service import ArtifactService
from src.artifacts.storage import member_prefix
from src.identity import IdentityRepository
from tests.mock_data import TEST_USER_EMAIL, TEST_USER_EMAIL_2, owner_for, user_id_for
from tests.oauth_handoff import owner_headers

BUCKET = "innomightlabs-conversations-meta"
OWNER = owner_for(TEST_USER_EMAIL)


@pytest.fixture
def deletion_service(test_client, monkeypatch):
    from main import app

    monkeypatch.setattr("src.artifacts.storage.settings.conversation_media_bucket", BUCKET)
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
    service = ArtifactService()
    app.dependency_overrides[get_artifact_service] = lambda: service
    try:
        yield service
    finally:
        app.dependency_overrides.pop(get_artifact_service, None)


def create_artifact(service, *, account_id=OWNER.account_id, user_id=OWNER.user_id):
    response = service.create_artifact(
        account_id=account_id, user_id=user_id, artifact_type="text", title="Notes",
        filename="notes.txt", mime_type="text/plain", body=b"hello",
    )
    artifact = service.repository.find_by_id(member_partition(account_id, user_id), response.artifact_id)
    assert artifact is not None
    return artifact


def row(service, artifact):
    return service.repository.table.get_item(
        Key={"pk": artifact.pk, "sk": artifact.sk}, ConsistentRead=True,
    ).get("Item")


def object_body(service, artifact):
    return service.storage.get_object_body(artifact.s3_key)


def assert_object_missing(service, artifact):
    with pytest.raises(ClientError) as error:
        object_body(service, artifact)
    assert error.value.response["Error"]["Code"] == "NoSuchKey"


def bulk(client, ids, headers):
    return client.request("DELETE", "/artifacts/bulk", headers=headers, json={"artifact_ids": ids})


@pytest.mark.parametrize("bytes_missing", [False, True])
def test_single_cleanup_and_missing_bytes_are_successful(
    test_client, auth_headers, deletion_service, bytes_missing,
):
    artifact = create_artifact(deletion_service)
    sibling = create_artifact(deletion_service)
    if bytes_missing:
        deletion_service.storage.client.delete_object(Bucket=BUCKET, Key=artifact.s3_key)
    response = test_client.delete(f"/artifacts/{artifact.artifact_id}", headers=auth_headers)
    assert response.status_code == 204, response.text
    assert response.content == b""
    assert row(deletion_service, artifact) is None
    assert_object_missing(deletion_service, artifact)
    assert row(deletion_service, sibling)
    assert object_body(deletion_service, sibling) == b"hello"
    retry = test_client.delete(f"/artifacts/{artifact.artifact_id}", headers=auth_headers)
    assert retry.status_code == 204
    assert retry.content == b""


def test_missing_artifact_never_touches_s3(test_client, auth_headers, deletion_service, monkeypatch):
    delete = Mock(wraps=deletion_service.storage.client.delete_object)
    monkeypatch.setattr(deletion_service.storage.client, "delete_object", delete)
    response = test_client.delete("/artifacts/missing", headers=auth_headers)
    assert response.status_code == 204
    assert response.content == b""
    delete.assert_not_called()


def test_other_member_and_other_account_are_idempotent_without_foreign_mutation(test_client, deletion_service, dynamodb_table, monkeypatch):
    account = AccountService().create_account(IdentityRepository().get(OWNER.user_id), "Team")
    other = IdentityRepository().get(user_id_for(TEST_USER_EMAIL_2))
    dynamodb_table.put_item(Item=Member(
        account_id=account.account_id, user_id=other.user_id, email=other.email, name=other.name,
    ).to_dynamo_item())
    artifact = create_artifact(deletion_service, account_id=account.account_id)
    delete = Mock(wraps=deletion_service.storage.client.delete_object)
    monkeypatch.setattr(deletion_service.storage.client, "delete_object", delete)
    for headers in (
        {**owner_headers(TEST_USER_EMAIL_2), "X-Account-Id": account.account_id},
        owner_headers(TEST_USER_EMAIL),
    ):
        response = test_client.delete(f"/artifacts/{artifact.artifact_id}", headers=headers)
        assert response.status_code == 204, response.text
        assert response.content == b""
        response = bulk(test_client, [artifact.artifact_id], headers)
        assert response.status_code == 200, response.text
        assert response.json() == {"deleted_ids": [artifact.artifact_id], "failed": []}
    delete.assert_not_called()
    assert row(deletion_service, artifact)
    assert object_body(deletion_service, artifact) == b"hello"


@pytest.mark.parametrize("audience", [None, "widget", "a2a", "access", "public_api"])
def test_non_owner_auth_is_denied(test_client, deletion_service, audience, monkeypatch):
    artifact = create_artifact(deletion_service)
    headers = {}
    if audience:
        now = datetime.now(timezone.utc)
        token = jwt.encode(
            {"aud": audience, "sub": OWNER.user_id, "iat": now, "exp": now + timedelta(hours=1)},
            "test-secret", algorithm="HS256",
        )
        headers = {"Authorization": f"Bearer {token}"}
    delete = Mock(wraps=deletion_service.storage.client.delete_object)
    monkeypatch.setattr(deletion_service.storage.client, "delete_object", delete)
    assert test_client.delete(f"/artifacts/{artifact.artifact_id}", headers=headers).status_code in (401, 403)
    assert bulk(test_client, [artifact.artifact_id], headers).status_code in (401, 403)
    delete.assert_not_called()
    assert row(deletion_service, artifact)


@pytest.mark.parametrize("body", [
    {"artifact_ids": []}, {"artifact_ids": ["x"] * 101}, {"artifact_ids": [""]},
    {"artifact_ids": ["x" * 129]}, {"artifact_ids": [123]}, {"artifact_ids": "x"},
    {"artifact_ids": ["x"], "account_id": "other"},
    {"artifact_ids": ["x"], "user_id": "other"}, {},
])
def test_bulk_rejects_invalid_body(test_client, auth_headers, deletion_service, body, monkeypatch):
    delete = Mock(wraps=deletion_service.storage.client.delete_object)
    monkeypatch.setattr(deletion_service.storage.client, "delete_object", delete)
    response = test_client.request("DELETE", "/artifacts/bulk", headers=auth_headers, json=body)
    assert response.status_code == 422, response.text
    delete.assert_not_called()


def test_bulk_route_order_deduplication_and_mixed_results(test_client, auth_headers, deletion_service, monkeypatch):
    first, second = create_artifact(deletion_service), create_artifact(deletion_service)
    delete = Mock(wraps=deletion_service.storage.client.delete_object)
    monkeypatch.setattr(deletion_service.storage.client, "delete_object", delete)
    response = bulk(test_client, ["missing", second.artifact_id, second.artifact_id,
                                  first.artifact_id, "missing", "another"], auth_headers)
    assert response.status_code == 200, response.text
    assert response.json() == {
        "deleted_ids": ["missing", second.artifact_id, first.artifact_id, "another"],
        "failed": [],
    }
    assert delete.call_count == 2
    assert row(deletion_service, first) is None
    assert row(deletion_service, second) is None
    assert_object_missing(deletion_service, first)
    assert_object_missing(deletion_service, second)


@pytest.mark.parametrize("ids", [["x"], ["x" * 128] * 100])
def test_bulk_bounds_are_inclusive(test_client, auth_headers, deletion_service, ids):
    response = bulk(test_client, ids, auth_headers)
    assert response.status_code == 200
    assert response.json() == {"deleted_ids": list(dict.fromkeys(ids)), "failed": []}


@pytest.mark.parametrize("boundary", ["storage", "repository", "lookup"])
def test_failures_are_safe_and_retryable(test_client, auth_headers, deletion_service, monkeypatch, boundary):
    artifact = create_artifact(deletion_service)
    target, method = {
        "storage": (deletion_service.storage.client, "delete_object"),
        "repository": (deletion_service.repository.table, "delete_item"),
        "lookup": (deletion_service.repository.table, "query"),
    }[boundary]
    original = getattr(target, method)
    monkeypatch.setattr(target, method, Mock(side_effect=RuntimeError(f"SECRET provider {artifact.s3_key}")))
    response = test_client.delete(f"/artifacts/{artifact.artifact_id}", headers=auth_headers)
    assert response.status_code == 502
    assert response.json() == {
        "detail": "Artifact deletion failed", "path": f"/artifacts/{artifact.artifact_id}",
    }
    assert "SECRET" not in response.text and artifact.s3_key not in response.text
    assert row(deletion_service, artifact)
    if boundary == "repository":
        assert_object_missing(deletion_service, artifact)
    else:
        assert object_body(deletion_service, artifact) == b"hello"
    monkeypatch.setattr(target, method, original)
    assert test_client.delete(f"/artifacts/{artifact.artifact_id}", headers=auth_headers).status_code == 204
    assert row(deletion_service, artifact) is None
    assert_object_missing(deletion_service, artifact)


@pytest.mark.parametrize("boundary", ["storage", "repository"])
def test_bulk_continues_after_deletion_failure(test_client, auth_headers, deletion_service, monkeypatch, boundary):
    failed, valid = create_artifact(deletion_service), create_artifact(deletion_service)
    target, method = (
        (deletion_service.storage.client, "delete_object") if boundary == "storage"
        else (deletion_service.repository.table, "delete_item")
    )
    original = getattr(target, method)

    def delete(**kwargs):
        if kwargs["Key"] == (failed.s3_key if boundary == "storage" else {"pk": failed.pk, "sk": failed.sk}):
            raise RuntimeError(f"SECRET {failed.s3_key}")
        return original(**kwargs)

    monkeypatch.setattr(target, method, delete)
    response = bulk(test_client, [failed.artifact_id, "missing", valid.artifact_id, failed.artifact_id], auth_headers)
    assert response.status_code == 200
    assert response.json() == {
        "deleted_ids": ["missing", valid.artifact_id],
        "failed": [
            {"artifact_id": failed.artifact_id, "code": "DELETE_FAILED", "message": "Artifact deletion failed"},

        ],
    }
    assert row(deletion_service, failed)
    if boundary == "storage":
        assert object_body(deletion_service, failed) == b"hello"
    else:
        assert_object_missing(deletion_service, failed)
    assert row(deletion_service, valid) is None
    assert_object_missing(deletion_service, valid)
    monkeypatch.setattr(target, method, original)
    retry = bulk(test_client, [failed.artifact_id], auth_headers)
    assert retry.json() == {"deleted_ids": [failed.artifact_id], "failed": []}
    assert row(deletion_service, failed) is None
    assert_object_missing(deletion_service, failed)


@pytest.mark.parametrize("route", ["single", "bulk"])
def test_stale_gsi_retry_is_idempotent(test_client, auth_headers, deletion_service, monkeypatch, route):
    artifact = create_artifact(deletion_service)
    stale = row(deletion_service, artifact)
    assert test_client.delete(f"/artifacts/{artifact.artifact_id}", headers=auth_headers).status_code == 204
    assert row(deletion_service, artifact) is None
    assert_object_missing(deletion_service, artifact)
    query = Mock(return_value={"Items": [stale]})
    get = Mock(wraps=deletion_service.repository.table.get_item)
    storage_delete = Mock(wraps=deletion_service.storage.client.delete_object)
    metadata_delete = Mock(wraps=deletion_service.repository.table.delete_item)
    monkeypatch.setattr(deletion_service.repository.table, "query", query)
    monkeypatch.setattr(deletion_service.repository.table, "get_item", get)
    monkeypatch.setattr(deletion_service.storage.client, "delete_object", storage_delete)
    monkeypatch.setattr(deletion_service.repository.table, "delete_item", metadata_delete)
    if route == "single":
        response = test_client.delete(f"/artifacts/{artifact.artifact_id}", headers=auth_headers)
        assert response.status_code == 204, response.text
        assert response.content == b""
    else:
        response = bulk(test_client, [artifact.artifact_id, artifact.artifact_id], auth_headers)
        assert response.status_code == 200, response.text
        assert response.json() == {"deleted_ids": [artifact.artifact_id], "failed": []}
    query.assert_called_once()
    get.assert_not_called()
    storage_delete.assert_called_once_with(Bucket=BUCKET, Key=artifact.s3_key)
    metadata_delete.assert_called_once_with(Key={"pk": artifact.pk, "sk": artifact.sk})
    assert row(deletion_service, artifact) is None
    assert_object_missing(deletion_service, artifact)


def test_deletion_uses_exact_trusted_stored_key(test_client, auth_headers, deletion_service, monkeypatch):
    artifact = create_artifact(deletion_service)
    stored_key = (
        f"{member_prefix(artifact.account_id, artifact.user_id)}/artifacts/2020/01/02/"
        f"{artifact.artifact_id}/replacement.txt"
    )
    deletion_service.storage.put_artifact(key=stored_key, body=b"replacement", content_type="text/plain")
    item = row(deletion_service, artifact)
    item["s3_key"] = stored_key
    deletion_service.repository.table.put_item(Item=item)
    delete = Mock(wraps=deletion_service.storage.client.delete_object)
    monkeypatch.setattr(deletion_service.storage.client, "delete_object", delete)
    response = test_client.delete(f"/artifacts/{artifact.artifact_id}", headers=auth_headers)
    assert response.status_code == 204, response.text
    delete.assert_called_once_with(Bucket=BUCKET, Key=stored_key)
    assert row(deletion_service, artifact) is None
    with pytest.raises(ClientError) as error:
        deletion_service.storage.get_object_body(stored_key)
    assert error.value.response["Error"]["Code"] == "NoSuchKey"
    assert object_body(deletion_service, artifact) == b"hello"


@pytest.mark.parametrize("exists", [False, True])
def test_deletion_looks_up_once_and_deletes_unconditionally(deletion_service, monkeypatch, exists):
    artifact = create_artifact(deletion_service)
    lookup = Mock(wraps=deletion_service.repository.find_by_id)
    storage_delete = Mock(wraps=deletion_service.storage.delete_artifact)
    metadata_delete = Mock(wraps=deletion_service.repository.table.delete_item)
    if not exists:
        deletion_service.repository.table.delete_item(Key={"pk": artifact.pk, "sk": artifact.sk})
    monkeypatch.setattr(deletion_service.repository, "find_by_id", lookup)
    monkeypatch.setattr(deletion_service.storage, "delete_artifact", storage_delete)
    monkeypatch.setattr(deletion_service.repository.table, "delete_item", metadata_delete)
    calls = Mock()
    calls.attach_mock(lookup, "lookup")
    calls.attach_mock(storage_delete, "storage_delete")
    calls.attach_mock(metadata_delete, "metadata_delete")
    assert deletion_service.delete_artifact(OWNER.member_pk, artifact.artifact_id) is None
    lookup.assert_called_once_with(OWNER.member_pk, artifact.artifact_id)
    if exists:
        storage_delete.assert_called_once_with(artifact.s3_key)
        metadata_delete.assert_called_once_with(Key={"pk": artifact.pk, "sk": artifact.sk})
        assert [call[0] for call in calls.mock_calls] == ["lookup", "storage_delete", "metadata_delete"]
        assert_object_missing(deletion_service, artifact)
    else:
        storage_delete.assert_not_called()
        metadata_delete.assert_not_called()
        assert object_body(deletion_service, artifact) == b"hello"
    assert row(deletion_service, artifact) is None
