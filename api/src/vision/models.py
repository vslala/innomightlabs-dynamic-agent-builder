"""The image-input feature's own records: the account's setting, the upload ledger and the limits clients see."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel, Field, model_validator

from src.config import settings
from src.messages.models import ImageAttachment

#: Formats every provider accepts. Fixed rather than configured: a format one provider refuses would fail only at read time.
ALLOWED_FORMATS = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp", "GIF": "image/gif"}


class ImageInputLimits(BaseModel):
    """What an image may be. Sent to clients so the browser checks against the same numbers as the server."""

    max_bytes: int
    max_images_per_message: int
    max_edge_px: int
    max_pixels: int
    formats: list[str] = Field(default_factory=lambda: list(ALLOWED_FORMATS.values()))

    @classmethod
    def from_settings(cls) -> "ImageInputLimits":
        return cls(
            max_bytes=settings.vision_max_image_bytes,
            max_images_per_message=settings.vision_max_images_per_message,
            max_edge_px=settings.vision_max_edge_px,
            max_pixels=settings.vision_max_pixels,
        )


class ImageRef(BaseModel):
    """An image in the conversation and where it sits, so a description can be saved back onto its message."""

    message_sk: str
    index: int
    attachment: ImageAttachment


class VisionSettings(BaseModel):
    """The account's image-input feature: whether it is on, and which model reads images. Admins set it."""

    account_id: str
    #: The user_id of whoever last changed it, for audit
    updated_by: str | None = None
    enabled: bool = False
    provider_name: str | None = None
    model_name: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime | None = None

    @model_validator(mode="after")
    def validate_model_when_enabled(self) -> "VisionSettings":
        if self.enabled and (not self.provider_name or not self.model_name):
            raise ValueError("provider_name and model_name are required when image reading is enabled")
        return self

    @property
    def is_configured(self) -> bool:
        return self.enabled and bool(self.provider_name and self.model_name)

    @property
    def pk(self) -> str:
        return f"Account#{self.account_id}"

    @property
    def sk(self) -> str:
        return "VisionSettings"

    def to_dynamo_item(self) -> dict[str, Any]:
        return {
            "pk": self.pk,
            "sk": self.sk,
            "account_id": self.account_id,
            "updated_by": self.updated_by,
            "enabled": self.enabled,
            "provider_name": self.provider_name,
            "model_name": self.model_name,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "entity_type": "VisionSettings",
        }

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "VisionSettings":
        return cls(
            account_id=item["account_id"],
            updated_by=item.get("updated_by"),
            enabled=bool(item.get("enabled", False)),
            provider_name=item.get("provider_name"),
            model_name=item.get("model_name"),
            created_at=datetime.fromisoformat(item["created_at"]),
            updated_at=datetime.fromisoformat(item["updated_at"]) if item.get("updated_at") else None,
        )


class VisionSettingsRequest(BaseModel):
    enabled: bool = False
    provider_name: str | None = None
    model_name: str | None = None

    @model_validator(mode="after")
    def validate_model_when_enabled(self) -> "VisionSettingsRequest":
        if self.enabled and (not self.provider_name or not self.model_name):
            raise ValueError("provider_name and model_name are required when image reading is enabled")
        return self


class VisionSettingsResponse(BaseModel):
    enabled: bool
    provider_name: str | None = None
    model_name: str | None = None
    is_configured: bool

    @classmethod
    def from_settings(cls, vision_settings: VisionSettings | None) -> "VisionSettingsResponse":
        if not vision_settings:
            return cls(enabled=False, is_configured=False)
        return cls(
            enabled=vision_settings.enabled,
            provider_name=vision_settings.provider_name,
            model_name=vision_settings.model_name,
            is_configured=vision_settings.is_configured,
        )


class ImageUploadResponse(BaseModel):
    """What the uploader gets back: the id to send with the message, and where to fetch the image."""

    image_id: str
    filename: str
    mime_type: str
    size_bytes: int
    width: int
    height: int
    url: str

    @classmethod
    def of(cls, upload: "ImageUpload", url: str) -> "ImageUploadResponse":
        return cls(
            image_id=upload.image_id,
            filename=upload.filename,
            mime_type=upload.mime_type,
            size_bytes=upload.size_bytes,
            width=upload.width,
            height=upload.height,
            url=url,
        )


class ImageUploadStatus:
    PENDING = "pending"
    ATTACHED = "attached"


class ImageUpload(BaseModel):
    """One uploaded image: the ledger row that locates its bytes and records whether a message has claimed it.

    Lives in the conversation's partition under `IMAGE#`, which no message query reads, and goes with the
    conversation when it is deleted.
    """

    image_id: str
    conversation_id: str
    agent_id: str
    account_id: str
    uploaded_by: str
    s3_key: str
    filename: str
    mime_type: str
    size_bytes: int
    width: int
    height: int
    status: str = ImageUploadStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def pk(self) -> str:
        return f"CONVERSATION#{self.conversation_id}"

    @property
    def sk(self) -> str:
        return f"IMAGE#{self.image_id}"

    @property
    def expires_at(self) -> datetime:
        return self.created_at + timedelta(hours=settings.vision_pending_upload_ttl_hours)

    def to_dynamo_item(self) -> dict[str, Any]:
        item = {
            **self.model_dump(mode="json"),
            "pk": self.pk,
            "sk": self.sk,
            "created_at": self.created_at.isoformat(),
            "entity_type": "ImageUpload",
        }
        if self.status == ImageUploadStatus.PENDING:
            item["ttl"] = int(self.expires_at.timestamp())
        return item

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "ImageUpload":
        return cls(**{name: item[name] for name in cls.model_fields if name in item})
