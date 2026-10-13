"""Images in the embedded widget: visitors and guests upload, send and see them; limits and ownership hold."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
import pytest

from src.config import settings
from src.messages.models import Message
from src.messages.repositories import DynamoDBMessageRepository
from src.widget import router as widget_router
from tests.vision_support import create_media_bucket, create_memgpt_agent, enable_vision_for_test_user, png_upload


def visitor_token(visitor_id: str, agent_id: str, kind: str = "google") -> str:
    return jwt.encode(
        {
            "aud": "widget_visitor", "sub": visitor_id, "email": f"{visitor_id}@example.com", "name": "Visitor",
            "picture": None, "agent_id": agent_id, "type": "widget_visitor", "kind": kind,
            "exp": datetime.now(timezone.utc) + timedelta(hours=4), "iat": datetime.now(timezone.utc),
        },
        "test-secret",
        algorithm="HS256",
    )


@pytest.fixture
def widget(test_client, auth_headers):
    create_media_bucket()
    enable_vision_for_test_user()
    agent_id = create_memgpt_agent(test_client, auth_headers)
    key = test_client.post(f"/agents/{agent_id}/api-keys", json={"name": "k", "allowed_origins": []}, headers=auth_headers)
    public_key = key.json()["public_key"]

    class Widget:
        def headers(self, visitor_id: str = "visitor-1") -> dict[str, str]:
            return {"X-API-Key": public_key, "Authorization": f"Bearer {visitor_token(visitor_id, agent_id)}"}

        def conversation(self, visitor_id: str = "visitor-1") -> str:
            created = test_client.post("/widget/conversations", json={}, headers=self.headers(visitor_id))
            assert created.status_code == 201, created.text
            return str(created.json()["conversation_id"])

    result = Widget()
    result.agent_id, result.public_key = agent_id, public_key  # type: ignore[attr-defined]
    return result


def test_a_visitor_uploads_and_sees_their_image(test_client, widget) -> None:
    conversation_id = widget.conversation()

    uploaded = test_client.post(
        f"/widget/conversations/{conversation_id}/images", files=png_upload(), headers=widget.headers()
    )

    assert uploaded.status_code == 201, uploaded.text
    image = uploaded.json()
    assert image["url"].endswith(f"/widget/conversations/{conversation_id}/images/{image['image_id']}")
    fetched = test_client.get(f"/widget/conversations/{conversation_id}/images/{image['image_id']}", headers=widget.headers())
    assert fetched.status_code == 200 and fetched.headers["content-type"] == "image/png"


def test_another_visitors_conversation_is_off_limits(test_client, widget) -> None:
    conversation_id = widget.conversation("visitor-1")
    image_id = test_client.post(
        f"/widget/conversations/{conversation_id}/images", files=png_upload(), headers=widget.headers("visitor-1")
    ).json()["image_id"]
    other = widget.headers("visitor-2")

    assert test_client.post(f"/widget/conversations/{conversation_id}/images", files=png_upload(), headers=other).status_code == 403
    assert test_client.get(f"/widget/conversations/{conversation_id}/images/{image_id}", headers=other).status_code == 403


def test_uploads_need_a_visitor_token(test_client, widget) -> None:
    conversation_id = widget.conversation()

    assert test_client.post(
        f"/widget/conversations/{conversation_id}/images", files=png_upload(), headers={"X-API-Key": widget.public_key}
    ).status_code == 401


def test_the_feature_flag_is_enforced_by_the_server(test_client, widget, auth_headers) -> None:
    from src.vision.models import VisionSettings
    from src.vision.repository import VisionSettingsRepository
    from tests.mock_data import account_for

    VisionSettingsRepository().save(VisionSettings(account_id=account_for(), enabled=False))
    conversation_id = widget.conversation()

    refused = test_client.post(f"/widget/conversations/{conversation_id}/images", files=png_upload(), headers=widget.headers())

    assert refused.status_code == 403
    assert refused.json()["detail"]["code"] == "image_input_disabled"


def test_a_visitor_is_limited_in_how_many_images_they_upload(test_client, widget, monkeypatch) -> None:
    monkeypatch.setattr(settings, "widget_image_uploads_per_visitor_hour", 1)
    conversation_id = widget.conversation()
    upload = lambda: test_client.post(  # noqa: E731
        f"/widget/conversations/{conversation_id}/images", files=png_upload(), headers=widget.headers()
    )

    assert upload().status_code == 201
    limited = upload()

    assert limited.status_code == 429
    assert limited.json()["detail"]["code"] == "image_upload_limited"
    assert "retry-after" in limited.headers


def test_a_refused_upload_does_not_use_up_the_visitors_allowance(test_client, widget, monkeypatch) -> None:
    monkeypatch.setattr(settings, "widget_image_uploads_per_visitor_hour", 1)
    conversation_id = widget.conversation()
    url = f"/widget/conversations/{conversation_id}/images"

    refused = test_client.post(url, files={"file": ("x.png", b"not an image", "image/png")}, headers=widget.headers())
    accepted = test_client.post(url, files=png_upload(), headers=widget.headers())

    assert refused.status_code == 422
    assert accepted.status_code == 201


def test_the_key_has_a_daily_cap_across_visitors(test_client, widget, monkeypatch) -> None:
    monkeypatch.setattr(settings, "widget_image_uploads_per_key_day", 1)
    first, second = widget.conversation("visitor-1"), widget.conversation("visitor-2")

    one = test_client.post(f"/widget/conversations/{first}/images", files=png_upload(), headers=widget.headers("visitor-1"))
    two = test_client.post(f"/widget/conversations/{second}/images", files=png_upload(), headers=widget.headers("visitor-2"))

    assert (one.status_code, two.status_code) == (201, 429)


def test_sending_an_image_passes_it_to_the_agent_and_the_history_shows_it(test_client, widget, monkeypatch) -> None:
    conversation_id = widget.conversation()
    image_id = test_client.post(
        f"/widget/conversations/{conversation_id}/images", files=png_upload(), headers=widget.headers()
    ).json()["image_id"]
    captured: dict[str, Any] = {}

    class FakeArchitecture:
        async def handle_message(self, **kwargs):
            captured.update(kwargs)
            DynamoDBMessageRepository().save(
                Message(conversation_id=conversation_id, role="user", content=kwargs["user_message"],
                        image_attachments=kwargs["images"])
            )
            if False:  # pragma: no cover
                yield None

    monkeypatch.setattr(widget_router, "get_agent_architecture", lambda _name: FakeArchitecture())

    with test_client.stream(
        "POST", f"/widget/conversations/{conversation_id}/messages",
        json={"content": "", "image_ids": [image_id]}, headers=widget.headers(),
    ) as response:
        assert response.status_code == 200
        list(response.iter_lines())

    assert [image.image_id for image in captured["images"]] == [image_id]
    history = test_client.get(f"/widget/conversations/{conversation_id}/messages", headers=widget.headers()).json()
    assert history[0]["image_attachments"][0]["image_id"] == image_id
    assert history[0]["image_attachments"][0]["url"].endswith(f"/widget/conversations/{conversation_id}/images/{image_id}")


def test_a_message_needs_text_or_an_image(test_client, widget) -> None:
    conversation_id = widget.conversation()

    empty = test_client.post(
        f"/widget/conversations/{conversation_id}/messages", json={"content": "  "}, headers=widget.headers()
    )

    assert empty.status_code == 422


def test_an_image_from_another_conversation_cannot_be_sent(test_client, widget) -> None:
    mine, theirs = widget.conversation("visitor-1"), widget.conversation("visitor-2")
    image_id = test_client.post(
        f"/widget/conversations/{theirs}/images", files=png_upload(), headers=widget.headers("visitor-2")
    ).json()["image_id"]

    response = test_client.post(
        f"/widget/conversations/{mine}/messages", json={"content": "hi", "image_ids": [image_id]},
        headers=widget.headers("visitor-1"),
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "image_not_found"


def test_the_widget_shell_tells_the_app_whether_images_are_available(test_client, widget) -> None:
    import json
    import re

    shell = test_client.get(f"/embed/{widget.public_key}").text
    bootstrap = json.loads(re.search(r'id="innomight-bootstrap">(.*?)</script>', shell).group(1))  # type: ignore[union-attr]

    assert bootstrap["image_input"]["available"] is True
    assert bootstrap["image_input"]["limits"]["max_images_per_message"] == 4


class TestGuests:
    """Support flows run as guests: they get the same upload and send path, behind the same limits."""

    @pytest.fixture
    def guest(self, test_client, widget, auth_headers, monkeypatch):
        from src.apikeys.repository import ApiKeyRepository

        monkeypatch.setattr(widget_router, "check_guest_email", lambda raw: raw.strip().lower())
        key = ApiKeyRepository().find_by_public_key(widget.public_key)
        test_client.patch(f"/agents/{widget.agent_id}/api-keys/{key.key_id}", json={"allow_guests": True}, headers=auth_headers)
        started = test_client.post("/widget/auth/guest", json={"email": "guest@gmail.com"}, headers={"X-API-Key": widget.public_key})
        assert started.status_code == 200, started.text
        return {"X-API-Key": widget.public_key, "Authorization": "Bearer " + started.json()["access_token"]}

    def test_a_guest_uploads_an_image(self, test_client, guest) -> None:
        conversation_id = test_client.post("/widget/conversations", json={}, headers=guest).json()["conversation_id"]

        uploaded = test_client.post(f"/widget/conversations/{conversation_id}/images", files=png_upload(), headers=guest)

        assert uploaded.status_code == 201, uploaded.text

    def test_an_ended_guest_session_can_no_longer_upload(self, test_client, guest) -> None:
        conversation_id = test_client.post("/widget/conversations", json={}, headers=guest).json()["conversation_id"]
        test_client.post("/widget/auth/guest/end", headers=guest)

        denied = test_client.post(f"/widget/conversations/{conversation_id}/images", files=png_upload(), headers=guest)

        assert denied.status_code == 401
        assert denied.json()["detail"] == "guest_session_ended"
