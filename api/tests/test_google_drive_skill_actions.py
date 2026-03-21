from __future__ import annotations

import asyncio
import sys
import types

from src.skills.google_drive.actions import delete, read, search


class FakeResponse:
    def __init__(self, *, status_code: int = 200, json_data=None, text: str = "", content: bytes = b""):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text
        self.content = content

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self):
        return self._json_data


class FakeAsyncClient:
    def __init__(self, responses: list[FakeResponse]):
        self._responses = responses
        self.patch_calls: list[dict] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get(self, url, params=None, headers=None):
        del url, params, headers
        return self._responses.pop(0)

    async def patch(self, url, params=None, headers=None, json=None):
        self.patch_calls.append({"url": url, "params": params, "headers": headers, "json": json})
        return self._responses.pop(0)


def test_google_drive_search_returns_compact_results(monkeypatch):
    captured: dict = {}

    async def fake_access_token(context):
        assert context["owner_email"] == "owner@example.com"
        return "token"

    class CapturingClient(FakeAsyncClient):
        async def get(self, url, params=None, headers=None):
            captured["url"] = url
            captured["params"] = params
            return await super().get(url, params=params, headers=headers)

    fake_client = CapturingClient(
        [
            FakeResponse(
                json_data={
                    "files": [
                        {
                            "id": "file-1",
                            "name": "Roadmap",
                            "mimeType": "text/plain",
                            "modifiedTime": "2026-03-16T10:00:00Z",
                            "size": "120",
                            "trashed": False,
                            "webViewLink": "https://drive.google.com/file/d/file-1/view",
                        }
                    ]
                }
            )
        ]
    )

    monkeypatch.setattr("src.skills.google_drive.actions._get_access_token", fake_access_token)
    monkeypatch.setattr("src.skills.google_drive.actions.httpx.AsyncClient", lambda timeout=20.0: fake_client)

    result = asyncio.run(search({"query": "roadmap"}, {}, {"owner_email": "owner@example.com"}))
    assert "Google Drive results:" in result
    assert "[file-1] Roadmap" in result
    assert "type=file" in result
    assert captured["params"]["supportsAllDrives"] == "true"
    assert captured["params"]["includeItemsFromAllDrives"] == "true"


def test_google_drive_search_supports_children_mode_and_folder_filter(monkeypatch):
    captured: dict = {}

    async def fake_access_token(context):
        del context
        return "token"

    class CapturingClient(FakeAsyncClient):
        async def get(self, url, params=None, headers=None):
            captured["url"] = url
            captured["params"] = params
            captured["headers"] = headers
            return await super().get(url, params=params, headers=headers)

    fake_client = CapturingClient(
        [
            FakeResponse(
                json_data={
                    "files": [
                        {
                            "id": "folder-1",
                            "name": "Personal",
                            "mimeType": "application/vnd.google-apps.folder",
                            "modifiedTime": "2026-03-16T10:00:00Z",
                            "size": None,
                            "trashed": False,
                            "webViewLink": "https://drive.google.com/drive/folders/folder-1",
                        }
                    ]
                }
            )
        ]
    )

    monkeypatch.setattr("src.skills.google_drive.actions._get_access_token", fake_access_token)
    monkeypatch.setattr("src.skills.google_drive.actions.httpx.AsyncClient", lambda timeout=20.0: fake_client)

    result = asyncio.run(
        search(
            {
                "mode": "children",
                "parent_folder_id": "parent-123",
                "entry_type": "folders",
                "query": "Personal",
                "order_by": "name",
            },
            {},
            {"owner_email": "owner@example.com"},
        )
    )

    assert "Google Drive children for folder parent-123:" in result
    assert "type=folder" in result
    assert "'parent-123' in parents" in captured["params"]["q"]
    assert "mimeType = 'application/vnd.google-apps.folder'" in captured["params"]["q"]
    assert "name contains 'Personal'" in captured["params"]["q"]
    assert captured["params"]["orderBy"] == "name"
    assert captured["params"]["supportsAllDrives"] == "true"
    assert captured["params"]["includeItemsFromAllDrives"] == "true"


def test_google_drive_search_children_retries_with_shortcut_target_and_drive_id(monkeypatch):
    captured_calls: list[dict] = []

    async def fake_access_token(context):
        del context
        return "token"

    class CapturingClient(FakeAsyncClient):
        async def get(self, url, params=None, headers=None):
            captured_calls.append({"url": url, "params": params, "headers": headers})
            return await super().get(url, params=params, headers=headers)

    fake_client = CapturingClient(
        [
            FakeResponse(json_data={"files": []}),
            FakeResponse(
                json_data={
                    "id": "shortcut-1",
                    "name": "Personal Folder",
                    "mimeType": "application/vnd.google-apps.shortcut",
                    "driveId": "drive-123",
                    "shortcutDetails": {
                        "targetId": "folder-target-1",
                        "targetMimeType": "application/vnd.google-apps.folder",
                    },
                }
            ),
            FakeResponse(
                json_data={
                    "id": "folder-target-1",
                    "name": "Personal Folder",
                    "mimeType": "application/vnd.google-apps.folder",
                    "driveId": "drive-123",
                }
            ),
            FakeResponse(
                json_data={
                    "files": [
                        {
                            "id": "file-9",
                            "name": "doc.txt",
                            "mimeType": "text/plain",
                            "modifiedTime": "2026-03-16T10:00:00Z",
                            "size": "10",
                            "trashed": False,
                            "webViewLink": "https://drive.google.com/file/d/file-9/view",
                        }
                    ]
                }
            ),
        ]
    )

    monkeypatch.setattr("src.skills.google_drive.actions._get_access_token", fake_access_token)
    monkeypatch.setattr("src.skills.google_drive.actions.httpx.AsyncClient", lambda timeout=20.0: fake_client)

    result = asyncio.run(
        search(
            {
                "mode": "children",
                "parent_folder_id": "shortcut-1",
                "entry_type": "files",
            },
            {},
            {"owner_email": "owner@example.com"},
        )
    )

    assert "[file-9] doc.txt" in result
    list_calls = [call for call in captured_calls if call["url"].endswith("/files")]
    assert list_calls[0]["params"]["corpora"] == "allDrives"
    assert list_calls[-1]["params"]["corpora"] == "drive"
    assert list_calls[-1]["params"]["driveId"] == "drive-123"
    assert "'folder-target-1' in parents" in list_calls[-1]["params"]["q"]


def test_google_drive_search_children_ignores_parent_metadata_404_after_empty_list(monkeypatch):
    async def fake_access_token(context):
        del context
        return "token"

    fake_client = FakeAsyncClient(
        [
            FakeResponse(json_data={"files": []}),
            FakeResponse(status_code=404, text="File not found"),
        ]
    )

    monkeypatch.setattr("src.skills.google_drive.actions._get_access_token", fake_access_token)
    monkeypatch.setattr("src.skills.google_drive.actions.httpx.AsyncClient", lambda timeout=20.0: fake_client)

    result = asyncio.run(
        search(
            {
                "mode": "children",
                "parent_folder_id": "1DqKSfGCflgo6rYffMNuBtrnYcA5tw8GV",
                "entry_type": "files",
            },
            {},
            {"owner_email": "owner@example.com"},
        )
    )

    assert result == "No Google Drive files found for those filters."


def test_google_drive_search_children_recursive_finds_nested_files(monkeypatch):
    async def fake_access_token(context):
        del context
        return "token"

    fake_client = FakeAsyncClient(
        [
            FakeResponse(
                json_data={
                    "id": "root-1",
                    "name": "Root",
                    "mimeType": "application/vnd.google-apps.folder",
                    "driveId": "drive-1",
                }
            ),
            FakeResponse(
                json_data={
                    "files": [
                        {
                            "id": "sub-1",
                            "name": "Subfolder",
                            "mimeType": "application/vnd.google-apps.folder",
                            "modifiedTime": "2026-03-16T10:00:00Z",
                            "size": None,
                            "trashed": False,
                            "webViewLink": "https://drive.google.com/drive/folders/sub-1",
                            "parents": ["root-1"],
                            "driveId": "drive-1",
                        }
                    ]
                }
            ),
            FakeResponse(
                json_data={
                    "files": [
                        {
                            "id": "file-deep-1",
                            "name": "deep.txt",
                            "mimeType": "text/plain",
                            "modifiedTime": "2026-03-16T10:01:00Z",
                            "size": "99",
                            "trashed": False,
                            "webViewLink": "https://drive.google.com/file/d/file-deep-1/view",
                            "parents": ["sub-1"],
                            "driveId": "drive-1",
                        }
                    ]
                }
            ),
        ]
    )

    monkeypatch.setattr("src.skills.google_drive.actions._get_access_token", fake_access_token)
    monkeypatch.setattr("src.skills.google_drive.actions.httpx.AsyncClient", lambda timeout=20.0: fake_client)

    result = asyncio.run(
        search(
            {
                "mode": "children",
                "parent_folder_id": "root-1",
                "entry_type": "files",
                "recursive": True,
            },
            {},
            {"owner_email": "owner@example.com"},
        )
    )

    assert "Google Drive recursive children for folder root-1:" in result
    assert "[file-deep-1] deep.txt" in result


def test_google_drive_search_children_diagnostics_includes_parent_resolution(monkeypatch):
    async def fake_access_token(context):
        del context
        return "token"

    fake_client = FakeAsyncClient(
        [
            FakeResponse(json_data={"files": []}),
            FakeResponse(
                json_data={
                    "id": "shortcut-1",
                    "name": "Personal Folder",
                    "mimeType": "application/vnd.google-apps.shortcut",
                    "driveId": "drive-123",
                    "shortcutDetails": {
                        "targetId": "folder-target-1",
                        "targetMimeType": "application/vnd.google-apps.folder",
                    },
                }
            ),
            FakeResponse(
                json_data={
                    "id": "folder-target-1",
                    "name": "Personal Folder",
                    "mimeType": "application/vnd.google-apps.folder",
                    "driveId": "drive-123",
                }
            ),
            FakeResponse(json_data={"files": []}),
        ]
    )

    monkeypatch.setattr("src.skills.google_drive.actions._get_access_token", fake_access_token)
    monkeypatch.setattr("src.skills.google_drive.actions.httpx.AsyncClient", lambda timeout=20.0: fake_client)

    result = asyncio.run(
        search(
            {
                "mode": "children",
                "parent_folder_id": "shortcut-1",
                "entry_type": "files",
                "diagnostics": True,
            },
            {},
            {"owner_email": "owner@example.com"},
        )
    )

    assert "No Google Drive files found for those filters." in result
    assert "<diagnostics>" in result
    assert "requested_parent_id=shortcut-1" in result
    assert "resolved_parent_id=folder-target-1" in result
    assert "shortcut_target_found=True" in result


def test_google_drive_search_requires_parent_for_children_mode(monkeypatch):
    async def fake_access_token(context):
        del context
        return "token"

    monkeypatch.setattr("src.skills.google_drive.actions._get_access_token", fake_access_token)

    try:
        asyncio.run(search({"mode": "children"}, {}, {"owner_email": "owner@example.com"}))
        assert False, "expected parent_folder_id requirement"
    except ValueError as exc:
        assert "parent_folder_id is required when mode=children" in str(exc)


def test_google_drive_read_supports_google_doc_export(monkeypatch):
    async def fake_access_token(context):
        del context
        return "token"

    fake_client = FakeAsyncClient(
        [
            FakeResponse(
                json_data={
                    "id": "doc-1",
                    "name": "Spec",
                    "mimeType": "application/vnd.google-apps.document",
                    "modifiedTime": "2026-03-16T10:00:00Z",
                    "size": "0",
                    "trashed": False,
                    "webViewLink": "https://drive.google.com/file/d/doc-1/view",
                }
            ),
            FakeResponse(text="Hello from Google Docs"),
        ]
    )

    monkeypatch.setattr("src.skills.google_drive.actions._get_access_token", fake_access_token)
    monkeypatch.setattr("src.skills.google_drive.actions.httpx.AsyncClient", lambda timeout=30.0: fake_client)

    result = asyncio.run(read({"file_id": "doc-1"}, {}, {"owner_email": "owner@example.com"}))
    assert "Hello from Google Docs" in result
    assert "content_truncated=False" in result


def test_google_drive_read_supports_text_download(monkeypatch):
    async def fake_access_token(context):
        del context
        return "token"

    fake_client = FakeAsyncClient(
        [
            FakeResponse(
                json_data={
                    "id": "txt-1",
                    "name": "notes.txt",
                    "mimeType": "text/plain",
                    "modifiedTime": "2026-03-16T10:00:00Z",
                    "size": "22",
                    "trashed": False,
                    "webViewLink": "https://drive.google.com/file/d/txt-1/view",
                }
            ),
            FakeResponse(content=b"plain text body"),
        ]
    )

    monkeypatch.setattr("src.skills.google_drive.actions._get_access_token", fake_access_token)
    monkeypatch.setattr("src.skills.google_drive.actions.httpx.AsyncClient", lambda timeout=30.0: fake_client)

    result = asyncio.run(read({"file_id": "txt-1"}, {}, {"owner_email": "owner@example.com"}))
    assert "plain text body" in result


def test_google_drive_read_supports_pdf(monkeypatch):
    async def fake_access_token(context):
        del context
        return "token"

    class FakePage:
        def extract_text(self):
            return "pdf text"

    class FakePdfReader:
        def __init__(self, stream):
            del stream
            self.pages = [FakePage()]

    fake_client = FakeAsyncClient(
        [
            FakeResponse(
                json_data={
                    "id": "pdf-1",
                    "name": "sample.pdf",
                    "mimeType": "application/pdf",
                    "modifiedTime": "2026-03-16T10:00:00Z",
                    "size": "1200",
                    "trashed": False,
                    "webViewLink": "https://drive.google.com/file/d/pdf-1/view",
                }
            ),
            FakeResponse(content=b"%PDF-1.4"),
        ]
    )

    monkeypatch.setattr("src.skills.google_drive.actions._get_access_token", fake_access_token)
    monkeypatch.setattr("src.skills.google_drive.actions.httpx.AsyncClient", lambda timeout=30.0: fake_client)
    monkeypatch.setitem(sys.modules, "pypdf", types.SimpleNamespace(PdfReader=FakePdfReader))

    result = asyncio.run(read({"file_id": "pdf-1"}, {}, {"owner_email": "owner@example.com"}))
    assert "pdf text" in result


def test_google_drive_read_rejects_unsupported_binary(monkeypatch):
    async def fake_access_token(context):
        del context
        return "token"

    fake_client = FakeAsyncClient(
        [
            FakeResponse(
                json_data={
                    "id": "bin-1",
                    "name": "archive.zip",
                    "mimeType": "application/zip",
                    "modifiedTime": "2026-03-16T10:00:00Z",
                    "size": "2048",
                    "trashed": False,
                    "webViewLink": "https://drive.google.com/file/d/bin-1/view",
                }
            ),
        ]
    )

    monkeypatch.setattr("src.skills.google_drive.actions._get_access_token", fake_access_token)
    monkeypatch.setattr("src.skills.google_drive.actions.httpx.AsyncClient", lambda timeout=30.0: fake_client)

    try:
        asyncio.run(read({"file_id": "bin-1"}, {}, {"owner_email": "owner@example.com"}))
        assert False, "expected unsupported binary error"
    except ValueError as exc:
        assert "Unsupported Google Drive file type" in str(exc)


def test_google_drive_delete_moves_file_to_trash(monkeypatch):
    async def fake_access_token(context):
        del context
        return "token"

    fake_client = FakeAsyncClient(
        [
            FakeResponse(
                json_data={
                    "id": "file-2",
                    "name": "trash-me.txt",
                    "mimeType": "text/plain",
                    "modifiedTime": "2026-03-16T10:00:00Z",
                    "size": "12",
                    "trashed": False,
                    "webViewLink": "https://drive.google.com/file/d/file-2/view",
                }
            ),
            FakeResponse(
                json_data={
                    "id": "file-2",
                    "name": "trash-me.txt",
                    "trashed": True,
                }
            ),
        ]
    )

    monkeypatch.setattr("src.skills.google_drive.actions._get_access_token", fake_access_token)
    monkeypatch.setattr("src.skills.google_drive.actions.httpx.AsyncClient", lambda timeout=20.0: fake_client)

    result = asyncio.run(delete({"file_id": "file-2"}, {}, {"owner_email": "owner@example.com"}))
    assert "Moved Google Drive file to trash" in result
    assert fake_client.patch_calls[0]["json"] == {"trashed": True}
