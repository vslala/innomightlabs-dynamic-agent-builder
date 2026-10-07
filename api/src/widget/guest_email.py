"""Validate deliverability, not ownership, before a guest identity is created."""
from ipaddress import ip_address

import dns.resolver
from dns.exception import DNSException, Timeout
from disposable_email_domains import blocklist as DISPOSABLE_DOMAINS
from email_validator import EmailNotValidError, validate_email

from src.config import settings

#: Hostnames that can't be a real mail server. Parked domains often publish `MX 0 localhost.`
UNROUTABLE_SUFFIXES = (".localhost", ".local", ".invalid", ".test", ".example", ".internal")
NO_INBOX = "We can't send email to that address. Please check it or use a different one."
CANT_CHECK = "We couldn't check that address. Please try again."


class GuestEmailRejected(ValueError):
    """A visitor-facing reason the address cannot be used."""


def check_guest_email(raw: str) -> str:
    try:
        result = validate_email(raw.strip(), check_deliverability=True,
                                timeout=settings.widget_guest_email_dns_timeout_seconds)
    except EmailNotValidError as error:
        raise GuestEmailRejected(str(error)) from error
    except (DNSException, TimeoutError, OSError) as error:
        raise GuestEmailRejected(CANT_CHECK) from error
    # email-validator returns normally with unknown-deliverability on DNS timeouts.
    # Only a positive MX/fallback result is sufficient for a guest session.
    if not getattr(result, "mx", None):
        raise GuestEmailRejected(CANT_CHECK)
    domain = (result.ascii_domain or result.domain).lower()
    if domain in DISPOSABLE_DOMAINS:
        raise GuestEmailRejected("Please use your own email address, not a temporary one.")
    _require_reachable_mail_server(result.mx)
    return result.normalized


def _require_reachable_mail_server(mx: list[tuple[int, str]]) -> None:
    """At least one mail server must be a public host, not `localhost` or a private address."""
    timed_out = False
    for _, host in sorted(mx):
        host = host.rstrip(".").lower()
        if _unroutable_name(host):
            continue
        try:
            if any(ip_address(address).is_global for address in _addresses(host)):
                return
        except Timeout:
            timed_out = True
        except (DNSException, ValueError):
            continue
    raise GuestEmailRejected(CANT_CHECK if timed_out else NO_INBOX)


def _unroutable_name(host: str) -> bool:
    return host == "localhost" or "." not in host or host.endswith(UNROUTABLE_SUFFIXES)


def _addresses(host: str) -> list[str]:
    try:
        return [str(ip_address(host))]  # an MX that is an IP literal
    except ValueError:
        pass
    resolver = dns.resolver.Resolver()
    resolver.lifetime = settings.widget_guest_email_dns_timeout_seconds
    addresses: list[str] = []
    for record_type in ("A", "AAAA"):
        try:
            addresses += [answer.to_text() for answer in resolver.resolve(host, record_type)]
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
            continue
    return addresses
