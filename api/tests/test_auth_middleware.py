"""Owner routes take owner tokens for existing users, and nothing else."""

from datetime import datetime, timedelta, timezone

import jwt
from fastapi.testclient import TestClient

from tests.mock_data import TEST_USER_EMAIL


def _token(**claims) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({"iat": now, "exp": now + timedelta(hours=1), **claims}, "test-secret", algorithm="HS256")


def _get_agents(test_client: TestClient, token: str):
    return test_client.get("/agents", headers={"Authorization": f"Bearer {token}"})


def test_an_owner_token_for_an_existing_user_is_accepted(test_client: TestClient):
    assert _get_agents(test_client, _token(aud="owner", sub=TEST_USER_EMAIL)).status_code == 200


def test_a_widget_visitor_token_is_not_an_owner_session(test_client: TestClient):
    visitor = _token(aud="widget_visitor", type="widget_visitor", sub=TEST_USER_EMAIL, agent_id="agent-1")
    assert _get_agents(test_client, visitor).status_code == 401


def test_a_token_without_an_audience_is_refused(test_client: TestClient):
    assert _get_agents(test_client, _token(sub=TEST_USER_EMAIL)).status_code == 401


def test_an_a2a_token_is_refused(test_client: TestClient):
    a2a = _token(aud="innomightlabs:a2a", sub="agent:a:api_key:k", owner_email=TEST_USER_EMAIL)
    assert _get_agents(test_client, a2a).status_code == 401


def test_a_token_for_someone_who_never_signed_up_is_refused(test_client: TestClient):
    assert _get_agents(test_client, _token(aud="owner", sub="1234567890")).status_code == 401


def test_the_token_is_not_read_from_the_query_string(test_client: TestClient):
    token = _token(aud="owner", sub=TEST_USER_EMAIL)
    assert test_client.get(f"/agents?token={token}").status_code == 401
