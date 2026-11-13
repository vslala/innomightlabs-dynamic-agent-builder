"""Provider adapters for agent image generation."""

import base64
import json
import logging
import struct
from dataclasses import dataclass
from typing import Any, AsyncIterator, Protocol

import httpx

from src.agents.image_generation.models import (
    GeneratedImageBytes,
    ImageGenerationStreamEvent,
    ImageGenerationOptions,
)
from src.config import settings
from src.llm.providers.openai_api.chat import OPENAI_API_BASE_URL

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ImageDimensions:
    width: int | None
    height: int | None


class ImageGenerationProvider(Protocol):
    """Provider-neutral image generation contract."""

    async def generate(
        self,
        *,
        prompt: str,
        credentials: dict[str, Any],
        model: str,
        options: ImageGenerationOptions,
    ) -> list[GeneratedImageBytes]:
        ...

    def stream_generate(
        self,
        *,
        prompt: str,
        credentials: dict[str, Any],
        model: str,
        options: ImageGenerationOptions,
    ) -> AsyncIterator[ImageGenerationStreamEvent]:
        ...


class ResponsesImageGenerationProvider:
    """Draws with the Responses API's `image_generation` tool, which any of the provider's chat models can call.

    The ChatGPT sign-in and an OpenAI API key speak the same stream; they differ in where it's sent and how the
    request is authorised."""

    #: Names the provider in errors
    label = "OpenAI"
    credential_field = "access_token"
    #: Recorded with each image
    provider_key = "openai"

    def endpoint(self) -> str:
        raise NotImplementedError

    async def generate(
        self,
        *,
        prompt: str,
        credentials: dict[str, Any],
        model: str,
        options: ImageGenerationOptions,
    ) -> list[GeneratedImageBytes]:
        results: list[GeneratedImageBytes] = []
        async for event in self.stream_generate(
            prompt=prompt,
            credentials=credentials,
            model=model,
            options=options,
        ):
            if event.kind == "image" and event.image:
                results.append(event.image)

        if not results:
            raise RuntimeError(f"{self.label} image generation completed without image output")

        return results

    async def stream_generate(
        self,
        *,
        prompt: str,
        credentials: dict[str, Any],
        model: str,
        options: ImageGenerationOptions,
    ) -> AsyncIterator[ImageGenerationStreamEvent]:
        token = credentials.get(self.credential_field)
        if not token:
            raise ValueError(f"Missing required {self.label} credential: '{self.credential_field}'")

        tool: dict[str, Any] = {
            "type": "image_generation",
            "output_format": options.output_format,
        }
        if options.size:
            tool["size"] = options.size
        if options.quality:
            tool["quality"] = options.quality

        body = {
            "model": model,
            "instructions": "Generate the requested image.",
            "input": [
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": prompt}],
                }
            ],
            "tools": [tool],
            "store": False,
            "stream": True,
        }

        async with httpx.AsyncClient(timeout=180.0) as client:
            async with client.stream(
                "POST",
                self.endpoint(),
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=body,
            ) as response:
                if not response.is_success:
                    error_text = (await response.aread()).decode("utf-8", errors="ignore")
                    raise RuntimeError(f"{self.label} image generation error: {error_text}")

                async for raw_line in response.aiter_lines():
                    line = raw_line.strip()
                    if not line.startswith("data:"):
                        continue

                    data = line[5:].strip()
                    if not data or data == "[DONE]":
                        continue

                    try:
                        event = json.loads(data)
                    except json.JSONDecodeError:
                        continue

                    event_type = event.get("type")
                    if event_type in {"response.failed", "error"}:
                        raise RuntimeError(f"{self.label} image generation failed: {event}")

                    if event_type == "response.image_generation_call.in_progress":
                        yield ImageGenerationStreamEvent(kind="started", message="Image generation started")

                    elif event_type == "response.image_generation_call.generating":
                        yield ImageGenerationStreamEvent(kind="generating", message="Generating image")

                    elif event_type == "response.image_generation_call.partial_image":
                        image_b64 = event.get("partial_image_b64")
                        output_format = str(event.get("output_format") or options.output_format or "png")
                        if image_b64:
                            yield ImageGenerationStreamEvent(
                                kind="partial",
                                image_b64=image_b64,
                                output_format=output_format,
                                mime_type=_mime_type_for_format(output_format),
                                quality=event.get("quality"),
                            )

                    elif event_type == "response.output_item.done":
                        item = event.get("item") or {}
                        if item.get("type") != "image_generation_call":
                            continue

                        image_b64 = item.get("result")
                        if not image_b64:
                            continue

                        output_format = str(item.get("output_format") or options.output_format or "png")
                        image_bytes = base64.b64decode(image_b64)
                        dimensions = _dimensions_for_image(image_bytes, output_format)
                        generated = GeneratedImageBytes(
                            data=image_bytes,
                            output_format=output_format,
                            mime_type=_mime_type_for_format(output_format),
                            prompt=prompt,
                            revised_prompt=item.get("revised_prompt"),
                            width=dimensions.width,
                            height=dimensions.height,
                            quality=item.get("quality"),
                            background=item.get("background"),
                            provider_metadata={
                                "provider": self.provider_key,
                                "item_id": item.get("id"),
                                "action": item.get("action"),
                                "size": item.get("size"),
                            },
                        )
                        yield ImageGenerationStreamEvent(
                            kind="image",
                            image=generated,
                            output_format=output_format,
                            mime_type=generated.mime_type,
                            width=dimensions.width,
                            height=dimensions.height,
                        )

                    elif event_type == "response.completed":
                        yield ImageGenerationStreamEvent(kind="completed", message="Image generation complete")
                        break


class CodexOpenAIImageGenerationProvider(ResponsesImageGenerationProvider):
    """The ChatGPT sign-in: the Codex backend."""

    label = "OpenAI Codex"
    provider_key = "openai_codex"

    def endpoint(self) -> str:
        return settings.openai_oauth_responses_url


class OpenAIAPIImageGenerationProvider(ResponsesImageGenerationProvider):
    """An OpenAI API key."""

    label = "OpenAI API"
    credential_field = "api_key"
    provider_key = "openai_api"

    def endpoint(self) -> str:
        return f"{OPENAI_API_BASE_URL}/responses"


class ImageProviderFactory:
    """Resolve provider adapters by agent provider/backend."""

    def __init__(self):
        self._providers: dict[str, ImageGenerationProvider] = {
            "openai": CodexOpenAIImageGenerationProvider(),
            "openaiapi": OpenAIAPIImageGenerationProvider(),
        }

    def get(self, provider_name: str) -> ImageGenerationProvider:
        provider = self._providers.get(provider_name.lower())
        if not provider:
            raise ValueError(f"Image generation is not implemented for provider '{provider_name}'")
        return provider


def _mime_type_for_format(output_format: str) -> str:
    normalized = output_format.lower().lstrip(".")
    if normalized in {"jpg", "jpeg"}:
        return "image/jpeg"
    if normalized == "webp":
        return "image/webp"
    return "image/png"


def _dimensions_for_image(data: bytes, output_format: str) -> ImageDimensions:
    normalized = output_format.lower().lstrip(".")
    if normalized == "png" and data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        width, height = struct.unpack(">II", data[16:24])
        return ImageDimensions(width=int(width), height=int(height))
    return ImageDimensions(width=None, height=None)
