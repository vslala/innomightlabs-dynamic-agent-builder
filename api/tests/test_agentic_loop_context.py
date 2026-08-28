from dataclasses import dataclass
from typing import Any

from src.agents.loop_context import (
    append_assistant_tool_uses,
    append_user_tool_results,
    tool_result_block,
    tool_use_block,
)


@dataclass
class FakeToolEvent:
    tool_name: str
    tool_input: dict[str, Any]
    tool_use_id: str
    thought_signature: bytes | None = None


def test_append_assistant_tool_uses_preserves_current_context_shape():
    context = []
    tool_event = FakeToolEvent(
        tool_name="lookup_customer",
        tool_input={"customer_id": "cus_123"},
        tool_use_id="tooluse_1",
    )

    append_assistant_tool_uses(
        context,
        iteration_text="I will check.",
        tool_events=[tool_event],
    )

    assert context == [
        {
            "role": "assistant",
            "content": [
                {"text": "I will check."},
                {
                    "toolUse": {
                        "toolUseId": "tooluse_1",
                        "name": "lookup_customer",
                        "input": {"customer_id": "cus_123"},
                    }
                },
            ],
        }
    ]


def test_tool_use_block_preserves_thought_signature():
    tool_event = FakeToolEvent(
        tool_name="lookup_customer",
        tool_input={"customer_id": "cus_123"},
        tool_use_id="tooluse_1",
        thought_signature=b"gemini-signature",
    )

    assert tool_use_block(tool_event) == {
        "toolUse": {
            "toolUseId": "tooluse_1",
            "name": "lookup_customer",
            "input": {"customer_id": "cus_123"},
            "thoughtSignature": b"gemini-signature",
        }
    }


def test_append_user_tool_results_preserves_current_context_shape():
    context = []
    result = tool_result_block("tooluse_1", "customer found")

    append_user_tool_results(context, [result])

    assert context == [
        {
            "role": "user",
            "content": [
                {
                    "toolResult": {
                        "toolUseId": "tooluse_1",
                        "content": [{"text": "customer found"}],
                    }
                }
            ],
        }
    ]
