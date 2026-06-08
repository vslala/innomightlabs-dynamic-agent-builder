from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from src.messages.models import Message


COMPACTION_TEMPLATE_DIR = Path(__file__).parent / "templates"
COMPACTION_TEMPLATE = "context_compaction.j2"

_env = Environment(
    loader=FileSystemLoader(COMPACTION_TEMPLATE_DIR),
    undefined=StrictUndefined,
    autoescape=False,
    trim_blocks=True,
    lstrip_blocks=True,
)


class MessageCompactionStrategy(Protocol):
    def compact(self, *, conversation_id: str, messages: list[Message], target_tokens: int) -> Message:
        ...


@dataclass(frozen=True)
class TemplateMessageCompactionStrategy:
    """Model-agnostic compaction for transient message repositories."""

    chars_per_token: int = 4
    max_message_chars: int = 4_000

    def compact(self, *, conversation_id: str, messages: list[Message], target_tokens: int) -> Message:
        goal = self._latest_user_goal(messages)
        compacted_messages = self._compact_messages(messages, target_chars=target_tokens * self.chars_per_token)

        template = _env.get_template(COMPACTION_TEMPLATE)
        content = template.render(
            compacted_at=datetime.now(timezone.utc).isoformat(),
            goal=goal,
            messages=compacted_messages,
        ).strip()

        return Message(
            conversation_id=conversation_id,
            created_by=self._latest_created_by(messages),
            role="user",
            content=content,
        )

    def _latest_user_goal(self, messages: list[Message]) -> str:
        for message in reversed(messages):
            if message.role == "user" and message.content.strip():
                return self._trim_text(message.content.strip(), self.max_message_chars)
        return "Continue the task using the compacted working context."

    def _latest_created_by(self, messages: list[Message]) -> str:
        for message in reversed(messages):
            if message.created_by:
                return message.created_by
        return ""

    def _compact_messages(self, messages: list[Message], *, target_chars: int) -> list[dict[str, str]]:
        selected: list[dict[str, str]] = []
        used_chars = 0

        for message in reversed(messages):
            content = self._trim_text(message.content.strip(), self.max_message_chars)
            if not content:
                continue

            entry = {
                "role": message.role,
                "created_at": message.created_at.isoformat(),
                "content": content,
            }
            entry_chars = sum(len(value) for value in entry.values())
            if selected and used_chars + entry_chars > target_chars:
                break

            selected.insert(0, entry)
            used_chars += entry_chars

        return selected

    def _trim_text(self, text: str, max_chars: int) -> str:
        if len(text) <= max_chars:
            return text
        return f"{text[: max_chars - 1].rstrip()}..."
