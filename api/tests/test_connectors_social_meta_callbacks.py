"""Meta's deauthorize and data-deletion callbacks: signed by the app secret, they find a person's accounts in every
InnomightLabs account through the grant items."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from urllib.parse import urlparse

import pytest

from src.config import settings
from src.config.settings import SocialAppCredentials
from src.connectors.social import networks
from src.connectors.social.meta_callbacks import parse_signed_request
from src.connectors.social.models import SocialAccount, SocialAccountStatus
from src.connectors.social.networks.facebook_pages import FacebookPagesNetwork
from src.connectors.social.repository import SocialAccountRepository
from src.crypto import encrypt

SECRET = "meta-secret"


def signed(payload: dict, secret: str = SECRET) -> str:
    def b64(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    body = b64(json.dumps(payload).encode())
    return f"{b64(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())}.{body}"


@pytest.fixture
def meta_app(monkeypatch):
    monkeypatch.setattr(networks, "NETWORKS", (FacebookPagesNetwork(),))
    monkeypatch.setattr(settings, "social_apps", {"facebook_pages": SocialAppCredentials("meta-app", SECRET)})


def connected(account_id: str, page: str, grant_id: str = "fb-user-1") -> SocialAccount:
    return SocialAccountRepository().connect(SocialAccount(
        account_id=account_id, network="facebook_page", external_id=page, handle=page, display_name=page,
        encrypted_credentials=encrypt(json.dumps({"page_access_token": "t", "page_id": page})), grant_id=grant_id,
        connected_by="someone",
    ))


def callback(test_client, kind: str, user_id: str = "fb-user-1", **overrides):
    payload = {"algorithm": "HMAC-SHA256", "issued_at": 1, "user_id": user_id, **overrides}
    return test_client.post(f"/connectors/social/meta/facebook_pages/{kind}", data={"signed_request": signed(payload)})


def test_a_signed_request_is_read_only_with_the_apps_signature():
    request = signed({"algorithm": "HMAC-SHA256", "user_id": "42"})
    assert parse_signed_request(request, SECRET)["user_id"] == "42"

    for bad in (signed({"algorithm": "HMAC-SHA256", "user_id": "42"}, "other-secret"),
                signed({"algorithm": "HMAC-SHA1", "user_id": "42"}),
                signed({"algorithm": "HMAC-SHA256"}),
                "not-a-signed-request", ""):
        with pytest.raises(ValueError):
            parse_signed_request(bad, SECRET)


def test_deauthorize_stops_posting_for_every_account_of_the_grant_in_any_innomightlabs_account(test_client, dynamodb_table, meta_app):
    mine, theirs, someone_else = connected("account-a", "111"), connected("account-b", "222"), connected("account-a", "333", "fb-user-2")

    response = callback(test_client, "deauthorize")

    assert response.status_code == 200
    repository = SocialAccountRepository()
    for account in (mine, theirs):
        reloaded = repository.get(account.account_id, account.social_account_id)
        assert reloaded.status == SocialAccountStatus.NEEDS_RECONNECT
        assert reloaded.last_error == "Access was removed in Facebook Pages"
    assert repository.get("account-a", someone_else.social_account_id).status == SocialAccountStatus.ACTIVE


def test_data_deletion_deletes_the_grants_accounts_and_links_to_a_status_page(test_client, dynamodb_table, meta_app):
    connected("account-a", "111")
    connected("account-b", "222")
    kept = connected("account-a", "333", "fb-user-2")

    response = callback(test_client, "data-deletion")

    assert response.status_code == 200
    body = response.json()
    assert body["url"].endswith(f"/connectors/social/meta/deletion/{body['confirmation_code']}")
    repository = SocialAccountRepository()
    assert repository.for_grant("facebook_page", "fb-user-1") == []
    assert repository.list("account-b") == []
    assert [account.social_account_id for account in repository.list("account-a")] == [kept.social_account_id]

    page = test_client.get(urlparse(body["url"]).path)
    assert page.status_code == 200 and "Your data has been deleted" in page.text
    assert body["confirmation_code"] in page.text and "(2)" in page.text


def test_an_unknown_deletion_code_says_so(test_client, dynamodb_table, meta_app):
    page = test_client.get("/connectors/social/meta/deletion/nope")
    assert page.status_code == 404 and "not found" in page.text


def test_a_callback_with_a_bad_signature_changes_nothing(test_client, dynamodb_table, meta_app):
    account = connected("account-a", "111")

    response = test_client.post("/connectors/social/meta/facebook_pages/data-deletion",
                                data={"signed_request": signed({"algorithm": "HMAC-SHA256", "user_id": "fb-user-1"}, "forged")})

    assert response.status_code == 400
    assert SocialAccountRepository().get("account-a", account.social_account_id) is not None


def test_a_callback_for_an_app_we_do_not_have_is_not_found(test_client, dynamodb_table, meta_app):
    assert test_client.post("/connectors/social/meta/myspace/deauthorize", data={"signed_request": "x.y"}).status_code == 404
