"""Login for other apps that share this identity provider (AUTH_APP_URLS)."""
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from src.auth.apps import DEFAULT_APP, app_from_state, create_state

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
        return {"email": "new.user@example.com", "name": "New User"}


@pytest.fixture
def signed_in_as_new_user(monkeypatch, dynamodb_table):
    welcome_emails = []

    async def record_welcome_email(email: str):
        welcome_emails.append(email)

    monkeypatch.setattr("src.auth.router._get_provider", lambda _name: FakeProvider())
    monkeypatch.setattr("src.auth.router.send_welcome_email_safe", record_welcome_email)
    return welcome_emails


def test_state_round_trips_the_registered_app():
    assert app_from_state(create_state("bidsignal")) == "bidsignal"


@pytest.mark.parametrize("state", [None, "", "not-a-jwt", "a.b.c"])
def test_unreadable_state_falls_back_to_the_default_app(state):
    assert app_from_state(state) == DEFAULT_APP


def test_state_for_an_app_no_longer_registered_falls_back_to_the_default_app(monkeypatch):
    state = create_state("bidsignal")
    monkeypatch.setattr("src.config.settings.auth_app_urls", {})

    assert app_from_state(state) == DEFAULT_APP


@pytest.fixture
def fake_provider(monkeypatch):
    monkeypatch.setattr("src.auth.router._get_provider", lambda _name: FakeProvider())


def test_login_carries_the_app_through_the_provider_round_trip(test_client: TestClient, fake_provider):
    response = test_client.get("/auth/google?app=bidsignal", follow_redirects=False)

    state = parse_qs(urlparse(response.headers["location"]).query)["state"][0]
    assert app_from_state(state) == "bidsignal"


def test_login_rejects_an_unregistered_app(test_client: TestClient, fake_provider):
    response = test_client.get("/auth/google?app=unknown", follow_redirects=False)

    assert response.status_code == 400


def test_callback_redirects_to_the_app_the_login_started_from(
    test_client: TestClient, signed_in_as_new_user: list[str]
):
    state = create_state("bidsignal")

    response = test_client.get(f"/auth/callback/google?code=abc&state={state}", follow_redirects=False)

    location = urlparse(response.headers["location"])
    assert f"{location.scheme}://{location.netloc}{location.path}" == f"{BIDSIGNAL_URL}/login-success"
    assert parse_qs(location.query)["token"]
    assert signed_in_as_new_user == []


def test_callback_without_an_app_redirects_to_the_default_frontend_and_welcomes_the_user(
    test_client: TestClient, signed_in_as_new_user: list[str]
):
    response = test_client.get("/auth/callback/google?code=abc", follow_redirects=False)

    assert response.headers["location"].startswith("https://app.example.com/login-success?token=")
    assert signed_in_as_new_user == ["new.user@example.com"]


def test_provider_error_returns_to_the_app_the_login_started_from(test_client: TestClient):
    state = create_state("bidsignal")

    response = test_client.get(f"/auth/callback/google?error=access_denied&state={state}", follow_redirects=False)

    assert response.headers["location"] == f"{BIDSIGNAL_URL}/login?error=access_denied"
