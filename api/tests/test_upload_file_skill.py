from __future__ import annotations

import asyncio
import base64
from pathlib import Path

import boto3
import httpx
import pytest
import yaml

from src.artifacts.service import ArtifactService
from src.skills.registry import SkillRegistry
from src.skills.workspaces import workspace_id_from_context
from src.skills.upload_file.actions import upload_file as upload_file_action
from src.skills.upload_file.mime import infer_mime_type
from src.skills.upload_file.models import MAX_ARTIFACT_UPLOAD_BYTES, UploadFileRequest
from tests.mock_data import owner_for, user_id_for, account_for, TEST_USER_EMAIL


def upload_file(arguments: dict, config: dict, context: dict) -> dict:
    return asyncio.run(upload_file_action(arguments, config, context))


def _create_media_bucket(bucket_name: str = "innomightlabs-conversations-meta") -> None:
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=bucket_name)


def _context() -> dict:
    return {
        "account_id": account_for(TEST_USER_EMAIL),
        "owner_id": user_id_for(TEST_USER_EMAIL),
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

    stored = ArtifactService().repository.find_by_id(owner_for(TEST_USER_EMAIL).member_pk, result["artifact_id"])
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


MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 4 + bytes(range(256)) * 40
WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 600


def _runner(monkeypatch, handler):
    """The workspace source, talking to a fake runner."""
    from src.skills.upload_file import sources

    monkeypatch.setattr("src.skills.upload_file.sources.settings.cli_runner_base_url", "http://runner")
    monkeypatch.setattr("src.skills.upload_file.sources.settings.cli_runner_shared_token", "secret")
    monkeypatch.setattr(
        sources, "SOURCES", [sources.WorkspaceFileSource(httpx.MockTransport(handler)), sources.InlineContentSource()]
    )


def _video_arguments(**overrides) -> dict:
    return {
        "artifact_type": "video",
        "title": "Tour",
        "filename": "tour.mp4",
        "workspace_path": "videos/tour.mp4",
        **overrides,
    }


def test_a_workspace_video_is_streamed_from_the_runner_into_an_artifact(dynamodb_table, monkeypatch):
    _create_media_bucket()
    monkeypatch.setattr("src.artifacts.storage.settings.conversation_media_bucket", "innomightlabs-conversations-meta")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"], seen["auth"] = request.url, request.headers["authorization"]
        return httpx.Response(200, content=MP4)

    _runner(monkeypatch, handler)

    result = upload_file(_video_arguments(mime_type="text/html"), {}, _context())

    assert seen["url"].path == "/v1/filesystem/files"
    assert seen["url"].params["path"] == "videos/tour.mp4"
    assert seen["url"].params["workspace_id"] == workspace_id_from_context(_context())
    assert seen["auth"] == "Bearer secret"
    assert result["mime_type"] == "video/mp4", "an agent can't relabel a video"
    assert result["size_bytes"] == len(MP4)
    assert result["view_url"], "a video opens in the browser"
    stored = boto3.client("s3", region_name="us-east-1").get_object(
        Bucket="innomightlabs-conversations-meta",
        Key=ArtifactService().repository.find_by_id(owner_for(TEST_USER_EMAIL).member_pk, result["artifact_id"]).s3_key,
    )
    assert stored["Body"].read() == MP4
    assert stored["ContentType"] == "video/mp4"


def test_the_workspace_always_comes_from_the_run_not_the_arguments(dynamodb_table, monkeypatch):
    _create_media_bucket()
    monkeypatch.setattr("src.artifacts.storage.settings.conversation_media_bucket", "innomightlabs-conversations-meta")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["id"] = request.url.params["workspace_id"]
        return httpx.Response(200, content=WEBM)

    _runner(monkeypatch, handler)

    upload_file(_video_arguments(filename="a.webm", workspace_id="f" * 48), {}, _context())

    assert seen["id"] == workspace_id_from_context(_context())


def test_video_requests_are_checked_before_the_runner_is_called():
    for arguments, message in (
        ({"artifact_type": "video", "title": "T", "filename": "a.mp4", "text_content": "x"}, "workspace_path"),
        ({"artifact_type": "text", "title": "T", "filename": "a.txt", "text_content": "x", "workspace_path": "a"}, "exactly one"),
    ):
        with pytest.raises(ValueError, match=message):
            UploadFileRequest.model_validate(arguments)


@pytest.mark.parametrize(
    ("filename", "body", "message"),
    [
        ("tour.gif", MP4, "must end with"),
        ("tour.mp4", b"<html>not a video</html>" * 20, "not a valid mp4"),
        ("tour.webm", MP4, "not a valid webm"),
        ("tour.mp4", WEBM, "not a valid mp4"),
    ],
)
def test_a_file_that_is_not_the_video_it_claims_is_refused(dynamodb_table, monkeypatch, filename, body, message):
    _runner(monkeypatch, lambda request: httpx.Response(200, content=body))

    with pytest.raises(ValueError, match=message):
        upload_file(_video_arguments(filename=filename), {}, _context())


def test_a_video_over_the_limit_is_refused_while_streaming(dynamodb_table, monkeypatch):
    monkeypatch.setattr("src.skills.upload_file.actions.max_bytes_for", lambda artifact_type: 1000)
    _runner(monkeypatch, lambda request: httpx.Response(200, content=MP4))

    with pytest.raises(ValueError, match="upload limit"):
        upload_file(_video_arguments(), {}, _context())


def test_runner_refusals_are_explained(dynamodb_table, monkeypatch):
    for status, message in ((404, "isn't in this conversation's workspace"), (401, "credentials"), (400, "sandbox_violation")):
        _runner(monkeypatch, lambda request, status=status: httpx.Response(status, json={"detail": "sandbox_violation: no"}))
        with pytest.raises(RuntimeError, match=message):
            upload_file(_video_arguments(), {}, _context())


def test_video_mime_types_follow_the_extension():
    assert infer_mime_type("video", "a.webm", None) == "video/webm"
    assert infer_mime_type("video", "a.MOV", "text/html") == "video/quicktime"
