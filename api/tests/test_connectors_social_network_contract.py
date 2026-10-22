"""What every social network must be, so a new one plugs in without touching anything else (docs/LLD-social-cross-posting.md,
"Adding a network"). Each strategy in `NETWORKS` runs the same checks."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from src.config import settings
from src.config.settings import SocialAppCredentials
from src.connectors.social.networks import NETWORKS, enabled_networks, network_for

CONNECTOR_ASSETS = Path(__file__).resolve().parents[2] / "spa" / "src" / "assets" / "connectors"


@pytest.fixture
def registered(monkeypatch):
    """Every network's OAuth app registered."""
    monkeypatch.setattr(settings, "social_apps", {n.app: SocialAppCredentials("id", "secret") for n in NETWORKS})
    monkeypatch.setattr(settings, "social_oauth_redirect_uri", "https://api.example/connectors/social/oauth/callback")


def test_networks_have_distinct_keys():
    assert len({network.key for network in NETWORKS}) == len(NETWORKS)


@pytest.mark.parametrize("network", NETWORKS, ids=lambda network: network.key)
def test_a_network_describes_itself(network):
    assert network_for(network.key) is network
    assert network.display_name and network.description and network.app
    assert any(CONNECTOR_ASSETS.glob(f"{network.icon}.*")), f"no brand mark for {network.icon!r} in spa/src/assets/connectors"
    assert network.limits.max_text > 0
    assert callable(network.publish)


@pytest.mark.parametrize("network", NETWORKS, ids=lambda network: network.key)
def test_a_network_is_hidden_until_its_oauth_app_is_registered(network, monkeypatch, registered):
    assert network in enabled_networks()

    monkeypatch.setattr(settings, "social_apps", {})

    assert network not in enabled_networks()


@pytest.mark.parametrize("network", NETWORKS, ids=lambda network: network.key)
def test_the_sign_in_link_carries_our_state_and_the_shared_callback(network, registered):
    query = parse_qs(urlparse(network.authorize_url("sealed-state", "challenge")).query)

    assert query["state"] == ["sealed-state"]
    assert query["client_id"] == ["id"]
    assert query["redirect_uri"] == ["https://api.example/connectors/social/oauth/callback"]


def test_an_unknown_network_is_a_value_error():
    with pytest.raises(ValueError, match="Unknown social network"):
        network_for("myspace")
