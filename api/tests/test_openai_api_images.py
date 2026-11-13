"""An OpenAI API key draws with OpenAI's image models on the images endpoint, streamed. No call leaves the test."""

import base64
import json

import pytest

from src.llm.images import ImageGenerationOptions, collect_images
from src.llm.providers import provider

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADUlEQVR4nGNk+M8AAwUBAelBqTQAAAAASUVORK5CYII="
)
PNG_B64 = base64.b64encode(PNG_1X1).decode()


def _stream(monkeypatch, events: list[dict], *, status: int = 200) -> dict:
    sent: dict = {}

    class Response:
        is_success = status == 200
        status_code = status

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc_info):
            return False

        async def aread(self):
            return b'{"error": {"message": "invalid size"}}'

        async def aiter_lines(self):
            for event in events:
                yield f"data: {json.dumps(event)}"

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc_info):
            return False

        def stream(self, method, url, headers=None, json=None):
            sent.update(url=url, authorization=headers["Authorization"], body=json)
            return Response()

    monkeypatch.setattr("src.llm.providers.openai_api.images.httpx.AsyncClient", Client)
    return sent


async def _draw(**options):
    return [
        event
        async for event in provider("OpenAIAPI").images.draw(
            prompt="red pixel", credentials={"api_key": "sk-test"}, model="gpt-image-2",
            options=ImageGenerationOptions(**options),
        )
    ]


async def test_it_draws_at_the_images_endpoint_streaming_previews(monkeypatch):
    sent = _stream(monkeypatch, [{"type": "image_generation.completed", "b64_json": PNG_B64}])

    await _draw(size="1024x1536", quality="high", output_format="png")

    assert sent["url"] == "https://api.openai.com/v1/images/generations"
    assert sent["authorization"] == "Bearer sk-test"
    assert sent["body"] == {
        "model": "gpt-image-2", "prompt": "red pixel", "n": 1, "output_format": "png", "stream": True,
        "partial_images": 2, "size": "1024x1536", "quality": "high",
    }


async def test_previews_then_the_picture_arrive_as_drawing_events(monkeypatch):
    _stream(monkeypatch, [
        {"type": "image_generation.partial_image", "b64_json": PNG_B64, "partial_image_index": 0, "output_format": "png"},
        {"type": "image_generation.completed", "b64_json": PNG_B64, "quality": "high", "background": "opaque",
         "size": "1024x1024"},
    ])

    events = await _draw()

    assert [event.kind for event in events] == ["started", "generating", "partial", "image", "completed"]
    assert events[2].image_b64 == PNG_B64 and events[2].mime_type == "image/png"
    image = events[3].image
    assert (image.width, image.height, image.quality, image.background) == (1, 1, "high", "opaque")
    assert image.provider_metadata == {"provider": "openai_api", "size": "1024x1024"}


async def test_a_refused_drawing_raises_with_the_status_and_openais_words(monkeypatch):
    _stream(monkeypatch, [], status=400)

    with pytest.raises(RuntimeError, match=r"\(400\).*invalid size"):
        await _draw()


async def test_a_stream_without_a_picture_is_an_error(monkeypatch):
    _stream(monkeypatch, [{"type": "image_generation.partial_image", "b64_json": PNG_B64}])

    with pytest.raises(RuntimeError, match="without image output"):
        await collect_images(provider("OpenAIAPI").images.draw(
            prompt="x", credentials={"api_key": "k"}, model="gpt-image-2", options=ImageGenerationOptions()))


async def test_it_wants_an_api_key():
    with pytest.raises(ValueError, match="api_key"):
        await collect_images(provider("OpenAIAPI").images.draw(
            prompt="x", credentials={}, model="gpt-image-2", options=ImageGenerationOptions()))
