"""OpenAI with an API key: the public Responses API, its model list, and the settings wiring."""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from src.config.settings import DEFAULT_OPENAI_MODELS
from src.crypto import encrypt
from src.llm import models as llm_models
from src.llm.credentials import load_provider_credentials
from src.llm.models import find_model_source, models_service
from src.llm.providers import get_llm_provider
from src.llm.providers.openai_api import OpenAIAPIProvider
from src.settings.models import ProviderSettings
from tests.mock_data import TEST_USER_EMAIL


class FakeStreamResponse:
    def __init__(self, lines: list[str], status_code: int = 200, body: bytes = b""):
        self.headers = {"x-request-id": "req_123"}
        self.status_code = status_code
        self._lines = lines
        self._body = body

    @property
    def is_success(self) -> bool:
        return self.status_code < 400

    async def aiter_lines(self):
        for line in self._lines:
            yield line

    async def aread(self) -> bytes:
        return self._body


class FakeStreamContext:
    def __init__(self, response: FakeStreamResponse):
        self._response = response

    async def __aenter__(self):
        return self._response

    async def __aexit__(self, *exc_info):
        return False


def _fake_client(response: FakeStreamResponse, seen: list[dict]):
    class Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc_info):
            return False

        def stream(self, method, url, headers=None, json=None):
            seen.append({"url": url, "headers": headers, "json": json})
            return FakeStreamContext(response)

    return Client


def _sse(*events: dict) -> list[str]:
    return [f"data: {json.dumps(event)}" for event in events] + ["data: [DONE]"]


async def _events(monkeypatch, response: FakeStreamResponse, credentials=None, tools=None):
    seen: list[dict] = []
    monkeypatch.setattr("src.llm.providers.openai.httpx.AsyncClient", _fake_client(response, seen))
    events = [
        event
        async for event in OpenAIAPIProvider().stream_response(
            messages=[{"role": "system", "content": "Be terse."}, {"role": "user", "content": "Weather in Paris?"}],
            credentials={"api_key": "sk-test"} if credentials is None else credentials,
            tools=tools,
            model="gpt-5.5",
        )
    ]
    return events, seen


WEATHER_TOOL = {
    "type": "function",
    "name": "get_weather",
    "description": "Weather for a city",
    "parameters": {"type": "object", "properties": {"city": {"type": "string"}}},
}


class TestStreaming:
    async def test_calls_the_public_responses_api_with_the_users_key(self, monkeypatch):
        _, [request] = await _events(monkeypatch, FakeStreamResponse(_sse({"type": "response.completed", "response": {}})))

        assert request["url"] == "https://api.openai.com/v1/responses"
        assert request["headers"]["Authorization"] == "Bearer sk-test"
        assert request["headers"]["Accept"] == "text/event-stream"
        # Nothing ChatGPT-account specific leaks onto the public API.
        assert not {"ChatGPT-Account-ID", "session-id", "originator"} & set(request["headers"])

    async def test_sends_the_same_responses_envelope_as_the_codex_provider(self, monkeypatch):
        _, [request] = await _events(
            monkeypatch, FakeStreamResponse(_sse({"type": "response.completed", "response": {}})), tools=[WEATHER_TOOL]
        )

        body = request["json"]
        assert body["model"] == "gpt-5.5"
        assert body["instructions"] == "Be terse."
        assert body["input"] == [{"role": "user", "content": [{"type": "input_text", "text": "Weather in Paris?"}]}]
        assert [tool["name"] for tool in body["tools"]] == ["get_weather"]
        assert body["stream"] is True
        assert body["store"] is False
        assert body["parallel_tool_calls"] is False

    async def test_streams_text_a_tool_call_usage_and_stop(self, monkeypatch):
        events, _ = await _events(
            monkeypatch,
            FakeStreamResponse(
                _sse(
                    {"type": "response.output_text.delta", "delta": "Checking"},
                    {
                        "type": "response.output_item.added",
                        "item": {"type": "function_call", "id": "fc_1", "call_id": "call_1", "name": "get_weather"},
                    },
                    {"type": "response.function_call_arguments.delta", "item_id": "fc_1", "delta": '{"city":'},
                    {"type": "response.function_call_arguments.delta", "item_id": "fc_1", "delta": '"Paris"}'},
                    {"type": "response.function_call_arguments.done", "item_id": "fc_1"},
                    {"type": "response.completed", "response": {"usage": {"input_tokens": 40, "output_tokens": 9}}},
                )
            ),
            tools=[WEATHER_TOOL],
        )

        assert [event.type for event in events] == ["text", "tool_use", "usage", "stop"]
        assert events[0].content == "Checking"
        assert (events[1].tool_use_id, events[1].tool_name, events[1].tool_input) == (
            "call_1",
            "get_weather",
            {"city": "Paris"},
        )
        assert (events[2].prompt_tokens, events[2].completion_tokens) == (40, 9)
        assert events[3].content == "end_turn"

    async def test_an_account_out_of_credit_raises_with_openais_reason(self, monkeypatch):
        """The public API accepts the request, then reports exhausted credit as an in-stream error event."""
        with pytest.raises(RuntimeError, match="credit_balance_exhausted"):
            await _events(
                monkeypatch,
                FakeStreamResponse(
                    _sse(
                        {
                            "type": "error",
                            "error": {"type": "insufficient_quota", "code": "credit_balance_exhausted"},
                        }
                    )
                ),
            )

    async def test_a_rejected_key_raises_naming_the_api_endpoint(self, monkeypatch):
        with pytest.raises(RuntimeError, match=r"OpenAI API responses error \(401, request_id=req_123\)"):
            await _events(monkeypatch, FakeStreamResponse([], status_code=401, body=b'{"error": "invalid_api_key"}'))

    async def test_a_missing_key_fails_before_any_request(self, monkeypatch):
        with pytest.raises(ValueError, match="api_key"):
            await _events(monkeypatch, FakeStreamResponse([]), credentials={})


#: A slice of a real `GET /v1/models` payload, `created` timestamps included.
MODELS_PAYLOAD = {
    "object": "list",
    "data": [
        {"id": "gpt-4.1", "created": 1744316542, "object": "model", "owned_by": "system"},
        {"id": "gpt-4.1-2025-04-14", "created": 1744315746, "object": "model", "owned_by": "system"},
        {"id": "gpt-5.5", "created": 1776900000, "object": "model", "owned_by": "system"},
        {"id": "gpt-5.5-pro", "created": 1776900001, "object": "model", "owned_by": "system"},
        {"id": "o4-mini", "created": 1744225351, "object": "model", "owned_by": "system"},
        {"id": "gpt-4o", "created": 1715367049, "object": "model", "owned_by": "system"},
        {"id": "gpt-4", "created": 1687882411, "object": "model", "owned_by": "openai"},
        {"id": "gpt-4-turbo", "created": 1712361441, "object": "model", "owned_by": "system"},
        {"id": "gpt-3.5-turbo-0125", "created": 1706048358, "object": "model", "owned_by": "system"},
        {"id": "text-embedding-3-small", "created": 1705948997, "object": "model", "owned_by": "system"},
        {"id": "gpt-4o-mini-tts", "created": 1742403959, "object": "model", "owned_by": "system"},
        {"id": "gpt-realtime", "created": 1756271701, "object": "model", "owned_by": "system"},
        {"id": "gpt-image-2", "created": 1776700000, "object": "model", "owned_by": "system"},
        {"id": "gpt-5-search-api", "created": 1760043960, "object": "model", "owned_by": "system"},
        {"id": "gpt-5.1-codex", "created": 1762988221, "object": "model", "owned_by": "system"},
        {"id": "gpt-5-chat-latest", "created": 1754073306, "object": "model", "owned_by": "system"},
        {"id": "whisper-1", "created": 1677532384, "object": "model", "owned_by": "openai-internal"},
        {"id": "davinci-002", "created": 1692634301, "object": "model", "owned_by": "system"},
    ],
}


def _provider_settings(**credentials) -> ProviderSettings:
    return ProviderSettings(
        user_email=TEST_USER_EMAIL,
        provider_name="OpenAIAPI",
        encrypted_credentials=encrypt(json.dumps(credentials or {"api_key": "sk-test"})),
    )


def _models_response(monkeypatch, payload=MODELS_PAYLOAD, status_code: int = 200) -> list[httpx.Request]:
    seen: list[httpx.Request] = []

    def fake_get(url, headers=None, timeout=None):
        request = httpx.Request("GET", url, headers=headers)
        seen.append(request)
        return httpx.Response(status_code, json=payload, request=request)

    monkeypatch.setattr("src.llm.models.httpx.get", fake_get)
    return seen


class TestModelDiscovery:
    @pytest.fixture(autouse=True)
    def configured_models(self, monkeypatch):
        monkeypatch.setattr(llm_models.settings, "openai_models", DEFAULT_OPENAI_MODELS.copy())

    def test_lists_only_chat_models_newest_first(self, monkeypatch):
        seen = _models_response(monkeypatch)

        models = models_service.get_openai_api_models(_provider_settings())

        assert [model.model_name for model in models] == ["gpt-5.5", "gpt-4.1", "o4-mini", "gpt-4o"]
        assert models[0].display_name == "[OpenAI API] gpt-5.5"
        assert {model.provider for model in models} == {"openai_api"}
        [request] = seen
        assert str(request.url) == "https://api.openai.com/v1/models"
        assert request.headers["Authorization"] == "Bearer sk-test"

    @pytest.mark.parametrize("status_code", [401, 500])
    def test_falls_back_to_the_configured_models_when_the_list_cant_be_read(self, monkeypatch, status_code):
        _models_response(monkeypatch, payload={"error": {}}, status_code=status_code)

        models = models_service.get_openai_api_models(_provider_settings())

        assert [model.model_name for model in models] == DEFAULT_OPENAI_MODELS

    def test_falls_back_on_an_unexpected_payload(self, monkeypatch):
        _models_response(monkeypatch, payload={"data": "nope"})

        assert [m.model_name for m in models_service.get_openai_api_models(_provider_settings())] == DEFAULT_OPENAI_MODELS

    def test_is_a_configurable_model_source(self):
        source = find_model_source("openaiapi")

        assert source is not None and source.provider_name == "OpenAIAPI"


class TestWiring:
    def test_the_factory_returns_the_api_key_provider(self):
        assert isinstance(get_llm_provider("OpenAIAPI"), OpenAIAPIProvider)

    async def test_stored_credentials_load_as_the_saved_key(self):
        credentials = await load_provider_credentials(
            provider_name="OpenAIAPI",
            provider_settings=_provider_settings(api_key="sk-test"),
            provider_settings_repo=None,  # type: ignore[arg-type]  # the static path never touches it
        )

        assert credentials == {"api_key": "sk-test"}

    def test_is_offered_with_an_api_key_form(self, test_client: TestClient, auth_headers: dict):
        response = test_client.get("/settings/providers", headers=auth_headers)

        provider = next(p for p in response.json() if p["provider_name"] == "OpenAIAPI")
        assert [field["name"] for field in provider["form"]["form_inputs"]] == ["api_key"]
        assert provider["form"]["form_inputs"][0]["input_type"] == "password"

    def test_saves_a_key_without_echoing_it_back(self, test_client: TestClient, auth_headers: dict):
        saved = test_client.post("/settings/providers/OpenAIAPI", json={"api_key": "sk-test"}, headers=auth_headers)
        fetched = test_client.get("/settings/providers/OpenAIAPI", headers=auth_headers)

        assert saved.status_code == 201
        assert fetched.json()["is_configured"] is True
        assert "sk-test" not in fetched.text

    def test_the_key_is_required(self, test_client: TestClient, auth_headers: dict):
        response = test_client.post("/settings/providers/OpenAIAPI", json={"api_key": ""}, headers=auth_headers)

        assert response.status_code == 400
