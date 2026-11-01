"""REST Template calls hosts by name only, layered over the shared public-internet guard.

`outbound.async_client` already refuses anything off the public internet. On top of that a request (and each redirect
hop) must name its host: a bare IP address reaches a server directly, past the name its owner publishes. Platform
domains are allowed, so an automation can call an InnomightLabs webhook or another automation.
"""

from __future__ import annotations

import ipaddress
import socket

import httpx

from src.common.outbound import BlockedDestination


def is_ip_address(host: str) -> bool:
    """True for any form the resolver treats as an address, including the legacy ones (`134744072`, `0x8.8.8.8`)."""
    name = host.strip("[]").rstrip(".").split("%", 1)[0]
    try:
        ipaddress.ip_address(name)
        return True
    except ValueError:
        pass
    try:
        socket.inet_aton(name)
        return True
    except OSError:
        return False


async def refuse_unnamed_destinations(request: httpx.Request) -> None:
    """A request hook, so it runs for the first request and every redirect hop before any socket opens."""
    try:
        if is_ip_address(request.url.host):
            raise BlockedDestination("REST Template calls hosts by domain name, not IP address")
        # The Host header must name the host the URL does, so the call is the one the URL shows.
        expected = httpx.Request(request.method, request.url).headers["host"]
        if request.headers.get("host", "").lower() != expected.lower():
            raise BlockedDestination("REST Template does not allow overriding the Host header")
    except BlockedDestination as exc:
        raise httpx.ConnectError(str(exc), request=request) from exc
