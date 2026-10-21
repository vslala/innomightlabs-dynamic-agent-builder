from __future__ import annotations

from src.connectors.social.networks.base import SocialNetwork
from src.connectors.social.networks.linkedin import LinkedInNetwork

#: Adding a network: write networks/<key>.py and add it here. Nothing else changes.
NETWORKS: tuple[SocialNetwork, ...] = (LinkedInNetwork(),)


def network_for(key: str) -> SocialNetwork:
    for network in NETWORKS:
        if network.key == key:
            return network
    raise ValueError(f"Unknown social network: {key}")


def enabled_networks() -> list[SocialNetwork]:
    """Networks whose OAuth app is registered: an unset client id hides the network everywhere."""
    return [network for network in NETWORKS if network.configured()]
