"""Grok (xAI): chat through its Responses API, its catalog, and drawing with its image models. No call leaves the test."""

import base64
import io
import json

import httpx
import pytest
from PIL import Image

from src.agents.image_generation.models import GenerateImageRequest
from src.agents.image_generation.service import AgentImageGenerationService
from src.agents.models import Agent
from src.agents.repository import AgentRepository
from src.config import settings
from src.conversations.models import Conversation
from src.conversations.repository import ConversationRepository
from src.crypto import encrypt
from src.llm.images import ImageGenerationOptions, collect_images
from src.llm.models import ModelCapability
from src.llm.providers import provider
from src.settings.models import ProviderSettings
from tests.mock_data import TEST_USER_EMAIL, agent_fields, conversation_fields
from tests.test_agent_image_generation_service import FakeStorage

GROK = provider("Grok")


# --- Chat ---------------------------------------------------------------------------------------


class RecordedStream:
    """An httpx.AsyncClient whose stream answers with the given events and remembers the request."""

    sent: dict = {}

    def __init__(self, events: list[dict]):
        self.events = events

    def __call__(self, *args, **kwargs):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    def stream(self, method, url, headers=None, json=None):
        RecordedStream.sent = {"url": url, "headers": headers, "body": json}
        return _Response([f"data: {_json(event)}" for event in self.events] + ["data: [DONE]"])


class _Response:
    headers: dict[str, str] = {}
    is_success = True

    def __init__(self, lines):
        self.lines = lines

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def aiter_lines(self):
        for line in self.lines:
            yield line


def _json(value) -> str:
    return json.dumps(value)


async def _chat(monkeypatch, events: list[dict], tools=None, model=None):
    monkeypatch.setattr("src.llm.wire.responses.httpx.AsyncClient", RecordedStream(events))
    return [
        event
        async for event in GROK.chat.stream_response(
            [{"role": "system", "content": "Be brief."}, {"role": "user", "content": "Hi"}],
            {"api_key": "xai-test"},
            tools,
            model,
        )
    ]


async def test_grok_chats_at_xais_responses_endpoint_with_the_key(monkeypatch):
    await _chat(monkeypatch, [{"type": "response.completed", "response": {}}])

    assert RecordedStream.sent["url"] == "https://api.x.ai/v1/responses"
    assert RecordedStream.sent["headers"]["Authorization"] == "Bearer xai-test"


async def test_grok_is_sent_the_common_body_without_codexs_reasoning_fields(monkeypatch):
    await _chat(monkeypatch, [{"type": "response.completed", "response": {}}])

    body = RecordedStream.sent["body"]
    assert body["model"] == "grok-4.7"  # no model chosen: Grok's default, not an OpenAI one
    assert body["instructions"] == "Be brief."
    assert not {"include", "text", "reasoning"} & body.keys()


async def test_grok_streams_text_a_tool_call_usage_and_one_stop(monkeypatch):
    events = await _chat(monkeypatch, [
        {"type": "response.output_text.delta", "delta": "Looking"},
        {"type": "response.output_item.added", "item": {"type": "function_call", "id": "fc_1", "call_id": "call_1",
                                                         "name": "search"}},
        {"type": "response.function_call_arguments.delta", "item_id": "fc_1", "delta": '{"q": "x"}'},
        {"type": "response.function_call_arguments.done", "item_id": "fc_1"},
        {"type": "response.completed", "response": {"usage": {"input_tokens": 5, "output_tokens": 3}}},
    ], model="grok-4.6")

    assert [(e.type, e.content or e.tool_name) for e in events] == [
        ("text", "Looking"), ("tool_use", "search"), ("usage", ""), ("stop", "end_turn"),
    ]
    assert events[1].tool_input == {"q": "x"} and (events[2].prompt_tokens, events[2].completion_tokens) == (5, 3)


async def test_grok_without_a_key_says_which_credential_is_missing():
    with pytest.raises(ValueError, match="api_key"):
        [event async for event in GROK.chat.stream_response([{"role": "user", "content": "Hi"}], {})]


def test_xais_unknown_model_answer_is_a_refusal_the_fallback_retries():
    assert GROK.refuses_model(RuntimeError(
        'Grok responses error (404, request_id=r): {"error": "The model grok-9 does not exist or your team does not '
        'have access to it."}'
    ))


# --- Catalog ------------------------------------------------------------------------------------


def _settings() -> ProviderSettings:
    return ProviderSettings(account_id="acct", provider_name="Grok", encrypted_credentials=encrypt(json.dumps({"api_key": "xai-test"})))


def _listings(monkeypatch, answers: dict[str, object]) -> list[str]:
    asked: list[str] = []

    def fake_get(url, headers=None, timeout=None):
        asked.append(url)
        answer = answers.get(url.rsplit("/", 1)[-1])
        if isinstance(answer, Exception):
            raise answer
        return httpx.Response(200, json=answer, request=httpx.Request("GET", url))

    monkeypatch.setattr("src.llm.providers.grok.catalog.httpx.get", fake_get)
    return asked


def test_the_catalog_lists_chat_models_newest_first_then_the_image_models(monkeypatch):
    asked = _listings(monkeypatch, {
        "language-models": {"models": [
            {"id": "grok-4.6", "created": 1, "input_modalities": ["text"]},
            {"id": "grok-4.7", "created": 2, "input_modalities": ["text", "image"]},
        ]},
        "image-generation-models": {"models": [{"id": "grok-imagine-image-2.0"}]},
    })

    models = GROK.catalog.list_models(_settings())

    assert [(m.model_name, m.capabilities) for m in models] == [
        ("grok-4.7", [ModelCapability.CHAT, ModelCapability.IMAGE_UNDERSTANDING]),
        ("grok-4.6", [ModelCapability.CHAT]),
        ("grok-imagine-image-2.0", [ModelCapability.IMAGE_GENERATION]),
    ]
    assert asked == ["https://api.x.ai/v1/language-models", "https://api.x.ai/v1/image-generation-models"]


def test_a_listing_that_cant_be_read_is_replaced_by_the_configured_models(monkeypatch):
    monkeypatch.setattr(settings, "grok_models", ["grok-4.7"])
    monkeypatch.setattr(settings, "grok_image_models", ["grok-imagine-image-2.0"])
    _listings(monkeypatch, {"language-models": httpx.ConnectError("down"), "image-generation-models": {"data": "nope"}})

    models = GROK.catalog.list_models(_settings())

    assert [(m.model_name, m.can(ModelCapability.CHAT), m.can(ModelCapability.IMAGE_GENERATION)) for m in models] == [
        ("grok-4.7", True, False),
        ("grok-imagine-image-2.0", False, True),
    ]


# --- Drawing ------------------------------------------------------------------------------------


def _jpeg(width: int, height: int) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), "red").save(buffer, "JPEG")
    return buffer.getvalue()


def _drawing(monkeypatch, status: int = 200) -> dict:
    sent: dict = {}

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc_info):
            return False

        async def post(self, url, headers=None, json=None):
            sent.update(url=url, authorization=headers["Authorization"], body=json)
            answer = {"data": [{"b64_json": base64.b64encode(_jpeg(48, 32)).decode()}]} if status == 200 else {"error": "x"}
            return httpx.Response(status, json=answer, request=httpx.Request("POST", url))

    monkeypatch.setattr("src.llm.wire.images_api.httpx.AsyncClient", Client)
    return sent


async def test_grok_draws_at_xais_images_endpoint_in_its_own_words(monkeypatch):
    sent = _drawing(monkeypatch)

    await collect_images(GROK.images.draw(
        prompt="a fox", credentials={"api_key": "xai-test"}, model="grok-imagine-image-2.0",
        options=ImageGenerationOptions(size="1536x1024", quality="high"),
    ))

    assert sent["url"] == "https://api.x.ai/v1/images/generations"
    assert sent["authorization"] == "Bearer xai-test"
    assert sent["body"] == {
        "model": "grok-imagine-image-2.0", "prompt": "a fox", "n": 1, "aspect_ratio": "3:2", "quality": "medium",
        "response_format": "b64_json",
    }


async def test_a_size_or_quality_xai_doesnt_name_lets_it_choose(monkeypatch):
    sent = _drawing(monkeypatch)

    await collect_images(GROK.images.draw(
        prompt="a fox", credentials={"api_key": "k"}, model="grok-imagine-image-2.0", options=ImageGenerationOptions(),
    ))

    assert (sent["body"]["aspect_ratio"], sent["body"]["quality"]) == ("auto", "auto")


async def test_the_jpeg_xai_sends_is_stored_as_a_jpeg_with_its_size(monkeypatch):
    _drawing(monkeypatch)

    events = [event async for event in GROK.images.draw(
        prompt="a fox", credentials={"api_key": "k"}, model="grok-imagine-image-2.0",
        options=ImageGenerationOptions(output_format="png"),
    )]

    assert [event.kind for event in events] == ["started", "generating", "image", "completed"]
    image = events[2].image
    assert (image.output_format, image.mime_type, image.width, image.height) == ("jpeg", "image/jpeg", 48, 32)
    assert image.provider_metadata == {"provider": "grok", "aspect_ratio": "auto"}


async def test_a_refused_drawing_raises_with_xais_status(monkeypatch):
    _drawing(monkeypatch, status=400)

    with pytest.raises(RuntimeError, match=r"Grok image generation error \(400\)"):
        await collect_images(GROK.images.draw(
            prompt="x", credentials={"api_key": "k"}, model="grok-imagine-image-2.0", options=ImageGenerationOptions(),
        ))


# --- End to end: Settings > Image Generation, then an agent draws --------------------------------


async def test_an_admin_chooses_groks_image_model_and_an_agent_on_another_provider_draws_with_it(
    test_client, auth_headers, without_bedrock, monkeypatch
):
    _listings(monkeypatch, {
        "language-models": {"models": [{"id": "grok-4.7", "input_modalities": ["text", "image"]}]},
        "image-generation-models": {"models": [{"id": "grok-imagine-image-2.0"}]},
    })
    sent = _drawing(monkeypatch)
    assert test_client.post("/settings/providers/Grok", json={"api_key": "xai-test"}, headers=auth_headers).status_code == 201

    form = test_client.get("/image-generation/settings/schema", headers=auth_headers).json()
    offered = next(field for field in form["form_inputs"] if field["name"] == "model_name")["options"]
    assert [(option["group"], option["value"]) for option in offered] == [("Grok", "grok-imagine-image-2.0")]
    refused = test_client.put("/image-generation/settings", headers=auth_headers,
                              json={"enabled": True, "provider_name": "Grok", "model_name": "grok-4.7"})
    assert refused.status_code == 400  # a chat model that can't draw
    saved = test_client.put("/image-generation/settings", headers=auth_headers,
                            json={"enabled": True, "provider_name": "Grok", "model_name": "grok-imagine-image-2.0"})
    assert saved.status_code == 200, saved.text

    agent = AgentRepository().save(Agent(
        agent_name="Writer", agent_architecture="krishna-memgpt", agent_provider="Anthropic", agent_model="claude-haiku",
        agent_persona="You write.", **agent_fields(TEST_USER_EMAIL),
    ))
    conversation = ConversationRepository().save(Conversation(
        title="Pictures", agent_id=agent.agent_id, **conversation_fields(TEST_USER_EMAIL)))
    result = await AgentImageGenerationService(storage=FakeStorage()).generate_for_widget(
        agent=agent, conversation=conversation, actor_email=TEST_USER_EMAIL, request=GenerateImageRequest(prompt="a fox"),
    )

    assert sent["body"]["model"] == "grok-imagine-image-2.0" and sent["authorization"] == "Bearer xai-test"
    assert (result.images[0].mime_type, result.images[0].width, result.images[0].filename) == (
        "image/jpeg", 48, "generated-image-1.jpeg")
