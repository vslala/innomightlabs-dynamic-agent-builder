"""Connect flows (Gmail, Drive, Ads, MCP, remote A2A) finish in the SPA, signed in.

A provider callback is a plain browser navigation: it can't tell whose browser it is in. So
someone could send a victim their own consent link, and the victim's Google account would land
on the attacker's agent. The callbacks therefore store nothing. Each one hands the code and
state back to the SPA in an encrypted, short-lived blob, and the SPA posts it to
/connectors/oauth/complete with the user's own token. The flow completes only when that user
is the one who started it.
"""

from __future__ import annotations

import json
import time
from typing import Any, Optional
from urllib.parse import urlencode, urlsplit

from fastapi.responses import RedirectResponse

from src.config import settings
from src.crypto import decrypt, encrypt

HANDOFF_PARAM = "oauth_complete"
HANDOFF_TTL_SECONDS = 600


def safe_return_to(return_to: str) -> str:
    """Connect flows only ever send the user back to our own SPA."""
    frontend = urlsplit(settings.frontend_url)
    target = urlsplit(return_to)
    if (target.scheme, target.netloc) != (frontend.scheme, frontend.netloc):
        raise ValueError("return_to must be a page of this app")
    return return_to


def handoff_redirect(
    return_to: str,
    *,
    flow: str,
    state: Optional[str],
    code: Optional[str],
    error: Optional[str],
) -> RedirectResponse:
    blob = encrypt(json.dumps({
        "flow": flow,
        "state": state,
        "code": code,
        "error": error,
        "expires_at": int(time.time()) + HANDOFF_TTL_SECONDS,
    }))
    separator = "&" if "?" in return_to else "?"
    return RedirectResponse(f"{return_to}{separator}{urlencode({HANDOFF_PARAM: blob})}")


def read_handoff(blob: str) -> Optional[dict[str, Any]]:
    try:
        handoff = json.loads(decrypt(blob))
    except Exception:
        return None
    if not isinstance(handoff, dict) or int(handoff.get("expires_at") or 0) < time.time():
        return None
    return handoff
