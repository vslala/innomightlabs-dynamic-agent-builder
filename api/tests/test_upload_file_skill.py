from __future__ import annotations

import asyncio
import base64
from pathlib import Path

import boto3
import pytest
import yaml

from src.skills.registry import SkillRegistry
from src.skills.upload_file.actions import upload_file
from src.skills.upload_file.mime import infer_mime_type
from src.skills.upload_file.models import MAX_ARTIFACT_UPLOAD_BYTES, UploadFileRequest
from tests.mock_data import TEST_USER_EMAIL


def _create_media_bucket(bucket_name: str = "innomightlabs-conversations-meta") -> None:
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=bucket_name)


def _context() -> dict:
    return {
        "owner_email": TEST_USER_EMAIL,
        "agent_id": "agent-1",
        "conversation_id": "conversation-1",
        "user_message_id": "message-1",
        "automation_id": "automation-1",
        "automation_run_id": "run-1",
        "automation_node_id": "node-1",
    }


def test_upload_file_manifest_declares_action_and_aliases():
    with open("src/skills/upload_file/manifest.yml") as handle:
        manifest = yaml.safe_load(handle)

    action = manifest["actions"][0]

    assert manifest["id"] == "upload_file"
    assert manifest["namespace"] == "core.artifacts"
    assert action["name"] == "upload_file"
    assert {"save_artifact", "upload_artifact", "save_file"}.issubset(set(action["aliases"]))


def test_upload_file_text_creates_artifact(dynamodb_table, monkeypatch):
    _create_media_bucket()
    monkeypatch.setattr("src.artifacts.storage.settings.conversation_media_bucket", "innomightlabs-conversations-meta")

    result = upload_file(
        {
            "artifact_type": "markdown",
            "title": "Build Notes",
            "filename": "../build notes.md",
            "text_content": "# Build Notes",
            "metadata": {"topic": "build"},
        },
        {},
        _context(),
    )

    assert result["ok"] is True
    assert result["artifact_type"] == "markdown"
    assert result["filename"] == "build-notes.md"
    assert result["mime_type"] == "text/markdown; charset=utf-8"
    assert result["url"] == result["view_url"]
    assert result["download_url"]

    from src.artifacts.service import ArtifactService

    stored = ArtifactService().repository.find_by_id(TEST_USER_EMAIL, result["artifact_id"])
    assert stored is not None
    assert stored.source.skill_id == "upload_file"
    assert stored.source.agent_id == "agent-1"
    assert stored.source.conversation_id == "conversation-1"
    assert stored.source.metadata == {"topic": "build"}


def test_upload_file_base64_decodes_and_allows_mime_override(dynamodb_table, monkeypatch):
    _create_media_bucket()
    monkeypatch.setattr("src.artifacts.storage.settings.conversation_media_bucket", "innomightlabs-conversations-meta")

    result = upload_file(
        {
            "artifact_type": "csv",
            "title": "Metrics",
            "filename": "metrics.csv",
            "mime_type": "application/vnd.custom+csv",
            "base64_content": base64.b64encode(b"name,value\nwins,3\n").decode("ascii"),
        },
        {},
        _context(),
    )

    assert result["ok"] is True
    assert result["mime_type"] == "application/vnd.custom+csv"
    assert result["size_bytes"] == len(b"name,value\nwins,3\n")


def test_upload_file_rejects_invalid_content_shapes():
    with pytest.raises(ValueError, match="exactly one"):
        UploadFileRequest.model_validate(
            {
                "artifact_type": "text",
                "title": "Bad",
                "filename": "bad.txt",
                "text_content": "a",
                "base64_content": "YQ==",
            }
        )

    with pytest.raises(ValueError, match="valid base64"):
        UploadFileRequest.model_validate(
            {
                "artifact_type": "text",
                "title": "Bad",
                "filename": "bad.txt",
                "base64_content": "not-base64!",
            }
        )

    with pytest.raises(ValueError, match="UTF-8 text"):
        UploadFileRequest.model_validate(
            {
                "artifact_type": "text",
                "title": "Bad",
                "filename": "bad.bin",
                "base64_content": base64.b64encode(b"\xff\xfe").decode("ascii"),
            }
        )


def test_upload_file_rejects_large_payload():
    with pytest.raises(ValueError, match="10 MB"):
        UploadFileRequest.model_validate(
            {
                "artifact_type": "text",
                "title": "Large",
                "filename": "large.txt",
                "text_content": "a" * (MAX_ARTIFACT_UPLOAD_BYTES + 1),
            }
        )


def test_upload_file_html_uses_safety_validator(dynamodb_table, monkeypatch):
    _create_media_bucket()
    monkeypatch.setattr("src.artifacts.storage.settings.conversation_media_bucket", "innomightlabs-conversations-meta")

    safe = upload_file(
        {
            "artifact_type": "html_report",
            "title": "Report",
            "filename": "report.html",
            "text_content": "```html\n<!doctype html><html><head><style>body{color:#111}</style></head><body>Report</body></html>\n```",
        },
        {},
        _context(),
    )

    assert safe["ok"] is True
    assert safe["mime_type"] == "text/html; charset=utf-8"

    with pytest.raises(ValueError, match="blocked <script>"):
        upload_file(
            {
                "artifact_type": "html_report",
                "title": "Bad",
                "filename": "bad.html",
                "text_content": "<!doctype html><html><body><script>alert(1)</script></body></html>",
            },
            {},
            _context(),
        )


def test_upload_file_mime_inference():
    assert infer_mime_type("json", "data.json", None) == "application/json; charset=utf-8"
    assert infer_mime_type("code", "script.py", None) == "text/x-python; charset=utf-8"
    assert infer_mime_type("file", "notes.txt", None) == "text/plain; charset=utf-8"
    assert infer_mime_type("text", "notes.txt", "text/custom") == "text/custom"


def test_upload_file_registry_alias_executes(dynamodb_table, monkeypatch):
    _create_media_bucket()
    monkeypatch.setattr("src.artifacts.storage.settings.conversation_media_bucket", "innomightlabs-conversations-meta")
    registry = SkillRegistry(Path("src/skills"))

    result = asyncio.run(
        registry.execute_action(
            "upload_file",
            "save_file",
            {
                "artifact_type": "text",
                "title": "Hello",
                "filename": "hello.txt",
                "text_content": "hello",
            },
            {},
            _context(),
        )
    )

    assert result["ok"] is True
    assert result["filename"] == "hello.txt"
