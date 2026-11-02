"""A post's images, once per network: padded into Instagram's aspect range, and for networks that fetch images
(Threads, Instagram) stored behind a sealed, expiring URL on the API that names only that rendition."""

from __future__ import annotations

import io
import json
import time

import boto3
import pytest
from PIL import Image

from src.config import settings
from src.connectors.social.media import SourceImage, prepare
from src.connectors.social.networks.base import NetworkLimits, PublishError, PublishErrorKind
from src.connectors.social.networks.facebook_pages import FacebookPagesNetwork
from src.connectors.social.networks.instagram import InstagramNetwork
from src.connectors.social.networks.threads import ThreadsNetwork
from src.connectors.social.renditions import Renditions, media_url, rendition_key
from src.crypto import encrypt

BUCKET = "innomightlabs-conversations-renditions"
KEY = "accounts/acct-1/social/post-1/instagram/0.jpg"


def png(size: tuple[int, int]) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, "red").save(out, "PNG")
    return out.getvalue()


def size_of(data: bytes) -> tuple[int, int]:
    with Image.open(io.BytesIO(data)) as image:
        return image.size


@pytest.fixture
def media(mock_aws_context, monkeypatch):
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket=BUCKET)
    monkeypatch.setattr("src.artifacts.storage.settings.conversation_media_bucket", BUCKET)
    monkeypatch.setattr(settings, "social_media_base_url", "https://api.example")
    return s3


def token_of(url: str) -> str:
    return url.removeprefix("https://api.example/connectors/social/media/").removesuffix(".jpg")


@pytest.mark.parametrize(("source", "padded"), [
    ((900, 1600), (1152, 1440)),   # a 9:16 phone screenshot, scaled to 1440 high, gets bars at the sides: 4:5
    ((2000, 500), (1440, 754)),    # a 4:1 panorama gets bars above and below: 1.91:1
    ((1000, 1000), (1000, 1000)),  # square is within range
], ids=["tall", "wide", "square"])
def test_an_image_outside_instagrams_aspect_range_is_padded_not_cropped(source, padded):
    prepared = prepare(SourceImage(png(source)), InstagramNetwork.limits)
    assert size_of(prepared.data) == padded


def test_other_networks_keep_the_images_shape():
    assert size_of(prepare(SourceImage(png((900, 1600))), NetworkLimits(max_text=1, max_images=1)).data) == (900, 1600)


def test_each_network_gets_its_images_once_and_only_fetching_networks_get_a_stored_url(media):
    renditions = Renditions("acct-1", "post-1", (SourceImage(png((800, 800)), alt_text="Red"), SourceImage(png((400, 400)))))
    instagram, threads, facebook = InstagramNetwork(), ThreadsNetwork(), FacebookPagesNetwork()

    first = renditions.for_network(instagram)
    assert renditions.for_network(instagram) is first, "a second Instagram account shares the encode and the URL"
    assert [image.alt_text for image in first] == ["Red", ""]
    assert rendition_key(token_of(first[0].url or "")) == KEY
    stored = media.get_object(Bucket=BUCKET, Key=KEY)
    assert stored["ContentType"] == "image/jpeg" and stored["Body"].read() == first[0].data
    assert media.get_object_tagging(Bucket=BUCKET, Key=KEY)["TagSet"] == [{"Key": "retention", "Value": "social-rendition"}]

    assert rendition_key(token_of(renditions.for_network(threads)[1].url or "")) == "accounts/acct-1/social/post-1/threads/1.jpg"
    assert all(image.url is None for image in renditions.for_network(facebook)), "Facebook takes the bytes"
    assert len(media.list_objects_v2(Bucket=BUCKET)["Contents"]) == 4


def test_a_rendition_that_cannot_be_stored_is_safe_to_retry(mock_aws_context, monkeypatch):
    monkeypatch.setattr("src.artifacts.storage.settings.conversation_media_bucket", "no-such-bucket")
    with pytest.raises(PublishError) as raised:
        Renditions("acct-1", "post-1", (SourceImage(png((400, 400))),)).for_network(ThreadsNetwork())
    assert raised.value.kind == PublishErrorKind.TRANSIENT


def test_the_media_route_serves_a_rendition_to_anyone_with_its_url(test_client, media):
    media.put_object(Bucket=BUCKET, Key=KEY, Body=b"\xff\xd8jpeg")
    path = media_url(KEY).removeprefix("https://api.example")

    response = test_client.get(path)
    assert response.status_code == 200 and response.content == b"\xff\xd8jpeg"
    assert response.headers["content-type"] == "image/jpeg"
    assert test_client.head(path).status_code == 200, "Meta's fetcher may check the URL first"


@pytest.mark.parametrize("token", [
    encrypt(json.dumps({"k": KEY, "exp": int(time.time()) - 1})),
    encrypt(json.dumps({"k": "accounts/acct-1/members/user-1/artifacts/secret.pdf", "exp": int(time.time()) + 60})),
    encrypt(json.dumps({"k": "accounts/acct-1/social/../../x/0.jpg", "exp": int(time.time()) + 60})),
    "not-a-token",
], ids=["expired", "not a rendition", "climbs out", "forged"])
def test_the_media_route_refuses_anything_but_a_live_rendition_token(test_client, media, token):
    media.put_object(Bucket=BUCKET, Key=KEY, Body=b"\xff\xd8jpeg")
    assert test_client.get(f"/connectors/social/media/{token}.jpg").status_code == 404


def test_a_rendition_that_is_gone_is_not_found(test_client, media):
    assert test_client.get(media_url(KEY).removeprefix("https://api.example")).status_code == 404
