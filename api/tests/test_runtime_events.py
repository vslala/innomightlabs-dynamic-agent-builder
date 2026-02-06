from fastapi import status
from tests.mock_data import TEST_USER_EMAIL, AGENT_CREATE_REQUEST


def test_runtime_events_requires_authentication(test_client):
    resp = test_client.get(
        "/agents/a/conversations/c/runtime-events?actor_id=u"
    )
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED


def test_runtime_events_list_empty(test_client, auth_headers):
    # Create agent
    agent_resp = test_client.post("/agents", json=AGENT_CREATE_REQUEST, headers=auth_headers)
    assert agent_resp.status_code == 201
    agent_id = agent_resp.json()["agent_id"]

    # Create conversation
    conv_resp = test_client.post(
        "/conversations/",
        json={"title": "t", "agent_id": agent_id},
        headers=auth_headers,
    )
    assert conv_resp.status_code == 201
    conversation_id = conv_resp.json()["conversation_id"]

    # No events yet
    resp = test_client.get(
        f"/agents/{agent_id}/conversations/{conversation_id}/runtime-events",
        params={"actor_id": TEST_USER_EMAIL, "limit": 10},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["has_more"] is False


def test_runtime_events_list_requires_owner(test_client, auth_headers):
    # Create agent as owner
    agent_resp = test_client.post("/agents", json=AGENT_CREATE_REQUEST, headers=auth_headers)
    agent_id = agent_resp.json()["agent_id"]

    conv_resp = test_client.post(
        "/conversations/",
        json={"title": "t", "agent_id": agent_id},
        headers=auth_headers,
    )
    assert conv_resp.status_code == 201
    conversation_id = conv_resp.json()["conversation_id"]

    # Another user token
    import jwt
    from datetime import datetime, timedelta, timezone

    other = jwt.encode(
        {
            "sub": "other@example.com",
            "name": "Other",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            "iat": datetime.now(timezone.utc),
        },
        "test-secret",
        algorithm="HS256",
    )

    resp = test_client.get(
        f"/agents/{agent_id}/conversations/{conversation_id}/runtime-events",
        params={"actor_id": TEST_USER_EMAIL},
        headers={"Authorization": f"Bearer {other}"},
    )

    assert resp.status_code == 404
