from __future__ import annotations

import asyncio
import socket
from unittest.mock import AsyncMock

import httpcore
import pytest

from src.common import outbound
from src.config.settings import Settings, settings
from src.skills.rest_template.actions import get, post
from src.skills.rest_template.security import PlatformDestinationGuard

PLATFORM_IP = "8.8.8.8"
EXTERNAL_IP = "93.184.215.14"


def infos(*addresses):
    return [(socket.AF_INET6 if ":" in address else socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443)) for address in addresses]


@pytest.fixture
def dns(monkeypatch):
    answers = {}

    async def resolve(loop, host, port, **kwargs):
        return infos(*answers.get(host, [PLATFORM_IP]))

    monkeypatch.setattr(asyncio.BaseEventLoop, "getaddrinfo", resolve)
    monkeypatch.setattr(settings, "rest_template_blocked_ip_ranges", "")
    return answers


@pytest.mark.parametrize("url", [
    "https://innomightlabs.com", "https://INNOMIGHTLABS.COM./x",
    "https://api.innomightlabs.com", "https://a.b.innomightlabs.com:8443/x",
    "https://innomightlabs%2ecom", "https://cdn.innomightlabs.com",
])
@pytest.mark.parametrize("action", [get, post])
def test_platform_hosts_blocked_before_dns_or_socket(monkeypatch, url, action):
    resolve = AsyncMock(side_effect=AssertionError("must not resolve"))
    monkeypatch.setattr(asyncio.BaseEventLoop, "getaddrinfo", resolve)
    result = asyncio.run(action({"url": url}, {}, {}))
    assert not result["ok"]
    assert "platform destinations" in result["error"]
    resolve.assert_not_called()


@pytest.mark.parametrize("host", [PLATFORM_IP, "alias.example", "::ffff:8.8.8.8"])
def test_platform_ips_and_aliases_blocked_at_socket(dns, host):
    dns[host] = [host if ":" in host or host == PLATFORM_IP else PLATFORM_IP]
    inner = AsyncMock()
    guard = PlatformDestinationGuard()
    backend = outbound._AsyncPublicBackend(inner, guard.check_addresses)
    with pytest.raises(outbound.BlockedDestination, match="platform IP"):
        asyncio.run(backend.connect_tcp(host, 443))
    inner.connect_tcp.assert_not_called()


def test_mixed_public_answers_fail_closed(dns):
    dns["alias.example"] = [EXTERNAL_IP, PLATFORM_IP]
    inner = AsyncMock()
    guard = PlatformDestinationGuard()
    with pytest.raises(outbound.BlockedDestination, match="platform IP"):
        asyncio.run(outbound._AsyncPublicBackend(inner, guard.check_addresses).connect_tcp("alias.example", 443))
    inner.connect_tcp.assert_not_called()


def test_allowed_destination_connects_only_to_checked_ip(dns):
    dns["innomightlabs.com.attacker.example"] = [EXTERNAL_IP]
    inner = AsyncMock()
    guard = PlatformDestinationGuard()
    asyncio.run(outbound._AsyncPublicBackend(inner, guard.check_addresses).connect_tcp("innomightlabs.com.attacker.example", 443))
    inner.connect_tcp.assert_awaited_once_with(EXTERNAL_IP, 443, None, None, None)


@pytest.mark.parametrize("address", ["1.1.1.1", "2606:4700:4700::1111"])
def test_explicit_origin_cidrs_blocked(dns, monkeypatch, address):
    monkeypatch.setattr(settings, "rest_template_blocked_ip_ranges", "1.1.1.0/24,2606:4700:4700::/48")
    with pytest.raises(outbound.BlockedDestination, match="platform IP"):
        asyncio.run(PlatformDestinationGuard().check_addresses("external.example", [address]))


@pytest.mark.parametrize("network", ["::ffff:1.1.1.1/128", "::ffff:1.1.1.0/120", "::ffff:1.1.1.1"])
@pytest.mark.parametrize("address", ["1.1.1.1", "::ffff:1.1.1.1"])
def test_mapped_ipv6_deny_entries_block_both_address_forms(dns, monkeypatch, network, address):
    monkeypatch.setattr(settings, "rest_template_blocked_ip_ranges", network)
    with pytest.raises(outbound.BlockedDestination, match="platform IP"):
        asyncio.run(PlatformDestinationGuard().check_addresses("external.example", [address]))


def test_configured_platform_host_and_ip_are_protected(dns, monkeypatch):
    monkeypatch.setattr(settings, "api_base_url", "https://platform.up.railway.app")
    dns["platform.up.railway.app"] = ["1.1.1.1"]
    guard = PlatformDestinationGuard()
    with pytest.raises(outbound.BlockedDestination):
        guard.refuse_host("platform.up.railway.app")
    with pytest.raises(outbound.BlockedDestination, match="platform IP"):
        asyncio.run(guard.check_addresses("alias.example", ["1.1.1.1"]))


def test_protected_dns_failure_prevents_connection(dns, monkeypatch):
    dns["api.innomightlabs.com"] = []
    with pytest.raises(outbound.BlockedDestination, match="Could not resolve protected"):
        asyncio.run(PlatformDestinationGuard().check_addresses("external.example", [EXTERNAL_IP]))


@pytest.mark.parametrize("failure", [socket.gaierror("no DNS"), asyncio.TimeoutError()])
def test_protected_dns_errors_fail_closed(monkeypatch, failure):
    monkeypatch.setattr(asyncio.BaseEventLoop, "getaddrinfo", AsyncMock(side_effect=failure))
    with pytest.raises(outbound.BlockedDestination, match="Could not resolve protected"):
        asyncio.run(PlatformDestinationGuard().check_addresses("external.example", [EXTERNAL_IP]))


def test_host_header_cannot_route_external_ip_to_platform():
    result = asyncio.run(get({"url": f"http://{EXTERNAL_IP}", "headers": {"Host": "api.innomightlabs.com"}}, {}, {}))
    assert not result["ok"]
    assert "Host header" in result["error"]


class ResponseStream(httpcore.AsyncNetworkStream):
    def __init__(self, response: bytes):
        self.response = response

    async def read(self, max_bytes, timeout=None):
        response, self.response = self.response, b""
        return response

    async def write(self, buffer, timeout=None):
        pass

    async def aclose(self):
        pass

    def get_extra_info(self, info):
        return None


@pytest.mark.parametrize("target", ["http://api.innomightlabs.com/private", f"http://{PLATFORM_IP}/private", "http://alias.example/private"])
@pytest.mark.parametrize("action", [get, post])
def test_real_transport_blocks_redirect_before_second_socket(dns, monkeypatch, target, action):
    dns["external.example"] = [EXTERNAL_IP]
    from httpcore._backends.auto import AutoBackend

    connect = AsyncMock(return_value=ResponseStream(
        f"HTTP/1.1 307 Temporary Redirect\r\nLocation: {target}\r\nContent-Length: 0\r\n\r\n".encode()
    ))
    monkeypatch.setattr(AutoBackend, "connect_tcp", connect)
    result = asyncio.run(action({"url": "http://external.example/start"}, {}, {}))
    assert not result["ok"]
    assert "platform" in result["error"]
    assert connect.await_count == 1
    assert connect.call_args.args[0] == EXTERNAL_IP


def test_allowed_external_request_uses_guarded_transport(dns, monkeypatch):
    dns["external.example"] = [EXTERNAL_IP]
    from httpcore._backends.auto import AutoBackend

    connect = AsyncMock(return_value=ResponseStream(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok"))
    monkeypatch.setattr(AutoBackend, "connect_tcp", connect)
    result = asyncio.run(get({"url": "http://external.example"}, {}, {}))
    assert result == {"ok": True, "status_code": 200, "body_preview": "ok"}


def test_denylist_environment_setting(monkeypatch):
    monkeypatch.setenv("REST_TEMPLATE_BLOCKED_IP_RANGES", "1.1.1.1/32")
    assert Settings.from_env().rest_template_blocked_ip_ranges == "1.1.1.1/32"


def test_invalid_operator_denylist_fails_closed(monkeypatch):
    monkeypatch.setattr(settings, "rest_template_blocked_ip_ranges", "not-an-ip")
    with pytest.raises(ValueError, match="Invalid REST_TEMPLATE_BLOCKED_IP_RANGES"):
        PlatformDestinationGuard()
