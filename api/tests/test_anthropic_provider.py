from __future__ import annotations

from src.llm.providers.anthropic import AnthropicProvider


def test_anthropic_provider_adds_type_to_bedrock_style_text_blocks() -> None:
    provider = AnthropicProvider()

    system, messages = provider._extract_system_and_messages(
        [
            {"role": "system", "content": [{"text": "System prompt"}]},
            {
                "role": "assistant",
                "content": [{"text": "I will inspect that."}],
            },
        ]
    )

    assert system == "System prompt"
    assert messages == [
        {
            "role": "assistant",
            "content": [{"type": "text", "text": "I will inspect that."}],
        }
    ]


def test_anthropic_provider_converts_bedrock_tool_blocks() -> None:
    provider = AnthropicProvider()

    _system, messages = provider._extract_system_and_messages(
        [
            {
                "role": "assistant",
                "content": [
                    {
                        "toolUse": {
                            "toolUseId": "tool_123",
                            "name": "execute_skill_action",
                            "input": {"skill_id": "aws_cli"},
                        }
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "toolResult": {
                            "toolUseId": "tool_123",
                            "content": [{"text": '{"ok": true}'}],
                        }
                    }
                ],
            },
        ]
    )

    assert messages == [
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "tool_123",
                    "name": "execute_skill_action",
                    "input": {"skill_id": "aws_cli"},
                }
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "tool_123",
                    "content": '{"ok": true}',
                }
            ],
        },
    ]

