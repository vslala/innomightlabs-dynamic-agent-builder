from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from src.llm.ollama import OllamaConnection
from src.vision import capabilities
from src.vision.capabilities import (
    anthropic_reads_images,
    bedrock_reads_images,
    codex_reads_images,
    gemini_reads_images,
    ollama_reads_images,
    openai_api_reads_images,
    understanding,
)


def test_anthropic_trusts_the_reported_capability() -> None:
    model = SimpleNamespace(id="claude-x", capabilities=SimpleNamespace(image_input=SimpleNamespace(supported=False)))

    assert anthropic_reads_images(model) is False


def test_anthropic_falls_back_to_the_claude_family_when_capabilities_are_null() -> None:
    assert anthropic_reads_images(SimpleNamespace(id="claude-sonnet-4", capabilities=None)) is True


def test_bedrock_reads_the_input_modalities() -> None:
    assert bedrock_reads_images({"inputModalities": ["TEXT", "IMAGE"]}) is True
    assert bedrock_reads_images({"inputModalities": ["TEXT"]}) is False
    assert bedrock_reads_images({}) is False


def test_codex_reads_modalities_and_assumes_images_when_missing() -> None:
    assert codex_reads_images({"input_modalities": ["text"]}) is False
    assert codex_reads_images({"input_modalities": ["text", "image"]}) is True
    assert codex_reads_images({}) is True


@pytest.mark.parametrize(("model_id", "expected"), [("gpt-5.5", True), ("gpt-4o", True), ("o3-mini", True), ("gpt-3.5", False)])
def test_openai_api_models_are_matched_by_family(model_id: str, expected: bool) -> None:
    assert openai_api_reads_images(model_id) is expected


@pytest.mark.parametrize(
    ("model_id", "expected"),
    [("gemini-2.5-flash", True), ("gemini-embedding-001", False), ("imagen-4", False), ("gemma-3", False)],
)
def test_gemini_chat_models_read_images(model_id: str, expected: bool) -> None:
    assert gemini_reads_images(model_id) is expected


def test_understanding_is_the_capability_string_or_nothing() -> None:
    assert understanding(True) == ["image_understanding"]
    assert understanding(False) == []


def test_ollama_asks_each_model_once_and_reads_vision(monkeypatch: pytest.MonkeyPatch) -> None:
    capabilities._ollama_cache.clear()
    calls: list[str] = []

    def fake_post(url: str, json: dict, **_: object) -> httpx.Response:
        calls.append(json["model"])
        reply = {"capabilities": ["completion", "vision"] if json["model"] == "llava" else ["completion"]}
        return httpx.Response(200, json=reply, request=httpx.Request("POST", url))

    monkeypatch.setattr(capabilities.httpx, "post", fake_post)
    connection = OllamaConnection(base_url="http://ollama.test:11434")

    assert ollama_reads_images(connection, "llava") is True
    assert ollama_reads_images(connection, "llama3") is False
    assert ollama_reads_images(connection, "llava") is True
    assert calls == ["llava", "llama3"]


def test_ollama_that_cannot_answer_is_not_vision(monkeypatch: pytest.MonkeyPatch) -> None:
    capabilities._ollama_cache.clear()

    def failing_post(*_: object, **__: object) -> httpx.Response:
        raise httpx.ConnectError("down")

    monkeypatch.setattr(capabilities.httpx, "post", failing_post)

    assert ollama_reads_images(OllamaConnection(base_url="http://down.test"), "llava") is False
