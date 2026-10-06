"""What gets saved as the assistant's reply when the model itself said nothing."""

from src.agents.architectures.krishna_memgpt import TurnOutputs
from src.llm.events import SSEEvent, SSEEventType


def _ran(outputs: TurnOutputs, name: str, *, success: bool = True, times: int = 1) -> None:
    for _ in range(times):
        event = SSEEvent(
            event_type=SSEEventType.TOOL_CALL_RESULT,
            content="{}",
            tool_name="call_mcp_tool",
            display_tool_name=name,
            success=success,
        )
        list(outputs.absorb(event))


def test_the_models_own_answer_is_kept():
    outputs = TurnOutputs(full_text="Updated 20 tickets.")
    _ran(outputs, "editJiraIssue", times=20)

    assert outputs.assistant_text == "Updated 20 tickets."


def test_a_silent_turn_records_what_ran_so_the_next_turn_knows():
    outputs = TurnOutputs()
    _ran(outputs, "editJiraIssue", times=20)
    _ran(outputs, "searchJiraIssuesUsingJql")
    _ran(outputs, "editJiraIssue", success=False)

    assert outputs.assistant_text == (
        "I ran 22 tool calls (editJiraIssue ×21, searchJiraIssuesUsingJql; 1 failed), "
        "but I couldn't write a summary of them. "
        "Ask me to summarise what was done; I won't run them again unless you ask."
    )


def test_the_record_says_why_the_model_gave_no_summary():
    outputs = TurnOutputs(stop_reason="max_tokens")
    _ran(outputs, "editJiraIssue")

    assert "1 tool call (editJiraIssue)" in outputs.assistant_text
    assert "reached its output limit" in outputs.assistant_text


def test_nothing_is_saved_when_nothing_ran_and_nothing_was_said():
    assert TurnOutputs().assistant_text == ""
