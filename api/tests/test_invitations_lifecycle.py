import time

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from src.accounts import AccountService, Member
from src.config import settings
from src.exceptions import register_exception_handlers
from src.iam.dependencies import get_principal
from src.iam.invitations import InvitationService
from src.iam.invitations.models import token_digest
from src.iam.invitations.router import router
from src.iam.invitations.schemas import TokenRequest
from src.iam.principal import load_principal
from src.iam.repository import ConcurrentChange
from src.iam.service import IamError
from src.identity import IdentityRepository
from tests.mock_data import TEST_USER_EMAIL, TEST_USER_EMAIL_2, user_id_for

OWNER = user_id_for(TEST_USER_EMAIL)
INVITEE = user_id_for(TEST_USER_EMAIL_2)


@pytest.fixture
def lifecycle(dynamodb_table, monkeypatch):
    owner = IdentityRepository().get(OWNER)
    identity = IdentityRepository().get(INVITEE)
    account = AccountService().create_account(owner, "Invitation Lab")
    dynamodb_table.update_item(Key={"pk": account.pk, "sk": account.sk},
                              UpdateExpression="SET seat_limit = :seats", ExpressionAttributeValues={":seats": 5})
    for name, value in (("account_invite_expiry_days", 7), ("account_invite_pending_limit", 50),
                        ("account_invite_rate_limit", 20), ("account_invite_rate_window_seconds", 3600)):
        monkeypatch.setattr(settings, name, value, raising=False)
    now = [time.time()]
    service = InvitationService(clock=lambda: now[0])
    return service, account.account_id, identity, dynamodb_table, now


def error_code(code, fn, *args):
    with pytest.raises(IamError) as error:
        fn(*args)
    assert error.value.detail["code"] == code
    return error.value


def issue(lifecycle, email=None):
    service, aid, identity, _, _ = lifecycle
    return service.create(aid, OWNER, email or identity.email)


def set_metadata(table, aid, field, value):
    table.update_item(Key={"pk": f"Account#{aid}", "sk": "Account#Metadata"},
                      UpdateExpression="SET #field = :value", ExpressionAttributeNames={"#field": field},
                      ExpressionAttributeValues={":value": value})


def test_hash_only_and_atomic_acceptance_without_permission_presets(lifecycle):
    service, aid, identity, table, now = lifecycle
    invite, raw = issue(lifecycle, f"  {identity.email.upper()}  ")
    item = service.repository.get_item(invite.key)
    assert len(raw) == 43 and invite.token_hash == token_digest(raw)
    assert raw not in str(item) and raw not in repr(invite)
    assert item["gsi2_pk"] == item["gsi2_sk"] == f"InviteToken#{token_digest(raw)}"
    assert invite.email == identity.email and invite.ttl == int(now[0] + 7 * 86400)
    assert service.pending_by_hash(token_digest(raw)).invite_id == invite.invite_id
    assert service.preview(raw).model_dump() == {
        "account_id": aid, "account_name": "Invitation Lab", "email": identity.email,
        "expires_at": invite.expires_at, "status": "pending", "login_context": token_digest(raw),
    }
    before = service.repository.account(aid)["authz_version"]
    assert service.accept(raw, identity).model_dump() == {"account_id": aid, "invite_id": invite.invite_id}
    assert service.repository.account(aid)["authz_version"] == before + 1
    assert service.repository.get(aid, invite.invite_id).accepted_by == identity.user_id
    assert len(service.repository.prefix(aid, "Member#")) == 2
    assert not service.repository.prefix(aid, "Attachment#")
    state = service.repository.iam.load(aid)
    assert [p.policy.name for p in state.effective_policies(identity.user_id)] == ["OwnerAccess"]
    service.accept(raw, identity)
    assert len(service.repository.prefix(aid, "Member#")) == 2
    assert service.preview(raw).status == "accepted"
    error_code("INVALID_INVITATION", service.pending_by_hash, token_digest(raw))


def test_duplicate_and_expired_pending_are_logically_freed(lifecycle):
    service, aid, identity, _, now = lifecycle
    invite, raw = issue(lifecycle)
    error_code("INVITATION_EXISTS", service.create, aid, OWNER, identity.email.upper())
    now[0] += 8 * 86400
    error_code("INVALID_INVITATION", service.preview, raw)
    error_code("INVALID_INVITATION", service.accept, raw, identity)
    newer, _ = issue(lifecycle)
    assert service.repository.get(aid, invite.invite_id).status == "pending"  # no TTL cleanup needed
    assert newer.invite_id != invite.invite_id
    error_code("INVITATION_EXISTS", service.resend, aid, OWNER, invite.invite_id)


def test_resend_rotates_and_revocation_invalidates(lifecycle):
    service, aid, identity, _, _ = lifecycle
    invite, old = issue(lifecycle)
    rotated, raw = service.resend(aid, OWNER, invite.invite_id)
    assert rotated.invite_id == invite.invite_id and rotated.token_hash != invite.token_hash
    error_code("INVALID_INVITATION", service.preview, old)
    error_code("INVALID_INVITATION", service.accept, old, identity)
    service.revoke(aid, OWNER, invite.invite_id)
    error_code("INVALID_INVITATION", service.preview, raw)
    error_code("INVITATION_NOT_PENDING", service.resend, aid, OWNER, invite.invite_id)
    assert service.repository.get(aid, invite.invite_id).status == "revoked"


def test_gsi_stale_payload_is_not_authority(lifecycle, monkeypatch):
    service, aid, identity, _, _ = lifecycle
    old, raw = issue(lifecycle)
    service.resend(aid, OWNER, old.invite_id)
    original_query = service.repository.query

    def stale_gsi(**kwargs):
        if kwargs.get("IndexName") == "gsi2":
            return [old.item()]
        return original_query(**kwargs)

    monkeypatch.setattr(service.repository, "query", stale_gsi)
    error_code("INVALID_INVITATION", service.preview, raw)
    error_code("INVALID_INVITATION", service.accept, raw, identity)


@pytest.mark.parametrize("field,value,code", [("email_verified", False, "EMAIL_NOT_VERIFIED"),
                                              ("status", "inactive", "EMAIL_NOT_VERIFIED"),
                                              ("email", "different@example.com", "INVITATION_EMAIL_MISMATCH")])
def test_current_identity_required_not_stale_request_identity(lifecycle, field, value, code):
    service, aid, identity, table, _ = lifecycle
    _, raw = issue(lifecycle)
    table.update_item(Key={"pk": identity.pk, "sk": identity.sk}, UpdateExpression="SET #field = :value",
                      ExpressionAttributeNames={"#field": field}, ExpressionAttributeValues={":value": value})
    error_code(code, service.accept, raw, identity)
    assert len(service.repository.prefix(aid, "Member#")) == 1


@pytest.mark.parametrize("status", ["active", "suspended"])
def test_existing_members_cannot_be_invited_or_overwritten(lifecycle, status):
    service, aid, identity, table, _ = lifecycle
    invite, raw = issue(lifecycle)
    member = Member(account_id=aid, user_id=identity.user_id, email=identity.email,
                    name="Original", status=status)
    table.put_item(Item=member.to_dynamo_item())
    error_code("ALREADY_MEMBER", service.create, aid, OWNER, identity.email)
    error_code("ALREADY_MEMBER", service.resend, aid, OWNER, invite.invite_id)
    error_code("ALREADY_MEMBER", service.accept, raw, identity)
    assert service.repository.get_item({"pk": member.pk, "sk": member.sk})["name"] == "Original"


@pytest.mark.parametrize("status", ["removed", "suspended"])
def test_repeat_accept_does_not_resurrect_members(lifecycle, status):
    service, aid, identity, table, _ = lifecycle
    _, raw = issue(lifecycle)
    service.accept(raw, identity)
    key = {"pk": f"Account#{aid}", "sk": f"Member#{identity.user_id}"}
    if status == "removed":
        table.delete_item(Key=key)
    else:
        table.update_item(Key=key, UpdateExpression="SET #s = :s", ExpressionAttributeNames={"#s": "status"},
                          ExpressionAttributeValues={":s": "suspended"})
    error_code("MEMBERSHIP_UNAVAILABLE", service.accept, raw, identity)
    member = service.repository.get_item(key)
    assert member is None if status == "removed" else member["status"] == "suspended"


@pytest.mark.parametrize("value", [None, "5", True, 0, -1, Decimal("1.5")])
def test_seats_fail_closed_on_create_resend_accept(lifecycle, value):
    service, aid, identity, table, _ = lifecycle
    invite, raw = issue(lifecycle)
    if value is None:
        table.update_item(Key={"pk": f"Account#{aid}", "sk": "Account#Metadata"}, UpdateExpression="REMOVE seat_limit")
    else:
        set_metadata(table, aid, "seat_limit", value)
    error_code("SEAT_LIMIT_UNAVAILABLE", service.create, aid, OWNER, "other@example.com")
    error_code("SEAT_LIMIT_UNAVAILABLE", service.resend, aid, OWNER, invite.invite_id)
    error_code("SEAT_LIMIT_UNAVAILABLE", service.accept, raw, identity)


def test_seat_reservations_accept_conversion_and_suspended_members_count(lifecycle):
    service, aid, identity, table, _ = lifecycle
    set_metadata(table, aid, "seat_limit", 2)
    _, raw = issue(lifecycle)
    error_code("SEAT_LIMIT_REACHED", service.create, aid, OWNER, "other@example.com")
    service.accept(raw, identity)  # one reservation becomes one member, not two seats
    table.update_item(Key={"pk": f"Account#{aid}", "sk": f"Member#{identity.user_id}"},
                      UpdateExpression="SET #s = :s", ExpressionAttributeNames={"#s": "status"},
                      ExpressionAttributeValues={":s": "suspended"})
    error_code("SEAT_LIMIT_REACHED", service.create, aid, OWNER, "other@example.com")


def test_pending_limit_and_expiry_release_reservation(lifecycle, monkeypatch):
    service, aid, _, _, now = lifecycle
    monkeypatch.setattr(settings, "account_invite_pending_limit", 1)
    invite, _ = issue(lifecycle)
    error_code("PENDING_LIMIT_REACHED", service.create, aid, OWNER, "other@example.com")
    now[0] += 8 * 86400
    service.resend(aid, OWNER, invite.invite_id)
    error_code("PENDING_LIMIT_REACHED", service.create, aid, OWNER, "other@example.com")


def test_rate_limit_consumed_by_resend_and_released_on_transaction_failure(lifecycle, monkeypatch):
    service, aid, _, _, _ = lifecycle
    monkeypatch.setattr(settings, "account_invite_rate_limit", 1)
    original = service.repository.iam.commit
    monkeypatch.setattr(service.repository.iam, "commit", lambda *a, **k: (_ for _ in ()).throw(ConcurrentChange(aid)))
    error_code("CONFLICT", service.create, aid, OWNER, "other@example.com")
    monkeypatch.setattr(service.repository.iam, "commit", original)
    invite, _ = issue(lifecycle)  # failed transaction released its slot
    error_code("INVITATION_RATE_LIMITED", service.resend, aid, OWNER, invite.invite_id)


def test_permission_gates_and_account_active(lifecycle):
    service, aid, identity, table, _ = lifecycle
    error_code("NOT_A_MEMBER", service.create, aid, identity.user_id, "other@example.com")
    table.put_item(Item=Member(account_id=aid, user_id=identity.user_id, email=identity.email, name=identity.name).to_dynamo_item())
    error_code("ACCESS_DENIED", service.create, aid, identity.user_id, "other@example.com")
    error_code("ACCESS_DENIED", service.list_invitations, aid, identity.user_id)
    set_metadata(table, aid, "status", "pending_deletion")
    error_code("ACCOUNT_INACTIVE", service.create, aid, OWNER, "other@example.com")


@pytest.mark.parametrize("mutation", ["email", "verification", "status", "seats", "account_status"])
def test_accept_transaction_blocks_metadata_interleavings(lifecycle, monkeypatch, mutation):
    service, aid, identity, table, _ = lifecycle
    invite, raw = issue(lifecycle)
    original = service.repository.iam.commit

    def interleave(*args, **kwargs):
        if mutation in {"email", "verification", "status"}:
            field, value = {"email": ("email", "changed@example.com"), "verification": ("email_verified", False),
                            "status": ("status", "inactive")}[mutation]
            table.update_item(Key={"pk": identity.pk, "sk": identity.sk}, UpdateExpression="SET #f = :v",
                              ExpressionAttributeNames={"#f": field}, ExpressionAttributeValues={":v": value})
        else:
            field, value = ("seat_limit", 1) if mutation == "seats" else ("status", "pending_deletion")
            set_metadata(table, aid, field, value)  # intentionally no version bump (billing race)
        original(*args, **kwargs)

    monkeypatch.setattr(service.repository.iam, "commit", interleave)
    error_code("CONFLICT", service.accept, raw, identity)
    assert len(service.repository.prefix(aid, "Member#")) == 1
    assert service.repository.get(aid, invite.invite_id).status == "pending"


@pytest.mark.parametrize("other", ["create", "revoke", "resend", "accept"])
def test_accept_serializes_other_lifecycle_writes(lifecycle, monkeypatch, other):
    service, aid, identity, _, _ = lifecycle
    invite, raw = issue(lifecycle)
    original = service.repository.iam.commit
    winner = InvitationService()

    def interleave(*args, **kwargs):
        {"create": lambda: winner.create(aid, OWNER, "other@example.com"),
         "revoke": lambda: winner.revoke(aid, OWNER, invite.invite_id),
         "resend": lambda: winner.resend(aid, OWNER, invite.invite_id),
         "accept": lambda: winner.accept(raw, identity)}[other]()
        original(*args, **kwargs)

    monkeypatch.setattr(service.repository.iam, "commit", interleave)
    error_code("CONFLICT", service.accept, raw, identity)
    assert len(service.repository.prefix(aid, "Member#")) == (2 if other == "accept" else 1)
    assert service.repository.get(aid, invite.invite_id).status == ("accepted" if other == "accept" else "revoked" if other == "revoke" else "pending")


def test_two_creates_compete_for_last_seat(lifecycle, monkeypatch):
    service, aid, _, table, _ = lifecycle
    set_metadata(table, aid, "seat_limit", 2)
    original = service.repository.iam.commit

    def interleave(*args, **kwargs):
        InvitationService().create(aid, OWNER, "winner@example.com")
        original(*args, **kwargs)

    monkeypatch.setattr(service.repository.iam, "commit", interleave)
    error_code("CONFLICT", service.create, aid, OWNER, "loser@example.com")
    assert [invite.email for invite in service.repository.invites(aid)] == ["winner@example.com"]


def test_delivery_status_cannot_overwrite_rotated_invitation(lifecycle):
    service, aid, _, _, _ = lifecycle
    old, _ = issue(lifecycle)
    rotated, _ = service.resend(aid, OWNER, old.invite_id)
    assert not service.repository.mark_delivery(old, "sent")
    assert service.repository.get(aid, rotated.invite_id).delivery_status == "pending"
    assert service.repository.mark_delivery(rotated, "failed")
    assert service.repository.get(aid, rotated.invite_id).delivery_status == "failed"


def test_paginated_queries_are_strong_except_gsi(lifecycle, monkeypatch):
    service, aid, _, _, _ = lifecycle
    invite, raw = issue(lifecycle)
    original = service.repository.table.query
    calls = []

    def paginated(**kwargs):
        calls.append(kwargs.copy())
        if not kwargs.get("ExclusiveStartKey"):
            result = original(**kwargs)
            result["LastEvaluatedKey"] = invite.key
            return result
        return {"Items": []}

    monkeypatch.setattr(service.repository.table, "query", paginated)
    assert service.repository.invites(aid) == [invite]
    assert service.preview(raw).login_context == token_digest(raw)
    assert len(calls) == 4
    assert all(call.get("ConsistentRead") is True for call in calls if "IndexName" not in call)
    assert all("ConsistentRead" not in call for call in calls if "IndexName" in call)


@pytest.fixture
def routes(lifecycle, monkeypatch):
    from src.email import helpers
    service, aid, identity, _, _ = lifecycle
    sent = AsyncMock(return_value=True)
    monkeypatch.setattr(helpers, "send_account_invitation_email_safe", sent, raising=False)
    app = FastAPI()
    register_exception_handlers(app)  # the app's real 422 and error shapes
    app.include_router(router)

    @app.middleware("http")
    async def identity_middleware(request: Request, call_next):
        if request.headers.get("Test-Identity"):
            request.state.identity = identity
        return await call_next(request)

    app.dependency_overrides[get_principal] = lambda: load_principal(OWNER, aid)
    return TestClient(app), sent, app


def test_routes_send_only_email_secret_and_accept_without_target_principal(lifecycle, routes):
    service, aid, identity, _, _ = lifecycle
    client, sent, app = routes
    created = client.post("/iam/invitations", json={"email": identity.email})
    assert created.status_code == 201, created.text
    payload = created.json()
    url = sent.call_args.kwargs["invite_url"]
    assert url.startswith(f'{settings.frontend_url.rstrip("/")}/invitations/accept#token=')
    raw = url.split("#token=")[1]
    assert raw not in created.text and "token_hash" not in payload and payload["delivery_status"] == "sent"
    preview = client.post("/invitations/preview", json={"token": raw})
    assert preview.status_code == 200 and preview.json()["login_context"] == token_digest(raw)
    app.dependency_overrides[get_principal] = lambda: (_ for _ in ()).throw(AssertionError("No principal on acceptance"))
    assert client.post("/invitations/accept", json={"token": raw}).status_code == 401
    accepted = client.post("/invitations/accept", json={"token": raw}, headers={"Test-Identity": "yes"})
    assert accepted.status_code == 200, accepted.text
    assert accepted.json() == {"account_id": aid, "invite_id": payload["invite_id"]}


@pytest.mark.parametrize("exception", [False, True])
def test_mail_failures_preserve_pending_and_consume_rate_slot(lifecycle, routes, monkeypatch, exception):
    service, aid, identity, _, _ = lifecycle
    client, sent, _ = routes
    monkeypatch.setattr(settings, "account_invite_rate_limit", 1)
    sent.return_value = False
    if exception:
        sent.side_effect = RuntimeError("sensitive email URL")
    response = client.post("/iam/invitations", json={"email": identity.email})
    assert response.status_code == 502, response.text
    invite_id = response.json()["detail"]["invite_id"]
    invite = service.repository.get(aid, invite_id)
    assert invite.status == "pending" and invite.delivery_status == "failed"
    assert client.post(f"/iam/invitations/{invite_id}/resend").status_code == 429


def test_token_validation_never_echoes_secret(lifecycle, routes):
    client, _, _ = routes
    raw = "secret-invalid-token"
    for path in ("/invitations/preview", "/invitations/accept"):
        response = client.post(path, json={"token": raw})
        assert response.status_code == 422 and raw not in response.text
        response = client.post(path, json={"token": raw * 100})
        assert response.status_code == 422 and raw not in response.text
    assert raw not in repr(TokenRequest(token="x" * 43))
    assert "token" not in client.get("/openapi.json").json()["components"]["schemas"]["InvitationResponse"]["properties"]


def test_preview_throttling_fail_closed(lifecycle, routes, monkeypatch):
    from src.rate_limits.policy import RateLimitDecision
    client, _, _ = routes
    _, raw = issue(lifecycle)
    monkeypatch.setattr("src.iam.invitations.service.RateLimiter.acquire", lambda *a: RateLimitDecision(allowed=False))
    assert client.post("/invitations/preview", json={"token": raw}).status_code == 429


@pytest.mark.parametrize("operation", ["create", "resend"])
@pytest.mark.parametrize("field,value", [("seat_limit", 1), ("status", "pending_deletion")])
def test_issuance_guards_billing_and_account_status_without_version_bump(lifecycle, monkeypatch, operation, field, value):
    service, aid, identity, table, _ = lifecycle
    invite, raw = issue(lifecycle)
    original = service.repository.iam.commit

    def interleave(*args, **kwargs):
        set_metadata(table, aid, field, value)
        original(*args, **kwargs)

    monkeypatch.setattr(service.repository.iam, "commit", interleave)
    if operation == "create":
        error_code("CONFLICT", service.create, aid, OWNER, "other@example.com")
    else:
        error_code("CONFLICT", service.resend, aid, OWNER, invite.invite_id)
    assert service.repository.invites(aid) == [invite]
    assert service.repository.get(aid, invite.invite_id).token_hash == token_digest(raw)


def test_membership_conditional_put_does_not_overwrite_interleaved_member(lifecycle, monkeypatch):
    service, aid, identity, table, _ = lifecycle
    invite, raw = issue(lifecycle)
    original = service.repository.iam.commit
    existing = Member(account_id=aid, user_id=identity.user_id, email=identity.email,
                      name="Do not overwrite", status="suspended")

    def interleave(*args, **kwargs):
        table.put_item(Item=existing.to_dynamo_item())  # even a legacy writer without version bump
        original(*args, **kwargs)

    monkeypatch.setattr(service.repository.iam, "commit", interleave)
    error_code("CONFLICT", service.accept, raw, identity)
    assert service.repository.get_item({"pk": existing.pk, "sk": existing.sk})["name"] == existing.name
    assert service.repository.get(aid, invite.invite_id).status == "pending"


def test_http_gates_list_issue_resend_and_revoke(lifecycle, routes):
    service, aid, identity, table, _ = lifecycle
    client, _, app = routes
    invite, _ = issue(lifecycle)
    table.put_item(Item=Member(account_id=aid, user_id=identity.user_id, email=identity.email, name=identity.name).to_dynamo_item())
    app.dependency_overrides[get_principal] = lambda: load_principal(identity.user_id, aid)
    responses = [client.get("/iam/invitations"),
                 client.post("/iam/invitations", json={"email": "other@example.com"}),
                 client.post(f"/iam/invitations/{invite.invite_id}/resend"),
                 client.delete(f"/iam/invitations/{invite.invite_id}")]
    assert all(response.status_code == 403 for response in responses)
    assert service.repository.get(aid, invite.invite_id).status == "pending"


def test_http_resend_then_revoke_after_failed_delivery(lifecycle, routes):
    service, aid, identity, _, _ = lifecycle
    client, sent, _ = routes
    sent.return_value = False
    failed = client.post("/iam/invitations", json={"email": identity.email})
    invite_id = failed.json()["detail"]["invite_id"]
    old = sent.call_args.kwargs["invite_url"].split("#token=")[1]
    sent.return_value = True
    resent = client.post(f"/iam/invitations/{invite_id}/resend")
    raw = sent.call_args.kwargs["invite_url"].split("#token=")[1]
    assert resent.status_code == 200 and resent.json()["delivery_status"] == "sent"
    assert client.post("/invitations/preview", json={"token": old}).status_code == 404
    listed = client.get("/iam/invitations")
    assert listed.status_code == 200 and listed.json()[0]["invite_id"] == invite_id
    assert raw not in listed.text and "token_hash" not in listed.text
    assert client.delete(f"/iam/invitations/{invite_id}").status_code == 204
    assert client.post("/invitations/preview", json={"token": raw}).status_code == 404
