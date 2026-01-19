"""
Widget module for embeddable chat functionality.
"""

from src.widget.middleware import (
    WidgetAuthMiddleware,
    get_api_key_from_request,
    get_agent_id_from_request,
)
from src.widget.models import (
    WidgetConversation,
    WidgetConversationResponse,
    WidgetVisitor,
    WidgetConfigResponse,
    WidgetMessageRequest,
    CreateWidgetConversationRequest,
)
from src.widget.repository import WidgetConversationRepository
from src.widget.router import router as widget_router

__all__ = [
    # Middleware
    "WidgetAuthMiddleware",
    "get_api_key_from_request",
    "get_agent_id_from_request",
    # Models
    "WidgetConversation",
    "WidgetConversationResponse",
    "WidgetVisitor",
    "WidgetConfigResponse",
    "WidgetMessageRequest",
    "CreateWidgetConversationRequest",
    # Repository
    "WidgetConversationRepository",
    # Router
    "widget_router",
]
