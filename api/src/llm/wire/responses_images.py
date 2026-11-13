"""Drawing with the Responses API's `image_generation` tool, which any of the provider's chat models can call.

The ChatGPT sign-in (Codex) and an OpenAI API key send the same stream; they differ in where it goes and which
credential authorises it, so each is one `ResponsesToolImages` value, not a subclass."""

from __future__ import annotations

import base64
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx

from src.llm.images import (
    GeneratedImageBytes,
    ImageGenerationOptions,
    ImageGenerationStreamEvent,
    image_dimensions,
    mime_type_for_format,
)
from src.llm.wire.sse import sse_events

DRAW_TIMEOUT_SECONDS = 180.0


@dataclass(frozen=True)
class ResponsesToolImages:
    url: str
    #: The credentials key holding the bearer token ("access_token" for a sign-in, "api_key" for a key)
    credential_field: str
    #: Names the backend in errors
    label: str
    #: Recorded with each image
    provider_key: str

    async def draw(
        self, *, prompt: str, credentials: dict[str, Any], model: str, options: ImageGenerationOptions
    ) -> AsyncIterator[ImageGenerationStreamEvent]:
        token = credentials.get(self.credential_field)
        if not token:
            raise ValueError(f"Missing required {self.label} credential: '{self.credential_field}'")

        tool: dict[str, Any] = {"type": "image_generation", "output_format": options.output_format}
        if options.size:
            tool["size"] = options.size
        if options.quality:
            tool["quality"] = options.quality
        body = {
            "model": model,
            "instructions": "Generate the requested image.",
            "input": [{"role": "user", "content": [{"type": "input_text", "text": prompt}]}],
            "tools": [tool],
            "store": False,
            "stream": True,
        }

        async with httpx.AsyncClient(timeout=DRAW_TIMEOUT_SECONDS) as client:
            async with client.stream(
                "POST",
                self.url,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=body,
            ) as response:
                if not response.is_success:
                    error_text = (await response.aread()).decode("utf-8", errors="ignore")
                    raise RuntimeError(f"{self.label} image generation error: {error_text}")

                async for event in sse_events(response):
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
                                mime_type=mime_type_for_format(output_format),
                                quality=event.get("quality"),
                            )

                    elif event_type == "response.output_item.done":
                        item = event.get("item") or {}
                        if item.get("type") == "image_generation_call" and item.get("result"):
                            image = self._image(item, prompt, options)
                            yield ImageGenerationStreamEvent(
                                kind="image",
                                image=image,
                                output_format=image.output_format,
                                mime_type=image.mime_type,
                                width=image.width,
                                height=image.height,
                            )

                    elif event_type == "response.completed":
                        yield ImageGenerationStreamEvent(kind="completed", message="Image generation complete")
                        break

    def _image(self, item: dict[str, Any], prompt: str, options: ImageGenerationOptions) -> GeneratedImageBytes:
        output_format = str(item.get("output_format") or options.output_format or "png")
        data = base64.b64decode(item["result"])
        dimensions = image_dimensions(data, output_format)
        return GeneratedImageBytes(
            data=data,
            output_format=output_format,
            mime_type=mime_type_for_format(output_format),
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
