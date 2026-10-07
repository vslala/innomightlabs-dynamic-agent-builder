from types import SimpleNamespace

import pytest
from dns.exception import Timeout
from email_validator import EmailNotValidError, validate_email

from src.widget import guest_email


def test_normalizes_and_checks_deliverability(monkeypatch):
    def validate(raw, **kwargs):
        assert raw == "Name@GMAIL.com"
        assert kwargs["check_deliverability"] is True
        return SimpleNamespace(normalized="Name@gmail.com", domain="gmail.com", ascii_domain="gmail.com", mx=[(10, "mail.gmail.com")])
    monkeypatch.setattr(guest_email, "validate_email", validate)
    monkeypatch.setattr(guest_email, "_addresses", lambda host: ["142.250.1.27"])
    assert guest_email.check_guest_email(" Name@GMAIL.com ") == "Name@gmail.com"


@pytest.mark.parametrize("reason", ["Malformed address", "Domain does not exist", "Domain does not accept email"])
def test_rejections_keep_the_reason(monkeypatch, reason):
    def reject(*args, **kwargs):
        raise EmailNotValidError(reason)
    monkeypatch.setattr(guest_email, "validate_email", reject)
    with pytest.raises(guest_email.GuestEmailRejected, match=reason):
        guest_email.check_guest_email("invalid")


def test_disposable_domain(monkeypatch):
    monkeypatch.setattr(guest_email, "validate_email", lambda *args, **kwargs: SimpleNamespace(
        domain="mailinator.com", ascii_domain="mailinator.com", mx=[(10, "mail.mailinator.com")]))
    with pytest.raises(guest_email.GuestEmailRejected, match="temporary"):
        guest_email.check_guest_email("a@mailinator.com")


def test_dns_timeout_exception_fails_closed(monkeypatch):
    def timeout(*args, **kwargs):
        raise Timeout()
    monkeypatch.setattr(guest_email, "validate_email", timeout)
    with pytest.raises(guest_email.GuestEmailRejected, match="try again"):
        guest_email.check_guest_email("a@gmail.com")


def test_actual_email_validator_unknown_deliverability_fails_closed(monkeypatch):
    class Resolver:
        def resolve(self, *args, **kwargs):
            raise Timeout()
    monkeypatch.setattr(guest_email, "validate_email", lambda raw, **kwargs: validate_email(
        raw, check_deliverability=True, dns_resolver=Resolver()))
    with pytest.raises(guest_email.GuestEmailRejected, match="try again"):
        guest_email.check_guest_email("a@gmail.com")


def found(mx):
    return lambda *args, **kwargs: SimpleNamespace(
        normalized="a@parked.com", domain="parked.com", ascii_domain="parked.com", mx=mx)


@pytest.mark.parametrize("host", ["localhost.", "localhost", "mail", "mx.parked.local", "127.0.0.1"])
def test_mail_servers_that_cannot_be_real_are_rejected(monkeypatch, host):
    """Parked domains such as killer.com publish `MX 0 localhost.`, which passes a plain MX check."""
    monkeypatch.setattr(guest_email, "validate_email", found([(0, host)]))
    monkeypatch.setattr(guest_email, "_addresses", lambda host: pytest.fail("should not resolve"))
    if host[0].isdigit():
        monkeypatch.setattr(guest_email, "_addresses", lambda host: [host])
    with pytest.raises(guest_email.GuestEmailRejected, match="can't send email to that address"):
        guest_email.check_guest_email("a@parked.com")


@pytest.mark.parametrize("addresses", [["127.0.0.1"], ["10.0.0.5", "192.168.1.2"], []])
def test_mail_servers_on_private_or_missing_addresses_are_rejected(monkeypatch, addresses):
    monkeypatch.setattr(guest_email, "validate_email", found([(10, "mx.parked.com")]))
    monkeypatch.setattr(guest_email, "_addresses", lambda host: addresses)
    with pytest.raises(guest_email.GuestEmailRejected, match="can't send email to that address"):
        guest_email.check_guest_email("a@parked.com")


def test_one_reachable_mail_server_is_enough(monkeypatch):
    monkeypatch.setattr(guest_email, "validate_email", found([(0, "localhost."), (20, "mx2.parked.com")]))
    monkeypatch.setattr(guest_email, "_addresses", lambda host: ["93.184.215.14"])
    assert guest_email.check_guest_email("a@parked.com") == "a@parked.com"


def test_mail_server_lookup_timeout_asks_to_retry(monkeypatch):
    def timeout(host):
        raise Timeout()
    monkeypatch.setattr(guest_email, "validate_email", found([(10, "mx.parked.com")]))
    monkeypatch.setattr(guest_email, "_addresses", timeout)
    with pytest.raises(guest_email.GuestEmailRejected, match="try again"):
        guest_email.check_guest_email("a@parked.com")
