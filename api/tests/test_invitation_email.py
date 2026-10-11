"""Invitation delivery must not leak or persist its bearer token."""

from unittest.mock import AsyncMock, Mock

import pytest
from markupsafe import escape

from src.email import helpers, service
from src.email.invitation import AccountInvitationEmail, INVITATION_DELIVERY_FAILED
from src.email.message import INNOMIGHT_WORDMARK_URL

TOKEN = "raw-invitation-secret"
INVITE_URL = f"https://app.innomightlabs.com/invitations/accept#token={TOKEN}"
ARGS = {
    "to_email": "invitee@example.com",
    "account_name": "Research & Development",
    "invited_by": "immutable-user-id",
    "invite_url": INVITE_URL,
    "expires_at": "2026-10-18T12:00:00Z",
}


def invitation(**overrides):
    args = {key: value for key, value in ARGS.items() if key != "to_email"}
    return AccountInvitationEmail(**(args | overrides))


@pytest.fixture
def mailjet(monkeypatch):
    client = Mock()
    monkeypatch.setattr(service, "Client", Mock(return_value=client))
    client.send.create.return_value.status_code = 200
    client.send.create.return_value.json.return_value = {"Messages": [{"Status": "success"}]}
    return client


@pytest.fixture
def no_pending(monkeypatch):
    failure_handler = Mock(side_effect=AssertionError("Must not queue invitations"))
    pending_factory = Mock(side_effect=AssertionError("Must not persist invitations"))
    pending_repo = Mock(side_effect=AssertionError("Must not persist invitations"))
    monkeypatch.setattr(helpers, "_handle_email_failure", failure_handler)
    monkeypatch.setattr(helpers, "create_pending_email", pending_factory)
    monkeypatch.setattr(helpers, "PendingEmailRepository", pending_repo)
    yield
    failure_handler.assert_not_called()
    pending_factory.assert_not_called()
    pending_repo.assert_not_called()


def assert_safe_logs(caplog):
    assert caplog.records
    for record in caplog.records:
        assert record.getMessage() == INVITATION_DELIVERY_FAILED
        assert record.exc_info is None
        assert record.stack_info is None
        assert not record.args
    assert TOKEN not in caplog.text
    assert INVITE_URL not in caplog.text
    assert "provider-secret-response" not in caplog.text
    assert ARGS["to_email"] not in caplog.text


def test_house_brand_html_and_matching_plain_text():
    email = invitation()
    html = email.html()
    text = email.text()
    assert INNOMIGHT_WORDMARK_URL in html
    assert "InnomightLabs" in html and "InnomightLabs" in text
    assert "part of" in html
    assert "Research &amp; Development" in html
    assert ARGS["account_name"] in text
    assert ARGS["expires_at"] in html and ARGS["expires_at"] in text
    assert f'href="{INVITE_URL}"' in html
    assert f"Accept invitation: {INVITE_URL}" in text
    assert "ignore this email" in html and "ignore this email" in text
    assert ARGS["invited_by"] not in html and ARGS["invited_by"] not in text
    assert "Accept your account invitation" in html


def test_untrusted_names_are_escaped_and_inviter_is_not_exposed():
    account = '<script>alert("account")</script> & "Team"'
    inviter = '<img src=x onerror="alert(1)">immutable-user-id'
    email = invitation(account_name=account, invited_by=inviter, expires_at="<b>tomorrow</b>")
    html = email.html()
    assert str(escape(account)) in html
    assert "<script>" not in html and "<img src=x" not in html
    assert "&lt;b&gt;tomorrow&lt;/b&gt;" in html
    assert inviter not in html and inviter not in email.text()
    assert "immutable-user-id" not in html and "immutable-user-id" not in email.text()
    assert account in email.text()  # TextPart is plain text, not HTML.


@pytest.mark.parametrize("url", [
    INVITE_URL,
    "http://localhost:5173/invitations/accept#token=local-secret",
    'https://app.innomightlabs.com/invitations/accept#token=a&label="quoted"',
])
def test_http_https_links_preserved_and_attribute_escaped(url):
    email = invitation(invite_url=url)
    assert f'href="{escape(url)}"' in email.html()
    assert url in email.text()


@pytest.mark.parametrize("url", [
    "javascript:alert(1)", "data:text/html,<script>alert(1)</script>",
    "ftp://example.com/token", "//example.com/token", "/invitations#token=secret",
    "https:///missing-host", "https://user:pass@example.com/token",
    "https://example.com:invalid/token", "https://example.com\\@evil.com/token",
    "\nhttps://example.com/token", "https://example.com/\ttoken",
])
async def test_invalid_link_fails_before_provider_send(url, mailjet, no_pending, caplog):
    assert await helpers.send_account_invitation_email_safe(**(ARGS | {"invite_url": url})) is False
    mailjet.send.create.assert_not_called()
    assert_safe_logs(caplog)


async def test_delivery_payload_and_single_attempt(mailjet, no_pending):
    assert await helpers.send_account_invitation_email_safe(**ARGS) is True
    mailjet.send.create.assert_called_once()
    message = mailjet.send.create.call_args.kwargs["data"]["Messages"][0]
    assert message["From"] == {"Email": "noreply@innomightlabs.com", "Name": "InnomightLabs"}
    assert message["To"] == [{"Email": ARGS["to_email"]}]
    assert message["Subject"] == invitation().subject
    assert message["HTMLPart"] == invitation().html()
    assert message["TextPart"] == invitation().text()
    assert message["TrackClicks"] == "disabled"
    assert message["TrackOpens"] == "disabled"


@pytest.mark.parametrize(("status", "payload", "accepted"), [
    (200, {"Messages": [{"Status": "success"}, {"Status": "success"}]}, True),
    (200, {"Messages": [{"Status": "success"}, {"Status": "error", "Errors": [INVITE_URL]}]}, False),
    (200, {"Messages": [{"Status": "error", "Errors": ["provider-secret-response", INVITE_URL]}]}, False),
    (200, {"Messages": []}, False),
    (200, {}, False),
    (200, {"Messages": [{"Status": "Success"}]}, False),
    (200, {"Messages": [{}]}, False),
    (200, {"Messages": None}, False),
    (200, {"Messages": "success"}, False),
    (200, {"Messages": [None]}, False),
    (200, [], False),
    (201, {"Messages": [{"Status": "success"}]}, False),
    (400, {"Messages": [{"Status": "success"}]}, False),
    (500, {"error": INVITE_URL}, False),
])
async def test_provider_acceptance(status, payload, accepted, mailjet, no_pending, caplog):
    response = mailjet.send.create.return_value
    response.status_code = status
    response.json.return_value = payload
    assert await helpers.send_account_invitation_email_safe(**ARGS) is accepted
    mailjet.send.create.assert_called_once()
    if not accepted:
        assert_safe_logs(caplog)
    else:
        assert not caplog.records
    if status != 200:
        response.json.assert_not_called()


@pytest.mark.parametrize("failure", ["send", "json", "render", "client"])
async def test_exceptions_never_logged_or_persisted(failure, mailjet, monkeypatch, no_pending, caplog):
    error = RuntimeError(f"provider-secret-response {INVITE_URL}")
    if failure == "send":
        mailjet.send.create.side_effect = error
    elif failure == "json":
        mailjet.send.create.return_value.json.side_effect = error
    elif failure == "render":
        monkeypatch.setattr(AccountInvitationEmail, "html", Mock(side_effect=error))
    else:
        monkeypatch.setattr(service, "Client", Mock(side_effect=error))
    assert await helpers.send_account_invitation_email_safe(**ARGS) is False
    assert mailjet.send.create.call_count <= 1
    assert_safe_logs(caplog)


@pytest.mark.parametrize("outcome", [True, False, RuntimeError(INVITE_URL)])
async def test_helper_delegates_exact_args_once(outcome, monkeypatch, no_pending, caplog):
    send = AsyncMock()
    if isinstance(outcome, Exception):
        send.side_effect = outcome
    else:
        send.return_value = outcome
    factory = Mock(return_value=Mock(send_account_invitation_email=send))
    monkeypatch.setattr(helpers, "EmailService", factory)
    assert await helpers.send_account_invitation_email_safe(**ARGS) is (outcome is True)
    factory.assert_called_once_with()
    send.assert_awaited_once_with(**ARGS)
    if outcome is not True:
        assert_safe_logs(caplog)
