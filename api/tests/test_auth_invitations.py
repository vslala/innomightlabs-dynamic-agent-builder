"""Invitation OAuth is a verified identity handoff, never invitation acceptance."""
import time
from unittest.mock import AsyncMock, Mock
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from fastapi import HTTPException

from src.accounts import AccountService, personal_account_id
from src.auth import router as auth_router
from src.auth.apps import (
    DEFAULT_APP, NONCE_COOKIE, STATE_AUDIENCE, app_from_state, create_state,
    invitation_from_state,
)
from src.config import settings
from src.iam.invitations.models import iso_timestamp
from src.iam.invitations.service import InvitationService
from src.identity import Identity, IdentityRepository
from tests.mock_data import TEST_USER_EMAIL, user_id_for

EMAIL = "invited.person@example.com"
FRONTEND = "https://app.example.com"


class FakeProvider:
    def __init__(self, provider: str) -> None:
        verification = "verified_email" if provider == "google" else "email_verified"
        self.user_info = {"email": EMAIL.upper(), "name": "Invited Person", verification: True}
        self.exchange_code_for_tokens = AsyncMock(return_value={"access_token": "access"})

    def get_authorization_url(self, state: str | None = None) -> tuple[str, str | None]:
        return f"https://provider.example.com/authorize?state={state}", state

    async def get_user_info(self, access_token: str) -> dict:
        return self.user_info


@pytest.fixture(params=["google", "cognito"])
def provider_name(request):
    return request.param


@pytest.fixture
def flow(dynamodb_table, monkeypatch, provider_name):
    monkeypatch.setattr(settings, "frontend_url", FRONTEND)
    monkeypatch.setattr(settings, "auth_app_urls", {"other": "https://other.example.com"})
    owner = IdentityRepository().get(user_id_for(TEST_USER_EMAIL))
    account = AccountService().create_account(owner, "Inviting Account")
    dynamodb_table.update_item(
        Key={"pk": account.pk, "sk": account.sk}, UpdateExpression="SET seat_limit = :seats",
        ExpressionAttributeValues={":seats": 5},
    )
    service = InvitationService()
    invite, raw = service.create(account.account_id, owner.user_id, EMAIL)
    provider = FakeProvider(provider_name)
    monkeypatch.setattr(auth_router, "_get_provider", lambda _name: provider)
    welcome = AsyncMock()
    monkeypatch.setattr(auth_router, "send_welcome_email_safe", welcome)
    ensure = Mock(wraps=AccountService.ensure_personal_account)
    monkeypatch.setattr(AccountService, "ensure_personal_account", ensure)
    find = Mock(wraps=auth_router.identity_repository.find_or_create)
    monkeypatch.setattr(auth_router.identity_repository, "find_or_create", find)
    return service, invite, raw, provider, welcome, ensure, find


def start(test_client, provider_name, token_hash):
    response = test_client.get(
        f"/auth/{provider_name}", params={"invitation": token_hash}, follow_redirects=False,
    )
    assert response.status_code == 307
    return parse_qs(urlparse(response.headers["location"]).query)["state"][0]


def callback(test_client, provider_name, state, **params):
    return test_client.get(
        f"/auth/callback/{provider_name}", params={"state": state, "code": "abc", **params},
        follow_redirects=False,
    )


def assert_error(response, marker, flow):
    _, invite, raw, _, _, ensure, find = flow
    assert response.headers["location"] == f"{FRONTEND}/login?error={marker}"
    assert raw not in response.headers["location"]
    assert invite.token_hash not in response.headers["location"]
    ensure.assert_not_called()
    find.assert_not_called()


@pytest.mark.parametrize("existing", [False, True])
def test_matched_invitation_only_signs_in_and_marks_continuation(
    test_client, provider_name, flow, existing, dynamodb_table, caplog,
):
    service, invite, raw, _, welcome, ensure, find = flow
    identities = IdentityRepository()
    previous = identities.create(Identity(email=EMAIL, name="Old Name")) if existing else None
    def account_items():
        return sorted(
            (item for item in dynamodb_table.scan()["Items"] if item["pk"] == f"Account#{invite.account_id}"),
            key=lambda item: item["sk"],
        )

    before = account_items()
    state = start(test_client, provider_name, service.preview(raw).login_context)
    payload = jwt.decode(state, settings.jwt_secret, algorithms=[settings.jwt_algorithm], audience=STATE_AUDIENCE)
    assert payload["invitation"] == invite.token_hash
    assert set(payload) == {"app", "aud", "exp", "nonce", "invitation"}
    assert raw not in state and raw not in str(payload)
    assert app_from_state(state, test_client.cookies.get(NONCE_COOKIE)) == DEFAULT_APP
    assert invitation_from_state(state, test_client.cookies.get(NONCE_COOKIE)) == invite.token_hash

    response = callback(test_client, provider_name, state)
    location = urlparse(response.headers["location"])
    query = parse_qs(location.query)
    assert location.path == "/login-success"
    assert set(query) == {"code", "invitation"} and query["invitation"] == ["1"]
    assert raw not in response.headers["location"] and invite.token_hash not in response.headers["location"]
    assert raw not in caplog.text
    ensure.assert_not_called()
    find.assert_called_once()
    identity = identities.find_by_email(EMAIL)
    assert identity.email_verified is True and identity.name == "Invited Person"
    if previous:
        assert identity.user_id == previous.user_id
        welcome.assert_not_called()
    else:
        welcome.assert_awaited_once()
    assert dynamodb_table.get_item(Key={
        "pk": f"Account#{personal_account_id(identity.user_id)}", "sk": "Account#Metadata",
    }).get("Item") is None
    assert account_items() == before
    assert service.pending_by_hash(invite.token_hash).status == "pending"
    session = test_client.post("/auth/session", json={"code": query["code"][0]})
    assert session.status_code == 200
    claims = jwt.decode(session.json()["token"], settings.jwt_secret,
                        algorithms=[settings.jwt_algorithm], audience="owner")
    assert claims["sub"] == identity.user_id


def test_mismatched_email_rejected_before_identity_and_retry_works(test_client, provider_name, flow):
    _, invite, _, provider, _, ensure, find = flow
    provider.user_info["email"] = "wrong@example.com"
    state = start(test_client, provider_name, invite.token_hash)
    assert_error(callback(test_client, provider_name, state), "invitation_email_mismatch", flow)
    assert IdentityRepository().find_by_email("wrong@example.com") is None
    provider.user_info["email"] = EMAIL
    state = start(test_client, provider_name, invite.token_hash)
    assert "invitation=1" in callback(test_client, provider_name, state).headers["location"]
    ensure.assert_not_called()
    find.assert_called_once()


@pytest.mark.parametrize("verification", [False, "false", None])
def test_unverified_invitation_rejected_before_identity(test_client, provider_name, flow, verification):
    _, invite, _, provider, _, _, _ = flow
    field = "verified_email" if provider_name == "google" else "email_verified"
    provider.user_info[field] = verification
    state = start(test_client, provider_name, invite.token_hash)
    assert_error(callback(test_client, provider_name, state), "invitation_invalid", flow)


@pytest.mark.parametrize("change", ["expired", "revoked"])
def test_live_invitation_rechecked_after_provider_round_trip(
    test_client, provider_name, flow, dynamodb_table, change,
):
    service, invite, _, _, _, _, _ = flow
    state = start(test_client, provider_name, invite.token_hash)
    if change == "revoked":
        service.revoke(invite.account_id, invite.invited_by, invite.invite_id)
    else:
        expiry = int(time.time()) - 1
        dynamodb_table.update_item(Key=invite.key, UpdateExpression="SET #ttl = :expiry, expires_at = :iso",
                                  ExpressionAttributeNames={"#ttl": "ttl"},
                                  ExpressionAttributeValues={":expiry": expiry, ":iso": iso_timestamp(expiry)})
    assert_error(callback(test_client, provider_name, state), "invitation_invalid", flow)


@pytest.mark.parametrize("context", ["raw", "unknown", "malformed", "empty", "revoked"])
def test_start_rejects_invalid_context_before_creating_state(
    test_client, provider_name, flow, monkeypatch, context,
):
    service, invite, raw, provider, _, _, _ = flow
    if context == "revoked":
        service.revoke(invite.account_id, invite.invited_by, invite.invite_id)
    value = {"raw": raw, "unknown": "0" * 64, "malformed": "g" * 64,
             "empty": "", "revoked": invite.token_hash}[context]
    create = Mock(side_effect=AssertionError("No state should be issued"))
    monkeypatch.setattr(auth_router, "create_state", create)
    response = test_client.get(f"/auth/{provider_name}", params={"invitation": value}, follow_redirects=False)
    assert_error(response, "invitation_invalid", flow)
    create.assert_not_called()
    provider.exchange_code_for_tokens.assert_not_called()


@pytest.mark.parametrize("attack", ["nonce", "missing_nonce", "tampered", "expired", "audience", "other_app", "raw_claim"])
def test_invalid_state_never_creates_identity_or_suppresses_account_creation(
    test_client, provider_name, flow, attack,
):
    _, invite, raw, provider, _, _, _ = flow
    state = start(test_client, provider_name, invite.token_hash)
    nonce = test_client.cookies.get(NONCE_COOKIE)
    if attack in {"nonce", "missing_nonce"}:
        test_client.cookies.clear()
        if attack == "nonce":
            test_client.cookies.set(NONCE_COOKIE, "another-browser")
    else:
        payload = jwt.decode(state, settings.jwt_secret, algorithms=[settings.jwt_algorithm], audience=STATE_AUDIENCE)
        if attack == "expired":
            payload["exp"] = int(time.time()) - 1
        elif attack == "audience":
            payload["aud"] = "owner"
        elif attack == "other_app":
            payload["app"] = "other"
        elif attack == "raw_claim":
            payload["invitation"] = raw
        state = jwt.encode(payload, "wrong-secret" if attack == "tampered" else settings.jwt_secret,
                           algorithm=settings.jwt_algorithm)
    callback_nonce = None if attack == "missing_nonce" else "another-browser" if attack == "nonce" else nonce
    assert invitation_from_state(state, callback_nonce) is None
    assert_error(callback(test_client, provider_name, state), "auth_failed", flow)
    provider.exchange_code_for_tokens.assert_not_called()


def test_other_app_cannot_start_invitation_login(test_client, provider_name, flow):
    _, invite, _, _, _, _, _ = flow
    response = test_client.get(f"/auth/{provider_name}",
                               params={"app": "other", "invitation": invite.token_hash}, follow_redirects=False)
    assert response.status_code == 400
    with pytest.raises(HTTPException):
        create_state("other", invite.token_hash)


def test_provider_errors_return_safely_without_invitation_context(test_client, provider_name, flow):
    _, invite, raw, _, _, _, _ = flow
    state = start(test_client, provider_name, invite.token_hash)
    assert_error(callback(test_client, provider_name, state, error=f"{raw}-{invite.token_hash}"), "auth_failed", flow)


def test_normal_login_still_ensures_personal_account(test_client, provider_name, flow, monkeypatch):
    _, _, _, _, welcome, ensure, _ = flow
    # Keep the real implementation, including the bound instance argument.
    monkeypatch.setattr(AccountService, "ensure_personal_account",
                        lambda self, user: ensure(self, user))
    response = test_client.get(f"/auth/{provider_name}", follow_redirects=False)
    state = parse_qs(urlparse(response.headers["location"]).query)["state"][0]
    assert invitation_from_state(state, test_client.cookies.get(NONCE_COOKIE)) is None
    result = callback(test_client, provider_name, state)
    assert set(parse_qs(urlparse(result.headers["location"]).query)) == {"code"}
    ensure.assert_called_once()
    welcome.assert_awaited_once()
