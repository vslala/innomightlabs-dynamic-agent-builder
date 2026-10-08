"""
Vishwakarma: the architecture behind Ada, InnomightLabs' solution builder.

Named after the divine architect. Where Krishna MemGPT is a general agent, Vishwakarma runs one workflow:
discover what the person wants (with forms), draft a blueprint, collect requirements, plan, build once
approved, and explain how to try it. It has no memory or knowledge tools; its tools are the builder's
(forms, plan, apply, status), and its prompt carries the ideas, the blueprint language and the draft.

It is not in the architecture factory, so no agent can be created with it. The builder module creates
it explicitly. See docs/LLD-solution-blueprints.md.
"""

import logging
from typing import TYPE_CHECKING, Any, AsyncIterator, Optional

from src.agents.agentic_loop import PromptRefreshNeeded, TurnComplete, run_agentic_tool_loop
from src.agents.provider_session import open_provider_session
from src.agents.runtime_state import AgentTurnState
from src.agents.tool_audit import ToolCallAuditLog
from src.agents.tool_execution import ToolExecutionRouter
from src.agents.tool_runtime import ToolCategory, ToolRegistry
from src.blueprints.catalog import build_ideas, catalog
from src.builder.models import BuilderSession
from src.builder.repository import BuilderSessionRepository
from src.builder.tools import build_builder_tool_registry
from src.llm.conversation_strategy import FixedWindowStrategy
from src.llm.events import SSEEvent, SSEEventType
from src.messages.models import Attachment, Message
from src.messages.repositories import MessageRepository, get_message_repository
from src.settings.repository import ProviderSettingsRepository, get_provider_settings_repository
from src.skills.models import ActorKind
from src.skills.service import SkillService

from .base import AgentArchitecture
from .krishna_memgpt import TurnOutputs
from .vishwakarma_prompt import build_vishwakarma_system_prompt

if TYPE_CHECKING:
    from src.agents.models import Agent
    from src.conversations.models import Conversation

log = logging.getLogger(__name__)

ARCHITECTURE_NAME = "vishwakarma"


class VishwakarmaArchitecture(AgentArchitecture):
    def __init__(
        self,
        max_context_words: int = 8000,
        *,
        message_repository: Optional[MessageRepository] = None,
        session_repository: Optional[BuilderSessionRepository] = None,
        tool_registry: Optional[ToolRegistry] = None,
        provider_settings_repository: Optional[ProviderSettingsRepository] = None,
        skill_service: Optional[SkillService] = None,
    ):
        self.message_repo = message_repository or get_message_repository("dynamodb")
        self.sessions = session_repository or BuilderSessionRepository()
        self.tool_registry = tool_registry or build_builder_tool_registry()
        self.provider_settings_repo = provider_settings_repository or get_provider_settings_repository()
        self.skill_service = skill_service or SkillService()
        self.conversation_strategy = FixedWindowStrategy(max_words=max_context_words)

    @property
    def name(self) -> str:
        return ARCHITECTURE_NAME

    async def _run_turn(
        self,
        *,
        agent: "Agent",
        conversation: "Conversation",
        user_message: str,
        owner_email: str,
        actor_email: str,
        actor_id: str,
        actor_kind: ActorKind,
        attachments: list[Attachment] | None = None,
        api_key_id: str | None = None,
    ) -> AsyncIterator[SSEEvent]:
        # 1. Preflight: the session this conversation builds in.
        session = self.sessions.find(owner_email, conversation.conversation_id)
        if session is None:
            raise ValueError("This conversation isn't a building session.")
        state = AgentTurnState(
            owner_email=owner_email,
            actor_email=actor_email,
            actor_id=actor_id,
            actor_kind=actor_kind,
            conversation_id=conversation.conversation_id,
            agent_id=agent.agent_id,
            model_name=agent.agent_model or "",
            user_message=user_message,
            attachments=attachments or [],
            api_key_id=api_key_id,
            conversation_context=conversation.context,
        )

        user_msg = Message(
            conversation_id=state.conversation_id,
            created_by=actor_email,
            role="user",
            content=user_message,
            attachments=state.attachments,
        )
        self.message_repo.save(user_msg)
        state.user_message_id = user_msg.message_id
        yield SSEEvent(event_type=SSEEventType.USER_MESSAGE_SAVED, content="User message saved", message_id=user_msg.message_id)

        yield SSEEvent(event_type=SSEEventType.LIFECYCLE_NOTIFICATION, content="Loading provider configuration...")
        provider_session = await open_provider_session(
            agent, owner_email=owner_email, provider_settings_repo=self.provider_settings_repo
        )

        # 2. Context, then the prompt: the ideas, the blueprint language and the draft, loaded once.
        history = self.conversation_strategy.build_context(
            self.message_repo.find_by_conversation(conversation.conversation_id),
            session_timeout_minutes=agent.session_timeout_minutes,
        )
        blueprint_catalog = self._catalog(owner_email)
        ideas = build_ideas()
        context: list[dict[str, Any]] = [
            {"role": "system", "content": self._prompt(ideas, blueprint_catalog, session, conversation.context)},
            *history,
        ]

        # 3. The loop, with only the builder's tools.
        yield SSEEvent(event_type=SSEEventType.LIFECYCLE_NOTIFICATION, content="Thinking about your build...")
        outputs = TurnOutputs()
        audit = ToolCallAuditLog(
            message_repo=self.message_repo,
            conversation_id=conversation.conversation_id,
            actor_email=actor_email,
        )
        async for item in run_agentic_tool_loop(
            provider=provider_session.provider,
            context=context,
            credentials=provider_session.credentials,
            tools=self.tool_registry.definitions_for_categories({ToolCategory.BUILDER}),
            model=state.model_name,
            tool_router=ToolExecutionRouter(self.tool_registry),
            state=state,
        ):
            if isinstance(item, TurnComplete):
                outputs.full_text = item.full_text
                outputs.stop_reason = item.stop_reason
                continue
            if isinstance(item, PromptRefreshNeeded):
                # Planning or building changed the draft the prompt shows.
                refreshed = self.sessions.find(owner_email, conversation.conversation_id) or session
                context[0]["content"] = self._prompt(ideas, blueprint_catalog, refreshed, conversation.context)
                continue

            yield item
            for event in outputs.absorb(item):
                yield event
            audit.observe(item)
            if item.event_type == SSEEventType.ERROR:
                return

        # 4. Persist the reply.
        assistant_text = outputs.assistant_text
        if not assistant_text.strip():
            return
        if not outputs.full_text.strip():
            yield SSEEvent(event_type=SSEEventType.AGENT_RESPONSE_TO_USER, content=assistant_text)
        assistant_msg = Message(
            conversation_id=conversation.conversation_id,
            created_by=actor_email,
            role="assistant",
            content=assistant_text,
        )
        self.message_repo.save(assistant_msg)
        yield SSEEvent(
            event_type=SSEEventType.ASSISTANT_MESSAGE_SAVED,
            content="Assistant message saved",
            message_id=assistant_msg.message_id,
        )

    def _catalog(self, owner_email: str) -> dict[str, Any]:
        ready = {
            item.skill_id: item.available and item.oauth_connected is not False
            for item in self.skill_service.list_catalog(owner_email)
        }
        return catalog(ready=ready)

    @staticmethod
    def _prompt(ideas: list, blueprint_catalog: dict[str, Any], session: BuilderSession, conversation_context: str | None) -> str:
        return build_vishwakarma_system_prompt(
            ideas=ideas,
            catalog=blueprint_catalog,
            session=session,
            conversation_context=conversation_context,
        )
