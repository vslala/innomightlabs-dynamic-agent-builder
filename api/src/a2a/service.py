import base64
import hashlib
import json
import logging
import re
import time
from typing import Any
from uuid import uuid4

from src.a2a.models import (
    A2AAgentCapabilities,
    A2AAgentCard,
    A2AAgentInterface,
    A2AAgentListResponse,
    A2AAgentProvider,
    A2AAgentSummary,
    A2AApiKeySecurityScheme,
    A2AMessage,
    A2AMessageRole,
    A2AMessageSendRequest,
    A2ASecurityScheme,
    A2ASecurityRequirement,
    A2ASkill,
    A2AStringList,
    A2ATask,
    A2ATaskResponse,
    A2ATaskState,
    A2ATaskStatus,
    A2ATaskStatusUpdateEvent,
    A2ATextPart,
)
from src.a2a.repository import A2ATaskRepository
from src.agents.architectures import get_agent_architecture
from src.agents.models import Agent
from src.agents.repository import AgentRepository
from src.apikeys.models import AgentApiKey
from src.config import settings
from src.conversations.models import Conversation
from src.conversations.repository import ConversationRepository
from src.llm.events import SSEEvent, SSEEventType
from src.skills.models import AgentSkill
from src.skills.repository import AgentSkillRepository


A2A_PROTOCOL_VERSION = "1.0.0"
TEXT_MODE = "text/plain"
TASK_TTL_SECONDS = 30 * 24 * 60 * 60

log = logging.getLogger(__name__)


class A2ADiscoveryService:
    def __init__(
        self,
        agent_repository: AgentRepository | None = None,
        skill_repository: AgentSkillRepository | None = None,
    ):
        self.agent_repository = agent_repository or AgentRepository()
        self.skill_repository = skill_repository or AgentSkillRepository()

    def facilitator_card(self) -> A2AAgentCard:
        return A2AAgentCard(
            name="InnomightLabs A2A Facilitator",
            description="Discovery entrypoint for InnomightLabs agents enabled for Agent2Agent communication.",
            supportedInterfaces=self._agent_interfaces(f"{self._base_url()}/a2a"),
            provider=A2AAgentProvider(
                organization="InnomightLabs",
                url="https://innomightlabs.com",
            ),
            version=A2A_PROTOCOL_VERSION,
            capabilities=A2AAgentCapabilities(),
            securitySchemes=self._security_schemes(),
            securityRequirements=self._security_requirements(),
            defaultInputModes=[TEXT_MODE],
            defaultOutputModes=[TEXT_MODE],
            skills=[
                A2ASkill(
                    id="discover_public_agents",
                    name="Discover Public Agents",
                    description="List InnomightLabs agents enabled for Agent2Agent communication.",
                    tags=["discovery", "facilitator"],
                )
            ],
        )

    def agent_card(self, agent_id: str) -> A2AAgentCard | None:
        agent = self.agent_repository.find_agent2agent_enabled_by_id(agent_id)
        if not agent:
            return None

        return A2AAgentCard(
            name=_sanitize_text(agent.agent_name, max_length=100) or "Agent",
            description=_sanitize_text(agent.agent_description, max_length=1000)
            or "InnomightLabs agent enabled for Agent2Agent communication.",
            supportedInterfaces=self._agent_interfaces(self._agent_service_url(agent.agent_id)),
            provider=A2AAgentProvider(
                organization="InnomightLabs",
                url="https://innomightlabs.com",
            ),
            version=A2A_PROTOCOL_VERSION,
            capabilities=A2AAgentCapabilities(),
            securitySchemes=self._security_schemes(),
            securityRequirements=self._security_requirements(),
            defaultInputModes=[TEXT_MODE],
            defaultOutputModes=[TEXT_MODE],
            skills=self._agent_skills(agent.agent_id),
        )

    def list_agents(self, *, limit: int, cursor: str | None) -> A2AAgentListResponse:
        agents, next_key = self.agent_repository.list_agent2agent_enabled(
            limit=limit,
            cursor=_decode_cursor(cursor),
        )
        return A2AAgentListResponse(
            items=[self._summary(agent) for agent in agents],
            next_cursor=_encode_cursor(next_key),
        )

    def _summary(self, agent: Agent) -> A2AAgentSummary:
        return A2AAgentSummary(
            agent_id=agent.agent_id,
            name=_sanitize_text(agent.agent_name, max_length=100) or "Agent",
            description=_sanitize_text(agent.agent_description, max_length=1000),
            service_url=self._agent_service_url(agent.agent_id),
        )

    def _security_schemes(self) -> dict[str, A2ASecurityScheme]:
        return {
            "agentApiKey": A2ASecurityScheme(
                apiKeySecurityScheme=A2AApiKeySecurityScheme(
                    location="header",
                    name="Authorization",
                    description="Use Authorization: Bearer <agent API key>.",
                )
            )
        }

    def _security_requirements(self) -> list[A2ASecurityRequirement]:
        return [
            A2ASecurityRequirement(
                schemes={"agentApiKey": A2AStringList(list=[])}
            )
        ]

    def _agent_interfaces(self, url: str) -> list[A2AAgentInterface]:
        protocols = self._ordered_protocols()
        return [
            A2AAgentInterface(
                url=url,
                protocolBinding=protocol,
                protocolVersion="1.0",
            )
            for protocol in protocols
        ]

    def _ordered_protocols(self) -> list[str]:
        supported = [
            protocol
            for protocol in settings.a2a_supported_protocols
            if protocol in {"JSONRPC", "HTTP+JSON"}
        ]
        primary = settings.a2a_primary_protocol
        if primary in supported:
            return [primary, *[protocol for protocol in supported if protocol != primary]]
        return supported or ["JSONRPC"]

    def _agent_service_url(self, agent_id: str) -> str:
        return f"{self._base_url()}/a2a/agents/{agent_id}"

    def _base_url(self) -> str:
        return settings.api_base_url.rstrip("/")

    def _agent_skills(self, agent_id: str) -> list[A2ASkill]:
        skills = [
            A2ASkill(
                id="chat",
                name="Chat With Agent",
                description="Send a task or question to this agent.",
                tags=["text"],
            )
        ]

        installed_skills = self.skill_repository.list_by_agent(agent_id)
        for skill in sorted(installed_skills, key=lambda item: item.skill_name.lower()):
            if not skill.enabled:
                continue
            skills.append(_skill_to_a2a_skill(skill))

        return skills


def get_a2a_discovery_service() -> A2ADiscoveryService:
    return A2ADiscoveryService()


def _skill_to_a2a_skill(skill: AgentSkill) -> A2ASkill:
    return A2ASkill(
        id=_sanitize_skill_id(skill.installed_skill_id or skill.skill_id),
        name=_sanitize_text(skill.skill_name, max_length=100) or skill.skill_id,
        description=_sanitize_text(skill.skill_description, max_length=500)
        or "Installed agent skill.",
        tags=[
            tag
            for tag in [
                "installed_skill",
                _sanitize_skill_id(skill.namespace) if skill.namespace else "",
                _sanitize_skill_id(skill.skill_id),
            ]
            if tag
        ],
    )


class A2AInvocationService:
    def __init__(
        self,
        *,
        agent_repository: AgentRepository | None = None,
        conversation_repository: ConversationRepository | None = None,
        task_repository: A2ATaskRepository | None = None,
    ) -> None:
        self.agent_repository = agent_repository or AgentRepository()
        self.conversation_repository = conversation_repository or ConversationRepository()
        self.task_repository = task_repository or A2ATaskRepository()

    async def send_message(
        self,
        *,
        agent_id: str,
        request: A2AMessageSendRequest,
        api_key: AgentApiKey,
    ) -> A2ATaskResponse:
        agent = self._load_agent(agent_id=agent_id, api_key=api_key)
        self._validate_request(request)
        user_message = self._user_text(request.message)
        task = self._create_task(agent=agent, request=request, api_key=api_key)
        conversation = self._resolve_conversation(task=task, agent=agent)
        task.status = A2ATaskStatus(state=A2ATaskState.WORKING)
        self.task_repository.save(task)

        try:
            architecture = get_agent_architecture(agent.agent_architecture)
            invocation = await architecture.handle_message_buffered(
                agent=agent,
                conversation=conversation,
                user_message=user_message,
                owner_email=api_key.created_by,
                actor_email=api_key.created_by,
                actor_id=f"a2a:{api_key.key_id}",
                attachments=[],
            )
            self.conversation_repository.save(conversation)

            if invocation.success:
                task.status = A2ATaskStatus(
                    state=A2ATaskState.COMPLETED,
                    message=self._agent_message(invocation.response_text),
                )
            else:
                task.status = A2ATaskStatus(
                    state=A2ATaskState.FAILED,
                    message=self._agent_message(invocation.error or "Agent invocation failed"),
                )
            task.artifacts = [
                event.model_dump(mode="json", exclude_none=True)
                for event in invocation.events
            ]
        except Exception as exc:
            log.error("A2A message send failed: %s", exc, exc_info=True)
            task.status = A2ATaskStatus(
                state=A2ATaskState.FAILED,
                message=self._agent_message(str(exc)),
            )

        self.task_repository.save(task)
        return A2ATaskResponse(task=task)

    async def stream_message(
        self,
        *,
        agent_id: str,
        request: A2AMessageSendRequest,
        api_key: AgentApiKey,
    ):
        agent = self._load_agent(agent_id=agent_id, api_key=api_key)
        self._validate_request(request)
        user_text = self._user_text(request.message)
        task = self._create_task(agent=agent, request=request, api_key=api_key)
        conversation = self._resolve_conversation(task=task, agent=agent)
        task.status = A2ATaskStatus(state=A2ATaskState.WORKING)
        self.task_repository.save(task)

        response_parts: list[str] = []
        events: list[dict[str, Any]] = []

        yield self._stream_event(task=task, state=A2ATaskState.WORKING, final=False)

        try:
            architecture = get_agent_architecture(agent.agent_architecture)
            async for event in architecture.handle_message(  # pyright: ignore[reportGeneralTypeIssues]
                agent=agent,
                conversation=conversation,
                user_message=user_text,
                owner_email=api_key.created_by,
                actor_email=api_key.created_by,
                actor_id=f"a2a:{api_key.key_id}",
                attachments=[],
            ):
                events.append(event.model_dump(mode="json", exclude_none=True))
                if event.event_type == SSEEventType.AGENT_RESPONSE_TO_USER:
                    response_parts.append(event.content)
                elif event.event_type == SSEEventType.UI_FORM_RENDER:
                    task.status = A2ATaskStatus(
                        state=A2ATaskState.INPUT_REQUIRED,
                        message=self._agent_message(event.content),
                    )
                    yield self._stream_event(
                        task=task,
                        state=A2ATaskState.INPUT_REQUIRED,
                        message=task.status.message,
                        final=False,
                    )
                elif event.event_type == SSEEventType.ERROR:
                    task.status = A2ATaskStatus(
                        state=A2ATaskState.FAILED,
                        message=self._agent_message(event.content),
                    )
                    yield self._stream_event(
                        task=task,
                        state=A2ATaskState.FAILED,
                        message=task.status.message,
                        final=True,
                    )
                    self._finalize_stream_task(task=task, conversation=conversation, events=events)
                    return

            self.conversation_repository.save(conversation)
            task.status = A2ATaskStatus(
                state=A2ATaskState.COMPLETED,
                message=self._agent_message("".join(response_parts)),
            )
            task.artifacts = events
            self.task_repository.save(task)
            yield self._stream_event(
                task=task,
                state=A2ATaskState.COMPLETED,
                message=task.status.message,
                final=True,
            )
        except Exception as exc:
            log.error("A2A message stream failed: %s", exc, exc_info=True)
            task.status = A2ATaskStatus(
                state=A2ATaskState.FAILED,
                message=self._agent_message(str(exc)),
            )
            task.artifacts = events
            self.task_repository.save(task)
            yield self._stream_event(
                task=task,
                state=A2ATaskState.FAILED,
                message=task.status.message,
                final=True,
            )

    def get_task(self, *, agent_id: str, task_id: str, api_key: AgentApiKey) -> A2ATask | None:
        task = self.task_repository.find_by_id(agent_id=agent_id, task_id=task_id)
        if not task or task.client_key_id != api_key.key_id:
            return None
        return task

    def list_tasks(self, *, agent_id: str, api_key: AgentApiKey) -> list[A2ATask]:
        return self.task_repository.find_by_agent_and_client(
            agent_id=agent_id,
            client_key_id=api_key.key_id,
        )

    def _load_agent(self, *, agent_id: str, api_key: AgentApiKey) -> Agent:
        agent = self.agent_repository.find_agent_by_id(agent_id, api_key.created_by)
        if not agent or not agent.is_agent2agent_enabled:
            raise ValueError("Agent not found")
        return agent

    def _validate_request(self, request: A2AMessageSendRequest) -> None:
        if request.message.role != A2AMessageRole.USER:
            raise ValueError("Only ROLE_USER messages are accepted")
        accepted = (
            request.configuration.accepted_output_modes
            if request.configuration
            else None
        )
        if accepted and TEXT_MODE not in accepted:
            raise ValueError("Only text/plain output is supported")

    def _create_task(
        self,
        *,
        agent: Agent,
        request: A2AMessageSendRequest,
        api_key: AgentApiKey,
    ) -> A2ATask:
        context_id = request.message.context_id or str(uuid4())
        task_id = request.message.task_id or str(uuid4())
        conversation_id = _conversation_id(
            agent_id=agent.agent_id,
            client_key_id=api_key.key_id,
            context_id=context_id,
        )
        task = A2ATask(
            id=task_id,
            contextId=context_id,
            agentId=agent.agent_id,
            ownerEmail=api_key.created_by,
            clientKeyId=api_key.key_id,
            conversationId=conversation_id,
            status=A2ATaskStatus(state=A2ATaskState.SUBMITTED),
            history=[request.message],
            ttl=int(time.time()) + TASK_TTL_SECONDS,
        )
        return task

    def _resolve_conversation(self, *, task: A2ATask, agent: Agent) -> Conversation:
        conversation = self.conversation_repository.find_by_id(
            task.conversation_id,
            task.owner_email,
        )
        if conversation:
            if conversation.agent_id != agent.agent_id:
                raise ValueError("A2A context is bound to a different agent")
            return conversation

        conversation = Conversation(
            conversation_id=task.conversation_id,
            title=f"A2A: {agent.agent_name}",
            description=f"Agent2Agent context {task.context_id}",
            agent_id=agent.agent_id,
            created_by=task.owner_email,
        )
        self.conversation_repository.save(conversation)
        return conversation

    def _user_text(self, message: A2AMessage) -> str:
        return "\n".join(part.text for part in message.parts).strip()

    def _agent_message(self, text: str) -> A2AMessage:
        return A2AMessage(
            role=A2AMessageRole.AGENT,
            parts=[A2ATextPart(text=text or " ")],
        )

    def _stream_event(
        self,
        *,
        task: A2ATask,
        state: A2ATaskState,
        message: A2AMessage | None = None,
        final: bool,
    ) -> str:
        event = A2ATaskStatusUpdateEvent(
            taskId=task.task_id,
            contextId=task.context_id,
            status=A2ATaskStatus(state=state, message=message),
            final=final,
        )
        return f"data: {event.model_dump_json(by_alias=True, exclude_none=True)}\n\n"

    def _finalize_stream_task(
        self,
        *,
        task: A2ATask,
        conversation: Conversation,
        events: list[dict[str, Any]],
    ) -> None:
        self.conversation_repository.save(conversation)
        task.artifacts = events
        self.task_repository.save(task)


def get_a2a_invocation_service() -> A2AInvocationService:
    return A2AInvocationService()


def _sanitize_text(value: str | None, *, max_length: int) -> str | None:
    if value is None:
        return None
    compact = " ".join(value.strip().split())
    if not compact:
        return None
    return compact[:max_length]


def _sanitize_skill_id(value: str) -> str:
    sanitized = re.sub(r"[^a-zA-Z0-9_-]+", "_", value.strip())
    return sanitized.strip("_")[:100] or "skill"


def _encode_cursor(cursor: dict[str, Any] | None) -> str | None:
    if not cursor:
        return None
    encoded = base64.urlsafe_b64encode(json.dumps(cursor).encode("utf-8")).decode("ascii")
    return encoded.rstrip("=")


def _decode_cursor(cursor: str | None) -> dict[str, Any] | None:
    if not cursor:
        return None
    padded = cursor + ("=" * (-len(cursor) % 4))
    try:
        decoded = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        value = json.loads(decoded)
    except (ValueError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _conversation_id(*, agent_id: str, client_key_id: str, context_id: str) -> str:
    digest = hashlib.sha256(f"{client_key_id}:{context_id}".encode("utf-8")).hexdigest()[:16]
    return f"a2a-{agent_id}-{digest}"
