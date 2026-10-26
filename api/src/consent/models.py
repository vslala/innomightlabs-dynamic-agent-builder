"""Consent records: a request waiting on the person, and the standing "always allow" they can give an agent.

See docs/LLD-action-consent.md.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Annotated, Any, Iterable, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from src.config import settings
from src.consent.preview import ConsentPreview
from src.utils.dynamodb import convert_decimals, convert_floats_to_decimals

#: A request stays readable in the chat this long; its card can be approved for `consent_decision_window_hours`.
CONSENT_REQUEST_TTL_DAYS = 30


def skill_key(installed_skill_id: str, action: str) -> str:
    """The installed skill, not the skill: approving the work Gmail is not approving the personal one."""
    return f"skill:{installed_skill_id}.{action}"


def mcp_key(mcp_id: str, tool_name: str) -> str:
    return f"mcp:{mcp_id}.{tool_name}"


class ConsentStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class SkillActionSubject(BaseModel):
    kind: Literal["skill_action"] = "skill_action"
    skill_id: str
    installed_skill_id: str
    action: str


class McpToolSubject(BaseModel):
    kind: Literal["mcp_tool"] = "mcp_tool"
    mcp_id: str
    tool_name: str


class AutomationStepRef(BaseModel):
    automation_id: str
    node_id: str
    #: The step as the owner was shown it; approving a step that changed since is refused.
    fingerprint: str
    #: An agent step: the owner ticks what it may do, as the edit `grants:<node_id>`.
    agent_step: bool = False
    #: Turn the automation on once its steps are approved (a blueprint asked for it on).
    activate: bool = False


class AutomationStepsSubject(BaseModel):
    """Automation steps that act for the owner, raised by Ila when she builds them: the same consent as the editor's."""

    kind: Literal["automation_steps"] = "automation_steps"
    steps: list[AutomationStepRef]


ConsentSubject = Annotated[SkillActionSubject | McpToolSubject | AutomationStepsSubject, Field(discriminator="kind")]


class TurnCheckpoint(BaseModel):
    """The paused turn's own exchange with the model, exactly as it was, so the turn can carry on after the decision.

    The tool-call audit rows record the same calls, but not in a form a model can resume from: they lose which calls
    one model call made, the text beside them, Gemini's thought signatures and every result past 12 000 characters.
    """

    tool_use_id: str
    model_name: str
    #: Inline when small; otherwise in S3 at `exchange_ref`, as big tool-job results are.
    exchange: list[dict[str, Any]] | None = None
    exchange_ref: str | None = None
    #: The paused turn's reply. The turn resumes only while it is still the conversation's newest message.
    assistant_message_id: str | None = None


class ConsentRequest(BaseModel):
    """One exact call waiting on the person: what it is, what they were shown, and what they decided."""

    consent_id: str = Field(default_factory=lambda: f"consent_{uuid4().hex}")
    conversation_id: str
    agent_id: str
    account_id: str
    owner_id: str
    owner_email: str
    actor_email: str
    actor_id: str
    user_message_id: str | None = None
    tool_use_id: str
    subject: ConsentSubject
    key: str
    title: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    preview: ConsentPreview
    editable: list[str] = Field(default_factory=list)
    checkpoint: TurnCheckpoint | None = None
    status: ConsentStatus = ConsentStatus.PENDING
    edits: dict[str, Any] = Field(default_factory=dict)
    always: bool = False
    reason: str | None = None
    result: str | None = None
    decided_by: str | None = None
    decided_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def expires_at(self) -> datetime:
        return self.created_at + timedelta(hours=settings.consent_decision_window_hours)

    @property
    def approved(self) -> bool:
        return self.status in {ConsentStatus.APPROVED, ConsentStatus.RUNNING, ConsentStatus.SUCCEEDED, ConsentStatus.FAILED}

    @property
    def arguments_to_run(self) -> dict[str, Any]:
        return {**self.arguments, **self.edits}

    def is_open(self, now: datetime | None = None) -> bool:
        return self.status is ConsentStatus.PENDING and (now or datetime.now(timezone.utc)) < self.expires_at

    def state(self, now: datetime | None = None) -> str:
        """The status as the card shows it, with the two states that are only ever derived."""
        checked_at = now or datetime.now(timezone.utc)
        if self.status is ConsentStatus.PENDING and checked_at >= self.expires_at:
            return "expired"
        if (
            self.status is ConsentStatus.RUNNING
            and self.started_at is not None
            and (checked_at - self.started_at).total_seconds() > settings.consent_running_stale_seconds
        ):
            # The process died mid-call. Never retried: like a Gmail send, it may have happened.
            return "unknown"
        return self.status.value

    def checked_edits(self, edits: dict[str, Any]) -> dict[str, Any]:
        """The person's edits, refused unless each is an editable argument holding the same kind of value."""
        for name, value in edits.items():
            if name not in self.editable:
                raise ValueError(f"'{name}' can't be changed here")
            original = self.arguments.get(name, "")
            if isinstance(original, list):
                if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                    raise ValueError(f"'{name}' must be a list of text")
            elif not isinstance(value, str):
                raise ValueError(f"'{name}' must be text")
        return dict(edits)

    @property
    def pk(self) -> str:
        return f"CONVERSATION#{self.conversation_id}"

    @property
    def sk(self) -> str:
        return f"CONSENT#{self.created_at.isoformat()}#{self.consent_id}"

    def to_dynamo_item(self) -> dict[str, Any]:
        item = self.model_dump(mode="json", exclude={"checkpoint": {"exchange"}})
        if self.checkpoint is not None:
            item["checkpoint"]["exchange"] = encode_exchange(self.checkpoint.exchange)
        item.update(
            {
                "pk": self.pk,
                "sk": self.sk,
                "gsi2_pk": f"Consent#{self.consent_id}",
                "gsi2_sk": f"Consent#{self.consent_id}",
                "entity_type": "ConsentRequest",
                "ttl": int((self.created_at + timedelta(days=CONSENT_REQUEST_TTL_DAYS)).timestamp()),
            }
        )
        stored: dict[str, Any] = convert_floats_to_decimals(item)
        return stored

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "ConsentRequest":
        payload = convert_decimals(dict(item))
        for key in ("pk", "sk", "gsi2_pk", "gsi2_sk", "entity_type", "ttl"):
            payload.pop(key, None)
        checkpoint = payload.get("checkpoint")
        if checkpoint and checkpoint.get("exchange") is not None:
            checkpoint["exchange"] = decode_exchange(checkpoint["exchange"])
        return cls.model_validate(payload)

    def to_response(self, url_for_image: Any) -> "ConsentRequestResponse":
        return ConsentRequestResponse(
            consent_id=self.consent_id,
            conversation_id=self.conversation_id,
            agent_id=self.agent_id,
            subject_kind=self.subject.kind,
            key=self.key,
            title=self.title,
            summary=self.preview.summary,
            blocks=self.preview.with_images(url_for_image),
            editable=self.editable,
            state=self.state(),
            edits=self.edits,
            always=self.always,
            reason=self.reason,
            result=self.result,
            created_at=self.created_at,
            decided_at=self.decided_at,
            expires_at=self.expires_at,
        )


class ConsentRequestResponse(BaseModel):
    """What the card needs. The arguments are in the blocks; identities and the checkpoint stay on the server."""

    consent_id: str
    conversation_id: str
    agent_id: str
    subject_kind: str
    key: str
    title: str
    summary: str | None = None
    blocks: list[dict[str, Any]]
    editable: list[str]
    state: str
    edits: dict[str, Any] = Field(default_factory=dict)
    always: bool = False
    reason: str | None = None
    result: str | None = None
    created_at: datetime
    decided_at: datetime | None = None
    expires_at: datetime


class ConsentDecisionRequest(BaseModel):
    decision: Literal["approve", "reject"]
    #: Approve, and let this agent do this again without asking until the person changes it back.
    always: bool = False
    edits: dict[str, Any] = Field(default_factory=dict)
    reason: str | None = Field(default=None, max_length=2000)


class StandingConsent(BaseModel):
    """The owner said: this agent may do this without asking, until I say otherwise."""

    agent_id: str
    key: str
    title: str
    granted_by: str
    granted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    #: The card it was given on, if it came from one.
    consent_id: str | None = None

    @property
    def pk(self) -> str:
        return f"Agent#{self.agent_id}"

    @property
    def sk(self) -> str:
        return f"StandingConsent#{self.key}"

    def to_dynamo_item(self) -> dict[str, Any]:
        return {**self.model_dump(mode="json"), "pk": self.pk, "sk": self.sk, "entity_type": "StandingConsent"}

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "StandingConsent":
        return cls.model_validate({k: v for k, v in item.items() if k not in {"pk", "sk", "entity_type"}})


@dataclass(frozen=True)
class ConsentScope:
    """How a turn settles an action that needs consent and has no standing consent."""

    #: Someone will see a card in this conversation.
    can_ask: bool = True
    #: Subject keys an automation step was approved for.
    granted: frozenset[str] = field(default_factory=frozenset)
    #: The grant recorded on executions those keys allow.
    grant_ref: str | None = None

    @classmethod
    def interactive(cls) -> "ConsentScope":
        return cls()

    @classmethod
    def unattended(cls) -> "ConsentScope":
        return cls(can_ask=False)

    @classmethod
    def automation_step(cls, keys: Iterable[str], grant_ref: str) -> "ConsentScope":
        return cls(can_ask=False, granted=frozenset(keys), grant_ref=grant_ref)


def encode_exchange(value: Any) -> Any:
    """Bytes (Gemini's thought signatures) as tagged base64, so the exchange survives JSON and DynamoDB."""
    if isinstance(value, bytes):
        return {"__bytes__": base64.b64encode(value).decode("ascii")}
    if isinstance(value, dict):
        return {key: encode_exchange(item) for key, item in value.items()}
    if isinstance(value, list):
        return [encode_exchange(item) for item in value]
    return value


def decode_exchange(value: Any) -> Any:
    if isinstance(value, dict):
        if set(value) == {"__bytes__"}:
            return base64.b64decode(value["__bytes__"])
        return {key: decode_exchange(item) for key, item in value.items()}
    if isinstance(value, list):
        return [decode_exchange(item) for item in value]
    return value
