"""Widget visitor sign-in only completes in the browser that started it, and never puts a token in a URL."""

from __future__ import annotations

import json
import re
from uuid import uuid4
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from fastapi.testclient import TestClient

import src.widget.router as widget_router
from src.widget import sessions
from src.agents.models import Agent
from src.agents.repository import AgentRepository
from tests.mock_data import TEST_USER_EMAIL

API = "https://api.example.com"
IDE_CALLBACK = "vscode://undefined_publisher.innomightlabs-code-assist/auth-callback"


@pytest.fixture(autouse=True)
def google(monkeypatch):
    monkeypatch.setattr("src.config.settings.api_base_url", API)
    user = {"id": "google-user-123", "email": "visitor@example.com", "name": "Visitor", "verified_email": True}

    async def exchange(code: str, redirect_uri: str | None = None):
        assert redirect_uri == f"{API}/widget/auth/callback"
        return {"access_token": "google-access", "refresh_token": "google-refresh"}

    async def user_info(access_token: str):
        return dict(user)

    monkeypatch.setattr(widget_router.google_oauth, "exchange_code_for_tokens", exchange)
    monkeypatch.setattr(widget_router.google_oauth, "get_user_info", user_info)
    return user


def _widget_key(test_client: TestClient, auth_headers: dict, allowed_origins: list[str] | None = None) -> tuple[str, str]:
    # Saved directly: the free tier allows one agent through the API.
    agent_id = AgentRepository().save(
        Agent(
            agent_name=f"Widget Agent {uuid4().hex[:8]}",
            agent_architecture="krishna-mini",
            agent_provider="Bedrock",
            agent_persona="Helpful",
            created_by=TEST_USER_EMAIL,
        )
    ).agent_id
    key = test_client.post(
        f"/agents/{agent_id}/api-keys",
        json={"name": "Widget", "allowed_origins": allowed_origins or []},
        headers=auth_headers,
    ).json()
    return agent_id, key["public_key"]


def _start(test_client: TestClient, public_key: str, **params):
    response = test_client.get("/widget/auth/google", params={"api_key": public_key, **params}, follow_redirects=False)
    # The cookie is Secure (the API is https here) and the test client is not, so carry it by hand.
    if sessions.NONCE_COOKIE in response.cookies:
        test_client.cookies.set(sessions.NONCE_COOKIE, response.cookies[sessions.NONCE_COOKIE])
    state = parse_qs(urlparse(response.headers.get("location", "")).query).get("state", [None])[0]
    return response, state


def _posted(page: str) -> tuple[dict | None, str | None]:
    sign_in = json.loads(re.search(r"var signIn = (.*);", page).group(1))
    return (json.loads(sign_in["message"]) if sign_in["message"] else None), sign_in["origin"]


def test_the_popup_posts_a_one_time_code_to_the_embed_origin(test_client, auth_headers):
    agent_id, public_key = _widget_key(test_client, auth_headers)
    _, state = _start(test_client, public_key)

    page = test_client.get("/widget/auth/callback", params={"code": "c", "state": state})

    message, origin = _posted(page.text)
    assert origin == API
    assert "google-refresh" not in page.text
    session = test_client.post("/widget/auth/token", json={"code": message["code"]}, headers={"X-API-Key": public_key})
    assert session.status_code == 200
    body = session.json()
    claims = jwt.decode(body["access_token"], "test-secret", algorithms=["HS256"], audience="widget_visitor")
    assert claims["agent_id"] == agent_id
    assert body["refresh_token"] != "google-refresh"
    again = test_client.post("/widget/auth/token", json={"code": message["code"]}, headers={"X-API-Key": public_key})
    assert again.status_code == 401


def test_a_callback_without_the_browsers_nonce_signs_nobody_in(test_client, auth_headers):
    _, public_key = _widget_key(test_client, auth_headers)
    _, state = _start(test_client, public_key)
    test_client.cookies.clear()

    page = test_client.get("/widget/auth/callback", params={"code": "c", "state": state})

    assert _posted(page.text)[0] is None
    assert "another browser" in page.text


def test_any_other_redirect_target_is_refused(test_client, auth_headers):
    _, public_key = _widget_key(test_client, auth_headers)

    for redirect_uri in ("https://attacker.example/steal", f"{API}/widget/auth/callback-page", "vscode://evil/auth-callback"):
        response, _ = _start(test_client, public_key, redirect_uri=redirect_uri)
        assert response.status_code == 400, redirect_uri


def test_the_ide_gets_only_a_code_at_its_own_uri_handler(test_client, auth_headers):
    _, public_key = _widget_key(test_client, auth_headers)
    _, state = _start(test_client, public_key, redirect_uri=IDE_CALLBACK)

    response = test_client.get("/widget/auth/callback", params={"code": "c", "state": state}, follow_redirects=False)

    location = urlparse(response.headers["location"])
    assert f"{location.scheme}://{location.netloc}{location.path}" == IDE_CALLBACK
    assert parse_qs(location.query).keys() == {"code"}


def test_a_host_page_opener_must_be_an_allowed_origin(test_client, auth_headers):
    _, open_key = _widget_key(test_client, auth_headers)
    _, locked_key = _widget_key(test_client, auth_headers, ["https://shop.example"])

    assert _start(test_client, open_key, opener_origin="https://attacker.example")[0].status_code == 400
    assert _start(test_client, locked_key, opener_origin="https://attacker.example")[0].status_code == 400
    response, state = _start(test_client, locked_key, opener_origin="https://shop.example")
    assert response.status_code == 307

    page = test_client.get("/widget/auth/callback", params={"code": "c", "state": state})
    assert _posted(page.text)[1] == "https://shop.example"


def test_an_unverified_google_email_signs_nobody_in(test_client, auth_headers, google):
    google["verified_email"] = False
    _, public_key = _widget_key(test_client, auth_headers)
    _, state = _start(test_client, public_key)

    page = test_client.get("/widget/auth/callback", params={"code": "c", "state": state})

    assert _posted(page.text)[0] is None


def test_refresh_tokens_rotate_and_belong_to_one_agent(test_client, auth_headers):
    from src.widget.models import WidgetVisitor

    agent_id, public_key = _widget_key(test_client, auth_headers)
    _, other_key = _widget_key(test_client, auth_headers)
    code = sessions.create_login_code(agent_id, WidgetVisitor(visitor_id="v", email="visitor@example.com"))
    first = test_client.post("/widget/auth/token", json={"code": code}, headers={"X-API-Key": public_key}).json()

    elsewhere = test_client.post(
        "/widget/auth/refresh", json={"refresh_token": first["refresh_token"]}, headers={"X-API-Key": other_key}
    )
    assert elsewhere.status_code == 401

    code = sessions.create_login_code(agent_id, WidgetVisitor(visitor_id="v", email="visitor@example.com"))
    second = test_client.post("/widget/auth/token", json={"code": code}, headers={"X-API-Key": public_key}).json()
    refreshed = test_client.post(
        "/widget/auth/refresh", json={"refresh_token": second["refresh_token"]}, headers={"X-API-Key": public_key}
    )
    assert refreshed.status_code == 200
    reused = test_client.post(
        "/widget/auth/refresh", json={"refresh_token": second["refresh_token"]}, headers={"X-API-Key": public_key}
    )
    assert reused.status_code == 401

    latest = refreshed.json()["refresh_token"]
    test_client.post("/widget/auth/revoke", json={"refresh_token": latest}, headers={"X-API-Key": public_key})
    revoked = test_client.post("/widget/auth/refresh", json={"refresh_token": latest}, headers={"X-API-Key": public_key})
    assert revoked.status_code == 401
