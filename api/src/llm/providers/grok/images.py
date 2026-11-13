"""Drawing with xAI's image models (`grok-imagine-image*`) on its images endpoint. One request returns finished
pictures; there are no partial frames."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from src.llm.images import ImageGenerationOptions, ImageGenerationStreamEvent, generated_image
from src.llm.providers.grok.chat import GROK_API_BASE_URL
from src.llm.wire.images_api import generate_images

#: The image skill's OpenAI sizes in xAI's words; any other size lets xAI choose.
ASPECT_RATIOS = {"1024x1024": "1:1", "1536x1024": "3:2", "1024x1536": "2:3"}
#: xAI takes low, medium or auto, so OpenAI's "high" becomes xAI's best.
QUALITIES = {"low": "low", "medium": "medium", "high": "medium"}


class GrokImages:
    async def draw(
        self, *, prompt: str, credentials: dict[str, Any], model: str, options: ImageGenerationOptions
    ) -> AsyncIterator[ImageGenerationStreamEvent]:
        api_key = credentials.get("api_key")
        if not api_key:
            raise ValueError("Missing required Grok credential: 'api_key'")
        body = {
            "model": model,
            "prompt": prompt,
            "n": 1,
            "aspect_ratio": ASPECT_RATIOS.get(options.size or "", "auto"),
            "quality": QUALITIES.get(options.quality or "", "auto"),
        }

        yield ImageGenerationStreamEvent(kind="started", message="Image generation started")
        yield ImageGenerationStreamEvent(kind="generating", message="Generating image")
        for item in await generate_images(f"{GROK_API_BASE_URL}/images/generations", api_key, body, label="Grok"):
            image = generated_image(
                item["image"],
                prompt=prompt,
                provider_key="grok",
                revised_prompt=item.get("revised_prompt"),
                quality=body["quality"],
                metadata={"aspect_ratio": body["aspect_ratio"]},
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
