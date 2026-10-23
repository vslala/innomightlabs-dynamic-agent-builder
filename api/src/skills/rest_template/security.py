"""REST-only platform denylist, layered over the shared public-internet guard."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import unquote, urlsplit

import httpx

from src.common.outbound import BlockedDestination
from src.config.settings import settings

PLATFORM_DOMAIN = "innomightlabs.com"
DEFAULT_PROTECTED_HOSTS = (PLATFORM_DOMAIN, f"www.{PLATFORM_DOMAIN}", f"api.{PLATFORM_DOMAIN}", f"cdn.{PLATFORM_DOMAIN}")
IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address


def _host(value: str) -> str:
    return unquote(value).strip("[]").rstrip(".").lower()


def _ip(value: str) -> IPAddress:
    address = ipaddress.ip_address(value.split("%", 1)[0])
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        return address.ipv4_mapped
    return address


def _network(value: str) -> ipaddress.IPv4Network | ipaddress.IPv6Network:
    network = ipaddress.ip_network(value.strip(), strict=False)
    if isinstance(network, ipaddress.IPv6Network) and network.prefixlen >= 96:
        if mapped := network.network_address.ipv4_mapped:
            return ipaddress.IPv4Network((mapped, network.prefixlen - 96))
    return network


class PlatformDestinationGuard:
    def __init__(self) -> None:
        self.hosts = set(DEFAULT_PROTECTED_HOSTS)
        for url in (settings.api_base_url, settings.frontend_url, settings.widget_cdn_url):
            if host := urlsplit(url).hostname:
                self.hosts.add(_host(host))
        try:
            self.networks = [
                _network(value)
                for value in settings.rest_template_blocked_ip_ranges.split(",")
                if value.strip()
            ]
        except ValueError:
            raise ValueError("Invalid REST_TEMPLATE_BLOCKED_IP_RANGES configuration") from None

    def refuse_host(self, host: str) -> None:
        name = _host(host)
        if name in self.hosts or name.endswith(f".{PLATFORM_DOMAIN}"):
            raise BlockedDestination("REST Template cannot call InnomightLabs platform destinations")

    async def check_request(self, request: httpx.Request) -> None:
        try:
            self.refuse_host(request.url.host)
            # A public CDN IP with an attacker-supplied Host can route to the platform.
            expected = httpx.Request(request.method, request.url).headers["host"]
            if request.headers.get("host", "").lower() != expected.lower():
                raise BlockedDestination("REST Template does not allow overriding the Host header")
        except BlockedDestination as exc:
            raise httpx.ConnectError(str(exc), request=request) from exc

    async def check_addresses(self, host: str, addresses: list[str]) -> None:
        self.refuse_host(host)
        protected: set[IPAddress] = set()
        loop = asyncio.get_running_loop()
        # Resolve together under one deadline; never cache an incomplete denylist.
        names = [
            name for name in sorted(self.hosts)
            if name != "localhost" and not name.endswith((".localhost", ".internal", ".local"))
        ]
        try:
            answers = await asyncio.wait_for(
                asyncio.gather(*(loop.getaddrinfo(name, 443, type=socket.SOCK_STREAM) for name in names)),
                timeout=5,
            )
            for infos in answers:
                if not infos:
                    raise BlockedDestination("Could not resolve protected platform destinations; refusing REST request")
                protected.update(_ip(str(info[4][0])) for info in infos)
        except (OSError, asyncio.TimeoutError) as exc:
            raise BlockedDestination("Could not resolve protected platform destinations; refusing REST request") from exc
        for address in map(_ip, addresses):
            if address in protected or any(address in network for network in self.networks):
                raise BlockedDestination("REST Template cannot call InnomightLabs platform IP addresses")
