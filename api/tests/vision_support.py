"""Shared setup for the image-input tests: an agent, the account's settings and a bucket to store images in."""

from __future__ import annotations

import io

import boto3
from PIL import Image

from src.agents.models import Agent
from src.config import settings
from src.settings.models import ProviderSettings
from src.settings.repository import ProviderSettingsRepository
from src.vision.models import VisionSettings
from src.vision.repository import VisionSettingsRepository

ACCOUNT_ID = "account-1"


def make_agent(architecture: str = "krishna-memgpt", account_id: str = ACCOUNT_ID) -> Agent:
    return Agent(
        agent_name="Vision Agent",
        agent_architecture=architecture,
        agent_provider="Anthropic",
        agent_model="claude-sonnet-4",
        agent_persona="Helpful.",
        account_id=account_id,
        owner_id="owner-1",
        created_by="owner-1",
    )


def enable_vision(account_id: str = ACCOUNT_ID, provider: str = "Anthropic", model: str = "claude-vision") -> None:
    ProviderSettingsRepository().save(
        ProviderSettings(account_id=account_id, provider_name=provider, encrypted_credentials="encrypted")
    )
    VisionSettingsRepository().save(
        VisionSettings(account_id=account_id, enabled=True, provider_name=provider, model_name=model)
    )


def create_media_bucket() -> None:
    boto3.client("s3", region_name=settings.conversation_media_region).create_bucket(
        Bucket=settings.conversation_media_bucket
    )


def png_bytes(size: tuple[int, int] = (40, 30)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, "green").save(out, "PNG")
    return out.getvalue()


def png_upload(name: str = "shot.png") -> dict:
    """A multipart `file` field, as a browser sends a pasted image."""
    return {"file": (name, png_bytes(), "image/png")}


def create_memgpt_agent(test_client, auth_headers: dict) -> str:
    """An agent whose architecture can read images, owned by the test user."""
    from tests.mock_data import AGENT_CREATE_REQUEST

    response = test_client.post(
        "/agents",
        json={**AGENT_CREATE_REQUEST, "agent_architecture": "krishna-memgpt"},
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["agent_id"]


def enable_vision_for_test_user() -> None:
    """Image reading on in the test user's personal account, which owns the agents the route tests create."""
    from tests.mock_data import account_for

    enable_vision(account_id=account_for(), provider="Bedrock", model="claude-3-haiku")
