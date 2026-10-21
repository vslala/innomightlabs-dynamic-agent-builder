"""Images in social posts: fitted to each network, uploaded to LinkedIn as one image or several, found by id in the
conversation, and checked against the network's limits."""

from __future__ import annotations

import io
import json
from datetime import datetime, timedelta, timezone

import boto3
import httpx
import pytest
from PIL import Image

from src.config import settings
from src.config.settings import SocialAppCredentials
from src.connectors.social import networks
from src.connectors.social.media import SourceImage, prepare
from src.connectors.social.models import SocialAccount
from src.connectors.social.networks.base import NetworkLimits, PublishError, PublishErrorKind
from src.connectors.social.networks.linkedin import LinkedInNetwork
from src.connectors.social.planning import plan_targets
from src.connectors.social.repository import SocialAccountRepository
from src.crypto import encrypt
from src.messages.models import Message, MessageImage
from src.messages.repositories.factory import get_message_repository
from src.skills.social_media import actions
from src.vision.models import ImageUpload
from src.vision.repository import ImageUploadRepository
from tests.mock_data import TEST_USER_EMAIL, account_for, user_id_for

ACCOUNT_ID = account_for(TEST_USER_EMAIL)
OWNER_ID = user_id_for(TEST_USER_EMAIL)
BUCKET = "innomightlabs-conversations-meta"
CONVERSATION_ID = "conversation-1"


def png(size: tuple[int, int] = (200, 100), color=(255, 0, 0, 255)) -> bytes:
    out = io.BytesIO()
    Image.new("RGBA", size, color).save(out, "PNG")
    return out.getvalue()


class FakeLinkedIn:
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.uploads: list[bytes] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path == "/rest/images":
            number = len(self.requests)
            return httpx.Response(200, json={"value": {"uploadUrl": f"https://upload.linkedin.test/u/{number}", "image": f"urn:li:image:{number}"}})
        if request.method == "PUT":
            self.uploads.append(request.content)
            return httpx.Response(201)
        return httpx.Response(201, headers={"x-restli-id": "urn:li:share:1"})

    def post_body(self) -> dict:
        return json.loads(next(r for r in self.requests if r.url.path == "/rest/posts").content)


@pytest.fixture
def linkedin(monkeypatch) -> FakeLinkedIn:
    fake = FakeLinkedIn()
    monkeypatch.setattr(networks, "NETWORKS", (LinkedInNetwork(transport=httpx.MockTransport(fake)),))
    monkeypatch.setattr(settings, "social_apps", {"linked_in": SocialAppCredentials("id", "secret")})
    return fake


@pytest.fixture
def media(dynamodb_table, monkeypatch):
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
    monkeypatch.setattr("src.artifacts.storage.settings.conversation_media_bucket", BUCKET)
    return boto3.client("s3", region_name="us-east-1")


def connect() -> SocialAccount:
    return SocialAccountRepository().connect(SocialAccount(
        account_id=ACCOUNT_ID, network="linkedin", external_id="member-1", handle="Ada", display_name="Ada",
        encrypted_credentials=encrypt(json.dumps({"access_token": "li-token", "person_urn": "urn:li:person:member-1"})),
        token_expires_at=datetime.now(timezone.utc) + timedelta(days=30), connected_by=OWNER_ID,
    ))


def context() -> dict:
    return {"account_id": ACCOUNT_ID, "owner_id": OWNER_ID, "owner_email": TEST_USER_EMAIL, "conversation_id": CONVERSATION_ID}


def generated_image(s3, key: str, data: bytes) -> str:
    """An image the agent generated in the conversation: bytes in S3, metadata on an assistant message."""
    s3.put_object(Bucket=BUCKET, Key=key, Body=data)
    image = MessageImage(s3_key=key, filename="generated.png", mime_type="image/png", size_bytes=len(data))
    get_message_repository().save(Message(conversation_id=CONVERSATION_ID, created_by=TEST_USER_EMAIL,
                                          role="assistant", content="Generated image", images=[image]))
    return image.image_id


def test_an_image_is_fitted_to_the_network_and_flattened_onto_white():
    limits = NetworkLimits(max_text=10, max_images=1, max_image_side=100)
    prepared = prepare(SourceImage(png((400, 200), (0, 0, 0, 0)), "A logo"), limits)
    image = Image.open(io.BytesIO(prepared.data))
    assert prepared.mime_type == "image/jpeg" and prepared.alt_text == "A logo"
    assert max(image.size) == 100
    assert image.getpixel((5, 5)) == (255, 255, 255)


def test_an_unreadable_or_oversized_image_is_rejected():
    limits = NetworkLimits(max_text=10, max_images=1)
    with pytest.raises(PublishError) as unreadable:
        prepare(SourceImage(b"not an image"), limits)
    assert unreadable.value.kind == PublishErrorKind.REJECTED
    with pytest.raises(PublishError, match="too large"):
        prepare(SourceImage(png((300, 300))), NetworkLimits(max_text=10, max_images=1, max_image_bytes=10))


def test_too_many_images_and_text_only_networks_are_skipped_with_a_reason(dynamodb_table, linkedin):
    account = connect()
    [too_many] = plan_targets([account], "hello", image_count=21)
    assert (too_many.reason, too_many.detail) == ("too_many_images", "21/20 images")
    assert plan_targets([account], "hello", image_count=20)[0].ok


@pytest.mark.asyncio
async def test_one_image_is_uploaded_and_posted_as_media(media, linkedin):
    connect()
    image_id = generated_image(media, "agents/a/c/one.png", png())
    result = await actions.publish({"text": "With a picture", "images": [image_id], "alt_texts": ["A red box"]}, {}, context())
    assert result["status"] == "published"
    assert len(linkedin.uploads) == 1
    assert Image.open(io.BytesIO(linkedin.uploads[0])).format == "JPEG"
    assert linkedin.post_body()["content"] == {"media": {"id": "urn:li:image:1", "altText": "A red box"}}


@pytest.mark.asyncio
async def test_several_images_are_posted_as_a_multi_image_post_in_order(media, linkedin):
    connect()
    ids = [generated_image(media, f"agents/a/c/{n}.png", png((100 + n, 100))) for n in range(3)]
    result = await actions.publish({"text": "Three", "images": ids}, {}, context())
    assert result["status"] == "published" and len(linkedin.uploads) == 3
    images = linkedin.post_body()["content"]["multiImage"]["images"]
    assert [image["id"] for image in images] == ["urn:li:image:1", "urn:li:image:3", "urn:li:image:5"]


@pytest.mark.asyncio
async def test_an_uploaded_image_in_the_conversation_can_be_posted(media, linkedin):
    connect()
    media.put_object(Bucket=BUCKET, Key="agents/a/c/uploads/u1.png", Body=png())
    ImageUploadRepository().save(ImageUpload(
        image_id="u1", conversation_id=CONVERSATION_ID, agent_id="a", account_id=ACCOUNT_ID, uploaded_by=OWNER_ID,
        s3_key="agents/a/c/uploads/u1.png", filename="u1.png", mime_type="image/png", size_bytes=10, width=200, height=100,
    ))
    result = await actions.publish({"text": "Mine", "images": ["u1"]}, {}, context())
    assert result["status"] == "published"


@pytest.mark.asyncio
async def test_an_image_from_another_conversation_is_not_found(media, linkedin):
    connect()
    other = {**context(), "conversation_id": "someone-elses"}
    image_id = generated_image(media, "agents/a/c/mine.png", png())
    with pytest.raises(ValueError, match="No image"):
        await actions.publish({"text": "Stolen", "images": [image_id]}, {}, other)
    assert not linkedin.requests


@pytest.mark.asyncio
async def test_check_counts_the_images_against_the_limit(media, linkedin):
    connect()
    image_id = generated_image(media, "agents/a/c/x.png", png())
    result = await actions.check({"text": "ok", "images": [image_id]}, {}, context())
    assert result["targets"][0]["can_post"] is True
    accounts = await actions.accounts({}, {}, context())
    assert accounts["accounts"][0]["max_images"] == 20
