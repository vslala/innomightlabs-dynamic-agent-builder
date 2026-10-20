"""An HTTP client that only connects to the public internet.

This is the async half of `api/src/common/outbound.py`; the runner deploys on its own, so it carries a copy. Keep the
two in step. The check runs where the socket is opened: the client resolves the host itself, refuses it if any address
is not public, and connects to the address it checked, so a DNS answer that changes between check and connect
(rebinding) cannot slip through.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from typing import Any, Iterable

import httpcore
import httpx

_BLOCKED_HOST_SUFFIXES = (".internal", ".local", ".localhost")


class BlockedDestination(httpcore.ConnectError):
    """httpx reports this as an `httpx.ConnectError`."""


def async_client(**kwargs: Any) -> httpx.AsyncClient:
    # trust_env would route requests through an environment proxy, which then makes the connection we are checking.
    return httpx.AsyncClient(**kwargs, trust_env=False, transport=_AsyncPublicTransport())


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


# httpx does not take a network backend, so the transport swaps it into its httpcore pool. TLS still verifies against
# the URL's host name: httpcore passes that as the SNI/server name, whatever address the socket is connected to.
class _AsyncPublicTransport(httpx.AsyncHTTPTransport):
    def __init__(self) -> None:
        super().__init__(trust_env=False)
        self._pool._network_backend = _AsyncPublicBackend(self._pool._network_backend)
