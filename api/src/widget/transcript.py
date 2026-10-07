"""The transcript emailed to a guest when their session ends.

`build_transcript` picks the visible messages and applies the length cap; `GuestTranscriptEmail`
renders them in the house email layout (`assets/templates/emails/guest_transcript.html`, which
extends `_layout.html`) with a matching plain-text part. Everything a visitor or the agent wrote
is escaped; assistant markdown goes through a deliberately small allowlist renderer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from html import escape
from urllib.parse import urlsplit

from markupsafe import Markup

from src.email.message import EmailLink, render_email_template

_INLINE = re.compile(r"`([^`\n]+)`|\[([^\]\n]+)\]\(([^\s)]+)\)|\*\*([^*\n]+)\*\*|\*([^*\n]+)\*")
INNOMIGHTLABS_FOOTER = EmailLink("InnomightLabs", "https://innomightlabs.com")


def _inline(text: str) -> str:
    # Escape plain spans independently: generated HTML is never parsed as markdown.
    parts = []
    end = 0
    for match in _INLINE.finditer(text):
        parts.append(escape(text[end:match.start()]))
        code, label, url, bold, italic = match.groups()
        if code is not None:
            parts.append(f"<code>{escape(code)}</code>")
        elif label is not None:
            try:
                parsed = urlsplit(url)
                safe = parsed.scheme.lower() in {"https", "http"} and bool(parsed.hostname)
            except ValueError:
                safe = False
            parts.append(
                f'<a href="{escape(url, quote=True)}" rel="noreferrer" style="color:#0c66e4;">{escape(label)}</a>'
                if safe else escape(label)
            )
        elif bold is not None:
            parts.append(f"<strong>{escape(bold)}</strong>")
        else:
            parts.append(f"<em>{escape(italic)}</em>")
        end = match.end()
    parts.append(escape(text[end:]))
    return "".join(parts)


def render_assistant_markdown(text: str) -> str:
    blocks = []
    for paragraph in re.split(r"\n\s*\n", text):
        lines = paragraph.splitlines()
        if lines and all(re.match(r"^\s*[-*] ", line) for line in lines):
            items = "".join(f"<li>{_inline(re.sub(r'^\s*[-*] ', '', line))}</li>" for line in lines)
            blocks.append(f'<ul style="margin:0 0 8px 0; padding-left:20px;">{items}</ul>')
        elif lines and all(re.match(r"^\s*\d+\. ", line) for line in lines):
            items = "".join(f"<li>{_inline(re.sub(r'^\s*\d+\. ', '', line))}</li>" for line in lines)
            blocks.append(f'<ol style="margin:0 0 8px 0; padding-left:20px;">{items}</ol>')
        else:
            blocks.append('<p style="margin:0 0 8px 0;">' + "<br>".join(_inline(line) for line in lines) + "</p>")
    return "".join(blocks)


def is_visible_message(message: dict) -> bool:
    return (
        message.get("role") in {"user", "assistant"}
        and message.get("kind", "chat") == "chat"
        and not message.get("hidden", False)
        and not str(message.get("sk", "MESSAGE#")).startswith(("AUDIT#", "TURN#"))
    )


def origin_host(origin: str) -> str:
    try:
        parsed = urlsplit(origin)
        return parsed.hostname if parsed.scheme in {"http", "https"} and parsed.hostname else "the chat website"
    except ValueError:
        return "the chat website"


def time_label(value: object) -> str:
    """'7 Oct 2026, 12:05 UTC' for an ISO timestamp; anything else is shown as given."""
    try:
        moment = datetime.fromisoformat(str(value))
    except ValueError:
        return str(value or "")
    return f"{moment.day} {moment:%b %Y, %H:%M} UTC" if moment.tzinfo else f"{moment.day} {moment:%b %Y, %H:%M}"


def date_label(value: object) -> str:
    """'7 Oct 2026' for an ISO timestamp."""
    try:
        moment = datetime.fromisoformat(str(value))
    except ValueError:
        return str(value or "")
    return f"{moment.day} {moment:%b %Y}"


@dataclass(frozen=True)
class TranscriptMessage:
    label: str
    time_label: str
    from_visitor: bool
    text: str

    @property
    def html(self) -> Markup:
        # Visitors' words are shown as typed; the agent's markdown goes through the allowlist renderer.
        rendered = escape(self.text).replace("\n", "<br>") if self.from_visitor else render_assistant_markdown(self.text)
        return Markup(rendered)


@dataclass(frozen=True)
class TranscriptConversation:
    title: str
    messages: list[TranscriptMessage]


@dataclass(frozen=True)
class GuestTranscript:
    conversations: list[TranscriptConversation]
    truncated: bool = False


def build_transcript(conversations: list[dict], agent_name: str, max_chars: int = 100_000) -> GuestTranscript:
    """Visible messages in order, capped at `max_chars` of source text (never mid-tag, since HTML comes later)."""
    remaining = max(0, max_chars)
    built: list[TranscriptConversation] = []
    truncated = False
    for entry in sorted(conversations, key=lambda entry: str(entry["conversation"].get("created_at", ""))):
        title = str(entry["conversation"].get("title", "Conversation"))
        messages: list[TranscriptMessage] = []
        for message in sorted(entry["messages"], key=lambda message: str(message.get("created_at", ""))):
            if not is_visible_message(message):
                continue
            text = str(message.get("content", ""))
            if message.get("images"):
                text += "\n" + "\n".join("(image)" for _ in message["images"])
            if len(text) > remaining:
                text, truncated = text[:remaining], True
            remaining -= len(text)
            from_visitor = message["role"] == "user"
            messages.append(TranscriptMessage(
                label="You" if from_visitor else agent_name,
                time_label=time_label(message.get("created_at")) if message.get("created_at") else "",
                from_visitor=from_visitor,
                text=text,
            ))
            if truncated:
                break
        built.append(TranscriptConversation(title=title, messages=messages))
        if truncated:
            break
    return GuestTranscript(conversations=built, truncated=truncated)


@dataclass(frozen=True)
class GuestTranscriptEmail:
    agent_name: str
    origin: str
    started_at: str
    transcript: GuestTranscript
    footer: EmailLink = field(default=INNOMIGHTLABS_FOOTER)

    @property
    def heading(self) -> str:
        return f"Your conversation with {self.agent_name}"

    @property
    def subject(self) -> str:
        return " ".join(self.heading.splitlines())

    @property
    def preheader(self) -> str:
        return f"A copy of your chat on {self.origin_host}."

    @property
    def origin_host(self) -> str:
        return origin_host(self.origin)

    @property
    def date_label(self) -> str:
        return date_label(self.started_at)

    @property
    def conversations(self) -> list[TranscriptConversation]:
        return self.transcript.conversations

    @property
    def truncated(self) -> bool:
        return self.transcript.truncated

    def html(self) -> str:
        return render_email_template("guest_transcript.html", email=self)

    def text(self) -> str:
        parts = [self.heading, f"Here's a copy of your chat with {self.agent_name} on {self.origin_host}, {self.date_label}."]
        for conversation in self.conversations:
            if len(self.conversations) > 1:
                parts.append(f"— {conversation.title} —")
            for message in conversation.messages:
                stamp = f" · {message.time_label}" if message.time_label else ""
                parts.append(f"{message.label}{stamp}\n{message.text}")
        if self.truncated:
            parts.append("This transcript was shortened. The rest is in the site owner's archive.")
        parts.append(f"This chat has ended. To continue, open the chat on {self.origin_host} again.")
        parts.append(
            f"You received this because this address was entered to start a guest chat on {self.origin_host}. "
            "If that wasn't you, you can ignore this email."
        )
        parts.append(f"{self.footer.label} · {self.footer.url}")
        return "\n\n".join(parts) + "\n"
