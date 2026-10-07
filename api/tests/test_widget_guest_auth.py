from datetime import datetime, timezone

import jwt
import pytest

from src.config import settings
from src.widget import router
from src.widget.guests import GuestSessionRepository
from tests.test_widget_sign_in import _widget_key


@pytest.fixture
def guest_key(test_client, auth_headers, monkeypatch):
    monkeypatch.setattr(router, "check_guest_email", lambda raw: raw.strip().lower())
    agent_id, public_key = _widget_key(test_client, auth_headers)

    # Enable using the persisted key so the real widget middleware is exercised.
    from src.apikeys.repository import ApiKeyRepository
    repo = ApiKeyRepository()
    key = repo.find_by_public_key(public_key)
    response = test_client.patch(f"/agents/{agent_id}/api-keys/{key.key_id}",
                                json={"allow_guests": True}, headers=auth_headers)
    assert response.status_code == 200
    return agent_id, public_key


def start(test_client, public_key, email="guest@gmail.com"):
    return test_client.post("/widget/auth/guest", json={"email": email}, headers={"X-API-Key": public_key})


def test_disabled_by_default(test_client, auth_headers):
    _, key = _widget_key(test_client, auth_headers)
    response = start(test_client, key)
    assert response.status_code == 404
    assert response.json()["detail"] == "guests_disabled"


def test_start_conversation_and_end(test_client, guest_key):
    aid, key = guest_key
    response = start(test_client, key)
    assert response.status_code == 200
    body = response.json()
    assert body["visitor"]["kind"] == "guest"
    assert body["expires_in"] == 3600
    claims = jwt.decode(body["access_token"], settings.jwt_secret, algorithms=[settings.jwt_algorithm], audience="widget_visitor")
    assert claims["kind"] == "guest"
    headers = {"X-API-Key": key, "Authorization": "Bearer " + body["access_token"]}
    conversation = test_client.post("/widget/conversations", json={}, headers=headers)
    assert conversation.status_code == 201
    assert conversation.json()["visitor_kind"] == "guest"
    assert test_client.post("/widget/auth/guest/end", headers=headers).status_code == 204
    denied = test_client.get("/widget/conversations", headers=headers)
    assert denied.status_code == 401
    assert denied.json()["detail"] == "guest_session_ended"
    assert GuestSessionRepository().get(body["visitor"]["visitor_id"]).session_ends_at <= datetime.now(timezone.utc)


def test_start_ip_limit(test_client, guest_key, monkeypatch):
    monkeypatch.setattr(settings, "widget_guest_start_limit", 1)
    _, key = guest_key
    assert start(test_client, key).status_code == 200
    response = start(test_client, key, "other@gmail.com")
    assert response.status_code == 429
    assert response.json()["detail"] == "guest_start_limited"


def test_start_email_limit(test_client, guest_key, monkeypatch):
    monkeypatch.setattr(settings, "widget_guest_email_daily_limit", 1)
    _, key = guest_key
    assert start(test_client, key).status_code == 200
    assert start(test_client, key).status_code == 429


def test_email_rejection_is_422(test_client, guest_key, monkeypatch):
    from src.widget.guest_email import GuestEmailRejected
    def reject(raw):
        raise GuestEmailRejected("No mail here")
    monkeypatch.setattr(router, "check_guest_email", reject)
    response = start(test_client, guest_key[1])
    assert response.status_code == 422
    assert response.json()["detail"] == "No mail here"


def _guest_headers(test_client, key):
    body = start(test_client, key).json()
    return body, {"X-API-Key": key, "Authorization": "Bearer " + body["access_token"]}


def test_a_message_while_a_reply_is_streaming_is_busy_not_ended(test_client, guest_key):
    """A held turn lease used to be reported as guest_session_ended, which told the guest their chat was over."""
    _, key = guest_key
    body, headers = _guest_headers(test_client, key)
    conversation = test_client.post("/widget/conversations", json={}, headers=headers).json()
    repo = GuestSessionRepository()
    repo.table.update_item(
        Key={"pk": f"WidgetGuest#{body['visitor']['visitor_id']}", "sk": "WidgetGuest#Metadata"},
        UpdateExpression="SET turn_id = :t, turn_expires_at = :e",
        ExpressionAttributeValues={":t": "other-turn", ":e": int(datetime.now(timezone.utc).timestamp()) + 300},
    )

    response = test_client.post(f"/widget/conversations/{conversation['conversation_id']}/messages",
                                json={"content": "Hello again"}, headers=headers)

    assert response.status_code == 409
    assert response.json()["detail"] == "guest_turn_in_progress"
    assert repo.get(body["visitor"]["visitor_id"]).status == "active"


def test_creating_a_conversation_records_it_on_the_guest_session(test_client, guest_key):
    _, key = guest_key
    body, headers = _guest_headers(test_client, key)
    ids = {test_client.post("/widget/conversations", json={}, headers=headers).json()["conversation_id"] for _ in range(2)}
    assert GuestSessionRepository().get(body["visitor"]["visitor_id"]).conversation_ids == ids


def test_embed_bootstrap_carries_the_guest_flag_and_session_length(test_client, auth_headers, guest_key):
    import json
    import re

    def bootstrap(key):
        html = test_client.get(f"/embed/{key}").text
        return json.loads(re.search(r'id="innomight-bootstrap">(.*?)</script>', html, re.S).group(1))

    _, plain_key = _widget_key(test_client, auth_headers)
    assert bootstrap(plain_key)["allow_guests"] is False
    assert bootstrap(plain_key)["guest_session_timeout_minutes"] is None
    guest = bootstrap(guest_key[1])
    assert guest["allow_guests"] is True
    assert guest["guest_session_timeout_minutes"] == 60  # the test agent's default session timeout


def test_api_keys_default_to_no_guests_including_rows_written_before_the_flag(test_client, auth_headers):
    from src.apikeys.models import AgentApiKey

    agent_id, public_key = _widget_key(test_client, auth_headers)
    listed = test_client.get(f"/agents/{agent_id}/api-keys", headers=auth_headers).json()
    assert [key["allow_guests"] for key in listed] == [False]
    item = AgentApiKey(agent_id="a", name="Old", created_by="owner@example.com").to_dynamo_item()
    del item["allow_guests"]
    assert AgentApiKey.from_dynamo_item(item).allow_guests is False


def test_connectors_cant_be_shared_with_guests():
    from pydantic import ValidationError
    from src.connectors.mcp.models import MCPSharingUpdateRequest

    with pytest.raises(ValidationError, match="guest"):
        MCPSharingUpdateRequest(available_to=["visitor", "guest"], allowed_tools=["search"])


def test_guest_session_length_falls_back_when_the_agent_has_no_timeout():
    from src.widget.guests import guest_session_minutes

    assert guest_session_minutes(45) == 45
    assert guest_session_minutes(0) == settings.widget_guest_default_session_minutes
