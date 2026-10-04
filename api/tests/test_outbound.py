"""User-supplied URLs may only reach the public internet."""

from __future__ import annotations

import asyncio
import socket

import httpx
import pytest

from src.common import outbound


def _infos(*addresses: str) -> list[tuple]:
    return [(socket.AF_INET6 if ":" in a else socket.AF_INET, socket.SOCK_STREAM, 6, "", (a, 443)) for a in addresses]


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.1.2.3",
        "172.16.0.1",
        "192.168.4.27",
        "169.254.169.254",  # cloud metadata
        "100.64.0.1",  # CGNAT
        "0.0.0.0",
        "::1",
        "fd00::1",
        "fe80::1",
        "::ffff:127.0.0.1",
    ],
)
def test_non_public_addresses_are_refused(address: str):
    with pytest.raises(outbound.BlockedDestination):
        outbound.public_addresses("example.com", _infos(address))


def test_a_name_with_any_non_public_address_is_refused():
    with pytest.raises(outbound.BlockedDestination):
        outbound.public_addresses("example.com", _infos("93.184.215.14", "10.0.0.5"))


def test_public_addresses_pass():
    assert outbound.public_addresses("example.com", _infos("93.184.215.14")) == ["93.184.215.14"]


@pytest.mark.parametrize("host", ["localhost", "api.railway.internal", "printer.local", "app.localhost"])
def test_internal_names_are_refused_before_resolving(host: str):
    with pytest.raises(outbound.BlockedDestination):
        outbound.refuse_internal_name(host)


def test_the_async_client_refuses_to_connect_to_loopback():
    async def fetch():
        async with outbound.async_client(timeout=2) as client:
            await client.get("http://127.0.0.1:9/")

    with pytest.raises(httpx.ConnectError, match="non-public"):
        asyncio.run(fetch())


def test_the_sync_client_refuses_to_connect_to_link_local():
    with outbound.sync_client(timeout=2) as client:
        with pytest.raises(httpx.ConnectError, match="non-public"):
            client.get("http://169.254.169.254/latest/meta-data/")


def test_redirects_are_capped():
    assert outbound.async_client().max_redirects == outbound.MAX_REDIRECTS


def test_a_crawl_is_bounded(test_client, auth_headers):
    from src.knowledge.models import KnowledgeBase
    from src.knowledge.repository import KnowledgeBaseRepository
    from tests.mock_data import TEST_USER_EMAIL

    kb = KnowledgeBaseRepository().save(KnowledgeBase(name="KB", description="", created_by=TEST_USER_EMAIL))
    response = test_client.post(
        f"/knowledge-bases/{kb.kb_id}/crawl-jobs?auto_start=false",
        json={"source_type": "sitemap", "source_url": "https://example.com/sitemap.xml", "max_pages": 100000},
        headers=auth_headers,
    )

    assert response.status_code == 422
