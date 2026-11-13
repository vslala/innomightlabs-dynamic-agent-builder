"""Drawing with Gemini's image models (`gemini-*-image`): `generateContent` asked for an image as well as text. One
request returns the finished picture as inline data; there are no partial frames."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from google import genai
from google.genai import types

from src.llm.images import ImageGenerationOptions, ImageGenerationStreamEvent, aspect_ratio_of, generated_image


class GeminiImages:
    async def draw(
        self, *, prompt: str, credentials: dict[str, Any], model: str, options: ImageGenerationOptions
    ) -> AsyncIterator[ImageGenerationStreamEvent]:
        api_key = credentials.get("api_key")
        if not api_key:
            raise ValueError("Missing required Gemini credential: 'api_key'")
        aspect_ratio = aspect_ratio_of(options.size)
        config = types.GenerateContentConfig(
            # Image models answer with text beside the picture; asking for an image alone is refused.
            response_modalities=["TEXT", "IMAGE"],
            image_config=types.ImageConfig(aspect_ratio=aspect_ratio) if aspect_ratio else None,
        )

        yield ImageGenerationStreamEvent(kind="started", message="Image generation started")
        yield ImageGenerationStreamEvent(kind="generating", message="Generating image")
        response = await genai.Client(api_key=api_key).aio.models.generate_content(
            model=model, contents=prompt, config=config
        )
        for part in _parts(response):
            if part.inline_data and part.inline_data.data:
                image = generated_image(
                    part.inline_data.data, prompt=prompt, provider_key="gemini", metadata={"aspect_ratio": aspect_ratio}
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


def _parts(response: types.GenerateContentResponse) -> list[types.Part]:
    content = response.candidates[0].content if response.candidates else None
    return list(content.parts or []) if content else []
