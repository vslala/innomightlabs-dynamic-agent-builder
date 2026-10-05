"""What an owner agrees to before others may use their MCP connector.

The wording lives only here; the dashboard renders whatever we send. Change the text, bump the version,
and the next time an owner edits a share they are asked again. Existing shares keep working meanwhile.
"""

from __future__ import annotations

DISCLAIMER_VERSION = "2026-10-05"


def sharing_disclaimer(connection_name: str) -> list[str]:
    return [
        f"Anyone you share with, including anonymous visitors on your website, can make this agent call the "
        f"selected {connection_name} tools.",
        f"Every call runs through your {connection_name} connection with your account's permissions. Whatever it "
        f"reads, creates, or changes happens as you, and the results can be shown to whoever asked.",
        "Usage costs and rate limits on that account are yours.",
        "Only share tools you would be comfortable letting a stranger trigger. Every call is recorded in "
        "Analytics under MCP usage.",
    ]
