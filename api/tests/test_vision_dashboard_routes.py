"""Images in the dashboard chat: availability, upload, serving, and sending with a message."""

from __future__ import annotations

from typing import Any

import boto3
import pytest

from src.messages.models import Message
from src.messages.repositories import DynamoDBMessageRepository
from tests.mock_data import TEST_USER_EMAIL_2
from tests.oauth_handoff import owner_headers
from tests.vision_support import (
    create_media_bucket,
    create_memgpt_agent,
    enable_vision_for_test_user,
    png_upload,
)


@pytest.fixture
def chat(test_client, auth_headers):
    """A conversation with an image-reading agent, and the image feature on."""
    create_media_bucket()
    enable_vision_for_test_user()
    agent_id = create_memgpt_agent(test_client, auth_headers)
    conversation = test_client.post("/conversations/", json={"title": "Pics", "agent_id": agent_id}, headers=auth_headers)
    assert conversation.status_code == 201, conversation.text

    class Chat:
        pass

    chat = Chat()
    chat.agent_id, chat.conversation_id = agent_id, conversation.json()["conversation_id"]  # type: ignore[attr-defined]
    return chat


def _upload(test_client, auth_headers, chat, name: str = "shot.png"):
    return test_client.post(f"/conversations/{chat.conversation_id}/images", files=png_upload(name), headers=auth_headers)


def test_the_composer_learns_whether_images_are_available(test_client, auth_headers, chat) -> None:
    response = test_client.get(f"/agents/{chat.agent_id}/image-input", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True and body["reason"] is None
    assert body["limits"]["max_bytes"] == 5 * 1024 * 1024
    assert body["limits"]["formats"] == ["image/png", "image/jpeg", "image/webp", "image/gif"]


def test_the_composer_is_told_why_images_are_unavailable(test_client, auth_headers) -> None:
    agent_id = create_memgpt_agent(test_client, auth_headers)

    body = test_client.get(f"/agents/{agent_id}/image-input", headers=auth_headers).json()

    assert (body["available"], body["reason"]) == (False, "image_input_disabled")
    assert "turned off" in body["message"]


def test_upload_then_fetch_the_image(test_client, auth_headers, chat) -> None:
    uploaded = _upload(test_client, auth_headers, chat)

    assert uploaded.status_code == 201, uploaded.text
    body = uploaded.json()
    assert (body["filename"], body["mime_type"], body["width"], body["height"]) == ("shot.png", "image/png", 40, 30)
    assert body["url"].endswith(f"/conversations/{chat.conversation_id}/images/{body['image_id']}")

    fetched = test_client.get(f"/conversations/{chat.conversation_id}/images/{body['image_id']}", headers=auth_headers)
    assert fetched.status_code == 200
    assert fetched.headers["content-type"] == "image/png"
    assert fetched.headers["cache-control"] == "private, max-age=300"
    assert fetched.headers["x-content-type-options"] == "nosniff"


def test_someone_elses_conversation_images_are_not_found(test_client, auth_headers, chat) -> None:
    image_id = _upload(test_client, auth_headers, chat).json()["image_id"]
    stranger = owner_headers(TEST_USER_EMAIL_2)

    assert test_client.get(f"/conversations/{chat.conversation_id}/images/{image_id}", headers=stranger).status_code == 404
    assert test_client.post(
        f"/conversations/{chat.conversation_id}/images", files=png_upload(), headers=stranger
    ).status_code == 404


def test_upload_is_refused_with_a_code_while_the_feature_is_off(test_client, auth_headers) -> None:
    create_media_bucket()
    agent_id = create_memgpt_agent(test_client, auth_headers)
    conversation_id = test_client.post(
        "/conversations/", json={"title": "x", "agent_id": agent_id}, headers=auth_headers
    ).json()["conversation_id"]

    refused = test_client.post(f"/conversations/{conversation_id}/images", files=png_upload(), headers=auth_headers)

    assert refused.status_code == 403
    assert refused.json()["detail"]["code"] == "image_input_disabled"


def test_a_file_that_is_not_an_image_is_refused(test_client, auth_headers, chat) -> None:
    refused = test_client.post(
        f"/conversations/{chat.conversation_id}/images",
        files={"file": ("notes.png", b"just text", "image/png")},
        headers=auth_headers,
    )

    assert refused.status_code == 422
    assert refused.json()["detail"]["code"] == "image_unreadable"


def test_send_message_attaches_the_uploaded_images_to_the_turn(test_client, auth_headers, chat, monkeypatch) -> None:
    image_id = _upload(test_client, auth_headers, chat).json()["image_id"]
    started: dict[str, Any] = {}

    def fake_start_turn(**kwargs):
        started.update(kwargs)
        raise RuntimeError("stop here")

    monkeypatch.setattr("src.agents.router.start_turn", fake_start_turn)
    with pytest.raises(RuntimeError, match="stop here"):
        test_client.post(
            f"/agents/{chat.agent_id}/{chat.conversation_id}/send-message",
            json={"content": "what is this?", "image_ids": [image_id]},
            headers=auth_headers,
        )

    assert [image.image_id for image in started["images"]] == [image_id]
    assert started["images"][0].filename == "shot.png"


def test_send_message_with_an_unknown_image_starts_no_turn(test_client, auth_headers, chat, monkeypatch) -> None:
    monkeypatch.setattr("src.agents.router.start_turn", lambda **_: pytest.fail("a turn must not start"))

    response = test_client.post(
        f"/agents/{chat.agent_id}/{chat.conversation_id}/send-message",
        json={"content": "hi", "image_ids": ["not-an-upload"]},
        headers=auth_headers,
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "image_not_found"


def test_messages_list_the_images_without_the_agents_notes(test_client, auth_headers, chat) -> None:
    from src.messages.models import ImageAnalysis, ImageAttachment

    image = ImageAttachment(
        image_id="img-1", s3_key="k", filename="shot.png", mime_type="image/png", size_bytes=10, width=40, height=30,
        analysis=ImageAnalysis(description="private working note", provider_name="Bedrock", model_name="m"),
    )
    DynamoDBMessageRepository().save(
        Message(conversation_id=chat.conversation_id, role="user", content="look", image_attachments=[image])
    )

    response = test_client.get(f"/conversations/{chat.conversation_id}/messages", headers=auth_headers)

    attachment = response.json()["items"][0]["image_attachments"][0]
    assert attachment["image_id"] == "img-1"
    assert attachment["url"].endswith(f"/conversations/{chat.conversation_id}/images/img-1")
    assert "private working note" not in response.text
    assert "analysis" not in attachment


def test_deleting_the_conversation_deletes_its_uploads(test_client, auth_headers, chat) -> None:
    image_id = _upload(test_client, auth_headers, chat).json()["image_id"]

    from src.config import settings
    from src.vision.repository import ImageUploadRepository

    s3_key = ImageUploadRepository().find(chat.conversation_id, image_id).s3_key  # type: ignore[union-attr]
    s3 = boto3.client("s3", region_name=settings.conversation_media_region)
    assert s3.list_objects_v2(Bucket=settings.conversation_media_bucket, Prefix=s3_key)["KeyCount"] == 1

    assert test_client.delete(f"/conversations/{chat.conversation_id}", headers=auth_headers).status_code == 204

    assert ImageUploadRepository().find(chat.conversation_id, image_id) is None
    assert s3.list_objects_v2(Bucket=settings.conversation_media_bucket, Prefix=s3_key)["KeyCount"] == 0
