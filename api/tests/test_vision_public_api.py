"""Images over the public /v1 API: upload with a secret key, send by id, read them back."""

from __future__ import annotations

from typing import Any

import pytest

from src.config import settings
from src.llm.events import SSEEvent, SSEEventType
from src.messages.models import Message
from src.messages.repositories import DynamoDBMessageRepository
from tests.vision_support import create_media_bucket, create_memgpt_agent, enable_vision_for_test_user, png_upload


class RecordingArchitecture:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def handle_message(self, **kwargs):
        self.calls.append(kwargs)
        DynamoDBMessageRepository().save(
            Message(
                conversation_id=kwargs["conversation"].conversation_id, role="user", content=kwargs["user_message"],
                image_attachments=kwargs["images"],
            )
        )
        yield SSEEvent(event_type=SSEEventType.USER_MESSAGE_SAVED, content="saved", message_id="user-1")
        yield SSEEvent(event_type=SSEEventType.AGENT_RESPONSE_TO_USER, content="I see it.")
        yield SSEEvent(event_type=SSEEventType.ASSISTANT_MESSAGE_SAVED, content="saved", message_id="assistant-1")
        yield SSEEvent(event_type=SSEEventType.STREAM_COMPLETE, content="done")


@pytest.fixture
def architecture(monkeypatch) -> RecordingArchitecture:
    fake = RecordingArchitecture()
    monkeypatch.setattr("src.agents.turns.run.get_agent_architecture", lambda *_a, **_kw: fake)
    return fake


@pytest.fixture
def api(test_client, auth_headers):
    create_media_bucket()
    enable_vision_for_test_user()
    agent_id = create_memgpt_agent(test_client, auth_headers)
    key = test_client.post(f"/agents/{agent_id}/secret-keys", json={"name": "Server"}, headers=auth_headers).json()

    class Api:
        base = f"/v1/agents/{agent_id}"
        headers = {"Authorization": f"Bearer {key['secret']}"}

        def conversation(self, **body) -> str:
            created = test_client.post(f"{self.base}/conversations", json=body, headers=self.headers)
            assert created.status_code == 201
            return str(created.json()["conversation_id"])

    return Api()


def test_the_agent_says_whether_it_reads_images(test_client, api) -> None:
    body = test_client.get(api.base, headers=api.headers).json()

    assert body["image_input"]["available"] is True
    assert body["image_input"]["limits"]["max_bytes"] == settings.vision_max_image_bytes


def test_upload_send_and_read_back(test_client, api, architecture) -> None:
    conversation_id = api.conversation()
    uploaded = test_client.post(
        f"{api.base}/conversations/{conversation_id}/images", files=png_upload(), headers=api.headers
    )
    assert uploaded.status_code == 201, uploaded.text
    image = uploaded.json()
    assert image["url"].endswith(f"{api.base}/conversations/{conversation_id}/images/{image['image_id']}")

    sent = test_client.post(
        f"{api.base}/conversations/{conversation_id}/messages",
        json={"content": "What is this?", "image_ids": [image["image_id"]], "stream": False},
        headers=api.headers,
    )

    assert sent.status_code == 200, sent.text
    assert [i.image_id for i in architecture.calls[0]["images"]] == [image["image_id"]]
    fetched = test_client.get(f"{api.base}/conversations/{conversation_id}/images/{image['image_id']}", headers=api.headers)
    assert fetched.status_code == 200 and fetched.headers["content-type"] == "image/png"
    messages = test_client.get(f"{api.base}/conversations/{conversation_id}/messages", headers=api.headers).json()
    assert messages["items"][0]["image_attachments"][0]["image_id"] == image["image_id"]


def test_an_image_can_be_sent_without_any_text(test_client, api, architecture) -> None:
    conversation_id = api.conversation()
    image_id = test_client.post(
        f"{api.base}/conversations/{conversation_id}/images", files=png_upload(), headers=api.headers
    ).json()["image_id"]

    sent = test_client.post(
        f"{api.base}/conversations/{conversation_id}/messages",
        json={"image_ids": [image_id], "stream": False}, headers=api.headers,
    )

    assert sent.status_code == 200, sent.text


def test_a_message_needs_content_or_an_image(test_client, api) -> None:
    conversation_id = api.conversation()

    empty = test_client.post(
        f"{api.base}/conversations/{conversation_id}/messages", json={"content": ""}, headers=api.headers
    )

    assert empty.status_code == 422


def test_an_upload_needs_a_secret_key(test_client, api) -> None:
    conversation_id = api.conversation()

    assert test_client.post(f"{api.base}/conversations/{conversation_id}/images", files=png_upload()).status_code == 401


def test_images_do_not_cross_end_users(test_client, api) -> None:
    alices = api.conversation(end_user_id="alice")
    image_id = test_client.post(
        f"{api.base}/conversations/{alices}/images?end_user_id=alice", files=png_upload(), headers=api.headers
    ).json()["image_id"]

    other = test_client.get(f"{api.base}/conversations/{alices}/images/{image_id}?end_user_id=bob", headers=api.headers)

    assert other.status_code == 404


def test_the_key_has_a_daily_upload_cap(test_client, api, monkeypatch) -> None:
    monkeypatch.setattr(settings, "api_image_uploads_per_key_day", 1)
    conversation_id = api.conversation()
    url = f"{api.base}/conversations/{conversation_id}/images"

    first = test_client.post(url, files=png_upload(), headers=api.headers)
    second = test_client.post(url, files=png_upload(), headers=api.headers)

    assert (first.status_code, second.status_code) == (201, 429)
    assert second.json()["detail"]["code"] == "image_upload_limited"


def test_uploads_are_refused_while_the_feature_is_off(test_client, api) -> None:
    from src.vision.models import VisionSettings
    from src.vision.repository import VisionSettingsRepository
    from tests.mock_data import account_for

    VisionSettingsRepository().save(VisionSettings(account_id=account_for(), enabled=False))
    conversation_id = api.conversation()

    refused = test_client.post(f"{api.base}/conversations/{conversation_id}/images", files=png_upload(), headers=api.headers)

    assert refused.status_code == 403
    assert refused.json()["detail"]["code"] == "image_input_disabled"
