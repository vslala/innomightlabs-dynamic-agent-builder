"""Gemini draws with its image models through `generateContent`; its catalog keeps them apart from the chat models.
No call leaves the test."""

import io
import json
from types import SimpleNamespace

import pytest
from PIL import Image

from src.crypto import encrypt
from src.llm.images import ImageGenerationOptions, collect_images
from src.llm.models import ModelCapability
from src.llm.providers import provider
from src.settings.models import ProviderSettings

GEMINI = provider("Gemini")


def _png(width: int, height: int) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), "blue").save(buffer, "PNG")
    return buffer.getvalue()


def test_the_catalog_offers_image_models_for_drawing_and_not_for_chat(monkeypatch):
    listed = [
        SimpleNamespace(name="models/gemini-2.5-flash", display_name="Gemini 2.5 Flash", supported_actions=["generateContent"]),
        SimpleNamespace(name="models/gemini-3-pro-image", display_name="Nano Banana Pro", supported_actions=["generateContent"]),
        SimpleNamespace(name="models/gemini-nano-banana-2.1", display_name="Nano Banana", supported_actions=["generateContent"]),
    ]
    monkeypatch.setattr("google.genai.Client", lambda api_key: SimpleNamespace(models=SimpleNamespace(list=lambda config: listed)))
    settings = ProviderSettings(account_id="a", provider_name="Gemini", encrypted_credentials=encrypt(json.dumps({"api_key": "k"})))

    models = {m.model_name: m for m in GEMINI.catalog.list_models(settings)}

    assert models["gemini-2.5-flash"].can(ModelCapability.CHAT, ModelCapability.IMAGE_UNDERSTANDING)
    for drawing in ("gemini-3-pro-image", "gemini-nano-banana-2.1"):
        assert models[drawing].capabilities == [ModelCapability.IMAGE_GENERATION]


class FakeGenai:
    """genai.Client: answers generate_content with the given parts and remembers the request."""

    def __init__(self, parts):
        self.parts = parts
        self.asked: dict = {}

    def __call__(self, api_key):
        self.asked["api_key"] = api_key
        return SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=self.generate_content)))

    async def generate_content(self, *, model, contents, config):
        self.asked.update(model=model, contents=contents, config=config)
        return SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=self.parts))])


def _part(data: bytes | None = None, text: str | None = None):
    return SimpleNamespace(inline_data=SimpleNamespace(data=data, mime_type="image/png") if data else None, text=text)


async def _draw(monkeypatch, parts, **options):
    fake = FakeGenai(parts)
    monkeypatch.setattr("google.genai.Client", fake)
    events = [event async for event in GEMINI.images.draw(
        prompt="a lighthouse", credentials={"api_key": "gm-key"}, model="gemini-3-pro-image",
        options=ImageGenerationOptions(**options),
    )]
    return fake.asked, events


async def test_gemini_is_asked_for_an_image_as_well_as_text_in_the_skills_aspect_ratio(monkeypatch):
    asked, _ = await _draw(monkeypatch, [_part(_png(4, 2))], size="1536x1024")

    assert (asked["api_key"], asked["model"], asked["contents"]) == ("gm-key", "gemini-3-pro-image", "a lighthouse")
    assert asked["config"].response_modalities == ["TEXT", "IMAGE"]
    assert asked["config"].image_config.aspect_ratio == "3:2"


async def test_a_size_gemini_isnt_told_lets_it_choose(monkeypatch):
    asked, _ = await _draw(monkeypatch, [_part(_png(4, 2))])

    assert asked["config"].image_config is None


async def test_the_inline_picture_is_the_image_and_the_text_beside_it_is_left_out(monkeypatch):
    _, events = await _draw(monkeypatch, [_part(text="Here is your lighthouse."), _part(_png(4, 2))])

    assert [event.kind for event in events] == ["started", "generating", "image", "completed"]
    image = events[2].image
    assert (image.output_format, image.width, image.height) == ("png", 4, 2)
    assert image.provider_metadata["provider"] == "gemini"


async def test_an_answer_without_a_picture_is_an_error(monkeypatch):
    monkeypatch.setattr("google.genai.Client", FakeGenai([_part(text="I can't draw that.")]))

    with pytest.raises(RuntimeError, match="without image output"):
        await collect_images(GEMINI.images.draw(
            prompt="x", credentials={"api_key": "k"}, model="gemini-3-pro-image", options=ImageGenerationOptions()))
