"""
Widget router for embeddable chat functionality.

Provides endpoints for:
- Widget configuration
- Visitor OAuth authentication
- Chat conversations with SSE streaming
"""

import asyncio
from contextlib import suppress
from uuid import uuid4
import logging
import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Optional, cast
from urllib.parse import urlencode

import jwt
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel

from src.agents.architectures import get_agent_architecture
from src.agents.image_generation.models import GenerateImageRequest
from src.agents.image_generation.service import (
    AgentImageGenerationError,
    AgentImageGenerationService,
    ImageGenerationNotSupportedError,
)
from src.agents.access import owner_of
from src.agents.models import Agent
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
from src.widget.guest_email import GuestEmailRejected, check_guest_email
from src.widget.guests import GuestSessionEnded, GuestSessionRepository, GuestTurnInProgress, enforce_guest_limit
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
from src.messages.models import ImageAttachment, ImageAttachmentResponse
from src.vision.http import image_response, read_image_upload
from src.vision.models import ImageUploadResponse
from src.vision.uploads import ImageUploadService
from src.vision.limits import image_upload_slot, widget_upload_limits
from src.leads.files import MAX_UPLOAD_READ, LeadFiles
from src.leads.files import UPLOADS_LIMITED as LEAD_FILE_UPLOADS_LIMITED
from src.leads.files import widget_upload_limits as lead_file_upload_limits
from src.leads.models import LeadFileResponse
from src.leads.service import LeadsService
from src.rate_limits.slots import limit_slot

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
    image_attachments: list[ImageAttachmentResponse] = []


def widget_image_url(conversation_id: str, image_id: str) -> str:
    return f"{settings.api_base_url.rstrip('/')}/widget/conversations/{conversation_id}/images/{image_id}"


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
    agent: Agent,
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
    conversation = conversation_repo.find_by_id(conversation_id, agent.owner_partition)
    if not conversation:
        conversation = conversation_repo.save(
            Conversation(
                conversation_id=conversation_id,
                title=title,
                agent_id=agent.agent_id,
                account_id=agent.account_id,
                created_by=agent.owner_id,
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
        "kind": visitor.kind.value,
        "exp": datetime.now(timezone.utc) + timedelta(hours=1 if visitor.is_guest else WIDGET_JWT_EXPIRATION_HOURS),
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

    api_key = get_api_key_from_request(request)
    if payload.get("agent_id") != api_key.agent_id:
        raise HTTPException(401, detail="Invalid token agent")
    if payload.get("kind", "google") not in {"google", "guest"}:
        raise HTTPException(401, detail="Invalid visitor kind")
    visitor = WidgetVisitor(
        visitor_id=payload["sub"],
        email=payload["email"],
        name=payload.get("name"),
        picture=payload.get("picture"),
        kind=payload.get("kind", "google"),
    )
    if visitor.is_guest:
        try:
            request.state.guest_session = GuestSessionRepository().require_active(
                visitor.visitor_id, api_key.agent_id, api_key.key_id)
        except GuestSessionEnded as error:
            raise HTTPException(401, detail="guest_session_ended") from error
    return visitor


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


class WidgetGuestRequest(BaseModel):
    email: str


@router.post("/auth/guest", response_model=WidgetTokenResponse)
async def start_guest_session(
    request: Request,
    body: WidgetGuestRequest,
    api_key: Annotated[AgentApiKey, Depends(get_api_key_from_request)],
    agent_repo: Annotated[AgentRepository, Depends(get_agent_repository)],
) -> WidgetTokenResponse:
    if not api_key.allow_guests:
        raise HTTPException(404, detail="guests_disabled")
    ip = request.client.host if request.client else "unknown"
    enforce_guest_limit("GUEST_START_IP", ip)
    try:
        email = await run_in_threadpool(check_guest_email, body.email)
    except GuestEmailRejected as error:
        raise HTTPException(422, detail=str(error)) from error
    enforce_guest_limit("GUEST_START_EMAIL", email.casefold())
    agent = agent_repo.get(api_key.agent_id)
    if not agent:
        raise HTTPException(404, detail="Agent not found")
    session = widget_sessions.create_guest_session(agent_id=api_key.agent_id, key_id=api_key.key_id,
        email=email, session_timeout_minutes=agent.session_timeout_minutes,
        origin=request.headers.get("Origin", ""), ip=ip)
    return _token_response(session)


@router.post("/auth/guest/end", status_code=204)
async def end_guest_session(
    request: Request,
    visitor: Annotated[WidgetVisitor, Depends(get_visitor_from_request)],
) -> None:
    if not visitor.is_guest:
        raise HTTPException(400, detail="Not a guest session")
    try:
        GuestSessionRepository().end(request.state.guest_session)
    except GuestSessionEnded as error:
        raise HTTPException(401, detail="guest_session_ended") from error


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
    session = widget_sessions.rotate_refresh_token(body.refresh_token.strip(), api_key.agent_id, api_key.key_id)
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
        expires_in=(1 if session.visitor.is_guest else WIDGET_JWT_EXPIRATION_HOURS) * 3600,
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
    agent = agent_repo.get(api_key.agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    # The key acts for the agent's owner: their provider settings, connections and conversation
    owner_email = owner_of(agent).email

    conversation, conversation_repo = get_wordpress_ai_conversation(
        request=request,
        context=body.context,
        api_key=api_key,
        agent=agent,
    )

    architecture = get_agent_architecture(agent.agent_architecture)
    invocation = await architecture.handle_message_buffered(
        agent=agent,
        conversation=conversation,
        user_message=body.message,
        owner_email=owner_email,
        actor_email=owner_email,
        actor_id=owner_email,
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
    agent = agent_repo.get(api_key.agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    # The key acts for the agent's owner: their provider settings, connections and conversation
    owner_email = owner_of(agent).email

    conversation, conversation_repo = get_wordpress_ai_conversation(
        request=request,
        context=body.context,
        api_key=api_key,
        agent=agent,
    )

    try:
        result = await AgentImageGenerationService().generate_for_widget(
            agent=agent,
            conversation=conversation,
            actor_email=owner_email,
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
    agent = agent_repo.get(api_key.agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    # The key acts for the agent's owner: their provider settings, connections and conversation
    owner_email = owner_of(agent).email

    conversation, conversation_repo = get_wordpress_ai_conversation(
        request=request,
        context=body.context,
        api_key=api_key,
        agent=agent,
    )

    async def event_stream():
        try:
            async for event in AgentImageGenerationService().stream_for_widget(
                agent=agent,
                conversation=conversation,
                actor_email=owner_email,
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
        visitor_kind=visitor.kind,
        visitor_name=visitor.name,
        visitor_picture=visitor.picture,
        title=body.title or f"Chat with {visitor.name or 'Visitor'}",
    )

    if visitor.is_guest:
        from botocore.exceptions import ClientError

        guest = request.state.guest_session
        table = GuestSessionRepository().table
        try:
            # Creation must precede the closer's claim or fail, so it can't leave a row after cleanup.
            # The same write records the id on the session, which is how the closer finds it.
            table.meta.client.transact_write_items(TransactItems=[
                {"Update": {"TableName": table.name, "Key": {"pk": guest.pk, "sk": guest.sk},
                    "UpdateExpression": "ADD conversation_ids :cid",
                    "ConditionExpression": "attribute_exists(pk) AND #status = :active AND session_ends_at > :now",
                    "ExpressionAttributeNames": {"#status": "status"},
                    "ExpressionAttributeValues": {":active": "active", ":now": datetime.now(timezone.utc).isoformat(),
                                                  ":cid": {conversation.conversation_id}}}},
                {"Put": {"TableName": table.name, "Item": conversation.to_dynamo_item()}},
            ])
        except ClientError as error:
            if error.response["Error"]["Code"] == "TransactionCanceledException":
                raise HTTPException(401, detail="guest_session_ended") from error
            raise
        saved = conversation
    else:
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

    guest_repo = GuestSessionRepository() if visitor.is_guest else None
    images: list[ImageAttachment] = []
    turn_id = uuid4().hex
    if guest_repo:
        if len(body.content) > settings.widget_guest_max_message_chars:
            raise HTTPException(422, detail="Guest message is too long")
        # Take the turn first, so a message refused as busy or ended doesn't use up the guest's limits.
        try:
            guest_repo.touch(request.state.guest_session, datetime.now(timezone.utc), turn_id=turn_id)
        except GuestTurnInProgress as error:
            raise HTTPException(409, detail="guest_turn_in_progress") from error
        except GuestSessionEnded as error:
            raise HTTPException(401, detail="guest_session_ended") from error
        try:
            enforce_guest_limit("GUEST_MESSAGES", visitor.visitor_id)
            enforce_guest_limit("GUEST_KEY_DAILY", api_key.key_id)
        except HTTPException:
            guest_repo.finish_turn(request.state.guest_session, turn_id)
            raise

    if body.image_ids:
        try:
            images = await _attach_images(agent_repo, api_key, conversation_id, visitor, body.image_ids)
        except Exception:
            if guest_repo:
                guest_repo.finish_turn(request.state.guest_session, turn_id)
            raise

    async def heartbeat_guest_turn(stream_task: asyncio.Task | None) -> None:
        try:
            while True:
                await asyncio.sleep(30)
                assert guest_repo is not None
                guest_repo.heartbeat_turn(request.state.guest_session, turn_id)
        except Exception:
            log.exception("Guest turn lease renewal failed; cancelling the turn")
            if stream_task:
                stream_task.cancel()

    async def event_stream():
        heartbeat = asyncio.create_task(heartbeat_guest_turn(asyncio.current_task())) if guest_repo else None
        try:
            # Load agent
            yield SSEEvent(
                event_type=SSEEventType.LIFECYCLE_NOTIFICATION,
                content="Connecting to agent..."
            ).to_sse()

            # The key is bound to its agent, which runs as its owner
            agent = agent_repo.get(api_key.agent_id)

            if not agent:
                yield SSEEvent(
                    event_type=SSEEventType.ERROR,
                    content="Agent not found"
                ).to_sse()
                return
            owner_email = owner_of(agent).email

            # Get architecture and handle message
            architecture = get_agent_architecture(agent.agent_architecture)

            # Create a mock conversation object for the architecture
            # (architecture expects a Conversation, but we have WidgetConversation)
            from src.conversations.models import Conversation
            mock_conversation = Conversation(
                conversation_id=conversation.conversation_id,
                title=conversation.title,
                agent_id=conversation.agent_id,
                account_id=agent.account_id,
                created_by=visitor.email,  # Never saved: the visitor's chat is the WidgetConversation
            )

            async for event in architecture.handle_message(  # pyright: ignore[reportGeneralTypeIssues]
                agent=agent,
                conversation=mock_conversation,
                user_message=body.content,
                owner_email=owner_email,
                actor_email=visitor.email,
                actor_id=visitor.visitor_id,
                actor_kind=ActorKind.GUEST if visitor.is_guest else ActorKind.VISITOR,
                attachments=[],  # Widget doesn't support file attachments; images go in `images`
                images=images,
            ):
                yield event.to_sse()

            # Increment message count
            conv_repo.increment_message_count(api_key.agent_id, conversation_id)

        except Exception as e:
            log.error(f"Error in widget message stream: {e}", exc_info=True)
            yield SSEEvent(event_type=SSEEventType.ERROR, content=GENERIC_ERROR_MESSAGE).to_sse()
        finally:
            if heartbeat:
                heartbeat.cancel()
                with suppress(asyncio.CancelledError):
                    await heartbeat
            if guest_repo:
                guest_repo.finish_turn(request.state.guest_session, turn_id)

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
            image_attachments=[
                ImageAttachmentResponse(
                    **image.model_dump(include=set(ImageAttachmentResponse.model_fields) - {"url"}),
                    url=widget_image_url(conversation_id, image.image_id),
                )
                for image in message.image_attachments
            ],
        )
        for message in messages
        if message.role in {"user", "assistant"}
    ]


async def _attach_images(
    agent_repo: AgentRepository,
    api_key: AgentApiKey,
    conversation_id: str,
    visitor: WidgetVisitor,
    image_ids: list[str],
) -> list[ImageAttachment]:
    agent = agent_repo.get(api_key.agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return await asyncio.to_thread(
        ImageUploadService().attach,
        agent=agent,
        conversation_id=conversation_id,
        actor_id=visitor.visitor_id,
        image_ids=image_ids,
    )


def _own_conversation(
    api_key: AgentApiKey, visitor: WidgetVisitor, conv_repo: WidgetConversationRepository, conversation_id: str
) -> None:
    conversation = conv_repo.find_by_id(api_key.agent_id, conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conversation.visitor_id != visitor.visitor_id:
        raise HTTPException(status_code=403, detail="Access denied")


@router.post("/conversations/{conversation_id}/images", response_model=ImageUploadResponse, status_code=201)
async def upload_image(
    conversation_id: str,
    api_key: Annotated[AgentApiKey, Depends(get_api_key_from_request)],
    visitor: Annotated[WidgetVisitor, Depends(get_visitor_from_request)],
    conv_repo: Annotated[WidgetConversationRepository, Depends(get_widget_conversation_repository)],
    agent_repo: Annotated[AgentRepository, Depends(get_agent_repository)],
    file: UploadFile = File(...),
) -> ImageUploadResponse:
    """Upload an image to send with the visitor's next message; guests and signed-in visitors alike."""
    _own_conversation(api_key, visitor, conv_repo, conversation_id)
    agent = agent_repo.get(api_key.agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    with image_upload_slot(widget_upload_limits(visitor_id=visitor.visitor_id, key_id=api_key.key_id)):
        upload = await asyncio.to_thread(
            ImageUploadService().store,
            agent=agent,
            conversation_id=conversation_id,
            uploaded_by=visitor.visitor_id,
            filename=file.filename or "",
            raw=await read_image_upload(file),
        )
    return ImageUploadResponse.of(upload, widget_image_url(conversation_id, upload.image_id))


@router.post("/conversations/{conversation_id}/lead-files", response_model=LeadFileResponse, status_code=201)
async def upload_lead_file(
    conversation_id: str,
    api_key: Annotated[AgentApiKey, Depends(get_api_key_from_request)],
    visitor: Annotated[WidgetVisitor, Depends(get_visitor_from_request)],
    conv_repo: Annotated[WidgetConversationRepository, Depends(get_widget_conversation_repository)],
    agent_repo: Annotated[AgentRepository, Depends(get_agent_repository)],
    form: str = Form(..., description="The lead form's slug"),
    input_name: str = Form(..., alias="input", description="The form's file field"),
    file: UploadFile = File(...),
) -> LeadFileResponse:
    """Upload a file into a lead form the agent showed; put the returned `file_id` in that field's answer."""
    _own_conversation(api_key, visitor, conv_repo, conversation_id)
    agent = agent_repo.get(api_key.agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    lead_form = LeadsService().find_active_form(agent.account_id, form)

    with limit_slot(lead_file_upload_limits(visitor_id=visitor.visitor_id, key_id=api_key.key_id),
                    refusal=LEAD_FILE_UPLOADS_LIMITED):
        lead_file = await asyncio.to_thread(
            LeadFiles().store,
            lead_form,
            input_name=input_name,
            agent_id=agent.agent_id,
            conversation_id=conversation_id,
            uploaded_by=visitor.visitor_id,
            filename=file.filename or "",
            raw=await file.read(MAX_UPLOAD_READ),
        )
    return LeadFileResponse.of(lead_file)


@router.get("/conversations/{conversation_id}/images/{image_id}")
async def get_image(
    conversation_id: str,
    image_id: str,
    api_key: Annotated[AgentApiKey, Depends(get_api_key_from_request)],
    visitor: Annotated[WidgetVisitor, Depends(get_visitor_from_request)],
    conv_repo: Annotated[WidgetConversationRepository, Depends(get_widget_conversation_repository)],
) -> Response:
    """An image from the visitor's own conversation."""
    _own_conversation(api_key, visitor, conv_repo, conversation_id)
    stored = await asyncio.to_thread(
        ImageUploadService().open_bytes, conversation_id=conversation_id, image_id=image_id
    )
    return image_response(stored)
