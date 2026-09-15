from src.agents.tool_display import derive_display_tool


def test_unwraps_call_mcp_tool_to_the_real_mcp_tool_name_and_arguments():
    name, args = derive_display_tool(
        "call_mcp_tool",
        {
            "mcp_id": "atlassian",
            "tool_name": "searchJiraIssuesUsingJql",
            "arguments": {"cloudId": "abc", "jql": "project = KAN"},
        },
    )

    assert name == "searchJiraIssuesUsingJql"
    assert args == {"cloudId": "abc", "jql": "project = KAN"}


def test_call_mcp_tool_without_nested_tool_name_falls_back_to_the_wrapper():
    name, args = derive_display_tool("call_mcp_tool", {"mcp_id": "atlassian"})

    assert name == "call_mcp_tool"
    assert args == {"mcp_id": "atlassian"}


def test_call_mcp_tool_with_non_dict_arguments_drops_the_args():
    name, args = derive_display_tool(
        "call_mcp_tool",
        {"tool_name": "search_code", "arguments": "not a dict"},
    )

    assert name == "search_code"
    assert args is None


def test_non_wrapper_tool_passes_through_unchanged():
    name, args = derive_display_tool("list_mcp_tools", {"mcp_id": "atlassian"})

    assert name == "list_mcp_tools"
    assert args == {"mcp_id": "atlassian"}


def test_missing_tool_args_passes_through_unchanged():
    name, args = derive_display_tool("call_mcp_tool", None)

    assert name == "call_mcp_tool"
    assert args is None
