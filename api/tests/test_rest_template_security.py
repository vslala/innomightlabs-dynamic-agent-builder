from __future__ import annotations

import asyncio
import socket
from unittest.mock import AsyncMock

import httpcore
import pytest

from src.skills.rest_template.actions import get, post
from src.skills.rest_template.security import is_ip_address

EXTERNAL_IP = "93.184.215.14"


def infos(*addresses):
    return [(socket.AF_INET6 if ":" in address else socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443)) for address in addresses]


@pytest.fixture
def dns(monkeypatch):
    answers: dict[str, list[str]] = {}

    async def resolve(loop, host, port, **kwargs):
        return infos(*answers.get(host, [EXTERNAL_IP]))

    monkeypatch.setattr(asyncio.BaseEventLoop, "getaddrinfo", resolve)
    return answers


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


@pytest.fixture
def sockets(monkeypatch):
    from httpcore._backends.auto import AutoBackend

    def serve(*responses: bytes) -> AsyncMock:
        connect = AsyncMock(side_effect=[ResponseStream(response) for response in responses])
        monkeypatch.setattr(AutoBackend, "connect_tcp", connect)
        return connect

    return serve


@pytest.mark.parametrize("host", [
    EXTERNAL_IP, "8.8.8.8.", "[2606:4700:4700::1111]", "[::ffff:8.8.8.8]", "[fe80::1%25eth0]",
    "134744072", "0x8.8.8.8", "8.8.2056",
])
@pytest.mark.parametrize("action", [get, post])
def test_ip_address_hosts_refused_before_dns_or_socket(monkeypatch, host, action):
    resolve = AsyncMock(side_effect=AssertionError("must not resolve"))
    monkeypatch.setattr(asyncio.BaseEventLoop, "getaddrinfo", resolve)
    result = asyncio.run(action({"url": f"https://{host}/hook"}, {}, {}))
    assert not result["ok"]
    assert "domain name, not IP address" in result["error"]
    resolve.assert_not_called()


@pytest.mark.parametrize("host", ["example.com", "api.innomightlabs.com", "1.example", "8.8.8.8.nip.io", "xn--bcher-kva.example"])
def test_domain_names_are_not_ip_addresses(host):
    assert not is_ip_address(host)


@pytest.mark.parametrize("url", ["https://innomightlabs.com/x", "https://api.innomightlabs.com/automations/hook"])
def test_platform_domains_are_allowed(dns, sockets, url):
    connect = sockets(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok")
    result = asyncio.run(post({"url": url.replace("https", "http"), "json_body": {"a": 1}}, {}, {}))
    assert result == {"ok": True, "status_code": 200, "body_preview": "ok"}
    assert connect.call_args.args[0] == EXTERNAL_IP


def test_domain_resolving_to_a_private_address_is_still_refused(dns, sockets):
    dns["internal.example"] = ["10.0.0.5"]
    connect = sockets()
    result = asyncio.run(get({"url": "http://internal.example"}, {}, {}))
    assert not result["ok"]
    assert "non-public address" in result["error"]
    connect.assert_not_called()


def test_host_header_cannot_be_overridden():
    result = asyncio.run(get({"url": "http://example.com", "headers": {"Host": "api.innomightlabs.com"}}, {}, {}))
    assert not result["ok"]
    assert "Host header" in result["error"]


@pytest.mark.parametrize("target", [f"http://{EXTERNAL_IP}/private", "http://[2606:4700:4700::1111]/private"])
@pytest.mark.parametrize("action", [get, post])
def test_redirect_to_an_ip_address_is_refused_before_second_socket(dns, sockets, target, action):
    connect = sockets(f"HTTP/1.1 307 Temporary Redirect\r\nLocation: {target}\r\nContent-Length: 0\r\n\r\n".encode())
    result = asyncio.run(action({"url": "http://external.example/start"}, {}, {}))
    assert not result["ok"]
    assert "domain name, not IP address" in result["error"]
    assert connect.await_count == 1


def test_allowed_external_request_uses_guarded_transport(dns, sockets):
    connect = sockets(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok")
    result = asyncio.run(get({"url": "http://external.example"}, {}, {}))
    assert result == {"ok": True, "status_code": 200, "body_preview": "ok"}
    connect.assert_awaited_once()
