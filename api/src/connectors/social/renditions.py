"""A post's images, fitted once per network (docs/LLD-meta-social-networks.md §4).

Networks that take bytes (LinkedIn, Facebook) get the rendition in memory. Networks that fetch images from a URL
(Threads, Instagram; `limits.public_media`) also get it stored in the media bucket, behind a signed URL on this API
that names only that object and stops working after `social_media_url_ttl_seconds`. A lifecycle rule deletes the
stored copies after two days (`terraform/conversation_media.tf`, tag `retention=social-rendition`).
"""

from __future__ import annotations

import json
import time
from dataclasses import replace

from botocore.exceptions import BotoCoreError, ClientError

from src.artifacts.storage import ArtifactStorage
from src.config import settings
from src.connectors.social.documents import SourceDocument, prepare_document
from src.connectors.social.media import SourceImage, prepare
from src.connectors.social.networks.base import PreparedDocument, PreparedImage, PublishError, PublishErrorKind, SocialNetwork
from src.crypto import decrypt, encrypt

RENDITION_TAG = "retention=social-rendition"
MEDIA_PATH = "/connectors/social/media/"


class Renditions:
    """One post's media as each network takes it. Two accounts on one network share one encode and one URL."""

    def __init__(self, account_id: str, post_id: str, images: tuple[SourceImage, ...],
                 storage: ArtifactStorage | None = None, document: SourceDocument | None = None) -> None:
        self.account_id, self.post_id, self.images, self.document = account_id, post_id, images, document
        self._storage = storage
        self._by_network: dict[str, tuple[PreparedImage, ...]] = {}
        self._documents: dict[str, PreparedDocument] = {}

    def document_for(self, network: SocialNetwork) -> PreparedDocument | None:
        """The post's document checked against this network, or None when the post has none. Planning has already
        skipped networks that don't take documents; this rejects a file whose bytes aren't what its name says."""
        if self.document is None:
            return None
        if network.limits.documents is None:
            raise PublishError(PublishErrorKind.REJECTED, f"{network.display_name} can't post documents")
        if network.key not in self._documents:
            self._documents[network.key] = prepare_document(self.document, network.limits.documents)
        return self._documents[network.key]

    def for_network(self, network: SocialNetwork) -> tuple[PreparedImage, ...]:
        """Raises PublishError when an image can't be read or fitted. Synchronous, so targets running together
        can't both prepare the same network's images."""
        if network.key not in self._by_network:
            prepared = tuple(prepare(image, network.limits) for image in self.images)
            if network.limits.public_media:
                prepared = tuple(replace(image, url=self._store(network.key, index, image))
                                 for index, image in enumerate(prepared))
            self._by_network[network.key] = prepared
        return self._by_network[network.key]

    def _store(self, network: str, index: int, image: PreparedImage) -> str:
        key = f"accounts/{self.account_id}/social/{self.post_id}/{network}/{index}.jpg"
        self._storage = self._storage or ArtifactStorage()
        try:
            self._storage.put_artifact(key=key, body=image.data, content_type=image.mime_type, tagging=RENDITION_TAG)
        except (BotoCoreError, ClientError) as error:
            # Nothing has reached the network yet, so trying again is safe
            raise PublishError(PublishErrorKind.TRANSIENT, "The post's images could not be stored for the network") from error
        return media_url(key)


def media_url(key: str) -> str:
    token = encrypt(json.dumps({"k": key, "exp": int(time.time()) + settings.social_media_url_ttl_seconds}))
    return f"{settings.social_media_base_url}{MEDIA_PATH}{token}.jpg"


def rendition_key(token: str) -> str | None:
    """The object a media URL's token names, or None when it is forged, expired or names anything but a rendition."""
    try:
        claims = json.loads(decrypt(token))
        key, expires = str(claims["k"]), int(claims["exp"])
    except Exception:
        return None
    parts = key.split("/")
    if expires < time.time() or len(parts) != 6 or parts[0] != "accounts" or parts[2] != "social" or ".." in parts:
        return None
    return key
