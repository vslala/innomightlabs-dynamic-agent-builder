from __future__ import annotations

import asyncio
import base64

import pytest

from src.skills.google_mail.actions import archive, batch_delete, delete, mark_read, mark_unread, read, search
from src.skills.registry import SkillRegistry


class FakeResponse:
    def __init__(self, *, status_code: int = 200, json_data=None, text: str = ""):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self):
        return self._json_data


class FakeAsyncClient:
    def __init__(self, responses: list[FakeResponse]):
        self._responses = responses
        self.get_calls: list[dict] = []
        self.post_calls: list[dict] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get(self, url, params=None, headers=None):
        self.get_calls.append({"url": url, "params": params, "headers": headers})
        return self._responses.pop(0)

    async def post(self, url, data=None, headers=None, json=None):
        self.post_calls.append({"url": url, "data": data, "headers": headers, "json": json})
        return self._responses.pop(0)


def _b64url(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii").rstrip("=")


def test_google_mail_read_returns_headers_and_plain_text_body(monkeypatch):
    async def fake_access_token(context):
        assert context["owner_email"] == "owner@example.com"
        return "token"

    fake_client = FakeAsyncClient(
        [
            FakeResponse(
                json_data={
                    "id": "msg-1",
                    "threadId": "thread-1",
                    "labelIds": ["INBOX", "UNREAD"],
                    "payload": {
                        "headers": [
                            {"name": "Subject", "value": "Roadmap"},
                            {"name": "From", "value": "sender@example.com"},
                            {"name": "To", "value": "owner@example.com"},
                            {"name": "Date", "value": "Wed, 06 May 2026 10:00:00 +0000"},
                        ],
                        "parts": [
                            {
                                "mimeType": "text/plain",
                                "body": {"data": _b64url("Hello from Gmail")},
                            }
                        ],
                    },
                }
            )
        ]
    )

    monkeypatch.setattr("src.skills.google_mail.actions._get_access_token", fake_access_token)
    monkeypatch.setattr("src.skills.google_mail.actions.httpx.AsyncClient", lambda timeout=30.0: fake_client)

    result = asyncio.run(read({"message_id": "msg-1"}, {}, {"owner_email": "owner@example.com"}))

    assert "Gmail message:" in result
    assert "id=msg-1" in result
    assert "subject=Roadmap" in result
    assert "from=sender@example.com" in result
    assert "Hello from Gmail" in result
    assert fake_client.get_calls[0]["url"].endswith("/messages/msg-1")
    assert fake_client.get_calls[0]["params"] == {"format": "full"}


def test_google_mail_read_falls_back_to_html_body(monkeypatch):
    async def fake_access_token(context):
        del context
        return "token"

    fake_client = FakeAsyncClient(
        [
            FakeResponse(
                json_data={
                    "id": "msg-html",
                    "payload": {
                        "headers": [{"name": "Subject", "value": "HTML"}],
                        "parts": [
                            {
                                "mimeType": "text/html",
                                "body": {"data": _b64url("<p>Hello <strong>HTML</strong></p>")},
                            }
                        ],
                    },
                }
            )
        ]
    )

    monkeypatch.setattr("src.skills.google_mail.actions._get_access_token", fake_access_token)
    monkeypatch.setattr("src.skills.google_mail.actions.httpx.AsyncClient", lambda timeout=30.0: fake_client)

    result = asyncio.run(read({"message_id": "msg-html"}, {}, {"owner_email": "owner@example.com"}))

    assert "subject=HTML" in result
    assert "Hello" in result
    assert "HTML" in result


def test_google_mail_search_recent_20_fetches_metadata(monkeypatch):
    async def fake_access_token(context):
        assert context["owner_email"] == "owner@example.com"
        return "token"

    fake_client = FakeAsyncClient(
        [
            FakeResponse(
                json_data={
                    "messages": [{"id": "msg-1", "threadId": "thread-1"}],
                    "nextPageToken": "next-token",
                }
            ),
            FakeResponse(
                json_data={
                    "id": "msg-1",
                    "threadId": "thread-1",
                    "labelIds": ["INBOX", "UNREAD"],
                    "snippet": "Search result snippet",
                    "payload": {
                        "headers": [
                            {"name": "Subject", "value": "Roadmap"},
                            {"name": "From", "value": "sender@example.com"},
                            {"name": "To", "value": "owner@example.com"},
                            {"name": "Date", "value": "Wed, 06 May 2026 10:00:00 +0000"},
                        ]
                    },
                }
            ),
        ]
    )

    monkeypatch.setattr("src.skills.google_mail.actions._get_access_token", fake_access_token)
    monkeypatch.setattr("src.skills.google_mail.actions.httpx.AsyncClient", lambda timeout=20.0: fake_client)

    result = asyncio.run(search({"recent_20": True}, {}, {"owner_email": "owner@example.com"}))

    assert "Gmail search results:" in result
    assert "query=(recent messages)" in result
    assert "result_count=1" in result
    assert "next_page_token=next-token" in result
    assert "id=msg-1" in result
    assert "subject=Roadmap" in result
    assert "snippet=Search result snippet" in result
    assert fake_client.get_calls[0]["url"].endswith("/messages")
    assert fake_client.get_calls[0]["params"]["maxResults"] == 20
    assert "q" not in fake_client.get_calls[0]["params"]
    assert fake_client.get_calls[1]["url"].endswith("/messages/msg-1")
    assert fake_client.get_calls[1]["params"]["format"] == "metadata"


def test_google_mail_search_messages_alias_uses_search_handler(monkeypatch):
    async def fake_access_token(context):
        assert context["owner_email"] == "owner@example.com"
        return "token"

    fake_client = FakeAsyncClient(
        [
            FakeResponse(json_data={"messages": [{"id": "msg-1", "threadId": "thread-1"}]}),
            FakeResponse(
                json_data={
                    "id": "msg-1",
                    "threadId": "thread-1",
                    "labelIds": ["INBOX"],
                    "snippet": "Alias result snippet",
                    "payload": {
                        "headers": [
                            {"name": "Subject", "value": "Alias Result"},
                            {"name": "From", "value": "sender@example.com"},
                        ]
                    },
                }
            ),
        ]
    )

    monkeypatch.setattr("src.skills.google_mail.actions._get_access_token", fake_access_token)
    monkeypatch.setattr("src.skills.google_mail.actions.httpx.AsyncClient", lambda timeout=20.0: fake_client)

    registry = SkillRegistry()
    result = asyncio.run(
        registry.execute_action(
            skill_id="google_mail",
            action_name="search_messages",
            arguments={"query": "marketing", "page_size": 1},
            config={},
            context={"owner_email": "owner@example.com"},
        )
    )

    assert "subject=Alias Result" in result
    assert fake_client.get_calls[0]["params"]["q"] == "marketing"


def test_google_mail_search_builds_rich_query_and_filters(monkeypatch):
    async def fake_access_token(context):
        del context
        return "token"

    fake_client = FakeAsyncClient(
        [
            FakeResponse(json_data={"messages": [{"id": "msg-2", "threadId": "thread-2"}]}),
            FakeResponse(
                json_data={
                    "id": "msg-2",
                    "threadId": "thread-2",
                    "labelIds": ["INBOX"],
                    "payload": {
                        "headers": [
                            {"name": "Subject", "value": "Invoice May"},
                            {"name": "From", "value": "billing@example.com"},
                            {"name": "Date", "value": "Wed, 06 May 2026 09:00:00 +0000"},
                        ]
                    },
                }
            ),
        ]
    )

    monkeypatch.setattr("src.skills.google_mail.actions._get_access_token", fake_access_token)
    monkeypatch.setattr("src.skills.google_mail.actions.httpx.AsyncClient", lambda timeout=20.0: fake_client)

    result = asyncio.run(
        search(
            {
                "query": "invoice",
                "page_size": 100,
                "page_token": "page-2",
                "start_date": "2026-05-01",
                "end_date": "2026/05/07",
                "from_email": "billing@example.com",
                "to_email": "owner@example.com",
                "subject": "May invoice",
                "label_ids": ["INBOX"],
                "category": "primary",
                "has_attachment": True,
                "is_unread": True,
                "include_spam_trash": True,
            },
            {},
            {"owner_email": "owner@example.com"},
        )
    )

    params = fake_client.get_calls[0]["params"]
    assert params["maxResults"] == 50
    assert params["pageToken"] == "page-2"
    assert params["labelIds"] == ["INBOX"]
    assert params["includeSpamTrash"] is True
    assert "invoice" in params["q"]
    assert "after:2026/05/01" in params["q"]
    assert "before:2026/05/07" in params["q"]
    assert 'from:"billing@example.com"' in params["q"]
    assert 'to:"owner@example.com"' in params["q"]
    assert 'subject:"May invoice"' in params["q"]
    assert "category:primary" in params["q"]
    assert "has:attachment" in params["q"]
    assert "is:unread" in params["q"]
    assert "Invoice May" in result


def test_google_mail_search_returns_empty_message(monkeypatch):
    async def fake_access_token(context):
        del context
        return "token"

    fake_client = FakeAsyncClient([FakeResponse(json_data={"messages": []})])

    monkeypatch.setattr("src.skills.google_mail.actions._get_access_token", fake_access_token)
    monkeypatch.setattr("src.skills.google_mail.actions.httpx.AsyncClient", lambda timeout=20.0: fake_client)

    result = asyncio.run(search({"query": "missing"}, {}, {"owner_email": "owner@example.com"}))

    assert result == "No Gmail messages found for query: missing"


def test_google_mail_delete_moves_message_to_trash(monkeypatch):
    async def fake_access_token(context):
        del context
        return "token"

    fake_client = FakeAsyncClient([FakeResponse(json_data={"id": "msg-1"})])

    monkeypatch.setattr("src.skills.google_mail.actions._get_access_token", fake_access_token)
    monkeypatch.setattr("src.skills.google_mail.actions.httpx.AsyncClient", lambda timeout=20.0: fake_client)

    result = asyncio.run(delete({"message_id": "msg-1"}, {}, {"owner_email": "owner@example.com"}))

    assert result == "Moved Gmail message to trash: [msg-1]"
    assert fake_client.post_calls[0]["url"].endswith("/messages/msg-1/trash")


def test_google_mail_batch_delete_moves_messages_to_trash_in_chunks(monkeypatch):
    async def fake_access_token(context):
        del context
        return "token"

    fake_client = FakeAsyncClient(
        [
            FakeResponse(json_data={}),
            FakeResponse(json_data={}),
        ]
    )

    monkeypatch.setattr("src.skills.google_mail.actions._get_access_token", fake_access_token)
    monkeypatch.setattr("src.skills.google_mail.actions.httpx.AsyncClient", lambda timeout=30.0: fake_client)

    result = asyncio.run(
        batch_delete(
            {"message_ids": ["msg-1", "msg-2", "msg-1", " msg-3 "], "chunk_size": 2},
            {},
            {"owner_email": "owner@example.com"},
        )
    )

    assert result == "Moved 3 Gmail message(s) to trash in 2 batch request(s). duplicate_ids_ignored=1"
    assert fake_client.post_calls[0]["url"].endswith("/messages/batchModify")
    assert fake_client.post_calls[0]["json"] == {
        "ids": ["msg-1", "msg-2"],
        "addLabelIds": ["TRASH"],
        "removeLabelIds": ["INBOX"],
    }
    assert fake_client.post_calls[1]["json"] == {
        "ids": ["msg-3"],
        "addLabelIds": ["TRASH"],
        "removeLabelIds": ["INBOX"],
    }


def test_google_mail_batch_delete_rejects_empty_message_ids():
    with pytest.raises(ValueError, match="message_ids"):
        asyncio.run(batch_delete({"message_ids": []}, {}, {"owner_email": "owner@example.com"}))


def test_google_mail_batch_delete_reports_api_failure(monkeypatch):
    async def fake_access_token(context):
        del context
        return "token"

    fake_client = FakeAsyncClient([FakeResponse(status_code=403, text="forbidden")])

    monkeypatch.setattr("src.skills.google_mail.actions._get_access_token", fake_access_token)
    monkeypatch.setattr("src.skills.google_mail.actions.httpx.AsyncClient", lambda timeout=30.0: fake_client)

    with pytest.raises(RuntimeError, match="Gmail batch trash request failed \\(403\\): forbidden"):
        asyncio.run(batch_delete({"message_ids": ["msg-1"]}, {}, {"owner_email": "owner@example.com"}))


def test_google_mail_archive_removes_inbox_label(monkeypatch):
    async def fake_access_token(context):
        del context
        return "token"

    fake_client = FakeAsyncClient([FakeResponse(json_data={"id": "msg-1"})])

    monkeypatch.setattr("src.skills.google_mail.actions._get_access_token", fake_access_token)
    monkeypatch.setattr("src.skills.google_mail.actions.httpx.AsyncClient", lambda timeout=20.0: fake_client)

    result = asyncio.run(archive({"message_id": "msg-1"}, {}, {"owner_email": "owner@example.com"}))

    assert result == "Archived Gmail message: [msg-1]"
    assert fake_client.post_calls[0]["url"].endswith("/messages/msg-1/modify")
    assert fake_client.post_calls[0]["json"] == {"addLabelIds": [], "removeLabelIds": ["INBOX"]}


def test_google_mail_mark_read_removes_unread_label(monkeypatch):
    async def fake_access_token(context):
        del context
        return "token"

    fake_client = FakeAsyncClient([FakeResponse(json_data={"id": "msg-1"})])

    monkeypatch.setattr("src.skills.google_mail.actions._get_access_token", fake_access_token)
    monkeypatch.setattr("src.skills.google_mail.actions.httpx.AsyncClient", lambda timeout=20.0: fake_client)

    result = asyncio.run(mark_read({"message_id": "msg-1"}, {}, {"owner_email": "owner@example.com"}))

    assert result == "Marked Gmail message as read: [msg-1]"
    assert fake_client.post_calls[0]["json"] == {"addLabelIds": [], "removeLabelIds": ["UNREAD"]}


def test_google_mail_mark_unread_adds_unread_label(monkeypatch):
    async def fake_access_token(context):
        del context
        return "token"

    fake_client = FakeAsyncClient([FakeResponse(json_data={"id": "msg-1"})])

    monkeypatch.setattr("src.skills.google_mail.actions._get_access_token", fake_access_token)
    monkeypatch.setattr("src.skills.google_mail.actions.httpx.AsyncClient", lambda timeout=20.0: fake_client)

    result = asyncio.run(mark_unread({"message_id": "msg-1"}, {}, {"owner_email": "owner@example.com"}))

    assert result == "Marked Gmail message as unread: [msg-1]"
    assert fake_client.post_calls[0]["json"] == {"addLabelIds": ["UNREAD"], "removeLabelIds": []}
