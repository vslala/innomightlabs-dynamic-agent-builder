"""Jinja rendering for agent system prompts.

One environment for every architecture, so prompt sections can be shared
between them (see prompt_templates/shared/). Templates render already-loaded
data: no network calls, no DB reads, no Python-side layout helpers.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

PROMPT_TEMPLATE_DIR = Path(__file__).parent / "prompt_templates"

_env = Environment(
    loader=FileSystemLoader(PROMPT_TEMPLATE_DIR),
    undefined=StrictUndefined,
    autoescape=False,
    trim_blocks=True,
    lstrip_blocks=True,
)


def render_system_prompt(template_name: str, **context: Any) -> str:
    """Render `template_name` with `context`, plus the current timestamp.

    StrictUndefined is deliberate: a section that references data nobody
    passed should fail loudly here rather than silently render a gap into a
    live system prompt.
    """
    return (
        _env.get_template(template_name)
        .render(
            timestamp=datetime.now(timezone.utc).strftime("%A, %B %d, %Y at %I:%M %p UTC"),
            **context,
        )
        .strip()
    )
