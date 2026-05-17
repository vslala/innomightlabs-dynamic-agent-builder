from datetime import datetime, timezone

from src.agents.tool_audit import (
    MAX_TOOL_RESULT_CHARS,
    ToolCallAuditMessage,
    build_tool_call_audit_message,
)


def test_build_tool_call_audit_message_bounds_result_and_preserves_size():
    result = "x" * (MAX_TOOL_RESULT_CHARS + 5)

    audit = build_tool_call_audit_message(
        tool_call_id="tooluse_1",
        sequence=1,
        tool_name="search_docs",
        tool_args={"query": "pricing"},
        result=result,
        success=True,
        started_at=datetime.now(timezone.utc),
    )

    assert audit.type == "tool_call_audit"
    assert audit.result == "x" * MAX_TOOL_RESULT_CHARS
    assert audit.result_size_chars == MAX_TOOL_RESULT_CHARS + 5
    assert audit.result_truncated is True

    parsed = ToolCallAuditMessage.model_validate_json(audit.model_dump_json())
    assert parsed.tool_call_id == "tooluse_1"
    assert parsed.tool_args == {"query": "pricing"}
