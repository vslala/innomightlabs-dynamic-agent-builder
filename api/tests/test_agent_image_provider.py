import json

import pytest

from src.agents.image_generation.models import ImageGenerationOptions
from src.agents.image_generation.provider import CodexOpenAIImageGenerationProvider


PNG_1X1_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADUlEQVR4nGNk+M8AAwUB"
    "AelBqTQAAAAASUVORK5CYII="
)


class FakeStreamResponse:
    is_success = True

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def aiter_lines(self):
        events = [
            {"type": "response.created"},
            {
                "type": "response.output_item.done",
                "item": {
                    "id": "ig_test",
                    "type": "image_generation_call",
                    "result": PNG_1X1_B64,
                    "output_format": "png",
                    "revised_prompt": "A red pixel.",
                    "quality": "low",
                    "background": "opaque",
                },
            },
            {"type": "response.completed"},
        ]
        for event in events:
            yield f"data: {json.dumps(event)}"


class FakeAsyncClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    def stream(self, *args, **kwargs):
        return FakeStreamResponse()


@pytest.mark.asyncio
async def test_codex_provider_extracts_final_image_result(monkeypatch):
    monkeypatch.setattr(
        "src.agents.image_generation.provider.httpx.AsyncClient",
        FakeAsyncClient,
    )
    provider = CodexOpenAIImageGenerationProvider()

    images = await provider.generate(
        prompt="red pixel",
        credentials={"access_token": "token"},
        model="gpt-5.4",
        options=ImageGenerationOptions(output_format="png"),
    )

    assert len(images) == 1
    assert images[0].mime_type == "image/png"
    assert images[0].width == 1
    assert images[0].height == 1
    assert images[0].revised_prompt == "A red pixel."
