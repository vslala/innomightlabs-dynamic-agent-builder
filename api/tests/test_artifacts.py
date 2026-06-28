from __future__ import annotations

import boto3
import pytest
from fastapi.testclient import TestClient

from src.artifacts.models import ArtifactSource
from src.artifacts.service import ArtifactService
from src.artifacts.storage import ArtifactStorage, sanitize_filename
from tests.mock_data import TEST_USER_EMAIL


def _create_media_bucket(bucket_name: str = "innomightlabs-conversations-meta") -> None:
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=bucket_name)


def test_artifact_service_creates_metadata_and_s3_object(dynamodb_table, monkeypatch):
    _create_media_bucket()
    monkeypatch.setattr("src.artifacts.storage.settings.conversation_media_bucket", "innomightlabs-conversations-meta")

    service = ArtifactService()
    artifact = service.create_artifact(
        owner_email=TEST_USER_EMAIL,
        artifact_type="html_report",
        title="League Match Report",
        filename="../league report.html",
        mime_type="text/html",
        body=b"<html><body>Report</body></html>",
        source=ArtifactSource(skill_id="html_report", automation_id="automation-1"),
    )

    assert artifact.artifact_type == "html_report"
    assert artifact.filename == "league-report.html"
    assert artifact.size_bytes == 32
    assert artifact.url
    assert artifact.view_url.endswith(f"/dashboard/artifacts/{artifact.artifact_id}")

    listed = service.list_artifacts(TEST_USER_EMAIL)
    assert len(listed) == 1
    assert listed[0].artifact_id == artifact.artifact_id
    assert listed[0].source.skill_id == "html_report"

    stored = service.repository.find_by_id(TEST_USER_EMAIL, artifact.artifact_id)
    assert stored is not None
    assert stored.s3_key.startswith("users/")
    assert "/artifacts/" in stored.s3_key

    s3_object = boto3.client("s3", region_name="us-east-1").get_object(
        Bucket="innomightlabs-conversations-meta",
        Key=stored.s3_key,
    )
    assert s3_object["ContentType"] == "text/html"
    assert s3_object["Body"].read() == b"<html><body>Report</body></html>"


def test_artifact_service_is_owner_scoped(dynamodb_table, monkeypatch):
    _create_media_bucket()
    monkeypatch.setattr("src.artifacts.storage.settings.conversation_media_bucket", "innomightlabs-conversations-meta")

    service = ArtifactService()
    artifact = service.create_artifact(
        owner_email=TEST_USER_EMAIL,
        artifact_type="file",
        title="Export",
        filename="export.txt",
        mime_type="text/plain",
        body=b"hello",
    )

    assert service.repository.find_by_id("other@example.com", artifact.artifact_id) is None


def test_artifact_storage_uses_conversation_media_region(monkeypatch):
    captured = {}

    class FakeBoto3:
        def client(self, service_name: str, *, region_name: str):
            captured["service_name"] = service_name
            captured["region_name"] = region_name
            return object()

    monkeypatch.setattr("src.artifacts.storage.boto3", FakeBoto3())
    monkeypatch.setattr("src.artifacts.storage.settings.aws_region", "eu-west-2")
    monkeypatch.setattr("src.artifacts.storage.settings.conversation_media_region", "us-east-1")

    ArtifactStorage()

    assert captured == {"service_name": "s3", "region_name": "us-east-1"}


def test_artifacts_router_lists_gets_downloads_and_views(test_client: TestClient, auth_headers: dict, dynamodb_table):
    from main import app
    from src.artifacts.router import get_artifact_service

    _create_media_bucket()
    service = ArtifactService()
    artifact = service.create_artifact(
        owner_email=TEST_USER_EMAIL,
        artifact_type="html_report",
        title="Report",
        filename="report.html",
        mime_type="text/html",
        body=b"<html></html>",
    )

    app.dependency_overrides[get_artifact_service] = lambda: service
    try:
        list_response = test_client.get("/artifacts", headers=auth_headers)
        detail_response = test_client.get(f"/artifacts/{artifact.artifact_id}", headers=auth_headers)
        download_response = test_client.get(f"/artifacts/{artifact.artifact_id}/download", headers=auth_headers)
        view_response = test_client.get(f"/artifacts/{artifact.artifact_id}/view", headers=auth_headers)
    finally:
        app.dependency_overrides.pop(get_artifact_service, None)

    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["artifact_id"] == artifact.artifact_id
    assert detail_response.status_code == 200
    assert detail_response.json()["filename"] == "report.html"
    assert detail_response.json()["view_url"].endswith(f"/dashboard/artifacts/{artifact.artifact_id}")
    assert download_response.status_code == 200
    assert "url" in download_response.json()
    assert view_response.status_code == 200
    assert "report.html" in view_response.json()["url"]
    assert "response-content-disposition=inline" in view_response.json()["url"]


def test_artifact_view_rejects_non_html_artifact(dynamodb_table, monkeypatch):
    _create_media_bucket()
    monkeypatch.setattr("src.artifacts.storage.settings.conversation_media_bucket", "innomightlabs-conversations-meta")

    service = ArtifactService()
    artifact = service.create_artifact(
        owner_email=TEST_USER_EMAIL,
        artifact_type="file",
        title="Export",
        filename="export.txt",
        mime_type="text/plain",
        body=b"hello",
    )

    from src.artifacts.service import ArtifactNotViewableError

    with pytest.raises(ArtifactNotViewableError):
        service.view_url(TEST_USER_EMAIL, artifact.artifact_id)


def test_artifacts_router_returns_404_for_missing_artifact(test_client: TestClient, auth_headers: dict):
    response = test_client.get("/artifacts/missing", headers=auth_headers)
    assert response.status_code == 404


def test_sanitize_filename_removes_paths_and_unsafe_characters():
    assert sanitize_filename("../folder/My Report!.html") == "My-Report-.html"
    assert sanitize_filename("///") == "artifact"
