"""POST /connectors/oauth/complete: the signed-in half of every connect flow (see auth/oauth_handoff.py)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import partial

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPBearer
from pydantic import BaseModel

from src.auth.oauth_handoff import read_handoff
from src.auth.router import _google_skill_oauth_flows, complete_google_skill_oauth
from src.connectors.mcp.router import complete_mcp_oauth
from src.skills.agent2agent_client.router import complete_a2a_remote_oauth

Completer = Callable[..., Awaitable[dict[str, str]]]

router = APIRouter(prefix="/connectors", tags=["connectors"], dependencies=[Depends(HTTPBearer())])


class OAuthCompletionRequest(BaseModel):
    completion: str


class OAuthCompletionResponse(BaseModel):
    #: The query parameters the page that started the flow reads, e.g. {"mcp_oauth": "success", "mcp_id": ...}.
    result: dict[str, str]


def _completers() -> dict[str, Completer]:
    return {
        **{name: partial(complete_google_skill_oauth, flow) for name, flow in _google_skill_oauth_flows().items()},
        "mcp": complete_mcp_oauth,
        "a2a": complete_a2a_remote_oauth,
    }


@router.post("/oauth/complete", response_model=OAuthCompletionResponse)
async def complete_oauth(request: Request, body: OAuthCompletionRequest) -> OAuthCompletionResponse:
    handoff = read_handoff(body.completion)
    completer = _completers().get(str(handoff.get("flow"))) if handoff else None
    if not handoff or not completer:
        raise HTTPException(status_code=400, detail="This sign-in link has expired. Please connect again.")
    result = await completer(
        state=handoff.get("state"),
        code=handoff.get("code"),
        error=handoff.get("error"),
        user_email=request.state.user_email,
    )
    return OAuthCompletionResponse(result=result)
