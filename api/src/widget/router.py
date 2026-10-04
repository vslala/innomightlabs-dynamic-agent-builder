"""
Widget router for embeddable chat functionality.

Provides endpoints for:
- Widget configuration
- Visitor OAuth authentication
- Chat conversations with SSE streaming
"""

import logging
import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Optional, cast
from urllib.parse import urlencode

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from pydantic import BaseModel

from src.agents.architectures import get_agent_architecture
from src.agents.image_generation.models import GenerateImageRequest
from src.agents.image_generation.service import (
    AgentImageGenerationError,
    AgentImageGenerationService,
    ImageGenerationNotSupportedError,
)
from src.agents.repository import AgentRepository
from src.apikeys.models import AgentApiKey
from src.auth.google_oauth import GoogleOAuth
from src.auth.jwt_utils import WIDGET_VISITOR_AUDIENCE
from src.config import settings
from src.skills.models import ActorKind
from src.llm.events import SSEEvent, SSEEventType
from src.messages.repositories import MessageRepository, get_message_repository
from src.widget import sessions as widget_sessions
from src.widget.middleware import get_api_key_from_request
from src.widget.models import (
    CreateWidgetConversationRequest,
    WidgetGeneratedImage,
    WidgetGenerateImageRequest,
    WidgetGenerateImageResponse,
    WidgetGenerateTextRequest,
    WidgetGenerateTextResponse,
    WidgetConfigResponse,
    WidgetConversation,
    WidgetConversationResponse,
    WidgetMessageRequest,
    WidgetVisitor,
)
from src.widget.repository import WidgetConversationRepository
from src.exceptions import GENERIC_ERROR_MESSAGE

log = logging.getLogger(__name__)

router = APIRouter(prefix="/widget", tags=["widget"])

# Widget JWT settings (shorter expiration for visitors)
WIDGET_JWT_EXPIRATION_HOURS = 4

google_oauth = GoogleOAuth()


class WidgetTokenResponse(BaseModel):
    """Response containing visitor JWT token."""
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    expires_in: int  # seconds
    visitor: WidgetVisitor


class WidgetRefreshTokenRequest(BaseModel):
    refresh_token: str


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


def get_widget_message_repository() -> MessageRepository:
    """Dependency for MessageRepository."""
    return get_message_repository("dynamodb")


def get_wordpress_ai_conversation(
    *,
    request: Request,
    context: dict[str, Any],
    api_key: AgentApiKey,
    agent_id: str,
):
    """Load or create the owner conversation for a WordPress AI Client request."""
    from src.conversations.models import Conversation
    from src.conversations.repository import ConversationRepository

    site_identity = str(
        context.get("site_url")
        or context.get("home_url")
        or request.headers.get("Origin")
        or "wordpress"
    ).strip().lower().rstrip("/")

    post_id = str(
        context.get("post_id")
        or context.get("postId")
        or context.get("wordpress_post_id")
        or ""
    ).strip()

    conversation_identity = site_identity
    title = "WordPress AI Client"
    if post_id:
        conversation_identity = f"{site_identity}#post:{post_id}"
        title = f"WordPress Post {post_id}"

    identity_hash = hashlib.sha256(conversation_identity.encode("utf-8")).hexdigest()[:16]
    conversation_id = f"wordpress-ai-client-{api_key.agent_id}-{identity_hash}"
    conversation_repo = ConversationRepository()
    conversation = conversation_repo.find_by_id(conversation_id, api_key.created_by)
    if not conversation:
        conversation = conversation_repo.save(
            Conversation(
                conversation_id=conversation_id,
                title=title,
                agent_id=agent_id,
                created_by=api_key.created_by,
            )
        )

    return conversation, conversation_repo


def create_visitor_token(visitor: WidgetVisitor, agent_id: str) -> str:
    """Create a JWT token for a widget visitor."""
    payload = {
        "aud": WIDGET_VISITOR_AUDIENCE,
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
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm], audience=WIDGET_VISITOR_AUDIENCE
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


def get_widget_oauth_callback_url() -> str:
    """Return the externally registered Google OAuth callback URL for widgets."""
    return f"{settings.api_base_url.rstrip('/')}/widget/auth/callback"


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
    api_key: str = Query(..., description="Public API key (pk_live_xxx)"),
    redirect_uri: Optional[str] = Query(None, description="The IDE extension's URI handler; omit for the popup"),
    opener_origin: Optional[str] = Query(None, description="Origin of the page that opened the popup"),
):
    """
    Start a visitor's Google sign-in.

    The popup posts a one-time code to the window that opened it: the embed iframe (the API's own
    origin) by default, or a page on one of the key's allowed origins. The IDE extension instead
    gets the code at its own URI handler. Nothing else is a valid destination.
    """
    from src.apikeys.repository import ApiKeyRepository

    api_key_obj = ApiKeyRepository().find_by_public_key(api_key)
    if not api_key_obj or not api_key_obj.is_active:
        raise HTTPException(status_code=401, detail="Invalid API key")
    if redirect_uri and not widget_sessions.is_allowed_redirect_uri(redirect_uri):
        raise HTTPException(status_code=400, detail="redirect_uri is not allowed")
    origin = opener_origin or widget_sessions.api_origin()
    if origin != widget_sessions.api_origin() and not (
        api_key_obj.allowed_origins and origin in api_key_obj.allowed_origins
    ):
        raise HTTPException(status_code=400, detail="opener_origin must be one of this key's allowed origins")

    state, nonce = widget_sessions.create_state(
        widget_sessions.SignInState(public_key=api_key_obj.public_key, redirect_uri=redirect_uri, opener_origin=origin)
    )
    authorization_url, _ = google_oauth.get_authorization_url(
        state=state, redirect_uri=get_widget_oauth_callback_url()
    )
    response = RedirectResponse(url=authorization_url)
    response.set_cookie(
        widget_sessions.NONCE_COOKIE,
        nonce,
        max_age=int(widget_sessions.STATE_TTL.total_seconds()),
        path=widget_sessions.NONCE_COOKIE_PATH,
        httponly=True,
        secure=settings.api_base_url.startswith("https://"),
        samesite="lax",
    )
    return response


@router.get("/auth/callback")
async def widget_oauth_callback(
    request: Request,
    code: str = Query(None),
    error: str = Query(None),
    state: str = Query(None),
):
    """Finish a visitor's Google sign-in started in this browser, and hand over a one-time code."""
    from src.apikeys.repository import ApiKeyRepository

    sign_in = widget_sessions.read_state(state, request.cookies.get(widget_sessions.NONCE_COOKIE))
    if sign_in is None:
        return _sign_in_page(None, error="Sign-in expired or was started in another browser. Please try again.")
    if error or not code:
        return _sign_in_result(sign_in, error="Sign-in was cancelled.")

    api_key = ApiKeyRepository().find_by_public_key(sign_in.public_key)
    if not api_key or not api_key.is_active:
        return _sign_in_result(sign_in, error="This chat is no longer available.")

    try:
        widget_callback_url = get_widget_oauth_callback_url()
        tokens = await google_oauth.exchange_code_for_tokens(code, redirect_uri=widget_callback_url)
        access_token = tokens.get("access_token")
        if not access_token:
            raise ValueError("Google returned no access token")
        user_info = await google_oauth.get_user_info(access_token)
    except Exception as e:
        log.error(f"Widget OAuth error: {e}", exc_info=True)
        return _sign_in_result(sign_in, error="Sign-in failed. Please try again.")

    email = user_info.get("email")
    if not email or user_info.get("verified_email") is not True:
        return _sign_in_result(sign_in, error="Your Google account has no verified email address.")

    visitor = WidgetVisitor(
        visitor_id=user_info.get("id") or user_info.get("sub") or email,
        email=email,
        name=user_info.get("name"),
        picture=user_info.get("picture"),
    )
    return _sign_in_result(sign_in, code=widget_sessions.create_login_code(api_key.agent_id, visitor))


class WidgetCodeRequest(BaseModel):
    code: str


@router.post("/auth/token", response_model=WidgetTokenResponse)
async def redeem_widget_login_code(
    body: WidgetCodeRequest,
    api_key: Annotated[AgentApiKey, Depends(get_api_key_from_request)],
) -> WidgetTokenResponse:
    """Trade the one-time code from sign-in for a visitor session on this key's agent."""
    session = widget_sessions.redeem_login_code(body.code.strip(), api_key.agent_id)
    if session is None:
        raise HTTPException(status_code=401, detail="Sign-in expired. Please sign in again.")
    return _token_response(session)


@router.post("/auth/refresh", response_model=WidgetTokenResponse)
async def refresh_widget_token(
    body: WidgetRefreshTokenRequest,
    api_key: Annotated[AgentApiKey, Depends(get_api_key_from_request)],
) -> WidgetTokenResponse:
    """
    Trade a visitor refresh token for a new session. The refresh token rotates: the one sent
    stops working. It is only good for the agent it was issued for.
    """
    session = widget_sessions.rotate_refresh_token(body.refresh_token.strip(), api_key.agent_id)
    if session is None:
        raise HTTPException(status_code=401, detail="Token refresh failed")
    return _token_response(session)


@router.post("/auth/revoke", status_code=204)
async def revoke_widget_token(
    body: WidgetRefreshTokenRequest,
    api_key: Annotated[AgentApiKey, Depends(get_api_key_from_request)],
) -> None:
    """Sign out: the refresh token stops working."""
    del api_key
    widget_sessions.revoke_refresh_token(body.refresh_token.strip())


def _token_response(session: widget_sessions.VisitorSession) -> WidgetTokenResponse:
    return WidgetTokenResponse(
        access_token=create_visitor_token(session.visitor, session.agent_id),
        refresh_token=session.refresh_token,
        expires_in=WIDGET_JWT_EXPIRATION_HOURS * 3600,
        visitor=session.visitor,
    )


def _sign_in_result(
    sign_in: widget_sessions.SignInState, *, code: str | None = None, error: str | None = None
) -> Response:
    response: Response
    if sign_in.redirect_uri:
        response = RedirectResponse(url=f"{sign_in.redirect_uri}?{urlencode({'code': code} if code else {'error': error})}")
    else:
        response = _sign_in_page(sign_in.opener_origin, code=code, error=error)
    response.delete_cookie(widget_sessions.NONCE_COOKIE, path=widget_sessions.NONCE_COOKIE_PATH)
    return response


def _sign_in_page(opener_origin: str | None, *, code: str | None = None, error: str | None = None) -> HTMLResponse:
    """The popup's last page: posts the code to its opener, on that opener's origin only, then closes."""
    message = json.dumps({"type": "innomight-oauth-callback", "code": code} if code else None)
    script_data = json.dumps({"message": message, "origin": opener_origin, "error": error}).replace("</", "<\\/")
    return HTMLResponse(content=OAUTH_CALLBACK_HTML.replace("__SIGN_IN__", script_data))


# OAuth callback page HTML served by the backend
OAUTH_CALLBACK_HTML = """<!DOCTYPE html>
<html>
<head>
  <title>Signing in...</title>
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
      var signIn = __SIGN_IN__;
      if (signIn.error || !signIn.message) {
        document.querySelector('.spinner').remove();
        document.querySelector('p').textContent = signIn.error || 'Sign-in failed.';
        return;
      }
      if (window.opener) {
        window.opener.postMessage(JSON.parse(signIn.message), signIn.origin);
      }
      setTimeout(function() { window.close(); }, 500);
    })();
  </script>
</body>
</html>"""


@router.post("/generate-text", response_model=WidgetGenerateTextResponse)
async def generate_text(
    request: Request,
    body: WidgetGenerateTextRequest,
    api_key: Annotated[AgentApiKey, Depends(get_api_key_from_request)],
    agent_repo: Annotated[AgentRepository, Depends(get_agent_repository)],
) -> WidgetGenerateTextResponse:
    """
    Generate text for provider-style integrations using only the widget API key.

    The API key scopes the request to the owning agent. The invocation is treated
    as if the agent owner made the request.
    """
    agent = agent_repo.find_agent_by_id(api_key.agent_id, api_key.created_by)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    conversation, conversation_repo = get_wordpress_ai_conversation(
        request=request,
        context=body.context,
        api_key=api_key,
        agent_id=agent.agent_id,
    )

    architecture = get_agent_architecture(agent.agent_architecture)
    invocation = await architecture.handle_message_buffered(
        agent=agent,
        conversation=conversation,
        user_message=body.message,
        owner_email=api_key.created_by,
        actor_email=api_key.created_by,
        actor_id=api_key.created_by,
        # Only the public widget key stands behind this caller.
        actor_kind=ActorKind.VISITOR,
        attachments=[],
    )

    conversation_repo.save(conversation)

    if not invocation.success:
        raise HTTPException(
            status_code=500,
            detail=invocation.error or "Agent invocation failed",
        )

    return WidgetGenerateTextResponse(
        text=invocation.response_text,
        agent_id=agent.agent_id,
        conversation_id=conversation.conversation_id,
        message_ids={
            key: value
            for key, value in {
                "user_message_id": invocation.user_message_id,
                "assistant_message_id": invocation.assistant_message_id,
            }.items()
            if value
        },
    )


@router.post("/generate-image", response_model=WidgetGenerateImageResponse)
async def generate_image(
    request: Request,
    body: WidgetGenerateImageRequest,
    api_key: Annotated[AgentApiKey, Depends(get_api_key_from_request)],
    agent_repo: Annotated[AgentRepository, Depends(get_agent_repository)],
) -> WidgetGenerateImageResponse:
    """Generate an image for provider-style integrations using only the widget API key."""
    agent = agent_repo.find_agent_by_id(api_key.agent_id, api_key.created_by)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    conversation, conversation_repo = get_wordpress_ai_conversation(
        request=request,
        context=body.context,
        api_key=api_key,
        agent_id=agent.agent_id,
    )

    try:
        result = await AgentImageGenerationService().generate_for_widget(
            agent=agent,
            conversation=conversation,
            owner_email=api_key.created_by,
            actor_email=api_key.created_by,
            request=GenerateImageRequest(
                prompt=body.prompt,
                size=body.size,
                quality=body.quality,
                output_format=body.output_format,  # type: ignore[arg-type]
            ),
        )
    except ImageGenerationNotSupportedError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except AgentImageGenerationError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    conversation_repo.save(conversation)

    return WidgetGenerateImageResponse(
        images=[
            WidgetGeneratedImage(
                url=image.url,
                mime_type=image.mime_type,
                width=image.width,
                height=image.height,
            )
            for image in result.images
        ],
        agent_id=result.agent_id,
        conversation_id=result.conversation_id,
        message_ids={
            "user_message_id": result.user_message_id,
            "assistant_message_id": result.assistant_message_id,
        },
    )


@router.post("/generate-image-stream")
async def generate_image_stream(
    request: Request,
    body: WidgetGenerateImageRequest,
    api_key: Annotated[AgentApiKey, Depends(get_api_key_from_request)],
    agent_repo: Annotated[AgentRepository, Depends(get_agent_repository)],
):
    """Generate an image for provider-style integrations using widget API key SSE."""
    agent = agent_repo.find_agent_by_id(api_key.agent_id, api_key.created_by)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    conversation, conversation_repo = get_wordpress_ai_conversation(
        request=request,
        context=body.context,
        api_key=api_key,
        agent_id=agent.agent_id,
    )

    async def event_stream():
        try:
            async for event in AgentImageGenerationService().stream_for_widget(
                agent=agent,
                conversation=conversation,
                owner_email=api_key.created_by,
                actor_email=api_key.created_by,
                request=GenerateImageRequest(
                    prompt=body.prompt,
                    size=body.size,
                    quality=body.quality,
                    output_format=body.output_format,
                ),
            ):
                yield event.to_sse()
            conversation_repo.save(conversation)
        except ImageGenerationNotSupportedError as e:
            yield SSEEvent(event_type=SSEEventType.ERROR, content=str(e)).to_sse()
        except AgentImageGenerationError as e:
            yield SSEEvent(event_type=SSEEventType.ERROR, content=str(e)).to_sse()
        except Exception as e:
            log.error("Error in widget generate_image_stream: %s", e, exc_info=True)
            yield SSEEvent(event_type=SSEEventType.ERROR, content=GENERIC_ERROR_MESSAGE).to_sse()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


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
                owner_email=api_key.created_by,
                actor_email=visitor.email,
                actor_id=visitor.visitor_id,
                actor_kind=ActorKind.VISITOR,
                attachments=[],  # Widget doesn't support attachments yet
            ):
                yield event.to_sse()

            # Increment message count
            conv_repo.increment_message_count(api_key.agent_id, conversation_id)

        except Exception as e:
            log.error(f"Error in widget message stream: {e}", exc_info=True)
            yield SSEEvent(event_type=SSEEventType.ERROR, content=GENERIC_ERROR_MESSAGE).to_sse()

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
    message_repo: Annotated[MessageRepository, Depends(get_widget_message_repository)],
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
