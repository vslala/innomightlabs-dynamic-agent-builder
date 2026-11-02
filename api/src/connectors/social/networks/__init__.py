from __future__ import annotations

from src.connectors.social.networks.base import SocialNetwork
from src.connectors.social.networks.facebook_pages import FacebookPagesNetwork
from src.connectors.social.networks.instagram import InstagramNetwork
from src.connectors.social.networks.linkedin import LinkedInNetwork
from src.connectors.social.networks.linkedin_pages import LinkedInPagesNetwork
from src.connectors.social.networks.threads import ThreadsNetwork

#: Adding a network: write networks/<key>.py and add it here. Nothing else changes.
NETWORKS: tuple[SocialNetwork, ...] = (
    LinkedInNetwork(), LinkedInPagesNetwork(), FacebookPagesNetwork(), InstagramNetwork(), ThreadsNetwork(),
)


def network_for(key: str) -> SocialNetwork:
    for network in NETWORKS:
        if network.key == key:
            return network
    raise ValueError(f"Unknown social network: {key}")


def enabled_networks() -> list[SocialNetwork]:
    """Networks whose OAuth app is registered: an unset client id hides the network everywhere."""
    return [network for network in NETWORKS if network.configured()]


def networks_of_app(app: str) -> list[SocialNetwork]:
    """The networks one OAuth app serves (one Facebook sign-in serves Facebook Pages and Instagram)."""
    return [network for network in NETWORKS if network.app == app]
