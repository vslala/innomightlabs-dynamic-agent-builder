"""Provider adapters for agent image generation."""

import base64
import json
import logging
import struct
from typing import Any, AsyncIterator, Protocol

import httpx

from src.agents.image_generation.models import (
    GeneratedImageBytes,
    ImageGenerationStreamEvent,
    ImageGenerationOptions,
)
from src.config import settings

log = logging.getLogger(__name__)


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


class CodexOpenAIImageGenerationProvider:
    """OpenAI Codex/ChatGPT OAuth image generation provider."""

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
            raise RuntimeError("OpenAI Codex image generation completed without image output")

        return results

    async def stream_generate(
        self,
        *,
        prompt: str,
        credentials: dict[str, Any],
        model: str,
        options: ImageGenerationOptions,
    ) -> AsyncIterator[ImageGenerationStreamEvent]:
        access_token = credentials.get("access_token")
        if not access_token:
            raise ValueError("Missing required OpenAI OAuth access token")

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
                settings.openai_oauth_responses_url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json=body,
            ) as response:
                if not response.is_success:
                    error_text = (await response.aread()).decode("utf-8", errors="ignore")
                    raise RuntimeError(f"OpenAI Codex image generation error: {error_text}")

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
                        raise RuntimeError(f"OpenAI Codex image generation failed: {event}")

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
                        width, height = _dimensions_for_image(image_bytes, output_format)
                        generated = GeneratedImageBytes(
                            data=image_bytes,
                            output_format=output_format,
                            mime_type=_mime_type_for_format(output_format),
                            prompt=prompt,
                            revised_prompt=item.get("revised_prompt"),
                            width=width,
                            height=height,
                            quality=item.get("quality"),
                            background=item.get("background"),
                            provider_metadata={
                                "provider": "openai_codex",
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
                            width=width,
                            height=height,
                        )

                    elif event_type == "response.completed":
                        yield ImageGenerationStreamEvent(kind="completed", message="Image generation complete")
                        break


class ImageProviderFactory:
    """Resolve provider adapters by agent provider/backend."""

    def __init__(self):
        self._providers: dict[str, ImageGenerationProvider] = {
            "openai": CodexOpenAIImageGenerationProvider(),
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


def _dimensions_for_image(data: bytes, output_format: str) -> tuple[int | None, int | None]:
    normalized = output_format.lower().lstrip(".")
    if normalized == "png" and data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        width, height = struct.unpack(">II", data[16:24])
        return int(width), int(height)
    return None, None
