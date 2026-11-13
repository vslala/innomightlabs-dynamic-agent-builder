"""Drawing with OpenAI's image models (`gpt-image-*`) on the images endpoint, streamed so partial frames reach the chat
while the picture is drawn. The GPT image models always answer in base64."""

from __future__ import annotations

import base64
from collections.abc import AsyncIterator
from typing import Any

import httpx

from src.llm.images import ImageGenerationOptions, ImageGenerationStreamEvent, generated_image, mime_type_for_format
from src.llm.providers.openai_api.chat import OPENAI_API_BASE_URL
from src.llm.wire.responses import bearer_headers
from src.llm.wire.sse import sse_events

DRAW_TIMEOUT_SECONDS = 180.0
#: Previews sent before the finished picture (OpenAI allows 0-3; each costs output tokens).
PARTIAL_IMAGES = 2


class OpenAIAPIImages:
    async def draw(
        self, *, prompt: str, credentials: dict[str, Any], model: str, options: ImageGenerationOptions
    ) -> AsyncIterator[ImageGenerationStreamEvent]:
        # The image skill speaks OpenAI's own sizes and qualities, so they pass through as they are.
        body: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "n": 1,
            "output_format": options.output_format,
            "stream": True,
            "partial_images": PARTIAL_IMAGES,
        }
        if options.size:
            body["size"] = options.size
        if options.quality:
            body["quality"] = options.quality

        yield ImageGenerationStreamEvent(kind="started", message="Image generation started")
        async with httpx.AsyncClient(timeout=DRAW_TIMEOUT_SECONDS) as client:
            async with client.stream(
                "POST", f"{OPENAI_API_BASE_URL}/images/generations", headers=bearer_headers(credentials), json=body
            ) as response:
                if not response.is_success:
                    error_text = (await response.aread()).decode("utf-8", errors="ignore")
                    raise RuntimeError(f"OpenAI API image generation error ({response.status_code}): {error_text}")

                yield ImageGenerationStreamEvent(kind="generating", message="Generating image")
                async for event in sse_events(response):
                    event_type = event.get("type")
                    if event_type == "error":
                        raise RuntimeError(f"OpenAI API image generation failed: {event}")
                    if not event.get("b64_json"):
                        continue

                    if event_type == "image_generation.partial_image":
                        output_format = str(event.get("output_format") or options.output_format)
                        yield ImageGenerationStreamEvent(
                            kind="partial",
                            image_b64=event["b64_json"],
                            output_format=output_format,
                            mime_type=mime_type_for_format(output_format),
                            quality=event.get("quality"),
                        )
                    elif event_type == "image_generation.completed":
                        image = generated_image(
                            base64.b64decode(event["b64_json"]),
                            prompt=prompt,
                            provider_key="openai_api",
                            quality=event.get("quality"),
                            background=event.get("background"),
                            metadata={"size": event.get("size")},
                        )
                        yield ImageGenerationStreamEvent(
                            kind="image",
                            image=image,
                            output_format=image.output_format,
                            mime_type=image.mime_type,
                            width=image.width,
                            height=image.height,
                        )
        yield ImageGenerationStreamEvent(kind="completed", message="Image generation complete")
