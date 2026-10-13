"""Whether people talking to an agent may attach images: one rule every surface asks.

The UI, the upload routes, send-message and the `read_image` tool all ask `image_input_availability`, so
they cannot disagree. The agent's own account decides: for the dashboard that is the account the member is
working in; for the widget and the public API it is the agent owner's account, which pays for the turn.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel

from src.agents.models import Agent
from src.settings.repository import ProviderSettingsRepository, get_provider_settings_repository
from src.vision.errors import ImageInputError
from src.vision.models import ImageInputLimits
from src.vision.repository import VisionSettingsRepository, get_vision_settings_repository

#: Architectures that offer tools, and so can offer `read_image`. `krishna-mini` calls the model with no tools.
IMAGE_READING_ARCHITECTURES = frozenset({"krishna-memgpt"})


class ImageInputUnavailable(StrEnum):
    DISABLED = "image_input_disabled"  # the account hasn't turned it on
    NOT_CONFIGURED = "image_input_not_configured"  # on, but no model chosen or its provider has no credentials
    AGENT_UNSUPPORTED = "image_input_agent_unsupported"  # this architecture offers no tools


UNAVAILABLE_MESSAGES = {
    ImageInputUnavailable.DISABLED: "Image input is turned off for this account.",
    ImageInputUnavailable.NOT_CONFIGURED: (
        "Image reading isn't set up yet. An admin can choose a vision model in Settings."
    ),
    ImageInputUnavailable.AGENT_UNSUPPORTED: "This agent can't read images.",
}


class ImageInputAvailability(BaseModel):
    available: bool
    reason: ImageInputUnavailable | None = None
    message: str | None = None
    limits: ImageInputLimits


def image_input_availability(
    agent: Agent,
    *,
    vision_settings_repository: VisionSettingsRepository | None = None,
    provider_settings_repository: ProviderSettingsRepository | None = None,
) -> ImageInputAvailability:
    reason = _unavailable_reason(
        agent,
        vision_settings_repository or get_vision_settings_repository(),
        provider_settings_repository or get_provider_settings_repository(),
    )
    return ImageInputAvailability(
        available=reason is None,
        reason=reason,
        message=UNAVAILABLE_MESSAGES[reason] if reason else None,
        limits=ImageInputLimits.from_settings(),
    )


def require_image_input(agent: Agent) -> ImageInputAvailability:
    """The availability, or a 403 saying why images can't be used."""
    availability = image_input_availability(agent)
    if availability.reason:
        raise ImageInputError(availability.reason.value, UNAVAILABLE_MESSAGES[availability.reason], status_code=403)
    return availability


def _unavailable_reason(
    agent: Agent,
    vision_settings_repository: VisionSettingsRepository,
    provider_settings_repository: ProviderSettingsRepository,
) -> ImageInputUnavailable | None:
    if agent.agent_architecture not in IMAGE_READING_ARCHITECTURES:
        return ImageInputUnavailable.AGENT_UNSUPPORTED
    vision_settings = vision_settings_repository.find_in_account(agent.account_id)
    if not vision_settings or not vision_settings.enabled:
        return ImageInputUnavailable.DISABLED
    if not vision_settings.is_configured or not provider_settings_repository.find_by_provider(
        agent.account_id, str(vision_settings.provider_name)
    ):
        return ImageInputUnavailable.NOT_CONFIGURED
    return None
