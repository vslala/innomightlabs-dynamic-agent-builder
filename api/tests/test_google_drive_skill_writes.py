from __future__ import annotations

import asyncio
import json
from email import policy
from email.parser import BytesParser
from typing import Any

import httpx
import pytest

from src.skills.google_drive import actions
from src.skills.google_drive.models import FOLDER_MIME_TYPE, GOOGLE_DOC_MIME_TYPE
from src.skills.registry import SkillRegistry

CONTEXT = {"account_id": "drive-account", "owner_email": "owner@example.com"}
DriveHTTP = tuple[list[httpx.Request], list[httpx.Response]]


@pytest.fixture
def drive_http(monkeypatch: pytest.MonkeyPatch) -> DriveHTTP:
    requests: list[httpx.Request] = []
    responses: list[httpx.Response] = []
    original_client = httpx.AsyncClient

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["Authorization"] == "Bearer drive-token"
        assert request.url.params["supportsAllDrives"] == "true"
        assert "id" in request.url.params["fields"]
        return responses.pop(0)

    def client(*, timeout: float) -> httpx.AsyncClient:
        assert timeout == 30.0
        return original_client(transport=httpx.MockTransport(respond), timeout=timeout)

    async def access_token(context: dict[str, Any]) -> str:
        assert context == CONTEXT
        return "drive-token"

    monkeypatch.setattr(actions.httpx, "AsyncClient", client)
    monkeypatch.setattr(actions, "_get_access_token", access_token)
    return requests, responses


def multipart(request: httpx.Request) -> tuple[dict[str, Any], bytes, str]:
    assert request.headers["Content-Type"].startswith("multipart/related;")
    message = BytesParser(policy=policy.default).parsebytes(
        f"Content-Type: {request.headers['Content-Type']}\r\nMIME-Version: 1.0\r\n\r\n".encode()
        + request.content
    )
    metadata, media = list(message.iter_parts())
    assert metadata.get_content_type() == "application/json"
    assert media.get_content_charset() == "utf-8"
    metadata_bytes = metadata.get_payload(decode=True)
    media_bytes = media.get_payload(decode=True)
    assert isinstance(metadata_bytes, bytes)
    assert isinstance(media_bytes, bytes)
    metadata_json = json.loads(metadata_bytes)
    assert isinstance(metadata_json, dict)
    return metadata_json, media_bytes, media.get_content_type()


@pytest.mark.parametrize("mime_type", ["text/plain", "text/markdown", "text/csv", "application/json", "application/xml"])
def test_create_text_payload_and_result(drive_http: DriveHTTP, mime_type: str) -> None:
    requests, responses = drive_http
    responses.append(httpx.Response(200, json={"id": "new-file", "name": "Résumé", "mimeType": mime_type}))
    content = '  café ☕\r\n{"key": "value"}\n'
    result = asyncio.run(actions.create({
        "name": " Résumé ", "content": content, "mime_type": mime_type,
        "description": "Description", "parent_folder_id": " shared-folder ",
    }, {}, CONTEXT))
    assert "Created Google Drive entry:" in result
    assert "[new-file] Résumé" in result
    request, = requests
    assert request.method == "POST"
    assert str(request.url).startswith(actions.GOOGLE_DRIVE_UPLOAD_API + "?")
    assert request.url.params["uploadType"] == "multipart"
    metadata, media, media_type = multipart(request)
    assert metadata == {
        "name": "Résumé", "mimeType": mime_type, "description": "Description", "parents": ["shared-folder"],
    }
    assert media == content.encode("utf-8")
    assert media_type == mime_type


def test_create_defaults_to_empty_text_file(drive_http: DriveHTTP) -> None:
    requests, responses = drive_http
    responses.append(httpx.Response(200, json={"id": "empty", "name": "empty.txt"}))
    asyncio.run(actions.create({"name": "empty.txt"}, {}, CONTEXT))
    metadata, media, media_type = multipart(requests[0])
    assert metadata == {"name": "empty.txt", "mimeType": "text/plain"}
    assert media == b""
    assert media_type == "text/plain"


@pytest.mark.parametrize("mime_type", [FOLDER_MIME_TYPE, GOOGLE_DOC_MIME_TYPE])
def test_create_empty_native_entry(drive_http: DriveHTTP, mime_type: str) -> None:
    requests, responses = drive_http
    responses.append(httpx.Response(200, json={"id": "native", "name": "Entry", "mimeType": mime_type}))
    asyncio.run(actions.create({"name": "Entry", "mime_type": mime_type, "parent_folder_id": "root"}, {}, CONTEXT))
    request, = requests
    assert request.method == "POST"
    assert str(request.url).startswith(actions.GOOGLE_DRIVE_FILES_API + "?")
    assert "uploadType" not in request.url.params
    assert json.loads(request.content) == {"name": "Entry", "mimeType": mime_type, "parents": ["root"]}


@pytest.mark.parametrize("content", ["Hello, world!\n", ""])
def test_create_google_doc_imports_plain_text(drive_http: DriveHTTP, content: str) -> None:
    requests, responses = drive_http
    responses.append(httpx.Response(200, json={"id": "doc", "name": "Doc", "mimeType": GOOGLE_DOC_MIME_TYPE}))
    asyncio.run(actions.create({"name": "Doc", "mime_type": GOOGLE_DOC_MIME_TYPE, "content": content}, {}, CONTEXT))
    metadata, media, media_type = multipart(requests[0])
    assert metadata == {"name": "Doc", "mimeType": GOOGLE_DOC_MIME_TYPE}
    assert media_type == "text/plain"
    assert media == content.encode()


@pytest.mark.parametrize("arguments", [
    {}, {"name": "  "}, {"name": 123}, {"name": "x", "content": 123},
    {"name": "x", "parent_folder_id": " "}, {"name": "x", "description": []},
    {"name": "x", "mime_type": "application/pdf"},
    {"name": "x", "mime_type": "application/json-not-really"},
    {"name": "x", "mime_type": "text/plain\r\nX-Header: injected"},
    {"name": "x", "mime_type": "application/vnd.google-apps.spreadsheet"},
    {"name": "x", "mime_type": FOLDER_MIME_TYPE, "content": ""},
    {"name": "x", "mime_type": FOLDER_MIME_TYPE, "content": "text"},
    {"name": "x", "parents": ["unrecognized"]},
])
def test_create_validates_before_oauth(monkeypatch: pytest.MonkeyPatch, arguments: dict[str, Any]) -> None:
    async def unexpected_token(context: dict[str, Any]) -> str:
        pytest.fail("Invalid arguments must fail before OAuth or HTTP")

    monkeypatch.setattr(actions, "_get_access_token", unexpected_token)
    with pytest.raises(ValueError):
        asyncio.run(actions.create(arguments, {}, CONTEXT))


@pytest.mark.parametrize("arguments", [
    {}, {"file_id": " "}, {"file_id": "id"}, {"file_id": "id", "name": " "},
    {"file_id": "id", "content": None}, {"file_id": "id", "description": None},
    {"file_id": "id", "name": None}, {"file_id": "id", "content": 123},
    {"file_id": "id", "name": "new", "mime_type": "text/plain"},
    {"file_id": "id", "parent_folder_id": "move"},
])
def test_update_validates_before_oauth(monkeypatch: pytest.MonkeyPatch, arguments: dict[str, Any]) -> None:
    async def unexpected_token(context: dict[str, Any]) -> str:
        pytest.fail("Invalid arguments must fail before OAuth or HTTP")

    monkeypatch.setattr(actions, "_get_access_token", unexpected_token)
    with pytest.raises(ValueError):
        asyncio.run(actions.update(arguments, {}, CONTEXT))


@pytest.mark.parametrize("mime_type", [GOOGLE_DOC_MIME_TYPE, FOLDER_MIME_TYPE, "application/pdf"])
@pytest.mark.parametrize("changes", [{"name": "Renamed"}, {"description": ""}, {"name": "Renamed", "description": "New"}])
def test_update_metadata_and_modify_alias(drive_http: DriveHTTP, changes: dict[str, str], mime_type: str) -> None:
    requests, responses = drive_http
    responses.append(httpx.Response(200, json={"id": "native-doc", "name": "Renamed", "mimeType": mime_type}))
    registry = SkillRegistry()
    result = asyncio.run(registry.execute_action("google_drive", "modify", {"file_id": "native-doc", **changes}, {}, CONTEXT))
    assert "Updated Google Drive entry:" in result
    assert "[native-doc] Renamed" in result
    request, = requests
    assert request.method == "PATCH"
    assert request.url.path == "/drive/v3/files/native-doc"
    assert json.loads(request.content) == changes
    assert "uploadType" not in request.url.params


@pytest.mark.parametrize("content", ["  replacement ☕\n", ""])
@pytest.mark.parametrize("mime_type", ["text/plain", "application/json"])
def test_update_replaces_text_and_metadata_together(drive_http: DriveHTTP, content: str, mime_type: str) -> None:
    requests, responses = drive_http
    responses.extend([
        httpx.Response(200, json={"id": "file", "mimeType": mime_type}),
        httpx.Response(200, json={"id": "file", "name": "New name", "mimeType": mime_type}),
    ])
    asyncio.run(actions.update({"file_id": "file", "name": "New name", "description": "", "content": content}, {}, CONTEXT))
    assert [request.method for request in requests] == ["GET", "PATCH"]
    request = requests[1]
    assert request.url.path == "/upload/drive/v3/files/file"
    assert request.url.params["uploadType"] == "multipart"
    metadata, media, media_type = multipart(request)
    assert metadata == {"name": "New name", "description": ""}
    assert media_type == mime_type
    assert media == content.encode()


def test_update_content_only_does_not_change_metadata(drive_http: DriveHTTP) -> None:
    requests, responses = drive_http
    responses.extend([
        httpx.Response(200, json={"mimeType": "text/plain"}),
        httpx.Response(200, json={"id": "file", "name": "Unchanged"}),
    ])
    asyncio.run(actions.update({"file_id": "file", "content": "new"}, {}, CONTEXT))
    assert multipart(requests[1])[0] == {}


@pytest.mark.parametrize("mime_type", [
    GOOGLE_DOC_MIME_TYPE, FOLDER_MIME_TYPE, "application/vnd.google-apps.spreadsheet",
    "application/vnd.google-apps.presentation", "application/vnd.google-apps.shortcut",
    "application/pdf", "image/png", "application/json-fake", "", "text/plain\r\nInjected: yes",
])
def test_update_rejects_unsupported_content_without_mutating(drive_http: DriveHTTP, mime_type: str) -> None:
    requests, responses = drive_http
    responses.append(httpx.Response(200, json={"mimeType": mime_type}))
    with pytest.raises(ValueError, match="Content replacement supports stored text-like files only"):
        asyncio.run(actions.update({"file_id": "file", "content": "", "name": "Must not rename"}, {}, CONTEXT))
    assert [request.method for request in requests] == ["GET"]


@pytest.mark.parametrize("operation", ["create", "update", "replace", "metadata_fetch"])
@pytest.mark.parametrize("status", [400, 403, 404, 500])
def test_write_api_errors_are_bounded(drive_http: DriveHTTP, operation: str, status: int) -> None:
    requests, responses = drive_http
    if operation == "replace":
        responses.append(httpx.Response(200, json={"mimeType": "text/plain"}))
    responses.append(httpx.Response(status, text="x" * 800))
    if operation == "create":
        action, arguments = actions.create, {"name": "file", "content": "text"}
    elif operation == "metadata_fetch":
        action, arguments = actions.update, {"file_id": "file", "content": "text"}
    else:
        action = actions.update
        arguments = {"file_id": "file", "content": "text"} if operation == "replace" else {"file_id": "file", "description": ""}
    with pytest.raises(RuntimeError, match=rf"Google Drive .*failed \({status}\)") as error:
        asyncio.run(action(arguments, {}, CONTEXT))
    assert str(error.value).endswith("x" * 400)
    assert "x" * 401 not in str(error.value)
    if operation == "metadata_fetch":
        assert [request.method for request in requests] == ["GET"]


@pytest.mark.parametrize("action, arguments", [(actions.create, {"name": "file"}), (actions.update, {"file_id": "file", "name": "new"})])
def test_writes_propagate_oauth_errors(monkeypatch: pytest.MonkeyPatch, action: Any, arguments: dict[str, Any]) -> None:
    async def disconnected(context: dict[str, Any]) -> str:
        raise ValueError("Google Drive is not connected for this account")

    monkeypatch.setattr(actions, "_get_access_token", disconnected)
    with pytest.raises(ValueError, match="not connected"):
        asyncio.run(action(arguments, {}, CONTEXT))


def test_drive_manifest_registers_write_actions_and_schemas() -> None:
    registry = SkillRegistry()
    loaded = registry.get("google_drive")
    assert loaded is not None
    manifest = loaded.manifest
    assert manifest.requires_oauth
    assert manifest.oauth_provider_name == "GoogleDrive"
    create = manifest.find_action("create")
    update = manifest.find_action("update")
    assert create is not None and update is not None
    assert create.handler == "actions:create"
    assert update.handler == "actions:update"
    assert manifest.find_action("modify") == update
    assert create.input_schema["required"] == ["name"]
    assert update.input_schema["required"] == ["file_id"]
    assert create.input_schema["additionalProperties"] is False
    assert update.input_schema["additionalProperties"] is False
    assert set(create.input_schema["properties"]) == {"name", "description", "content", "mime_type", "parent_folder_id"}
    assert set(update.input_schema["properties"]) == {"file_id", "name", "description", "content"}
    assert registry._resolve_handler("google_drive", create.handler) is actions.create
    assert registry._resolve_handler("google_drive", update.handler) is actions.update
