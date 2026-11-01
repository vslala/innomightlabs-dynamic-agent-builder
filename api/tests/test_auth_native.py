"""Sign-in for the store apps: PKCE login codes, owner tokens and one refresh token per device."""
import time
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from fastapi.testclient import TestClient

from src.accounts import personal_account_id
from src.accounts.repository import AccountRepository
from src.auth import app_tokens
from src.auth.apps import DEFAULT_APP, NATIVE_APP, NONCE_COOKIE, create_state
from src.auth.oauth_handoff import safe_return_to
from src.config import settings
from src.config.settings import ConfigValidationError
from src.identity import IdentityRepository

SCHEME = "com.innomightlabs.app"
EMAIL = "phone.user@example.com"
# RFC 7636, appendix B
VERIFIER = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
CHALLENGE = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
PHONE = "8f14e45f-ceea-467e-a2f3-1c0a4b6d9e01"
TABLET = "c9f0f895-fb98-4b91-9b8e-5c7a1d2e3f40"


@pytest.fixture(autouse=True)
def native_app_on(monkeypatch):
    monkeypatch.setattr("src.config.settings.native_app_scheme", SCHEME)
    monkeypatch.setattr("src.config.settings.native_access_token_minutes", 60)
    monkeypatch.setattr("src.config.settings.frontend_url", "https://app.example.com")


class SignsIn:
    def get_authorization_url(self, state: str | None = None):
        return f"https://provider.example.com/authorize?state={state}", state

    async def exchange_code_for_tokens(self, code: str):
        return {"access_token": "access"}

    async def get_user_info(self, access_token: str):
        return {"email": EMAIL, "name": "Phone User", "verified_email": True}


async def _done(_email: str) -> None:
    return None


def callback(test_client: TestClient, monkeypatch, app: str = NATIVE_APP, challenge: str | None = CHALLENGE):
    """The OAuth callback, reached the real way: a state minted for the app and the browser's nonce cookie."""
    monkeypatch.setattr("src.auth.router._get_provider", lambda _name: SignsIn())
    monkeypatch.setattr("src.auth.router.send_welcome_email_safe", _done)
    login = create_state(app, code_challenge=challenge)
    test_client.cookies.set(NONCE_COOKIE, login.nonce)
    return test_client.get(f"/auth/callback/google?code=abc&state={login.state}", follow_redirects=False)


def login_code(test_client: TestClient, monkeypatch) -> str:
    return parse_qs(urlparse(callback(test_client, monkeypatch).headers["location"]).query)["code"][0]


def exchange(test_client: TestClient, code: str, verifier: str = VERIFIER, device_id: str = PHONE):
    return test_client.post("/auth/native/token", json={"code": code, "code_verifier": verifier, "device_id": device_id})


def refresh(test_client: TestClient, tokens: dict, device_id: str = PHONE):
    return test_client.post("/auth/native/refresh", json={
        "user_id": tokens["user_id"], "device_id": device_id, "refresh_token": tokens["refresh_token"],
    })


def signed_in(test_client: TestClient, monkeypatch, device_id: str = PHONE) -> dict:
    response = exchange(test_client, login_code(test_client, monkeypatch), device_id=device_id)
    assert response.status_code == 200
    return response.json()


# Starting a login


def test_a_native_login_starts_with_a_challenge(test_client: TestClient, monkeypatch):
    monkeypatch.setattr("src.auth.router._get_provider", lambda _name: SignsIn())

    response = test_client.get(f"/auth/google?app=mobile&code_challenge={CHALLENGE}", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"].startswith("https://provider.example.com/authorize")


@pytest.mark.parametrize("query", [
    "app=mobile",
    "app=mobile&code_challenge=too-short",
    f"app=mobile&code_challenge={CHALLENGE}&code_challenge_method=plain",
    f"code_challenge={CHALLENGE}",
])
def test_a_native_login_needs_a_valid_s256_challenge_and_only_native_logins_send_one(test_client: TestClient, monkeypatch, query):
    monkeypatch.setattr("src.auth.router._get_provider", lambda _name: SignsIn())

    assert test_client.get(f"/auth/google?{query}", follow_redirects=False).status_code == 400


def test_native_login_is_off_until_the_scheme_is_configured(test_client: TestClient, monkeypatch):
    monkeypatch.setattr("src.config.settings.native_app_scheme", "")
    monkeypatch.setattr("src.auth.router._get_provider", lambda _name: SignsIn())

    assert test_client.get(f"/auth/google?app=mobile&code_challenge={CHALLENGE}", follow_redirects=False).status_code == 400
    assert test_client.post("/auth/native/token", json={"code": "c", "code_verifier": VERIFIER, "device_id": PHONE}).status_code == 404


# The callback and the code


def test_the_callback_returns_the_code_through_the_app_scheme_and_sets_up_the_product_account(test_client: TestClient, monkeypatch):
    response = callback(test_client, monkeypatch)

    location = urlparse(response.headers["location"])
    assert (location.scheme, location.netloc, location.path) == (SCHEME, "auth", "/login-success")
    user = IdentityRepository().find_by_email(EMAIL)
    assert AccountRepository().get(personal_account_id(user.user_id)) is not None


def test_a_code_is_redeemed_with_the_verifier_for_owner_tokens(test_client: TestClient, monkeypatch):
    response = exchange(test_client, login_code(test_client, monkeypatch))

    body = response.json()
    claims = jwt.decode(body["access_token"], settings.jwt_secret, algorithms=["HS256"], audience="owner")
    assert response.status_code == 200
    assert body["user_id"] == claims["sub"] == IdentityRepository().find_by_email(EMAIL).user_id
    assert body["expires_in"] == 3600
    assert claims["exp"] - time.time() < 3600 + 5
    me = test_client.get("/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200 and me.json()["email"] == EMAIL


def test_an_intercepted_code_is_useless_without_the_verifier(test_client: TestClient, monkeypatch):
    code = login_code(test_client, monkeypatch)

    assert exchange(test_client, code, verifier="x" * 43).status_code == 401
    # The failed attempt used the code up: single use holds even for a wrong guess.
    assert exchange(test_client, code).status_code == 401


def test_a_code_works_once(test_client: TestClient, monkeypatch):
    code = login_code(test_client, monkeypatch)

    assert exchange(test_client, code).status_code == 200
    assert exchange(test_client, code).status_code == 401


def test_codes_do_not_cross_between_the_web_and_the_app(test_client: TestClient, monkeypatch):
    web_code = parse_qs(urlparse(callback(test_client, monkeypatch, DEFAULT_APP, None).headers["location"]).query)["code"][0]
    native_code = login_code(test_client, monkeypatch)

    assert exchange(test_client, web_code).status_code == 401
    assert test_client.post("/auth/session", json={"code": native_code}).status_code == 401


def test_an_expired_code_is_refused(test_client: TestClient, monkeypatch):
    code = login_code(test_client, monkeypatch)
    monkeypatch.setattr(time, "time", lambda: time.monotonic() + 10**10)

    assert exchange(test_client, code).status_code == 401


def test_a_deactivated_account_cannot_redeem_a_code(test_client: TestClient, monkeypatch):
    code = login_code(test_client, monkeypatch)
    IdentityRepository().mark_inactive(IdentityRepository().find_by_email(EMAIL).user_id)

    assert exchange(test_client, code).status_code == 401


# Refresh tokens, one per device


def test_a_refresh_token_rotates_and_works_once(test_client: TestClient, monkeypatch):
    first = signed_in(test_client, monkeypatch)

    second = refresh(test_client, first)

    assert second.status_code == 200
    assert second.json()["refresh_token"] != first["refresh_token"]
    assert refresh(test_client, first).status_code == 401
    assert refresh(test_client, second.json()).status_code == 200


def test_each_device_keeps_its_own_session(test_client: TestClient, monkeypatch):
    phone = signed_in(test_client, monkeypatch, PHONE)
    tablet = signed_in(test_client, monkeypatch, TABLET)

    assert refresh(test_client, phone, PHONE).status_code == 200
    assert refresh(test_client, tablet, TABLET).status_code == 200
    assert refresh(test_client, tablet, PHONE).status_code == 401


def revoke(test_client: TestClient, tokens: dict, device_id: str):
    return test_client.post("/auth/native/revoke", json={
        "user_id": tokens["user_id"], "device_id": device_id, "refresh_token": tokens["refresh_token"],
    })


def test_revoking_needs_the_devices_refresh_token(test_client: TestClient, monkeypatch):
    phone = signed_in(test_client, monkeypatch, PHONE)

    assert revoke(test_client, {**phone, "refresh_token": "not-it"}, PHONE).status_code == 204
    assert refresh(test_client, phone, PHONE).status_code == 200


def test_revoking_signs_out_only_that_device(test_client: TestClient, monkeypatch):
    phone = signed_in(test_client, monkeypatch, PHONE)
    tablet = signed_in(test_client, monkeypatch, TABLET)

    assert revoke(test_client, phone, PHONE).status_code == 204
    assert refresh(test_client, phone, PHONE).status_code == 401
    assert refresh(test_client, tablet, TABLET).status_code == 200


def test_a_deactivated_account_cannot_refresh(test_client: TestClient, monkeypatch):
    tokens = signed_in(test_client, monkeypatch)
    IdentityRepository().mark_inactive(tokens["user_id"])

    assert refresh(test_client, tokens).status_code == 401


def test_an_expired_refresh_token_is_refused(test_client: TestClient, monkeypatch):
    tokens = signed_in(test_client, monkeypatch)
    app_tokens.repository.put_refresh_token(
        tokens["user_id"], f"{NATIVE_APP}#{PHONE}", app_tokens._hash(tokens["refresh_token"]), int(time.time()) - 1,
    )

    assert refresh(test_client, tokens).status_code == 401


def test_the_native_endpoints_are_rate_limited(test_client: TestClient, monkeypatch):
    statuses = [
        test_client.post("/auth/native/token", json={"code": "c", "code_verifier": VERIFIER, "device_id": PHONE}).status_code
        for _ in range(31)
    ]

    assert statuses[:30] == [401] * 30
    assert statuses[30] == 429


def test_account_deletion_removes_every_devices_refresh_token(dynamodb_table, monkeypatch):
    from lambdas.account_deletion_handler.handler import AccountDeletionHandler
    from src.identity import Identity

    monkeypatch.setenv("DYNAMODB_TABLE", dynamodb_table.name)
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.delenv("DYNAMODB_ENDPOINT", raising=False)
    user = IdentityRepository().create(Identity(email=EMAIL, name="Phone User"))
    for device in (PHONE, TABLET):
        app_tokens.repository.put_refresh_token(user.user_id, f"{NATIVE_APP}#{device}", "hash", int(time.time()) + 60)

    AccountDeletionHandler().delete_user_entities(user.user_id, EMAIL)

    assert app_tokens.repository.get_refresh_token(user.user_id, f"{NATIVE_APP}#{PHONE}") is None
    assert app_tokens.repository.get_refresh_token(user.user_id, f"{NATIVE_APP}#{TABLET}") is None


# Connect flows and configuration


def test_connect_flows_may_return_to_the_app(monkeypatch):
    assert safe_return_to(f"{SCHEME}://return/dashboard/connectors") == f"{SCHEME}://return/dashboard/connectors"
    with pytest.raises(ValueError):
        safe_return_to(f"{SCHEME}://auth/login-success")
    with pytest.raises(ValueError):
        safe_return_to("com.someone.else://return/dashboard")
    monkeypatch.setattr("src.config.settings.native_app_scheme", "")
    with pytest.raises(ValueError):
        safe_return_to(f"{SCHEME}://return/dashboard/connectors")


def test_mobile_is_a_reserved_app_name(monkeypatch):
    monkeypatch.setattr("src.config.settings.auth_app_urls", {"mobile": "https://elsewhere.example.com"})

    with pytest.raises(ConfigValidationError):
        settings.validate_core()
