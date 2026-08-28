from google.genai import types

from src.crypto import encrypt
from src.llm.models import ModelsService
from src.llm.providers.base import LLMEvent
from src.llm.providers.factory import get_llm_provider
from src.llm.providers.gemini import GeminiProvider
from src.settings.models import ProviderSettings


class FakeGeminiModel:
    def __init__(self, name, display_name, supported_actions):
        self.name = name
        self.display_name = display_name
        self.supported_actions = supported_actions


def test_gemini_provider_converts_messages_and_tool_results():
    provider = GeminiProvider()

    converted = provider._convert_messages(
        [
            {"role": "system", "content": "Be concise."},
            {"role": "user", "content": "Check alex@example.com"},
            {
                "role": "assistant",
                "content": [
                    {
                        "toolUse": {
                            "toolUseId": "call_1",
                            "name": "get_account_status",
                            "input": {"email": "alex@example.com"},
                            "thoughtSignature": b"gemini-signature",
                        }
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "toolResult": {
                            "toolUseId": "call_1",
                            "content": [{"text": '{"status": "active"}'}],
                        }
                    }
                ],
            },
        ]
    )

    assert converted.system_instruction == "Be concise."
    assert [content.role for content in converted.messages] == ["user", "model", "user"]
    assert converted.messages[0].parts[0].text == "Check alex@example.com"
    assert converted.messages[1].parts[0].function_call.name == "get_account_status"
    assert converted.messages[1].parts[0].function_call.args == {"email": "alex@example.com"}
    assert converted.messages[1].parts[0].thought_signature == b"gemini-signature"
    assert converted.messages[2].parts[0].function_response.name == "get_account_status"
    assert converted.messages[2].parts[0].function_response.response == {"status": "active"}


def test_gemini_provider_normalizes_function_and_custom_tools():
    provider = GeminiProvider()

    tools = provider._normalize_tools(
        [
            {
                "type": "function",
                "name": "search",
                "description": "Search records",
                "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
            },
            {
                "custom": {
                    "name": "remember",
                    "description": "Store memory",
                    "input_schema": {"type": "object", "properties": {}},
                }
            },
        ]
    )

    assert tools is not None
    declarations = tools[0].function_declarations
    assert declarations is not None
    assert [declaration.name for declaration in declarations] == ["search", "remember"]
    assert declarations[0].parameters_json_schema == {
        "type": "object",
        "properties": {"query": {"type": "string"}},
    }


def test_gemini_provider_extracts_text_and_tool_use_events_from_chunk():
    provider = GeminiProvider()
    function_call_part = types.Part.from_function_call(
        name="get_account_status",
        args={"email": "alex@example.com"},
    )
    function_call_part.thought_signature = b"gemini-signature"
    chunk = types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part.from_text(text="Hello"),
                        function_call_part,
                    ],
                )
            )
        ]
    )

    events = provider._events_from_chunk(chunk, set())

    assert events[0] == LLMEvent(type="text", content="Hello")
    assert events[1].type == "tool_use"
    assert events[1].tool_name == "get_account_status"
    assert events[1].tool_input == {"email": "alex@example.com"}
    assert events[1].tool_use_id.startswith("gemini-get_account_status-")
    assert events[1].thought_signature == b"gemini-signature"


def test_gemini_provider_factory_supports_gemini():
    provider = get_llm_provider("Gemini")

    assert isinstance(provider, GeminiProvider)


def test_gemini_models_are_loaded_from_google_genai(monkeypatch):
    captured = {}

    class FakeModels:
        def list(self, config):
            captured["config"] = config
            return [
                FakeGeminiModel("models/gemini-2.5-pro", "Gemini 2.5 Pro", ["generateContent"]),
                FakeGeminiModel("models/text-embedding-004", "Text Embedding 004", ["embedContent"]),
                FakeGeminiModel("models/gemini-2.5-flash", "Gemini 2.5 Flash", ["generateContent"]),
            ]

    class FakeClient:
        def __init__(self, api_key):
            captured["api_key"] = api_key
            self.models = FakeModels()

    monkeypatch.setattr("google.genai.Client", FakeClient)
    provider_settings = ProviderSettings(
        user_email="owner@example.com",
        provider_name="Gemini",
        encrypted_credentials=encrypt('{"api_key": "gemini-key"}'),
    )

    models = ModelsService().get_gemini_models(provider_settings)

    assert captured["api_key"] == "gemini-key"
    assert captured["config"] == {"page_size": 1000, "query_base": True}
    assert [model.model_name for model in models] == ["gemini-2.5-flash", "gemini-2.5-pro"]
    assert [model.display_name for model in models] == [
        "[Gemini] Gemini 2.5 Flash",
        "[Gemini] Gemini 2.5 Pro",
    ]


def test_gemini_models_fallback_when_live_list_fails(monkeypatch):
    class FailingClient:
        def __init__(self, api_key):
            raise RuntimeError("not available")

    monkeypatch.setattr("google.genai.Client", FailingClient)
    provider_settings = ProviderSettings(
        user_email="owner@example.com",
        provider_name="Gemini",
        encrypted_credentials=encrypt('{"api_key": "gemini-key"}'),
    )

    models = ModelsService().get_gemini_models(provider_settings)

    assert [model.model_name for model in models] == ["gemini-2.5-flash", "gemini-2.5-pro"]
