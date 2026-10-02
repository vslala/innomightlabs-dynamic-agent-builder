"""HTML shell for the embeddable iframe chat widget.

The iframe the `embed.js` loader creates points here. Serving the shell from
the API (rather than the CDN) lets each widget key get its own
`frame-ancestors` policy, built from the key's allowed origins, and makes the
app's `/widget/*` calls same-origin. The app itself (JS + CSS) comes from the
CDN. See docs/LLD-public-api-and-embeddable-widget.md (Part 2).
"""

import html

from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from src.agents.repository import AgentRepository
from src.apikeys.repository import ApiKeyRepository
from src.config import settings

router = APIRouter(tags=["embed"])


class EmbedBootstrap(BaseModel):
    """Everything the iframe app needs before its first request, inlined in the shell."""

    public_key: str
    agent_id: str
    agent_name: str
    agent_description: str | None = None
    api_base_url: str


def embed_csp(allowed_origins: list[str]) -> str:
    """Only the key's allowed origins may frame the chat; an empty list allows any site."""
    ancestors = " ".join(allowed_origins) if allowed_origins else "*"
    cdn = settings.widget_cdn_url
    return "; ".join(
        [
            f"frame-ancestors {ancestors}",
            "default-src 'none'",
            f"script-src {cdn}",
            f"style-src {cdn} 'unsafe-inline'",
            f"font-src {cdn} data:",
            "img-src * data: blob:",
            "connect-src 'self'",
            "base-uri 'none'",
            "form-action 'none'",
            "object-src 'none'",
        ]
    )


def render_shell(bootstrap: EmbedBootstrap) -> str:
    cdn = settings.widget_cdn_url
    # JSON inside <script> only has to be kept from closing the tag early.
    bootstrap_json = bootstrap.model_dump_json().replace("<", "\\u003c")
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <meta name="robots" content="noindex" />
    <title>Chat with {html.escape(bootstrap.agent_name)}</title>
    <link rel="stylesheet" href="{cdn}/embed/app.css" />
    <script type="application/json" id="innomight-bootstrap">{bootstrap_json}</script>
    <script defer src="{cdn}/embed/app.js"></script>
  </head>
  <body>
    <div id="root"></div>
  </body>
</html>
"""


UNAVAILABLE_HTML = """<!doctype html>
<html lang="en">
  <head><meta charset="utf-8" /><title>Chat unavailable</title></head>
  <body style="margin:0;display:grid;place-items:center;height:100vh;font:14px system-ui,sans-serif;color:#8590a2">
    This chat is currently unavailable.
  </body>
</html>
"""

_COMMON_HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
}


def _unavailable() -> HTMLResponse:
    return HTMLResponse(
        UNAVAILABLE_HTML,
        status_code=404,
        headers={**_COMMON_HEADERS, "Content-Security-Policy": "frame-ancestors *; default-src 'none'; style-src 'unsafe-inline'"},
    )


@router.get("/embed/{public_key}", response_class=HTMLResponse)
async def embed_shell(public_key: str) -> HTMLResponse:
    api_key = ApiKeyRepository().find_by_public_key(public_key)
    if not api_key or not api_key.is_active:
        return _unavailable()

    agent = AgentRepository().find_agent_by_id(api_key.agent_id, api_key.created_by)
    if not agent:
        return _unavailable()

    bootstrap = EmbedBootstrap(
        public_key=api_key.public_key,
        agent_id=agent.agent_id,
        agent_name=agent.agent_name,
        agent_description=agent.agent_description,
        api_base_url=settings.api_base_url.rstrip("/"),
    )
    return HTMLResponse(
        render_shell(bootstrap),
        headers={**_COMMON_HEADERS, "Content-Security-Policy": embed_csp(api_key.allowed_origins)},
    )
