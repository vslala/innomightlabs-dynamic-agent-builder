from __future__ import annotations

from src.llm.providers.bedrock import BedrockProvider


def test_bedrock_provider_converts_canonical_messages() -> None:
    provider = BedrockProvider()

    converted = provider._convert_messages(
        [
            {"role": "system", "content": "Use tools carefully."},
            {"role": "user", "content": "List buckets"},
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "call_1",
                        "name": "run_aws",
                        "input": {"argv": ["s3api", "list-buckets"]},
                        "thought_signature": b"bedrock-signature",
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "call_1",
                        "content": '{"Buckets": []}',
                    }
                ],
            },
        ]
    )

    assert converted.system_prompt == "Use tools carefully."
    assert converted.messages == [
        {"role": "user", "content": [{"text": "List buckets"}]},
        {
            "role": "assistant",
            "content": [
                {
                    "toolUse": {
                        "toolUseId": "call_1",
                        "name": "run_aws",
                        "input": {"argv": ["s3api", "list-buckets"]},
                        "thoughtSignature": b"bedrock-signature",
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
                        "content": [{"text": '{"Buckets": []}'}],
                    }
                }
            ],
        },
    ]


def test_bedrock_provider_normalizes_function_tools() -> None:
    provider = BedrockProvider()

    tools = provider._normalize_tools(
        [
            {
                "type": "function",
                "name": "search",
                "description": "Search records",
                "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
            }
        ]
    )

    assert tools == [
        {
            "toolSpec": {
                "name": "search",
                "description": "Search records",
                "inputSchema": {
                    "json": {"type": "object", "properties": {"query": {"type": "string"}}}
                },
            }
        }
    ]
