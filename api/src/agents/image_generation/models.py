"""Models for agent image generation."""

from typing import Literal

from pydantic import BaseModel, Field

from src.llm.images import ImageGenerationOptions


class GenerateImageRequest(BaseModel):
    """Request to explicitly generate an image with an agent."""

    prompt: str = Field(min_length=1, max_length=4000)
    size: str | None = Field(default=None, max_length=32)
    quality: str | None = Field(default=None, max_length=32)
    output_format: Literal["png", "jpeg", "webp"] = "png"

    def options(self) -> ImageGenerationOptions:
        return ImageGenerationOptions(size=self.size, quality=self.quality, output_format=self.output_format)


class GeneratedImageResponse(BaseModel):
    """Generated image response item."""

    image_id: str
    url: str | None = None
    s3_key: str
    filename: str
    mime_type: str
    width: int | None = None
    height: int | None = None
    size_bytes: int
    prompt: str
    revised_prompt: str | None = None


class GenerateImageResponse(BaseModel):
    """Response for explicit agent image generation."""

    agent_id: str
    conversation_id: str
    user_message_id: str
    assistant_message_id: str
    images: list[GeneratedImageResponse]
