"""Invitation HTTP regressions through production main.app and its real auth middleware."""

from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlsplit

import pytest

from src.accounts import AccountService, Member
from src.accounts.repository import AccountRepository
from src.auth.jwt_utils import create_access_token
from src.config import settings
from src.email import helpers
from src.iam.invitations import InvitationRepository
from src.iam.invitations.models import token_digest
from src.identity import Identity, IdentityRepository
from tests.mock_data import TEST_USER_EMAIL, user_id_for


def headers(identity, account_id=None, audience="owner"):
    result = {
        "Authorization": f"Bearer {create_access_token(identity, audience=audience)}"
    }
    if account_id is not None:
        result["X-Account-Id"] = account_id
    return result


def emailed_token(mail):
    url = urlsplit(mail.await_args.kwargs["invite_url"])
    assert url.path == "/invitations/accept"
    assert not url.query
    token = parse_qs(url.fragment)["token"][0]
    assert len(token) == 43
    return token


@pytest.fixture
def invitation(dynamodb_table, monkeypatch):
    owner = IdentityRepository().get(user_id_for(TEST_USER_EMAIL))
    account = AccountService().create_account(owner, "Integration Invitations")
    dynamodb_table.update_item(
        Key={"pk": account.pk, "sk": account.sk},
        UpdateExpression="SET seat_limit = :seats",
        ExpressionAttributeValues={":seats": 5},
    )
    invitee = IdentityRepository().create(
        Identity(
            email="accountless.invitee@example.com",
            name="Accountless Invitee",
            email_verified=True,
        )
    )
    assert AccountRepository().list_memberships(invitee.user_id) == []
    mail = AsyncMock(return_value=True)
    monkeypatch.setattr(helpers, "send_account_invitation_email_safe", mail)
    monkeypatch.setattr(settings, "account_invite_expiry_days", 7)
    monkeypatch.setattr(settings, "account_invite_pending_limit", 50)
    monkeypatch.setattr(settings, "account_invite_rate_limit", 20)
    monkeypatch.setattr(settings, "account_invite_rate_window_seconds", 3600)
    return account, owner, invitee, mail


def create_invitation(client, invitation):
    account, owner, invitee, mail = invitation
    response = client.post(
        "/iam/invitations",
        headers=headers(owner, account.account_id),
        json={"email": invitee.email},
    )
    assert response.status_code == 201, response.text
    token = emailed_token(mail)
    assert token not in response.text and "token_hash" not in response.text
    assert response.json()["delivery_status"] == "sent"
    return response.json()["invite_id"], token


def test_accountless_create_email_preview_accept_members(test_client, invitation):
    account, owner, invitee, mail = invitation
    invite_id, token = create_invitation(test_client, invitation)
    mail.assert_awaited_once()
    assert mail.await_args.kwargs["to_email"] == invitee.email
    assert mail.await_args.kwargs["account_name"] == account.name
    stored = InvitationRepository().get(account.account_id, invite_id)
    assert stored.token_hash == token_digest(token)
    assert token not in str(stored.item())

    preview = test_client.post("/invitations/preview", json={"token": token})
    assert preview.status_code == 200, preview.text
    assert preview.json()["account_id"] == account.account_id
    assert preview.json()["email"] == invitee.email
    assert preview.json()["login_context"] == token_digest(token)
    assert token not in preview.text
    assert (
        test_client.post("/invitations/accept", json={"token": token}).status_code
        == 401
    )
    assert AccountRepository().list_memberships(invitee.user_id) == []
    # A principal dependency would fail here: the verified identity has no account at all.
    accepted = test_client.post(
        "/invitations/accept", headers=headers(invitee), json={"token": token}
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json() == {"account_id": account.account_id, "invite_id": invite_id}
    assert token not in accepted.text
    members = test_client.get(
        "/iam/members", headers=headers(owner, account.account_id)
    )
    assert members.status_code == 200, members.text
    member = next(item for item in members.json() if item["user_id"] == invitee.user_id)
    assert member["status"] == "active" and not member["is_owner"]
    assert member["policies"] == [] and member["group_ids"] == []
    assert [
        m.account_id for m in AccountRepository().list_memberships(invitee.user_id)
    ] == [account.account_id]
    assert not InvitationRepository().prefix(account.account_id, "Attachment#")


@pytest.mark.parametrize(
    "body", [None, {}, {"token": "short-secret"}, {"token": "x" * 43}]
)
def test_anonymous_accept_never_skips_auth_even_for_missing_or_malformed_body(
    test_client, body
):
    response = test_client.post("/invitations/accept", json=body)
    assert response.status_code == 401, response.text


@pytest.mark.parametrize("audience", ["app:dashboard", "user"])
def test_non_owner_audience_rejected_for_all_protected_invitation_routes(
    test_client, invitation, audience
):
    account, owner, invitee, mail = invitation
    invite_id, token = create_invitation(test_client, invitation)
    owner_headers = headers(owner, account.account_id, audience)
    responses = [
        test_client.get("/iam/invitations", headers=owner_headers),
        test_client.post(
            "/iam/invitations",
            headers=owner_headers,
            json={"email": "other@example.com"},
        ),
        test_client.post(f"/iam/invitations/{invite_id}/resend", headers=owner_headers),
        test_client.delete(f"/iam/invitations/{invite_id}", headers=owner_headers),
        test_client.post(
            "/invitations/accept",
            headers=headers(invitee, audience=audience),
            json={"token": token},
        ),
    ]
    assert [response.status_code for response in responses] == [401] * len(responses)
    assert InvitationRepository().get(account.account_id, invite_id).status == "pending"
    mail.assert_awaited_once()


def test_anonymous_and_unprivileged_member_cannot_manage_invitations(
    test_client, invitation, dynamodb_table
):
    account, _, invitee, mail = invitation
    invite_id, _ = create_invitation(test_client, invitation)
    dynamodb_table.put_item(
        Item=Member(
            account_id=account.account_id,
            user_id=invitee.user_id,
            email=invitee.email,
            name=invitee.name,
        ).to_dynamo_item()
    )
    for auth, status in (({}, 401), (headers(invitee, account.account_id), 403)):
        responses = [
            test_client.get("/iam/invitations", headers=auth),
            test_client.post(
                "/iam/invitations", headers=auth, json={"email": "other@example.com"}
            ),
            test_client.post(f"/iam/invitations/{invite_id}/resend", headers=auth),
            test_client.delete(f"/iam/invitations/{invite_id}", headers=auth),
        ]
        assert [response.status_code for response in responses] == [status] * len(
            responses
        )
    assert InvitationRepository().get(account.account_id, invite_id).status == "pending"
    mail.assert_awaited_once()


@pytest.mark.parametrize("has_unrelated_membership", [False, True])
def test_account_header_cannot_block_or_redirect_acceptance(
    test_client, invitation, has_unrelated_membership
):
    account, owner, invitee, _ = invitation
    unrelated_owner = invitee if has_unrelated_membership else owner
    unrelated = AccountService().create_account(unrelated_owner, "Unrelated")
    invite_id, token = create_invitation(test_client, invitation)
    before = InvitationRepository().prefix(unrelated.account_id, "Member#")
    response = test_client.post(
        "/invitations/accept",
        headers=headers(invitee, unrelated.account_id),
        json={"token": token},
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"account_id": account.account_id, "invite_id": invite_id}
    assert InvitationRepository().prefix(unrelated.account_id, "Member#") == before
    assert (
        InvitationRepository().get_item(
            {
                "pk": f"Account#{account.account_id}",
                "sk": f"Member#{invitee.user_id}",
            }
        )["status"]
        == "active"
    )


@pytest.mark.parametrize("recipient", ["wrong_email", "unverified"])
def test_accept_requires_matching_verified_identity(test_client, invitation, recipient):
    account, _, invitee, _ = invitation
    invite_id, token = create_invitation(test_client, invitation)
    if recipient == "wrong_email":
        identity = IdentityRepository().create(
            Identity(
                email="wrong.recipient@example.com", name="Wrong", email_verified=True
            )
        )
        code = "INVITATION_EMAIL_MISMATCH"
    else:
        identity = invitee
        IdentityRepository().table.update_item(
            Key={"pk": f"Identity#{invitee.user_id}", "sk": "Identity#Metadata"},
            UpdateExpression="SET email_verified = :verified",
            ExpressionAttributeValues={":verified": False},
        )
        code = "EMAIL_NOT_VERIFIED"
    response = test_client.post(
        "/invitations/accept", headers=headers(identity), json={"token": token}
    )
    assert response.status_code == 403, response.text
    assert response.json()["detail"]["code"] == code
    assert token not in response.text
    assert InvitationRepository().get(account.account_id, invite_id).status == "pending"
    assert AccountRepository().list_memberships(identity.user_id) == []


@pytest.mark.parametrize("path", ["/invitations/preview", "/invitations/accept"])
@pytest.mark.parametrize(
    "body",
    [
        {"token": "secret-invalid-token"},
        {"token": "secret-invalid-token" * 100},
        {"token": {"secret": "secret-invalid-token"}},
        {"token": "x" * 43, "extra": "secret-invalid-token"},
    ],
)
def test_main_validation_does_not_echo_token_or_body(
    test_client, invitation, path, body
):
    _, _, invitee, _ = invitation
    response = test_client.post(path, headers=headers(invitee), json=body)
    assert response.status_code == 422, response.text
    assert "secret-invalid-token" not in response.text
    assert "x" * 43 not in response.text
    assert all(
        set(issue) == {"type", "loc", "msg"} for issue in response.json()["errors"]
    )


@pytest.mark.parametrize("raises", [False, True])
def test_failed_mail_persists_resend_rotates_and_owner_can_list_revoke(
    test_client, invitation, raises
):
    account, owner, invitee, mail = invitation
    mail.return_value = False
    if raises:
        mail.side_effect = RuntimeError(
            "secret email URL must never reach the response"
        )
    response = test_client.post(
        "/iam/invitations",
        headers=headers(owner, account.account_id),
        json={"email": invitee.email},
    )
    old = emailed_token(mail)
    assert response.status_code == 502, response.text
    assert response.json()["detail"]["code"] == "INVITATION_DELIVERY_FAILED"
    assert old not in response.text and "secret email URL" not in response.text
    invite_id = response.json()["detail"]["invite_id"]
    stored = InvitationRepository().get(account.account_id, invite_id)
    assert stored.status == "pending" and stored.delivery_status == "failed"
    assert (
        test_client.post("/invitations/preview", json={"token": old}).status_code == 200
    )
    mail.side_effect = None
    mail.return_value = True
    resent = test_client.post(
        f"/iam/invitations/{invite_id}/resend",
        headers=headers(owner, account.account_id),
    )
    assert resent.status_code == 200, resent.text
    assert resent.json()["delivery_status"] == "sent"
    new = emailed_token(mail)
    assert new != old and new not in resent.text
    assert (
        test_client.post("/invitations/preview", json={"token": old}).status_code == 404
    )
    stale_accept = test_client.post(
        "/invitations/accept", headers=headers(invitee), json={"token": old}
    )
    assert stale_accept.status_code == 404 and old not in stale_accept.text
    listed = test_client.get(
        "/iam/invitations", headers=headers(owner, account.account_id)
    )
    assert listed.status_code == 200, listed.text
    assert [item["invite_id"] for item in listed.json()] == [invite_id]
    assert (
        old not in listed.text
        and new not in listed.text
        and "token_hash" not in listed.text
    )
    revoked = test_client.delete(
        f"/iam/invitations/{invite_id}", headers=headers(owner, account.account_id)
    )
    assert revoked.status_code == 204, revoked.text
    assert InvitationRepository().get(account.account_id, invite_id).status == "revoked"
    assert (
        test_client.post("/invitations/preview", json={"token": new}).status_code == 404
    )
    assert (
        test_client.post(
            "/invitations/accept", headers=headers(invitee), json={"token": new}
        ).status_code
        == 404
    )
    assert AccountRepository().list_memberships(invitee.user_id) == []


def test_unknown_seat_metadata_fails_closed_at_route(
    test_client, invitation, dynamodb_table
):
    account, owner, invitee, mail = invitation
    invite_id, token = create_invitation(test_client, invitation)
    dynamodb_table.update_item(
        Key={"pk": account.pk, "sk": account.sk},
        UpdateExpression="REMOVE seat_limit",
    )
    responses = [
        test_client.post(
            "/iam/invitations",
            headers=headers(owner, account.account_id),
            json={"email": "other@example.com"},
        ),
        test_client.post(
            f"/iam/invitations/{invite_id}/resend",
            headers=headers(owner, account.account_id),
        ),
        test_client.post(
            "/invitations/accept", headers=headers(invitee), json={"token": token}
        ),
    ]
    for response in responses:
        assert response.status_code == 409, response.text
        assert response.json()["detail"]["code"] == "SEAT_LIMIT_UNAVAILABLE"
        assert token not in response.text
    assert InvitationRepository().get(
        account.account_id, invite_id
    ).token_hash == token_digest(token)
    assert AccountRepository().list_memberships(invitee.user_id) == []
    mail.assert_awaited_once()
