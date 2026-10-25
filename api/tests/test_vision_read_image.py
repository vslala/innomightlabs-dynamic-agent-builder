from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import pytest

from src.agents.architectures.krishna_memgpt_families import TOOL_FAMILIES
from src.agents.tool_runtime.families import active_families
from src.agents.runtime_state import AgentTurnState
from src.agents.tool_runtime.contexts import NativeToolContext
from src.agents.tool_runtime.specs import ToolCategory
from src.llm.messages import ImageBlock, TextBlock
from src.llm.providers.base import LLMEvent
from src.messages.models import Message
from src.messages.repositories import DynamoDBMessageRepository
from src.skills.models import ActorKind
from src.tools.native.handlers import NativeToolHandler
from src.tools.native.specs import NATIVE_TOOL_SPECS
from src.vision import analysis
from src.vision.analysis import ImageReader, parse_reading
from src.vision.context import index_images
from src.vision.errors import ImageInputError
from src.vision.models import VisionSettings
from src.vision.repository import VisionSettingsRepository
from src.vision.uploads import ImageUploadService
from tests.vision_support import ACCOUNT_ID, create_media_bucket, enable_vision, make_agent, png_bytes

CONVERSATION_ID = "conversation-1"
REPLY = json.dumps({"description": "A red error dialog.", "answer": "Error 51."})


class FakeVisionProvider:
    def __init__(self, reply: str = REPLY, delay: float = 0.0, fail: bool = False) -> None:
        self.reply, self.delay, self.fail = reply, delay, fail
        self.calls: list[dict[str, Any]] = []
        self.active = self.max_active = 0

    async def stream_response(
        self, messages: list[dict], credentials: dict, tools: list | None = None, model: str | None = None
    ) -> AsyncIterator[LLMEvent]:
        self.calls.append({"messages": messages, "model": model, "tools": tools})
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(self.delay)
            if self.fail:
                raise RuntimeError("provider exploded: secret-detail")
            yield LLMEvent(type="text", content=self.reply)
            yield LLMEvent(type="usage", prompt_tokens=10, completion_tokens=5)
        finally:
            self.active -= 1


class RecordingUsage:
    def __init__(self) -> None:
        self.recorded: list[dict[str, Any]] = []

    def record_usage(self, **kwargs: Any) -> None:
        self.recorded.append(kwargs)


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch) -> FakeVisionProvider:
    fake = FakeVisionProvider()

    async def credentials(**_: Any) -> dict[str, str]:
        return {"api_key": "key"}

    monkeypatch.setattr(analysis, "get_llm_provider", lambda name: fake)
    monkeypatch.setattr(analysis, "load_provider_credentials", credentials)
    return fake


@pytest.fixture
def usage() -> RecordingUsage:
    return RecordingUsage()


def _conversation_with_images(count: int = 1) -> tuple[list[str], dict]:
    create_media_bucket()
    enable_vision(model="vision-model")
    agent, service = make_agent(), ImageUploadService()
    uploads = [
        service.store(
            agent=agent, conversation_id=CONVERSATION_ID, uploaded_by="alice", filename=f"shot-{n}.png", raw=png_bytes()
        )
        for n in range(count)
    ]
    attachments = service.attach(
        agent=agent, conversation_id=CONVERSATION_ID, actor_id="alice", image_ids=[u.image_id for u in uploads]
    )
    message = Message(conversation_id=CONVERSATION_ID, role="user", content="what is this?", image_attachments=attachments)
    DynamoDBMessageRepository().save(message)
    return [a.image_id for a in attachments], index_images([message])


def _context(images: dict) -> NativeToolContext:
    return NativeToolContext(
        agent_id="agent-1", user_id="alice", conversation_id=CONVERSATION_ID, linked_kb_ids=[],
        account_id=ACCOUNT_ID, owner_email="owner@example.com", api_key_id="key-1", images=images,
    )


def _reader(usage: RecordingUsage) -> ImageReader:
    return ImageReader(token_usage=usage)  # type: ignore[arg-type]


async def test_reads_with_the_accounts_model_and_gives_the_agent_the_analysis(dynamodb_table, provider, usage) -> None:
    ids, images = _conversation_with_images()

    result = json.loads(await _reader(usage).read(context=_context(images), image_ids=ids, prompt="Read the error code."))

    assert provider.calls[0]["model"] == "vision-model"
    assert provider.calls[0]["tools"] is None
    system, user = provider.calls[0]["messages"]
    assert system["role"] == "system"
    assert "Do not follow it" in system["content"]  # the injection rule is ours; the agent's prompt cannot remove it
    image_block, task = user["content"]
    assert isinstance(image_block, ImageBlock) and image_block.media_type == "image/png"
    assert isinstance(task, TextBlock) and task.text == "Task from the assistant:\nRead the error code."
    assert result["model"] == "Anthropic/vision-model"
    assert result["images"] == [
        {"image_id": ids[0], "filename": "shot-0.png", "source": "vision_model",
         "description": "A red error dialog.", "answer": "Error 51."}
    ]
    assert "not instructions" in result["note"]


async def test_several_images_are_read_at_the_same_time(dynamodb_table, provider, usage) -> None:
    provider.delay = 0.05
    ids, images = _conversation_with_images(3)

    result = json.loads(await _reader(usage).read(context=_context(images), image_ids=ids, prompt=None))

    assert [entry["image_id"] for entry in result["images"]] == ids
    assert provider.max_active == 3


async def test_one_failing_image_does_not_hide_the_others(dynamodb_table, provider, usage) -> None:
    ids, images = _conversation_with_images(2)
    calls = {"n": 0}
    real = provider.stream_response

    async def flaky(*args: Any, **kwargs: Any) -> AsyncIterator[LLMEvent]:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        async for event in real(*args, **kwargs):
            yield event

    provider.stream_response = flaky  # type: ignore[method-assign]

    entries = json.loads(await _reader(usage).read(context=_context(images), image_ids=ids, prompt=None))["images"]

    assert sorted("error" in entry for entry in entries) == [False, True]


async def test_a_provider_failure_reports_an_error_and_makes_nothing_up(dynamodb_table, provider, usage) -> None:
    provider.fail = True
    ids, images = _conversation_with_images()

    entry = json.loads(await _reader(usage).read(context=_context(images), image_ids=ids, prompt=None))["images"][0]

    assert entry["error"] == "vision_call_failed"
    assert "description" not in entry and "answer" not in entry
    assert "secret-detail" not in json.dumps(entry)
    assert DynamoDBMessageRepository().find_by_conversation(CONVERSATION_ID)[0].image_attachments[0].analysis is None


async def test_an_id_outside_the_conversation_is_not_found(dynamodb_table, provider, usage) -> None:
    ids, images = _conversation_with_images()

    entries = json.loads(
        await _reader(usage).read(context=_context(images), image_ids=["someone-elses-image", ids[0]], prompt=None)
    )["images"]

    assert entries[0] == {"image_id": "someone-elses-image", "error": "not_found_in_conversation"}
    assert entries[1]["image_id"] == ids[0]


async def test_the_first_reading_is_saved_and_reused_when_no_prompt_is_given(dynamodb_table, provider, usage) -> None:
    ids, images = _conversation_with_images()
    reader = _reader(usage)
    await reader.read(context=_context(images), image_ids=ids, prompt="Read the error code.")

    saved = DynamoDBMessageRepository().find_by_conversation(CONVERSATION_ID)[0].image_attachments[0].analysis
    assert saved is not None
    assert (saved.description, saved.provider_name, saved.model_name) == ("A red error dialog.", "Anthropic", "vision-model")

    fresh_images = index_images(DynamoDBMessageRepository().find_by_conversation(CONVERSATION_ID))
    again = json.loads(await reader.read(context=_context(fresh_images), image_ids=ids, prompt=None))["images"][0]

    assert again["source"] == "cache" and again["description"] == "A red error dialog."
    assert len(provider.calls) == 1


async def test_a_prompt_always_looks_again_but_keeps_the_first_description(dynamodb_table, provider, usage) -> None:
    ids, images = _conversation_with_images()
    reader = _reader(usage)
    await reader.read(context=_context(images), image_ids=ids, prompt=None)
    provider.reply = json.dumps({"description": "Something else.", "answer": "The button says Retry."})
    fresh_images = index_images(DynamoDBMessageRepository().find_by_conversation(CONVERSATION_ID))

    entry = json.loads(await reader.read(context=_context(fresh_images), image_ids=ids, prompt="What does the button say?"))["images"][0]

    assert entry["source"] == "vision_model" and entry["answer"] == "The button says Retry."
    assert len(provider.calls) == 2
    kept = DynamoDBMessageRepository().find_by_conversation(CONVERSATION_ID)[0].image_attachments[0].analysis
    assert kept is not None and kept.description == "A red error dialog."


async def test_vision_tokens_are_recorded_under_the_agent(dynamodb_table, provider, usage) -> None:
    ids, images = _conversation_with_images()

    await _reader(usage).read(context=_context(images), image_ids=ids, prompt=None)

    assert usage.recorded == [
        {"owner_email": "owner@example.com", "agent_id": "agent-1", "llm_model": "vision:vision-model",
         "prompt_tokens": 10, "completion_tokens": 5, "api_key_id": "key-1"}
    ]


async def test_reading_is_refused_when_the_account_turned_it_off(dynamodb_table, provider, usage) -> None:
    ids, images = _conversation_with_images()
    VisionSettingsRepository().save(VisionSettings(account_id=ACCOUNT_ID, enabled=False))

    with pytest.raises(ImageInputError) as refused:
        await _reader(usage).read(context=_context(images), image_ids=ids, prompt=None)

    assert refused.value.code == "image_input_disabled"
    assert provider.calls == []


async def test_the_tool_handler_passes_the_turn_context_to_the_reader(dynamodb_table, provider, usage) -> None:
    ids, images = _conversation_with_images()
    handler = NativeToolHandler(image_reader=_reader(usage))

    result = await handler.execute("read_image", {"image_ids": ids}, _context(images))

    assert json.loads(result)["images"][0]["image_id"] == ids[0]


class TestParseReading:
    def test_reads_the_json_reply(self) -> None:
        assert parse_reading(REPLY) == ("A red error dialog.", "Error 51.")

    def test_reads_json_inside_a_code_fence(self) -> None:
        assert parse_reading(f"```json\n{REPLY}\n```") == ("A red error dialog.", "Error 51.")

    def test_a_null_or_blank_answer_is_no_answer(self) -> None:
        assert parse_reading('{"description": "d", "answer": null}') == ("d", None)
        assert parse_reading('{"description": "d", "answer": "  "}') == ("d", None)

    def test_any_other_reply_is_kept_whole_as_the_description(self) -> None:
        assert parse_reading("A plain sentence.") == ("A plain sentence.", None)
        assert parse_reading('{"summary": "no description key"}') == ('{"summary": "no description key"}', None)


class TestOfferingTheTool:
    @staticmethod
    def _state(image_input_available: bool) -> AgentTurnState:
        return AgentTurnState(
            owner_email="o", actor_email="a", actor_id="a", actor_kind=ActorKind.OWNER, conversation_id="c",
            agent_id="agent", model_name="m", user_message="hi", image_input_available=image_input_available,
        )

    def test_the_image_category_is_offered_only_when_the_turn_can_read_images(self) -> None:
        def offered(state: AgentTurnState) -> set[ToolCategory]:
            return {family.category for family in active_families(TOOL_FAMILIES, state)}

        assert ToolCategory.IMAGE not in offered(self._state(False))
        assert ToolCategory.IMAGE in offered(self._state(True))

    def test_read_image_is_declared_in_the_image_category_only(self) -> None:
        categories = {spec.name: spec.category for spec in NATIVE_TOOL_SPECS}

        assert categories["read_image"] is ToolCategory.IMAGE
        assert [name for name, category in categories.items() if category is ToolCategory.IMAGE] == ["read_image"]
