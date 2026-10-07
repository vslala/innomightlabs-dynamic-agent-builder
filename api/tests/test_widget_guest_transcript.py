import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.widget.transcript import (
    GuestTranscriptEmail,
    build_transcript,
    origin_host,
    render_assistant_markdown,
    time_label,
)


def render_guest_transcript(entries, agent_name, max_chars=100_000):
    """The transcript as it appears in the email's HTML."""
    return GuestTranscriptEmail(agent_name=agent_name, origin="https://example.com", started_at="",
                                transcript=build_transcript(entries, agent_name, max_chars)).html()


def test_renderer_allowlist_and_dangerous_links():
    html = render_assistant_markdown('<script>x</script> **bold** *italic* `code`\n\n- one\n- two\n\n1. first\n2. second\n\n[good](https://example.com?a=1&b=2) [bad](javascript:alert) [data](data:text/html,x)')
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "<strong>bold</strong>" in html and "<em>italic</em>" in html
    assert "<code>code</code>" in html and "<li>one</li>" in html and "<li>first</li>" in html
    assert "<ul" in html and "<ol" in html
    assert 'href="https://example.com?a=1&amp;b=2"' in html
    assert "javascript:" not in html and "data:text" not in html
    # A link inside inline code stays code, not a link.
    assert "<code>[link](https://example.com)</code>" in render_assistant_markdown('`[link](https://example.com)`')
    assert "<a " not in render_assistant_markdown('`[link](https://example.com)`')


def test_transcript_excludes_private_rows_escapes_metadata_and_orders():
    entries = [{"conversation": {"title": '<img src=x>', "created_at": "1"}, "messages": [
        {"role": "assistant", "kind": "tool_audit", "content": "AUDIT"},
        {"role": "system", "content": "SYSTEM"},
        {"role": "assistant", "hidden": True, "content": "HIDDEN"},
        {"role": "assistant", "content": "second", "created_at": "2", "images": [{"url": "https://private"}]},
        {"role": "user", "content": "first **not bold** <script>", "created_at": "1"},
    ]}]
    html = render_guest_transcript(entries, 'Mira <svg>')
    assert all(secret not in html for secret in ["AUDIT", "SYSTEM", "HIDDEN", "https://private"])
    assert "<img src=x>" not in html and "<svg>" not in html and "<script>" not in html
    assert "Mira &lt;svg&gt;" in html and "**not bold**" in html
    assert html.index("first") < html.index("second") and "(image)" in html


def test_truncation_does_not_cut_html_tags():
    entries = [{"conversation": {"title": "Chat"}, "messages": [{"role": "user", "content": "<" * 100}]}]
    html = render_guest_transcript(entries, "Mira", max_chars=9)
    assert "&lt;" * 5 in html
    assert "shortened" in html and "owner's archive" in html
    assert html.count("<div") == html.count("</div>")


@pytest.mark.parametrize("origin,expected", [("https://example.com/path", "example.com"), ("javascript:alert(1)", "the chat website"), ("https://[invalid", "the chat website")])
def test_origin_host(origin, expected):
    assert origin_host(origin) == expected


def _email(agent_name="Mira", text="Hello {{agent_name}} <script>"):
    entries = [{"conversation": {"title": "Chat", "created_at": "2026-10-07T12:00:00+00:00"}, "messages": [
        {"role": "user", "content": text, "created_at": "2026-10-07T12:05:00+00:00"},
        {"role": "assistant", "content": "Hi **there**", "created_at": "2026-10-07T12:05:30+00:00"},
    ]}]
    return GuestTranscriptEmail(agent_name=agent_name, origin="https://innomightlabs.com/docs",
                                started_at="2026-10-07T12:00:00+00:00", transcript=build_transcript(entries, agent_name))


def test_transcript_uses_the_house_layout_with_a_text_part():
    email = _email()
    html, text = email.html(), email.text()
    assert "innomight-wordmark.png" in html and "InnomightLabs" in html
    assert "Your conversation with Mira" in html and "innomightlabs.com, 7 Oct 2026" in html
    assert ">You</strong> · 7 Oct 2026, 12:05 UTC" in html and "<strong>there</strong>" in html
    # Message text is escaped, and {{...}} in it is never treated as a template placeholder.
    assert "Hello {{agent_name}} &lt;script&gt;" in html and "<script>" not in html
    assert "If that wasn't you" in html
    assert "You · 7 Oct 2026, 12:05 UTC\nHello {{agent_name}} <script>" in text
    assert text.rstrip().endswith("InnomightLabs · https://innomightlabs.com")


@pytest.mark.parametrize("value,expected", [
    ("2026-10-07T09:05:00+00:00", "7 Oct 2026, 09:05 UTC"), ("not a date", "not a date"), ("", ""),
])
def test_time_label(value, expected):
    assert time_label(value) == expected


def test_email_sender_subject_and_parts():
    from src.email.service import EmailService

    service = EmailService()
    service.client = Mock()
    service.client.send.create.return_value = SimpleNamespace(status_code=200, json=lambda: {"Messages": [{"Status": "success"}]})
    assert asyncio.run(service.send_guest_transcript_email(to_email="guest@example.com", email=_email("Mira <img>\nInjected")))
    message = service.client.send.create.call_args.kwargs["data"]["Messages"][0]
    assert message["From"]["Email"] == "noreply@innomightlabs.com"
    assert message["From"]["Name"] == "Mira <img> Injected via InnomightLabs"
    assert "\n" not in message["Subject"]
    assert "Mira &lt;img&gt;" in message["HTMLPart"] and "<img>" not in message["HTMLPart"]
    assert message["TextPart"].startswith("Your conversation with Mira <img>")


def test_email_200_with_provider_error_is_failure():
    from src.email.service import EmailService

    service = EmailService()
    service.client = Mock()
    service.client.send.create.return_value = SimpleNamespace(status_code=200, json=lambda: {"Messages": [{"Status": "error"}]})
    assert not asyncio.run(service.send_guest_transcript_email(to_email="guest@example.com", email=_email()))


def test_safe_helper_returns_failure_without_another_retry_queue(monkeypatch):
    from src.email import helpers

    monkeypatch.setattr(helpers, "EmailService", Mock(side_effect=RuntimeError("unavailable")))
    pending = Mock()
    monkeypatch.setattr(helpers, "PendingEmailRepository", pending)
    assert not asyncio.run(helpers.send_guest_transcript_email_safe(to_email="guest@example.com", email=_email()))
    pending.assert_not_called()
