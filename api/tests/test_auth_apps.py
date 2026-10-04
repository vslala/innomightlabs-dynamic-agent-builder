"""Login for other apps that share this identity provider (AUTH_APP_URLS)."""
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from src.auth.apps import DEFAULT_APP, NONCE_COOKIE, app_from_state, create_state

BIDSIGNAL_URL = "https://bidsignal.example.com"


@pytest.fixture(autouse=True)
def registered_apps(monkeypatch):
    monkeypatch.setattr("src.config.settings.auth_app_urls", {"bidsignal": BIDSIGNAL_URL})
    monkeypatch.setattr("src.config.settings.frontend_url", "https://app.example.com")


class FakeProvider:
    def get_authorization_url(self, state: str | None = None):
        return f"https://provider.example.com/authorize?state={state}", state

    async def exchange_code_for_tokens(self, code: str):
        return {"access_token": "access"}

    async def get_user_info(self, access_token: str):
        return {"email": "new.user@example.com", "name": "New User", "verified_email": True}


@pytest.fixture
def signed_in_as_new_user(monkeypatch, dynamodb_table):
    welcome_emails = []

    async def record_welcome_email(email: str):
        welcome_emails.append(email)

    monkeypatch.setattr("src.auth.router._get_provider", lambda _name: FakeProvider())
    monkeypatch.setattr("src.auth.router.send_welcome_email_safe", record_welcome_email)
    return welcome_emails


def test_state_round_trips_the_registered_app():
    login = create_state("bidsignal")
    assert app_from_state(login.state, login.nonce) == "bidsignal"


@pytest.mark.parametrize("state", [None, "", "not-a-jwt", "a.b.c"])
def test_unreadable_state_is_refused(state):
    assert app_from_state(state, "nonce") is None


def test_state_from_another_browser_is_refused():
    login = create_state("bidsignal")
    assert app_from_state(login.state, None) is None
    assert app_from_state(login.state, create_state("bidsignal").nonce) is None


def test_state_for_an_app_no_longer_registered_is_refused(monkeypatch):
    login = create_state("bidsignal")
    monkeypatch.setattr("src.config.settings.auth_app_urls", {})

    assert app_from_state(login.state, login.nonce) is None


def _callback(test_client: TestClient, app: str, query: str):
    login = create_state(app)
    test_client.cookies.set(NONCE_COOKIE, login.nonce)
    return test_client.get(f"/auth/callback/google?{query}&state={login.state}", follow_redirects=False)


@pytest.fixture
def fake_provider(monkeypatch):
    monkeypatch.setattr("src.auth.router._get_provider", lambda _name: FakeProvider())


def test_login_carries_the_app_through_the_provider_round_trip(test_client: TestClient, fake_provider):
    response = test_client.get("/auth/google?app=bidsignal", follow_redirects=False)

    state = parse_qs(urlparse(response.headers["location"]).query)["state"][0]
    assert app_from_state(state, response.cookies[NONCE_COOKIE]) == "bidsignal"


def test_login_rejects_an_unregistered_app(test_client: TestClient, fake_provider):
    response = test_client.get("/auth/google?app=unknown", follow_redirects=False)

    assert response.status_code == 400


def test_callback_redirects_to_the_app_the_login_started_from(
    test_client: TestClient, signed_in_as_new_user: list[str]
):
    response = _callback(test_client, "bidsignal", "code=abc")

    location = urlparse(response.headers["location"])
    assert f"{location.scheme}://{location.netloc}{location.path}" == f"{BIDSIGNAL_URL}/login-success"
    assert parse_qs(location.query).keys() == {"code"}
    assert signed_in_as_new_user == []


def test_default_app_login_lands_with_a_one_time_code_and_welcomes_the_user(
    test_client: TestClient, signed_in_as_new_user: list[str]
):
    response = _callback(test_client, DEFAULT_APP, "code=abc")

    location = urlparse(response.headers["location"])
    assert f"{location.scheme}://{location.netloc}{location.path}" == "https://app.example.com/login-success"
    code = parse_qs(location.query)["code"][0]
    assert signed_in_as_new_user == ["new.user@example.com"]

    session = test_client.post("/auth/session", json={"code": code})
    assert session.status_code == 200
    me = test_client.get("/auth/me", headers={"Authorization": f"Bearer {session.json()['token']}"})
    assert me.json()["email"] == "new.user@example.com"
    assert test_client.post("/auth/session", json={"code": code}).status_code == 401


def test_a_callback_without_the_browsers_nonce_is_refused(
    test_client: TestClient, signed_in_as_new_user: list[str]
):
    state = create_state(DEFAULT_APP).state

    response = test_client.get(f"/auth/callback/google?code=abc&state={state}", follow_redirects=False)

    assert response.headers["location"] == "https://app.example.com/login?error=auth_failed"
    assert signed_in_as_new_user == []


def test_an_unverified_email_is_refused(test_client: TestClient, signed_in_as_new_user: list[str], monkeypatch):
    async def unverified(self, access_token: str):
        return {"email": "victim@example.com", "name": "Mallory", "email_verified": "false"}

    monkeypatch.setattr(FakeProvider, "get_user_info", unverified)

    response = _callback(test_client, DEFAULT_APP, "code=abc")

    assert response.headers["location"] == "https://app.example.com/login?error=email_not_verified"


def test_provider_error_returns_to_the_app_the_login_started_from(test_client: TestClient):
    response = _callback(test_client, "bidsignal", "error=access_denied")

    assert response.headers["location"] == f"{BIDSIGNAL_URL}/login?error=access_denied"
