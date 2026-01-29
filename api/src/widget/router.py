"""
Widget router for embeddable chat functionality.

Provides endpoints for:
- Widget configuration
- Visitor OAuth authentication
- Chat conversations with SSE streaming
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Optional, cast
from urllib.parse import urlencode

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel

from src.agents.architectures import get_agent_architecture
from src.agents.repository import AgentRepository
from src.apikeys.models import AgentApiKey
from src.auth.google_oauth import GoogleOAuth
from src.config import settings
from src.llm.events import SSEEvent, SSEEventType
from src.messages.repository import MessageRepository
from src.widget.middleware import get_api_key_from_request
from src.widget.models import (
    CreateWidgetConversationRequest,
    WidgetConfigResponse,
    WidgetConversation,
    WidgetConversationResponse,
    WidgetMessageRequest,
    WidgetVisitor,
)
from src.widget.repository import WidgetConversationRepository

log = logging.getLogger(__name__)

router = APIRouter(prefix="/widget", tags=["widget"])

# Widget JWT settings (shorter expiration for visitors)
WIDGET_JWT_EXPIRATION_HOURS = 4

google_oauth = GoogleOAuth()


class WidgetTokenResponse(BaseModel):
    """Response containing visitor JWT token."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
    visitor: WidgetVisitor


class WidgetMessageResponse(BaseModel):
    message_id: str
    role: str
    content: str
    created_at: str


def get_widget_conversation_repository() -> WidgetConversationRepository:
    """Dependency for WidgetConversationRepository."""
    return WidgetConversationRepository()


def get_agent_repository() -> AgentRepository:
    """Dependency for AgentRepository."""
    return AgentRepository()


def get_message_repository() -> MessageRepository:
    """Dependency for MessageRepository."""
    return MessageRepository()


def create_visitor_token(visitor: WidgetVisitor, agent_id: str) -> str:
    """Create a JWT token for a widget visitor."""
    payload = {
        "sub": visitor.visitor_id,
        "email": visitor.email,
        "name": visitor.name,
        "picture": visitor.picture,
        "agent_id": agent_id,  # Scope token to specific agent
        "type": "widget_visitor",
        "exp": datetime.now(timezone.utc) + timedelta(hours=WIDGET_JWT_EXPIRATION_HOURS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_visitor_token(token: str) -> dict[str, Any]:
    """Decode and validate a visitor JWT token."""
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
        if payload.get("type") != "widget_visitor":
            raise HTTPException(status_code=401, detail="Invalid token type")
        return cast(dict[str, Any], payload)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def get_visitor_from_request(request: Request) -> WidgetVisitor:
    """
    Extract visitor info from Authorization header.

    Validates the visitor token and returns visitor info.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = auth_header.split(" ")[1]
    payload = decode_visitor_token(token)

    return WidgetVisitor(
        visitor_id=payload["sub"],
        email=payload["email"],
        name=payload.get("name"),
        picture=payload.get("picture"),
    )


@router.get("/config", response_model=WidgetConfigResponse)
async def get_widget_config(
    request: Request,
    api_key: Annotated[AgentApiKey, Depends(get_api_key_from_request)],
    agent_repo: Annotated[AgentRepository, Depends(get_agent_repository)],
) -> WidgetConfigResponse:
    """
    Get widget configuration for initialization.

    Requires X-API-Key header.
    Returns agent info needed to configure the widget.
    """
    # Find the agent (we don't have user context here, so we need to look it up differently)
    # Since API keys are tied to agents, we can trust the agent_id from the key
    agent_id = api_key.agent_id

    # Query by agent ID - we need to find the agent without knowing the user
    # For now, we'll just return basic config from the API key
    # In production, you might want to cache agent info or store it with the key

    return WidgetConfigResponse(
        agent_name=api_key.name,  # Use key name as fallback
        agent_id=agent_id,
        welcome_message="Hello! How can I help you today?",
        theme={},
    )


@router.get("/auth/google")
async def widget_oauth_start(
    request: Request,
    api_key: str = Query(..., description="Public API key (pk_live_xxx)"),
    redirect_uri: Optional[str] = Query(None, description="URI to redirect after auth"),
):
    """
    Start OAuth flow for widget visitor.

    Requires api_key query parameter (since this is a redirect flow, not AJAX).
    Redirects to Google OAuth consent screen.
    """
    # Validate API key from query parameter
    from src.apikeys.repository import ApiKeyRepository
    api_key_repo = ApiKeyRepository()
    api_key_obj = api_key_repo.find_by_public_key(api_key)

    if not api_key_obj:
        raise HTTPException(status_code=401, detail="Invalid API key")

    if not api_key_obj.is_active:
        raise HTTPException(status_code=401, detail="API key is disabled")

    # Store state with API key info for callback
    # redirect_uri here is the final destination after OAuth (callback-page)
    state = f"{api_key_obj.public_key}|{redirect_uri or ''}"

    # Build the widget's OAuth callback URL (where Google redirects to)
    # This must be registered in Google OAuth console
    base_url = str(request.base_url).rstrip("/")
    widget_callback_url = f"{base_url}/widget/auth/callback"

    authorization_url, _ = google_oauth.get_authorization_url(
        state=state,
        redirect_uri=widget_callback_url
    )
    return RedirectResponse(url=authorization_url)


@router.get("/auth/callback")
async def widget_oauth_callback(
    request: Request,
    code: str = Query(None),
    error: str = Query(None),
    state: str = Query(None),
):
    """
    Handle OAuth callback for widget visitors.

    Exchanges code for tokens and creates visitor JWT.
    """
    if error:
        return {"error": error}

    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    # Parse state to get API key and final redirect URI
    api_key_str = ""
    redirect_uri = ""
    if state:
        parts = state.split("|", 1)
        api_key_str = parts[0]
        redirect_uri = parts[1] if len(parts) > 1 else ""

    # Validate API key
    from src.apikeys.repository import ApiKeyRepository
    api_key_repo = ApiKeyRepository()
    api_key = api_key_repo.find_by_public_key(api_key_str)

    if not api_key or not api_key.is_active:
        raise HTTPException(status_code=401, detail="Invalid or inactive API key")

    try:
        # Build the same callback URL used during authorization
        # Google requires redirect_uri to match exactly
        base_url = str(request.base_url).rstrip("/")
        widget_callback_url = f"{base_url}/widget/auth/callback"

        # Exchange code for tokens
        tokens = await google_oauth.exchange_code_for_tokens(code, redirect_uri=widget_callback_url)
        access_token = tokens.get("access_token")

        if not access_token:
            raise HTTPException(status_code=400, detail="Failed to get access token")

        # Get user info from Google
        user_info = await google_oauth.get_user_info(access_token)

        email = user_info.get("email")
        google_id = user_info.get("id") or user_info.get("sub")
        name = user_info.get("name")
        picture = user_info.get("picture")

        if not email:
            raise HTTPException(status_code=400, detail="Failed to get user email")

        # Create visitor object
        visitor = WidgetVisitor(
            visitor_id=google_id or email,
            email=email,
            name=name,
            picture=picture,
        )

        # Create visitor JWT
        visitor_token = create_visitor_token(visitor, api_key.agent_id)

        # If redirect_uri provided, redirect with token
        if redirect_uri:
            params = urlencode({
                "token": visitor_token,
                "visitor_id": visitor.visitor_id,
                "email": visitor.email,
                "name": visitor.name or "",
                "picture": visitor.picture or "",
            })
            return RedirectResponse(url=f"{redirect_uri}?{params}")

        # Otherwise return token in response
        return WidgetTokenResponse(
            access_token=visitor_token,
            expires_in=WIDGET_JWT_EXPIRATION_HOURS * 3600,
            visitor=visitor,
        )

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Widget OAuth error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Authentication failed")


# OAuth callback page HTML served by the backend
OAUTH_CALLBACK_HTML = """<!DOCTYPE html>
<html>
<head>
  <title>Authenticating...</title>
  <style>
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      display: flex;
      align-items: center;
      justify-content: center;
      height: 100vh;
      margin: 0;
      background: #f9fafb;
    }
    .container { text-align: center; }
    .spinner {
      width: 40px;
      height: 40px;
      border: 3px solid #e5e7eb;
      border-top-color: #6366f1;
      border-radius: 50%;
      animation: spin 0.8s linear infinite;
      margin: 0 auto 16px;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
    p { color: #6b7280; margin: 0; }
  </style>
</head>
<body>
  <div class="container">
    <div class="spinner"></div>
    <p>Completing sign in...</p>
  </div>
  <script>
    (function() {
      var params = new URLSearchParams(window.location.search);
      var token = params.get('token');
      var visitorId = params.get('visitor_id');
      var email = params.get('email');
      var name = params.get('name');
      var picture = params.get('picture');
      var error = params.get('error');

      if (error) {
        document.querySelector('p').textContent = 'Authentication failed: ' + error;
        return;
      }

      if (token && visitorId && email) {
        if (window.opener) {
          window.opener.postMessage({
            type: 'innomight-oauth-callback',
            token: token,
            visitor: {
              visitorId: visitorId,
              email: email,
              name: name || email.split('@')[0],
              picture: picture || null
            }
          }, '*');
        }
        setTimeout(function() { window.close(); }, 500);
      } else {
        document.querySelector('p').textContent = 'Missing authentication data';
      }
    })();
  </script>
</body>
</html>"""


@router.get("/auth/callback-page", response_class=HTMLResponse)
async def oauth_callback_page():
    """
    Serve the OAuth callback HTML page.

    This page receives the OAuth redirect, extracts the token from URL params,
    and posts it back to the parent window via postMessage.
    """
    return HTMLResponse(content=OAUTH_CALLBACK_HTML)


@router.post("/conversations", response_model=WidgetConversationResponse, status_code=201)
async def create_conversation(
    request: Request,
    body: CreateWidgetConversationRequest,
    api_key: Annotated[AgentApiKey, Depends(get_api_key_from_request)],
    visitor: Annotated[WidgetVisitor, Depends(get_visitor_from_request)],
    conv_repo: Annotated[WidgetConversationRepository, Depends(get_widget_conversation_repository)],
) -> WidgetConversationResponse:
    """
    Create a new conversation for a widget visitor.

    Requires X-API-Key header and visitor Authorization token.
    """
    conversation = WidgetConversation(
        agent_id=api_key.agent_id,
        visitor_id=visitor.visitor_id,
        visitor_email=visitor.email,
        visitor_name=visitor.name,
        visitor_picture=visitor.picture,
        title=body.title or f"Chat with {visitor.name or 'Visitor'}",
    )

    saved = conv_repo.save(conversation)
    log.info(f"Created widget conversation {saved.conversation_id} for visitor {visitor.visitor_id}")

    return saved.to_response()


@router.get("/conversations", response_model=list[WidgetConversationResponse])
async def list_conversations(
    request: Request,
    api_key: Annotated[AgentApiKey, Depends(get_api_key_from_request)],
    visitor: Annotated[WidgetVisitor, Depends(get_visitor_from_request)],
    conv_repo: Annotated[WidgetConversationRepository, Depends(get_widget_conversation_repository)],
) -> list[WidgetConversationResponse]:
    """
    List all conversations for the current visitor with this agent.

    Requires X-API-Key header and visitor Authorization token.
    """
    conversations = conv_repo.find_by_visitor_and_agent(
        visitor_id=visitor.visitor_id,
        agent_id=api_key.agent_id,
    )

    return [conv.to_response() for conv in conversations]


@router.get("/conversations/{conversation_id}", response_model=WidgetConversationResponse)
async def get_conversation(
    request: Request,
    conversation_id: str,
    api_key: Annotated[AgentApiKey, Depends(get_api_key_from_request)],
    visitor: Annotated[WidgetVisitor, Depends(get_visitor_from_request)],
    conv_repo: Annotated[WidgetConversationRepository, Depends(get_widget_conversation_repository)],
) -> WidgetConversationResponse:
    """
    Get a specific conversation.

    Requires X-API-Key header and visitor Authorization token.
    """
    conversation = conv_repo.find_by_id(api_key.agent_id, conversation_id)

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Verify visitor owns this conversation
    if conversation.visitor_id != visitor.visitor_id:
        raise HTTPException(status_code=403, detail="Access denied")

    return conversation.to_response()


@router.post("/conversations/{conversation_id}/messages")
async def send_message(
    request: Request,
    conversation_id: str,
    body: WidgetMessageRequest,
    api_key: Annotated[AgentApiKey, Depends(get_api_key_from_request)],
    visitor: Annotated[WidgetVisitor, Depends(get_visitor_from_request)],
    conv_repo: Annotated[WidgetConversationRepository, Depends(get_widget_conversation_repository)],
    agent_repo: Annotated[AgentRepository, Depends(get_agent_repository)],
):
    """
    Send a message to the agent and receive streaming response.

    Requires X-API-Key header and visitor Authorization token.
    Returns Server-Sent Events stream.
    """
    # Validate conversation
    conversation = conv_repo.find_by_id(api_key.agent_id, conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if conversation.visitor_id != visitor.visitor_id:
        raise HTTPException(status_code=403, detail="Access denied")

    async def event_stream():
        try:
            # Load agent
            yield SSEEvent(
                event_type=SSEEventType.LIFECYCLE_NOTIFICATION,
                content="Connecting to agent..."
            ).to_sse()

            # Find the agent - need to find by ID across all users
            # This is a limitation - we need a GSI on agent_id
            # For now, we'll use the API key's created_by to find the agent
            agent = agent_repo.find_agent_by_id(api_key.agent_id, api_key.created_by)

            if not agent:
                yield SSEEvent(
                    event_type=SSEEventType.ERROR,
                    content="Agent not found"
                ).to_sse()
                return

            # Get architecture and handle message
            architecture = get_agent_architecture(agent.agent_architecture)

            # Create a mock conversation object for the architecture
            # (architecture expects a Conversation, but we have WidgetConversation)
            from src.conversations.models import Conversation
            mock_conversation = Conversation(
                conversation_id=conversation.conversation_id,
                title=conversation.title,
                agent_id=conversation.agent_id,
                created_by=visitor.email,  # Use visitor email
            )

            async for event in architecture.handle_message(  # pyright: ignore[reportGeneralTypeIssues]
                agent=agent,
                conversation=mock_conversation,
                user_message=body.content,
                user_email=visitor.email,
                user_id=visitor.visitor_id,
                attachments=[],  # Widget doesn't support attachments yet
            ):
                yield event.to_sse()

            # Increment message count
            conv_repo.increment_message_count(api_key.agent_id, conversation_id)

        except Exception as e:
            log.error(f"Error in widget message stream: {e}", exc_info=True)
            yield SSEEvent(
                event_type=SSEEventType.ERROR,
                content=str(e)
            ).to_sse()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@router.get("/conversations/{conversation_id}/messages", response_model=list[WidgetMessageResponse])
async def list_messages(
    request: Request,
    conversation_id: str,
    api_key: Annotated[AgentApiKey, Depends(get_api_key_from_request)],
    visitor: Annotated[WidgetVisitor, Depends(get_visitor_from_request)],
    conv_repo: Annotated[WidgetConversationRepository, Depends(get_widget_conversation_repository)],
    message_repo: Annotated[MessageRepository, Depends(get_message_repository)],
):
    """
    List messages for a widget conversation.

    Requires X-API-Key header and visitor Authorization token.
    """
    conversation = conv_repo.find_by_id(api_key.agent_id, conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conversation.visitor_id != visitor.visitor_id:
        raise HTTPException(status_code=403, detail="Access denied")

    messages = message_repo.find_by_conversation(conversation_id)
    return [
        WidgetMessageResponse(
            message_id=message.message_id,
            role=message.role,
            content=message.content,
            created_at=message.created_at.isoformat(),
        )
        for message in messages
        if message.role in {"user", "assistant"}
    ]
