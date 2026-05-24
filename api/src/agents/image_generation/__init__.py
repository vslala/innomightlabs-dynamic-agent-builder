"""Agent image generation subdomain."""

from .capabilities import ImageCapability, image_capability_registry

__all__ = [
    "ImageCapability",
    "image_capability_registry",
]
