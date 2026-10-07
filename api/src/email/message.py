"""The house layout for plain, text-first emails: enquiries, their confirmations, support replies.

One template for all of them, so every such email looks the same: the Innomight wordmark, a
heading, a few paragraphs, and optionally a quoted message, a list of details and one link. It
renders an HTML part and a matching plain-text part. Everything is escaped, so a sender's own
words can go straight in.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from markupsafe import Markup, escape

#: Served by innomight.com from www/public/email/.
INNOMIGHT_WORDMARK_URL = "https://innomight.com/email/innomight-wordmark.png"

_TEMPLATES_DIR = Path(__file__).parent.parent.parent / "assets" / "templates" / "emails"


def _nl2br(text: str) -> Markup:
    return Markup("<br>\n").join(escape(line) for line in text.splitlines())


_env = Environment(
    loader=FileSystemLoader(_TEMPLATES_DIR),
    undefined=StrictUndefined,
    autoescape=True,
    trim_blocks=True,
    lstrip_blocks=True,
)
_env.filters["nl2br"] = _nl2br


def render_email_template(name: str, **context: object) -> str:
    """Render a template that extends `_layout.html`; `context["email"]` supplies heading, preheader and footer."""
    return _env.get_template(name).render(logo_url=INNOMIGHT_WORDMARK_URL, **context)


@dataclass(frozen=True)
class EmailLink:
    label: str
    url: str


@dataclass(frozen=True)
class MessageEmail:
    """What one email says. The layout decides how it looks."""

    heading: str
    paragraphs: list[str]
    #: Shown in the inbox after the subject.
    preheader: str = ""
    #: Someone's own words, set apart from ours.
    quote: str | None = None
    details: list[tuple[str, str]] = field(default_factory=list)
    #: Paragraphs after the quote and details.
    closing: list[str] = field(default_factory=list)
    action: EmailLink | None = None
    sign_off: str | None = None
    #: The site in the footer, e.g. ("InnomightLabs", "https://innomightlabs.com").
    footer: EmailLink = EmailLink("Innomight", "https://innomight.com")

    def html(self) -> str:
        return render_email_template("message.html", email=self)

    def text(self) -> str:
        parts = [self.heading, *self.paragraphs]
        if self.quote:
            parts.append("\n".join(f"> {line}" for line in self.quote.splitlines()))
        if self.details:
            parts.append("\n".join(f"{label}: {value}" for label, value in self.details))
        parts.extend(self.closing)
        if self.action:
            parts.append(f"{self.action.label}: {self.action.url}")
        if self.sign_off:
            parts.append(self.sign_off)
        parts.append(f"{self.footer.label} · {self.footer.url}")
        return "\n\n".join(parts) + "\n"
