"""Token endpoints for the backends of apps that share this login."""
import time
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from fastapi.testclient import TestClient

from src.auth import app_tokens
from src.auth.apps import NONCE_COOKIE, create_state
from src.users import UserRepository
from src.users.models import UserStatus

EMAIL = "new.user@example.com"
BIDSIGNAL = ("bidsignal", "bidsignal-secret")


@pytest.fixture(autouse=True)
def registered_bidsignal(monkeypatch):
    monkeypatch.setattr("src.config.settings.auth_app_urls", {"bidsignal": "https://bidsignal.example.com"})
    monkeypatch.setattr("src.config.settings.auth_app_secrets", {"bidsignal": "bidsignal-secret"})
    monkeypatch.setattr("src.config.settings.auth_app_access_token_minutes", 60)


class SignsIn:
    async def exchange_code_for_tokens(self, code: str):
        return {"access_token": "access"}

    async def get_user_info(self, access_token: str):
        return {"email": EMAIL, "name": "New User", "verified_email": True}


def login_code(test_client: TestClient, monkeypatch) -> str:
    """A code obtained the real way: through the OAuth callback."""
    monkeypatch.setattr("src.auth.router._get_provider", lambda _name: SignsIn())
    monkeypatch.setattr("src.auth.router.send_welcome_email_safe", lambda _email: _done())
    login = create_state("bidsignal")
    test_client.cookies.set(NONCE_COOKIE, login.nonce)
    response = test_client.get(f"/auth/callback/google?code=abc&state={login.state}", follow_redirects=False)
    return parse_qs(urlparse(response.headers["location"]).query)["code"][0]


async def _done() -> None:
    return None


def exchange(test_client: TestClient, code: str, auth=BIDSIGNAL):
    return test_client.post("/auth/token", json={"code": code}, auth=auth)


def refresh(test_client: TestClient, refresh_token: str, auth=BIDSIGNAL, email: str = EMAIL):
    return test_client.post("/auth/refresh", json={"email": email, "refresh_token": refresh_token}, auth=auth)


def test_a_login_code_is_exchanged_for_short_lived_tokens(test_client: TestClient, monkeypatch):
    response = exchange(test_client, login_code(test_client, monkeypatch))

    body = response.json()
    claims = jwt.decode(body["access_token"], "test-secret", algorithms=["HS256"], audience="app:bidsignal")
    assert response.status_code == 200
    assert body["email"] == claims["sub"] == EMAIL
    assert body["expires_in"] == 3600
    assert claims["exp"] - time.time() < 3600 + 5
    assert body["refresh_token"]


def test_a_login_code_works_once(test_client: TestClient, monkeypatch):
    code = login_code(test_client, monkeypatch)

    assert exchange(test_client, code).status_code == 200
    assert exchange(test_client, code).status_code == 401


def test_an_expired_login_code_is_refused(test_client: TestClient, monkeypatch):
    code = login_code(test_client, monkeypatch)
    monkeypatch.setattr(time, "time", lambda: time.monotonic() + 10**10)

    assert exchange(test_client, code).status_code == 401


@pytest.mark.parametrize("auth", [None, ("bidsignal", "wrong"), ("unknown", "bidsignal-secret")])
def test_token_endpoints_require_the_app_credentials(test_client: TestClient, monkeypatch, auth):
    code = login_code(test_client, monkeypatch)

    assert exchange(test_client, code, auth=auth).status_code == 401
    assert refresh(test_client, "anything", auth=auth).status_code == 401


def test_a_code_cannot_be_redeemed_by_another_app(test_client: TestClient, monkeypatch):
    monkeypatch.setattr("src.config.settings.auth_app_secrets", {"bidsignal": "bidsignal-secret", "other": "other-secret"})
    code = login_code(test_client, monkeypatch)

    assert exchange(test_client, code, auth=("other", "other-secret")).status_code == 401


def test_a_refresh_token_is_traded_for_a_new_pair_and_works_once(test_client: TestClient, monkeypatch):
    first = exchange(test_client, login_code(test_client, monkeypatch)).json()

    second = refresh(test_client, first["refresh_token"])

    assert second.status_code == 200
    assert second.json()["refresh_token"] != first["refresh_token"]
    assert second.json()["email"] == EMAIL
    assert refresh(test_client, first["refresh_token"]).status_code == 401
    assert refresh(test_client, second.json()["refresh_token"]).status_code == 200


def test_signing_in_again_replaces_the_refresh_token(test_client: TestClient, monkeypatch):
    first = exchange(test_client, login_code(test_client, monkeypatch)).json()
    exchange(test_client, login_code(test_client, monkeypatch))

    assert refresh(test_client, first["refresh_token"]).status_code == 401


def test_an_expired_refresh_token_is_refused(test_client: TestClient, monkeypatch):
    tokens = exchange(test_client, login_code(test_client, monkeypatch)).json()
    app_tokens.repository.put_refresh_token(EMAIL, "bidsignal", app_tokens._hash(tokens["refresh_token"]), int(time.time()) - 1)

    assert refresh(test_client, tokens["refresh_token"]).status_code == 401


def test_a_revoked_refresh_token_is_refused(test_client: TestClient, monkeypatch):
    tokens = exchange(test_client, login_code(test_client, monkeypatch)).json()

    revoked = test_client.post("/auth/revoke", json={"email": EMAIL}, auth=BIDSIGNAL)

    assert revoked.status_code == 204
    assert refresh(test_client, tokens["refresh_token"]).status_code == 401


def test_a_deactivated_account_cannot_refresh(test_client: TestClient, monkeypatch):
    tokens = exchange(test_client, login_code(test_client, monkeypatch)).json()
    UserRepository().mark_inactive(EMAIL)

    assert refresh(test_client, tokens["refresh_token"]).status_code == 401
    assert UserRepository().get_by_email(EMAIL).status == UserStatus.INACTIVE.value


def test_an_app_cannot_revoke_another_apps_refresh_token(test_client: TestClient, monkeypatch):
    monkeypatch.setattr("src.config.settings.auth_app_secrets", {"bidsignal": "bidsignal-secret", "other": "other-secret"})
    tokens = exchange(test_client, login_code(test_client, monkeypatch)).json()

    revoked = test_client.post("/auth/revoke", json={"email": EMAIL}, auth=("other", "other-secret"))

    assert revoked.status_code == 204
    assert refresh(test_client, tokens["refresh_token"]).status_code == 200


@pytest.mark.parametrize("auth", [None, ("bidsignal", "wrong"), ("unknown", "bidsignal-secret")])
def test_revoke_requires_the_app_credentials(test_client: TestClient, monkeypatch, auth):
    tokens = exchange(test_client, login_code(test_client, monkeypatch)).json()

    assert test_client.post("/auth/revoke", json={"email": EMAIL}, auth=auth).status_code == 401
    assert refresh(test_client, tokens["refresh_token"]).status_code == 200


def test_revoking_without_a_refresh_token_is_harmless(test_client: TestClient):
    assert test_client.post("/auth/revoke", json={"email": EMAIL}, auth=BIDSIGNAL).status_code == 204


def test_a_refresh_token_is_refused_for_an_unknown_user(test_client: TestClient):
    assert refresh(test_client, "anything", email="nobody@example.com").status_code == 401


def test_a_deactivated_account_cannot_redeem_a_login_code(test_client: TestClient, monkeypatch):
    code = login_code(test_client, monkeypatch)
    UserRepository().mark_inactive(EMAIL)

    assert exchange(test_client, code).status_code == 401


def test_the_token_endpoints_do_not_need_a_user_jwt(test_client: TestClient, monkeypatch):
    """They are public to AuthMiddleware; the app credentials are the only gate."""
    code = login_code(test_client, monkeypatch)

    assert "Authorization" not in test_client.headers
    assert exchange(test_client, code).status_code == 200


def test_account_deletion_removes_refresh_tokens(dynamodb_table, monkeypatch):
    from lambdas.account_deletion_handler.handler import AccountDeletionHandler

    monkeypatch.setenv("DYNAMODB_TABLE", dynamodb_table.name)
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.delenv("DYNAMODB_ENDPOINT", raising=False)
    app_tokens.repository.put_refresh_token(EMAIL, "bidsignal", "hash-1", int(time.time()) + 60)
    app_tokens.repository.put_refresh_token(EMAIL, "other", "hash-2", int(time.time()) + 60)
    app_tokens.repository.put_refresh_token("someone.else@example.com", "bidsignal", "hash-3", int(time.time()) + 60)

    counts = AccountDeletionHandler().delete_user_entities(EMAIL)

    assert counts["refresh_tokens"] == 2
    assert app_tokens.repository.get_refresh_token(EMAIL, "bidsignal") is None
    assert app_tokens.repository.get_refresh_token(EMAIL, "other") is None
    assert app_tokens.repository.get_refresh_token("someone.else@example.com", "bidsignal") is not None


def test_an_app_token_reads_auth_me_and_nothing_else(test_client: TestClient, monkeypatch):
    access_token = exchange(test_client, login_code(test_client, monkeypatch)).json()["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    me = test_client.get("/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["email"] == EMAIL
    assert test_client.get("/agents", headers=headers).status_code == 401
