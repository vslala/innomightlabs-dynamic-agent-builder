"""HTTP clients for URLs that users, agents or skill configs supply.

Such a URL can point anywhere, including at the services next to us: Railway's
private network, localhost, the cloud metadata endpoint. These clients refuse
every destination that is not on the public internet.

The check runs where the socket is opened, not on the URL. The client resolves
the host itself, refuses it if any of its addresses is not public, and connects
to the address it checked, so a DNS answer that changes between check and
connect (rebinding) cannot slip through. Every redirect hop opens its own
connection, so it is checked the same way.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from typing import Any, Iterable

import httpcore
import httpx

MAX_REDIRECTS = 5
_BLOCKED_HOST_SUFFIXES = (".internal", ".local", ".localhost")


class BlockedDestination(httpcore.ConnectError):
    """httpx reports this as an `httpx.ConnectError`, so callers handle it like any refused connection."""


def async_client(**kwargs: Any) -> httpx.AsyncClient:
    return httpx.AsyncClient(**_client_options(kwargs), transport=_AsyncPublicTransport())


def sync_client(**kwargs: Any) -> httpx.Client:
    return httpx.Client(**_client_options(kwargs), transport=_PublicTransport())


def _client_options(kwargs: dict[str, Any]) -> dict[str, Any]:
    # trust_env would route requests through an environment proxy, which then makes
    # the connection we are trying to check.
    return {"follow_redirects": True, **kwargs, "max_redirects": MAX_REDIRECTS, "trust_env": False}


def refuse_internal_name(host: str) -> None:
    name = host.strip("[]").rstrip(".").lower()
    if name == "localhost" or name.endswith(_BLOCKED_HOST_SUFFIXES):
        raise BlockedDestination(f"Refusing to connect to internal host {host}")


def public_addresses(host: str, infos: Iterable[tuple[Any, ...]]) -> list[str]:
    """The resolved addresses for `host`, or BlockedDestination when any of them is not public."""
    addresses = list(dict.fromkeys(str(info[4][0]) for info in infos))
    if not addresses:
        raise BlockedDestination(f"Could not resolve {host}")
    for address in addresses:
        if not _is_public(ipaddress.ip_address(address.split("%", 1)[0])):
            raise BlockedDestination(f"Refusing to connect to {host}: it resolves to a non-public address")
    return addresses


def _is_public(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    # is_global is False for private, loopback, link-local, CGNAT (100.64/10) and reserved ranges.
    return ip.is_global and not ip.is_multicast


class _AsyncPublicBackend(httpcore.AsyncNetworkBackend):
    def __init__(self, inner: httpcore.AsyncNetworkBackend):
        self._inner = inner

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[Any] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        refuse_internal_name(host)
        try:
            infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise httpcore.ConnectError(f"Could not resolve {host}") from exc
        address = public_addresses(host, infos)[0]
        return await self._inner.connect_tcp(address, port, timeout, local_address, socket_options)

    async def connect_unix_socket(self, path: str, timeout: float | None = None, socket_options: Any = None) -> Any:
        raise BlockedDestination("Unix sockets are not allowed")

    async def sleep(self, seconds: float) -> None:
        await self._inner.sleep(seconds)


class _PublicBackend(httpcore.NetworkBackend):
    def __init__(self, inner: httpcore.NetworkBackend):
        self._inner = inner

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[Any] | None = None,
    ) -> httpcore.NetworkStream:
        refuse_internal_name(host)
        try:
            infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise httpcore.ConnectError(f"Could not resolve {host}") from exc
        address = public_addresses(host, infos)[0]
        return self._inner.connect_tcp(address, port, timeout, local_address, socket_options)

    def connect_unix_socket(self, path: str, timeout: float | None = None, socket_options: Any = None) -> Any:
        raise BlockedDestination("Unix sockets are not allowed")

    def sleep(self, seconds: float) -> None:
        self._inner.sleep(seconds)


# httpx does not take a network backend, so the transports swap it into their
# httpcore pool. TLS still verifies against the URL's host name: httpcore passes
# that as the SNI/server name, whatever address the socket is connected to.
class _AsyncPublicTransport(httpx.AsyncHTTPTransport):
    def __init__(self) -> None:
        super().__init__(trust_env=False)
        self._pool._network_backend = _AsyncPublicBackend(self._pool._network_backend)


class _PublicTransport(httpx.HTTPTransport):
    def __init__(self) -> None:
        super().__init__(trust_env=False)
        self._pool._network_backend = _PublicBackend(self._pool._network_backend)
