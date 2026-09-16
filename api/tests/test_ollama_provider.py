import json

import httpx
import pytest

from src.llm.ollama import OllamaConnection, merge_thinking_override
from src.llm.providers.factory import get_llm_provider
from src.llm.providers.ollama import OllamaProvider


SAMPLE_TOOL = {
    "type": "function",
    "name": "search",
    "description": "Search records",
    "parameters": {"type": "object", "properties": {"q": {"type": "string"}}},
}

CREDENTIALS = {"endpoint_url": "http://ollama.test:11434", "api_key": ""}


def _stream_transport(lines: list[str], status_code: int = 200) -> httpx.MockTransport:
    """A transport replaying newline-delimited JSON chunks like Ollama does."""
    body = "".join(f"{line}\n" for line in lines).encode()
    return httpx.MockTransport(lambda request: httpx.Response(status_code, content=body))


async def _collect(provider: OllamaProvider, **kwargs) -> list:
    return [event async for event in provider.stream_response(**kwargs)]


class TestOllamaConnection:
    def test_strips_trailing_slash_and_omits_auth_without_a_key(self):
        connection = OllamaConnection.from_credentials({"endpoint_url": "http://localhost:11434/"})

        assert connection.base_url == "http://localhost:11434"
        assert connection.api_key is None
        assert connection.headers == {"Content-Type": "application/json"}

    def test_sends_bearer_auth_when_a_key_is_configured(self):
        connection = OllamaConnection.from_credentials(
            {"endpoint_url": "https://ollama.example.com", "api_key": "  secret-token  "}
        )

        assert connection.headers["Authorization"] == "Bearer secret-token"

    @pytest.mark.parametrize("blank", ["", "   ", None])
    def test_blank_api_key_is_treated_as_unauthenticated(self, blank):
        connection = OllamaConnection.from_credentials(
            {"endpoint_url": "http://localhost:11434", "api_key": blank}
        )

        assert connection.api_key is None
        assert "Authorization" not in connection.headers

    def test_missing_endpoint_url_is_rejected(self):
        with pytest.raises(ValueError, match="endpoint_url"):
            OllamaConnection.from_credentials({"api_key": "token"})

    @pytest.mark.parametrize(
        "endpoint_url",
        ["localhost:11434", "ftp://localhost:11434", "file:///etc/passwd", "not a url"],
    )
    def test_non_http_endpoints_are_rejected(self, endpoint_url):
        with pytest.raises(ValueError, match="absolute http"):
            OllamaConnection.from_credentials({"endpoint_url": endpoint_url})


class TestMergeThinkingOverride:
    @pytest.mark.parametrize("thinking_mode,expected", [("enabled", True), ("disabled", False)])
    def test_a_chosen_mode_adds_a_think_key(self, thinking_mode, expected):
        merged = merge_thinking_override({"endpoint_url": "http://x"}, thinking_mode=thinking_mode)

        assert merged == {"endpoint_url": "http://x", "think": expected}

    @pytest.mark.parametrize("thinking_mode", [None, "default", "", "garbage"])
    def test_anything_else_leaves_credentials_untouched(self, thinking_mode):
        credentials = {"endpoint_url": "http://x"}

        merged = merge_thinking_override(credentials, thinking_mode=thinking_mode)

        assert merged == credentials
        assert "think" not in merged

    def test_does_not_mutate_the_input_dict(self):
        credentials = {"endpoint_url": "http://x"}

        merge_thinking_override(credentials, thinking_mode="enabled")

        assert credentials == {"endpoint_url": "http://x"}


class TestOllamaRequestConversion:
    def test_converts_a_tool_round_trip_into_ollama_message_roles(self):
        provider = OllamaProvider()

        converted = provider._convert_messages(
            [
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "Find X"},
                {
                    "role": "assistant",
                    "content": [
                        {"text": "Looking that up"},
                        {"toolUse": {"toolUseId": "t1", "name": "search", "input": {"q": "X"}}},
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {"toolResult": {"toolUseId": "t1", "content": [{"text": "found it"}]}}
                    ],
                },
            ]
        )

        assert converted == [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Find X"},
            {
                "role": "assistant",
                "content": "Looking that up",
                "tool_calls": [{"function": {"name": "search", "arguments": {"q": "X"}}}],
            },
            # Results become their own `tool` message, named from the prior call.
            {"role": "tool", "content": "found it", "tool_name": "search"},
        ]

    def test_request_body_nests_tools_under_function(self):
        provider = OllamaProvider()

        body = provider._request_body(
            provider._request_input("llama3.1:8b", [{"role": "user", "content": "hi"}], [SAMPLE_TOOL])
        )

        assert body["model"] == "llama3.1:8b"
        assert body["stream"] is True
        assert body["tools"] == [
            {
                "type": "function",
                "function": {
                    "name": "search",
                    "description": "Search records",
                    "parameters": {"type": "object", "properties": {"q": {"type": "string"}}},
                },
            }
        ]

    def test_request_body_omits_tools_when_none_are_available(self):
        provider = OllamaProvider()

        body = provider._request_body(
            provider._request_input("llama3.1:8b", [{"role": "user", "content": "hi"}], None)
        )

        assert "tools" not in body

    @pytest.mark.parametrize("think", [True, False])
    def test_request_body_includes_an_explicit_think_choice(self, think):
        provider = OllamaProvider()

        body = provider._request_body(
            provider._request_input("llama3.1:8b", [{"role": "user", "content": "hi"}], None, think=think)
        )

        assert body["think"] is think

    def test_request_body_omits_think_when_unset(self):
        provider = OllamaProvider()

        body = provider._request_body(
            provider._request_input("llama3.1:8b", [{"role": "user", "content": "hi"}], None, think=None)
        )

        assert "think" not in body


class TestOllamaEventExtraction:
    def test_usage_is_read_from_the_final_chunk_and_never_raises(self):
        assert OllamaProvider._extract_usage({"prompt_eval_count": 26, "eval_count": 8}) == (26, 8)
        assert OllamaProvider._extract_usage({}) == (0, 0)
        assert OllamaProvider._extract_usage({"prompt_eval_count": None}) == (0, 0)
        assert OllamaProvider._extract_usage({"prompt_eval_count": "nope"}) == (0, 0)

    def test_synthesizes_unique_tool_call_ids_positionally(self):
        message = {
            "tool_calls": [
                {"function": {"name": "search", "arguments": {"q": "a"}}},
                {"function": {"name": "search", "arguments": {"q": "a"}}},
            ]
        }

        events = OllamaProvider._tool_use_events(message, id_offset=0)

        assert [event.tool_name for event in events] == ["search", "search"]
        # Identical repeated calls must still get distinct ids, since the agent
        # loop keys tool results off them.
        assert len({event.tool_use_id for event in events}) == 2
        assert all(event.tool_use_id for event in events)

    def test_prefers_a_server_supplied_tool_call_id(self):
        message = {"tool_calls": [{"id": "call-abc", "function": {"name": "search", "arguments": {}}}]}

        events = OllamaProvider._tool_use_events(message, id_offset=3)

        assert events[0].tool_use_id == "call-abc"

    def test_accepts_tool_arguments_as_object_or_json_string(self):
        assert OllamaProvider._tool_arguments({"q": "x"}) == {"q": "x"}
        assert OllamaProvider._tool_arguments('{"q": "x"}') == {"q": "x"}
        assert OllamaProvider._tool_arguments("not json") == {}
        assert OllamaProvider._tool_arguments("[1, 2]") == {}
        assert OllamaProvider._tool_arguments(None) == {}

    def test_malformed_tool_calls_are_skipped(self):
        message = {"tool_calls": ["nope", {}, {"function": {"name": ""}}, {"function": "bad"}]}

        assert OllamaProvider._tool_use_events(message, id_offset=0) == []


class TestOllamaStreaming:
    async def test_a_credentials_think_flag_reaches_the_outgoing_request_body(self):
        seen_bodies: list[dict] = []

        def capture(request: httpx.Request) -> httpx.Response:
            seen_bodies.append(json.loads(request.content))
            response_body = json.dumps({"message": {"role": "assistant", "content": "ok"}, "done": True}) + "\n"
            return httpx.Response(200, content=response_body.encode())

        provider = OllamaProvider(transport=httpx.MockTransport(capture))

        await _collect(
            provider,
            messages=[{"role": "user", "content": "hi"}],
            credentials={**CREDENTIALS, "think": False},
            model="llama3.1:8b",
        )

        assert seen_bodies[0]["think"] is False

    async def test_a_non_bool_think_credential_is_ignored(self):
        seen_bodies: list[dict] = []

        def capture(request: httpx.Request) -> httpx.Response:
            seen_bodies.append(json.loads(request.content))
            response_body = json.dumps({"message": {"role": "assistant", "content": "ok"}, "done": True}) + "\n"
            return httpx.Response(200, content=response_body.encode())

        provider = OllamaProvider(transport=httpx.MockTransport(capture))

        await _collect(
            provider,
            messages=[{"role": "user", "content": "hi"}],
            credentials={**CREDENTIALS, "think": "yes please"},
            model="llama3.1:8b",
        )

        assert "think" not in seen_bodies[0]

    async def test_streams_text_then_usage_then_stop(self):
        transport = _stream_transport(
            [
                json.dumps({"message": {"role": "assistant", "content": "Hello"}, "done": False}),
                json.dumps({"message": {"role": "assistant", "content": " there"}, "done": False}),
                json.dumps(
                    {
                        "message": {"role": "assistant", "content": ""},
                        "done": True,
                        "done_reason": "stop",
                        "prompt_eval_count": 26,
                        "eval_count": 8,
                    }
                ),
            ]
        )

        events = await _collect(
            OllamaProvider(transport=transport),
            messages=[{"role": "user", "content": "hi"}],
            credentials=CREDENTIALS,
            model="llama3.1:8b",
        )

        assert [(event.type, event.content) for event in events] == [
            ("text", "Hello"),
            ("text", " there"),
            ("usage", ""),
            ("stop", "stop"),
        ]
        assert events[2].prompt_tokens == 26
        assert events[2].completion_tokens == 8

    async def test_streams_a_tool_call(self):
        transport = _stream_transport(
            [
                json.dumps(
                    {
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [
                                {"function": {"name": "search", "arguments": {"q": "X"}}}
                            ],
                        },
                        "done": False,
                    }
                ),
                json.dumps({"message": {"role": "assistant", "content": ""}, "done": True}),
            ]
        )

        events = await _collect(
            OllamaProvider(transport=transport),
            messages=[{"role": "user", "content": "find X"}],
            credentials=CREDENTIALS,
            tools=[SAMPLE_TOOL],
            model="llama3.1:8b",
        )

        tool_events = [event for event in events if event.type == "tool_use"]
        assert len(tool_events) == 1
        assert tool_events[0].tool_name == "search"
        assert tool_events[0].tool_input == {"q": "X"}
        assert tool_events[0].tool_use_id

    async def test_malformed_lines_are_skipped_without_breaking_the_stream(self):
        transport = _stream_transport(
            [
                "not json at all",
                "[1, 2, 3]",
                json.dumps({"message": {"role": "assistant", "content": "still fine"}}),
                json.dumps({"done": True}),
            ]
        )

        events = await _collect(
            OllamaProvider(transport=transport),
            messages=[{"role": "user", "content": "hi"}],
            credentials=CREDENTIALS,
            model="llama3.1:8b",
        )

        assert [event.type for event in events] == ["text", "usage", "stop"]

    async def test_an_error_chunk_aborts_the_stream(self):
        transport = _stream_transport([json.dumps({"error": "model 'ghost' not found"})])

        with pytest.raises(RuntimeError, match="ghost"):
            await _collect(
                OllamaProvider(transport=transport),
                messages=[{"role": "user", "content": "hi"}],
                credentials=CREDENTIALS,
                model="ghost",
            )

    @pytest.mark.parametrize(
        ("status_code", "expected_message"),
        [
            (401, "rejected the request"),
            (403, "rejected the request"),
            (404, "does not have model"),
            (500, "HTTP 500"),
        ],
    )
    async def test_http_failures_map_to_actionable_messages(self, status_code, expected_message):
        transport = _stream_transport(["upstream failed"], status_code=status_code)

        with pytest.raises(RuntimeError, match=expected_message):
            await _collect(
                OllamaProvider(transport=transport),
                messages=[{"role": "user", "content": "hi"}],
                credentials=CREDENTIALS,
                model="llama3.1:8b",
            )

    async def test_an_unreachable_endpoint_reports_the_endpoint(self):
        def refuse(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        with pytest.raises(RuntimeError, match="Could not reach the Ollama endpoint"):
            await _collect(
                OllamaProvider(transport=httpx.MockTransport(refuse)),
                messages=[{"role": "user", "content": "hi"}],
                credentials=CREDENTIALS,
                model="llama3.1:8b",
            )

    @pytest.mark.parametrize("model", [None, "", "   "])
    async def test_a_missing_model_is_rejected_before_any_request(self, model):
        with pytest.raises(ValueError, match="requires an explicit model"):
            await _collect(
                OllamaProvider(),
                messages=[{"role": "user", "content": "hi"}],
                credentials=CREDENTIALS,
                model=model,
            )

    async def test_a_missing_endpoint_is_rejected_before_any_request(self):
        with pytest.raises(ValueError, match="endpoint_url"):
            await _collect(
                OllamaProvider(),
                messages=[{"role": "user", "content": "hi"}],
                credentials={},
                model="llama3.1:8b",
            )


def test_factory_resolves_the_ollama_provider():
    assert isinstance(get_llm_provider("Ollama"), OllamaProvider)


async def test_accepts_the_agent_loops_positional_call_convention():
    # src.agents.agentic_loop calls provider.stream_response(context, credentials,
    # tools, model) positionally, so no parameter may become keyword-only.
    transport = _stream_transport(
        [json.dumps({"message": {"role": "assistant", "content": "ok"}, "done": True})]
    )
    provider = OllamaProvider(transport=transport)

    events = [
        event
        async for event in provider.stream_response(
            [{"role": "user", "content": "hi"}],
            CREDENTIALS,
            [SAMPLE_TOOL],
            "llama3.1:8b",
        )
    ]

    assert [event.type for event in events] == ["text", "usage", "stop"]
