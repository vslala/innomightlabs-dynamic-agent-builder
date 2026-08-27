from __future__ import annotations

from src.llm.messages import TextBlock, ToolResultBlock, ToolUseBlock, normalize_messages, split_system_messages
from src.llm.tools import normalize_anthropic_tools, normalize_tool_definitions


def test_normalize_messages_accepts_internal_bedrock_style_blocks() -> None:
    messages = normalize_messages(
        [
            {"role": "system", "content": [{"text": "Be concise."}]},
            {"role": "assistant", "content": [{"text": "Checking."}]},
            {
                "role": "assistant",
                "content": [
                    {
                        "toolUse": {
                            "toolUseId": "call_1",
                            "name": "lookup",
                            "input": {"id": "123"},
                            "thoughtSignature": b"signature",
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
                            "content": [{"text": '{"ok": true}'}],
                        }
                    }
                ],
            },
        ]
    )

    system, conversation = split_system_messages(messages)

    assert system == "Be concise."
    assert conversation[0].content == [TextBlock(text="Checking.")]
    assert conversation[1].content == [
        ToolUseBlock(
            id="call_1",
            name="lookup",
            input={"id": "123"},
            thought_signature=b"signature",
        )
    ]
    assert conversation[2].content == [
        ToolResultBlock(tool_use_id="call_1", content='{"ok": true}')
    ]


def test_normalize_messages_accepts_anthropic_style_blocks() -> None:
    messages = normalize_messages(
        [
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "call_1",
                        "name": "lookup",
                        "input": {"id": "123"},
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "call_1",
                        "content": "found",
                    }
                ],
            },
        ]
    )

    assert messages[0].content == [ToolUseBlock(id="call_1", name="lookup", input={"id": "123"})]
    assert messages[1].content == [ToolResultBlock(tool_use_id="call_1", content="found")]


def test_normalize_tool_definitions_accepts_function_and_custom_shapes() -> None:
    tools = normalize_tool_definitions(
        [
            {
                "type": "function",
                "name": "search",
                "description": "Search records",
                "parameters": {"type": "object", "properties": {"q": {"type": "string"}}},
                "strict": True,
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

    assert [tool.name for tool in tools] == ["search", "remember"]
    assert tools[0].strict is True
    assert tools[0].to_openai()["parameters"] == {
        "type": "object",
        "properties": {"q": {"type": "string"}},
    }
    assert tools[1].to_anthropic()["input_schema"] == {"type": "object", "properties": {}}


def test_normalize_anthropic_tools_preserves_provider_native_tools() -> None:
    tools = normalize_anthropic_tools(
        [
            {"type": "web_search_20250305", "name": "web_search"},
            {"custom": {"name": "lookup", "input_schema": {"type": "object"}}},
        ]
    )

    assert tools == [
        {"type": "web_search_20250305", "name": "web_search"},
        {"name": "lookup", "description": "", "input_schema": {"type": "object"}},
    ]

