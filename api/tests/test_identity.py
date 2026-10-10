"""Identities: an immutable user_id, signed in by a unique email (KAN-74)."""
from urllib.parse import parse_qs, urlparse
from uuid import UUID

import jwt
import pytest
from fastapi.testclient import TestClient

from src.auth.apps import DEFAULT_APP, NONCE_COOKIE, create_state
from src.identity import EmailTaken, Identity, IdentityRepository

EMAIL = "Ada.Lovelace@Example.com"


@pytest.fixture
def identities(dynamodb_table) -> IdentityRepository:
    return IdentityRepository()


def test_an_identity_is_found_by_id_and_by_any_casing_of_its_email(identities):
    created = identities.create(Identity(email=EMAIL, name="Ada"))

    assert identities.get(created.user_id) == created
    assert identities.find_by_email("  ada.lovelace@example.COM ") == created
    assert identities.find_by_email("ada.lovelace+work@example.com") is None, "+tags are different addresses"


def test_an_email_belongs_to_one_identity(identities):
    identities.create(Identity(email=EMAIL, name="Ada"))
    impostor = Identity(email=EMAIL.lower(), name="Someone else")

    with pytest.raises(EmailTaken):
        identities.create(impostor)

    assert identities.get(impostor.user_id) is None, "the identity is not written without its email"


def test_find_or_create_returns_the_existing_identity(identities):
    first, created = identities.find_or_create(EMAIL, "Ada")
    again, created_again = identities.find_or_create(EMAIL.upper(), "Ada")

    assert (created, created_again) == (True, False)
    assert again.user_id == first.user_id


def test_concurrent_sign_ups_with_one_email_make_one_identity(identities, monkeypatch):
    """Every racer looked before anyone wrote. The conditional transaction lets one create; the rest
    get the winner. (Threads aren't used: moto's in-memory table isn't thread-safe; DynamoDB's
    transactions are atomic.)"""
    monkeypatch.setattr(identities, "find_by_email", _missing_once(identities.find_by_email))
    winner, created = identities.find_or_create(EMAIL, "Ada")
    racers = []
    for _ in range(3):
        monkeypatch.setattr(identities, "find_by_email", _missing_once(IdentityRepository().find_by_email))
        racers.append(identities.find_or_create(EMAIL, "Ada"))

    assert created is True
    assert {(user.user_id, was_created) for user, was_created in racers} == {(winner.user_id, False)}


def test_changing_the_email_moves_the_index_with_it(identities):
    user = identities.create(Identity(email=EMAIL, name="Ada", email_verified=True))

    identities.change_email(user.user_id, EMAIL, "ada@newmail.com")

    moved = identities.find_by_email("ada@newmail.com")
    assert moved is not None and moved.user_id == user.user_id
    assert moved.email_verified is False, "a new address has to be verified again"
    assert identities.find_by_email(EMAIL) is None


def test_an_email_already_in_use_cannot_be_taken(identities):
    ada = identities.create(Identity(email=EMAIL, name="Ada"))
    identities.create(Identity(email="grace@example.com", name="Grace"))

    with pytest.raises(EmailTaken):
        identities.change_email(ada.user_id, EMAIL, "grace@example.com")

    assert identities.get(ada.user_id).email == EMAIL
    assert identities.find_by_email(EMAIL).user_id == ada.user_id


class SignsIn:
    def __init__(self, email: str = EMAIL, name: str = "Ada", picture: str | None = None) -> None:
        self.user_info = {"email": email, "name": name, "picture": picture, "verified_email": True}

    async def exchange_code_for_tokens(self, code: str):
        return {"access_token": "access", "refresh_token": "provider-refresh"}

    async def get_user_info(self, access_token: str):
        return self.user_info


def sign_in(test_client: TestClient, monkeypatch, provider: SignsIn) -> dict:
    """The SPA's flow: the OAuth callback, then the one-time code for a session token."""
    monkeypatch.setattr("src.auth.router._get_provider", lambda _name: provider)
    monkeypatch.setattr("src.auth.router.send_welcome_email_safe", lambda _email: _done())
    login = create_state(DEFAULT_APP)
    test_client.cookies.set(NONCE_COOKIE, login.nonce)
    callback = test_client.get(f"/auth/callback/google?code=abc&state={login.state}", follow_redirects=False)
    code = parse_qs(urlparse(callback.headers["location"]).query)["code"][0]
    token = test_client.post("/auth/session", json={"code": code}).json()["token"]
    return jwt.decode(token, "test-secret", algorithms=["HS256"], audience="owner")


async def _done() -> None:
    return None


def test_signing_in_names_the_user_by_id(test_client: TestClient, monkeypatch):
    claims = sign_in(test_client, monkeypatch, SignsIn())

    identity = IdentityRepository().find_by_email(EMAIL)
    assert UUID(claims["sub"]) and claims["sub"] == identity.user_id
    assert claims["email"] == EMAIL
    assert identity.email_verified is True
    assert "provider-refresh" not in str(identity.to_dynamo_item()), "the provider's refresh token is not kept"


def test_signing_in_again_keeps_the_id_and_refreshes_the_profile(test_client: TestClient, monkeypatch):
    first = sign_in(test_client, monkeypatch, SignsIn(name="Ada"))
    second = sign_in(test_client, monkeypatch, SignsIn(email=EMAIL.lower(), name="Ada L.", picture="https://pic"))

    identity = IdentityRepository().get(first["sub"])
    assert second["sub"] == first["sub"]
    assert (identity.name, identity.picture) == ("Ada L.", "https://pic")


def test_auth_me_reports_the_user_id(test_client: TestClient, monkeypatch):
    claims = sign_in(test_client, monkeypatch, SignsIn())
    token = jwt.encode(claims, "test-secret", algorithm="HS256")

    me = test_client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).json()

    assert (me["user_id"], me["email"]) == (claims["sub"], EMAIL)


def test_local_sign_up_and_login_issue_tokens_for_one_identity(test_client: TestClient, monkeypatch):
    monkeypatch.setattr("src.config.settings.environment", "local")
    credentials = {"username": "ada", "password": "correct horse"}

    signed_up = test_client.post("/auth/local/signup", json=credentials)
    logged_in = test_client.post("/auth/local/login", json=credentials)
    taken = test_client.post("/auth/local/signup", json=credentials)

    subjects = {
        jwt.decode(response.json()["token"], "test-secret", algorithms=["HS256"], audience="owner")["sub"]
        for response in (signed_up, logged_in)
    }
    assert (signed_up.status_code, logged_in.status_code, taken.status_code) == (200, 200, 400)
    assert subjects == {IdentityRepository().find_by_email("ada@example.com").user_id}


def _missing_once(find_by_email):
    calls = {"n": 0}

    def find(email: str):
        calls["n"] += 1
        return None if calls["n"] == 1 else find_by_email(email)

    return find
