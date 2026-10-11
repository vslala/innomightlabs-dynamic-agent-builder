"""Configuration, logging and delivery boundaries for invitation secrets."""

import logging
import threading
from unittest.mock import Mock

import pytest

from src.auth.google_oauth import GoogleOAuth
from src.auth.oauth_providers import CognitoOAuthProvider
from src.config.settings import Settings
from src.email.invitation import AccountInvitationEmail
from src.email.service import EmailService

INVITE_SETTINGS = {
    "ACCOUNT_INVITE_EXPIRY_DAYS": ("account_invite_expiry_days", 7),
    "ACCOUNT_INVITE_PENDING_LIMIT": ("account_invite_pending_limit", 50),
    "ACCOUNT_INVITE_RATE_LIMIT": ("account_invite_rate_limit", 20),
    "ACCOUNT_INVITE_RATE_WINDOW_SECONDS": ("account_invite_rate_window_seconds", 3600),
}


def test_invitation_settings_defaults_and_overrides(monkeypatch):
    for name in INVITE_SETTINGS:
        monkeypatch.delenv(name, raising=False)
    defaults = Settings.from_env()
    for name, (attribute, default) in INVITE_SETTINGS.items():
        assert getattr(defaults, attribute) == default
        monkeypatch.setenv(name, str(default + 1))
    overridden = Settings.from_env()
    for attribute, default in INVITE_SETTINGS.values():
        assert getattr(overridden, attribute) == default + 1


@pytest.mark.parametrize("name", INVITE_SETTINGS)
@pytest.mark.parametrize("value", ["0", "-1", "not-an-integer"])
def test_invalid_invitation_configuration_is_refused(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError):
        Settings.from_env()


@pytest.mark.parametrize("provider", [GoogleOAuth, CognitoOAuthProvider])
def test_authorization_logs_do_not_expose_signed_state(provider, caplog):
    caplog.set_level(logging.DEBUG)
    state = "signed-invitation-context-with-browser-nonce"
    url, returned = provider().get_authorization_url(state=state)
    assert state in url and returned == state
    assert state not in caplog.text
    assert url not in caplog.text


async def test_invitation_mailjet_request_does_not_block_event_loop(monkeypatch):
    caller_thread = threading.get_ident()
    response = Mock(status_code=200)
    response.json.return_value = {"Messages": [{"Status": "success"}]}

    def send(**kwargs):
        assert threading.get_ident() != caller_thread
        assert kwargs["data"]["Messages"][0]["TrackClicks"] == "disabled"
        return response

    client = Mock()
    client.send.create.side_effect = send
    monkeypatch.setattr("src.email.service.Client", Mock(return_value=client))
    assert await EmailService().send_account_invitation_email(
        to_email="invitee@example.com", account_name="Team", invited_by="owner-id",
        invite_url="https://innomightlabs.com/invitations/accept#token=secret",
        expires_at="2026-10-18T00:00:00+00:00",
    )


def test_invitation_email_repr_does_not_expose_token():
    email = AccountInvitationEmail(
        account_name="Team", invited_by="owner-id",
        invite_url="https://innomightlabs.com/invitations/accept#token=secret-token",
        expires_at="2026-10-18T00:00:00+00:00",
    )
    assert "secret-token" not in repr(email)


def test_validation_errors_report_where_not_what_was_sent(test_client):
    """The app-wide 422 never echoes the submitted value (tokens, passwords, keys), in the body or the log."""
    response = test_client.post("/invitations/preview", json={"token": "hunter2-not-a-token"})
    assert response.status_code == 422
    assert "hunter2-not-a-token" not in response.text
    assert all(set(issue) == {"type", "loc", "msg"} for issue in response.json()["errors"])
