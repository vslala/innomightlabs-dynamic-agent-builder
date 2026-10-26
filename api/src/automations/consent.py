"""The owner's consent for automation steps that act for them, given once when the step is set up.

A step that runs a consent-required skill action can't go live or run without it. An agent step may name the
consent-required actions its agent can take on its own; anything else the agent tries is refused. Either way the
consent holds while the step's config is what the owner saw (`step_fingerprint`). See docs/LLD-action-consent.md.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Literal

from pydantic import BaseModel, Field

from src.accounts.owner import Owner
from src.automations.errors import AutomationValidationError
from src.automations.models import (
    AutomationActionType,
    AutomationConsent,
    AutomationNode,
    AutomationNodeType,
    step_fingerprint,
)
from src.automations.repository import AutomationRepository
from src.consent.preview import (
    ConsentPreview,
    FieldsBlock,
    GrantsBlock,
    PreviewField,
    PreviewGrant,
    WarningBlock,
    default_preview,
)
from src.agents.models import Agent
from src.agents.repository import AgentRepository
from src.consent.actions import ConsentAction, consent_actions
from src.consent.models import AutomationStepRef, AutomationStepsSubject
from src.consent.repository import ConsentRepository
from src.skills.models import SkillActionManifest
from src.skills.registry import SkillRegistry, get_skill_registry
from src.skills.service import SkillRuntimeService

AGENT_STEP_WARNING = "This agent will take the actions you tick on its own, every time the automation runs."


class ConsentRequiredError(AutomationValidationError):
    """Steps that act for the owner and don't have their consent for what they do now."""

    def __init__(self, steps: list[AutomationNode]):
        self.node_ids = [step.node_id for step in steps]
        names = ", ".join(f"'{step.name or step.node_id}'" for step in steps)
        super().__init__(f"Approve what these steps do before the automation can run: {names}")


class StepChangedError(AutomationValidationError):
    """The owner approved a step as it was; it has changed since."""


class StepConsentState(BaseModel):
    """A step that asks the owner first, and where its consent stands."""

    node_id: str
    step: str
    kind: Literal["action", "agent"]
    #: A skill action step can't run without it; an agent step runs without it, taking none of these actions.
    required: bool
    state: Literal["granted", "missing", "stale"]
    fingerprint: str
    title: str
    blocks: list[dict]
    granted_actions: list[str] = Field(default_factory=list)
    granted_at: datetime | None = None
    granted_by: str | None = None


class AutomationConsentService:
    def __init__(
        self,
        repo: AutomationRepository | None = None,
        skill_registry: SkillRegistry | None = None,
        skill_runtime: SkillRuntimeService | None = None,
        consents: ConsentRepository | None = None,
    ):
        self.repo = repo or AutomationRepository()
        self.skill_registry = skill_registry or get_skill_registry()
        self._skill_runtime = skill_runtime
        self._consents = consents
        self.agents = AgentRepository()

    @property
    def skill_runtime(self) -> SkillRuntimeService:
        # Made on first use: checking whether a graph needs consent rarely reaches an agent step's skills
        if self._skill_runtime is None:
            self._skill_runtime = SkillRuntimeService()
        return self._skill_runtime

    @property
    def consents(self) -> ConsentRepository:
        if self._consents is None:
            self._consents = ConsentRepository()
        return self._consents

    def consent_for(self, automation_id: str, step: AutomationNode) -> AutomationConsent | None:
        """The owner's consent for the step as it is now, if they gave it."""
        consent = self.repo.find_consent(automation_id, step.node_id)
        return consent if consent and consent.covers(step.config) else None

    def require(self, automation_id: str, steps: list[AutomationNode]) -> None:
        """Refuse to go live or run while a step that acts for the owner lacks their consent for what it does now."""
        missing = [
            step for step in steps
            if self._action_needing_consent(automation_id, step) and self.consent_for(automation_id, step) is None
        ]
        if missing:
            raise ConsentRequiredError(missing)

    def states(self, automation_id: str, steps: list[AutomationNode], *, suggested: dict[str, list[str]] | None = None) -> list[StepConsentState]:
        """Every step that asks first, with what the owner is shown to approve it. `suggested` pre-ticks agent grants."""
        found = []
        for step in steps:
            shown = self.preview(automation_id, step, (suggested or {}).get(step.node_id))
            if shown is None:
                continue
            preview, kind = shown
            consent = self.repo.find_consent(automation_id, step.node_id)
            state: Literal["granted", "missing", "stale"] = (
                "missing" if consent is None else "granted" if consent.covers(step.config) else "stale"
            )
            found.append(
                StepConsentState(
                    node_id=step.node_id,
                    step=step.name or step.node_id,
                    kind=kind,
                    required=kind == "action",
                    state=state,
                    fingerprint=step_fingerprint(step.config),
                    title=preview.title,
                    blocks=preview.with_images(self.consents.image_url),
                    granted_actions=consent.granted_actions if consent and state == "granted" else [],
                    granted_at=consent.granted_at if consent else None,
                    granted_by=consent.granted_by if consent else None,
                )
            )
        return found

    def grant(
        self,
        automation_id: str,
        step: AutomationNode,
        *,
        fingerprint: str,
        granted_actions: list[str],
        owner: Owner,
        via: Literal["editor", "chat"],
    ) -> AutomationConsent:
        """Record the owner's consent for the step exactly as they saw it."""
        if fingerprint != step_fingerprint(step.config):
            raise StepChangedError(f"'{step.name or step.node_id}' changed since you saw it. Review it again.")
        shown = self.preview(automation_id, step, granted_actions)
        if shown is None:
            raise AutomationValidationError("This step doesn't need your approval.")
        preview, kind = shown
        if kind == "action" and granted_actions:
            raise AutomationValidationError("Only an agent step takes a list of actions to allow.")
        candidates = {item.key for block in preview.blocks if isinstance(block, GrantsBlock) for item in block.items}
        unknown = set(granted_actions) - candidates
        if unknown:
            raise AutomationValidationError(f"This step's agent has no such action: {', '.join(sorted(unknown))}")
        return self.repo.save_consent(
            AutomationConsent(
                automation_id=automation_id,
                node_id=step.node_id,
                fingerprint=fingerprint,
                granted_actions=sorted(set(granted_actions)),
                preview=preview.model_dump(mode="json"),
                granted_by=owner.user_id,
                via=via,
            )
        )

    def revoke(self, automation_id: str, step: AutomationNode) -> None:
        self.repo.delete_consent(automation_id, step.node_id)

    def awaiting(
        self, automation_id: str, steps: list[AutomationNode], allow: dict[str, list[str]], *, activate: bool
    ) -> list[tuple[AutomationStepRef, ConsentPreview]]:
        """The steps to put on a consent card for a just-built automation, each as the owner would approve it.

        A step that acts for the owner, unless approved as it is; an agent step the blueprint `allow`s actions for,
        unless approved for exactly those. `allow` is by step alias, as `skill.action`.
        """
        found = []
        for step in steps:
            agent = self._agent(step)
            step_allow = allow.get(step.alias or "", [])
            wanted = (
                suggested_grants(consent_actions(agent.agent_id, agent.account_id, skill_runtime=self.skill_runtime), step_allow)
                if agent
                else []
            )
            shown = self.preview(automation_id, step, wanted)
            if shown is None:
                continue
            preview, kind = shown
            consent = self.consent_for(automation_id, step)
            if kind == "action" and consent is not None:
                continue
            if kind == "agent" and (not wanted or (consent is not None and set(consent.granted_actions) == set(wanted))):
                continue
            found.append((
                AutomationStepRef(
                    automation_id=automation_id, node_id=step.node_id, fingerprint=step_fingerprint(step.config),
                    agent_step=kind == "agent", activate=activate,
                ),
                preview,
            ))
        return found

    def approve_from_card(
        self, subject: AutomationStepsSubject, grants: dict[str, list[str]], owner: Owner, activate: Callable[[str], object]
    ) -> dict:
        """Record the owner's consent for each step on a decided card, then turn on what was waiting for it."""
        approved = []
        for ref in subject.steps:
            step = self.repo.find_node(ref.automation_id, ref.node_id)
            if step is None:
                raise StepChangedError("A step on this card no longer exists. Ask Ila to build it again.")
            self.grant(
                ref.automation_id, step, fingerprint=ref.fingerprint,
                granted_actions=grants.get(ref.node_id, []) if ref.agent_step else [], owner=owner, via="chat",
            )
            approved.append(step.name or step.node_id)
        activated = sorted({ref.automation_id for ref in subject.steps if ref.activate})
        for automation_id in activated:
            activate(automation_id)
        return {"approved_steps": approved, "turned_on": activated}

    def preview(
        self, automation_id: str, step: AutomationNode, ticked: list[str] | None
    ) -> tuple[ConsentPreview, Literal["action", "agent"]] | None:
        action = self._action_needing_consent(automation_id, step)
        if action is not None and action.consent is not None:
            arguments: dict[str, Any] = step.config["arguments"] if isinstance(step.config.get("arguments"), dict) else {}
            preview = default_preview(action.consent.title, arguments, action.input_schema)
            if action.consent.warning:
                preview.blocks.append(WarningBlock(text=action.consent.warning))
            return preview, "action"

        agent = self._agent(step)
        candidates = consent_actions(agent.agent_id, agent.account_id, skill_runtime=self.skill_runtime) if agent else []
        if agent is None or not candidates:
            return None
        always = {consent.key for consent in self.consents.list_standing(agent.agent_id)}
        chosen = set(ticked or [])
        prompt = step.config.get("prompt_template") or (step.config.get("arguments") or {}).get("prompt_template") or ""
        return (
            ConsentPreview(
                title="What this agent may do on its own",
                blocks=[
                    FieldsBlock(items=[PreviewField(label="Prompt", value=str(prompt))]),
                    GrantsBlock(
                        label="Without asking, it may",
                        argument=f"grants:{step.node_id}",
                        items=[
                            PreviewGrant(
                                key=candidate.key,
                                title=f"{candidate.title} ({candidate.source})",
                                warning=candidate.warning,
                                checked=candidate.key in chosen or candidate.key in always,
                                always_allowed=candidate.key in always,
                            )
                            for candidate in candidates
                        ],
                    ),
                    WarningBlock(text=AGENT_STEP_WARNING),
                ],
            ),
            "agent",
        )

    def _agent(self, step: AutomationNode) -> Agent | None:
        agent_id = step_agent_id(step)
        return self.agents.get(agent_id) if agent_id else None

    def _action_needing_consent(self, automation_id: str, step: AutomationNode) -> SkillActionManifest | None:
        config = step.config
        if step.type != AutomationNodeType.ACTION or config.get("action_type") != AutomationActionType.SKILL_ACTION.value:
            return None
        try:
            installed = self.repo.resolve_skill(
                automation_id,
                installed_skill_id=str(config.get("installed_skill_id") or "").strip(),
                skill_id=str(config.get("skill_id") or "").strip(),
            )
        except ValueError:
            return None
        loaded = self.skill_registry.get(installed.skill_id) if installed else None
        action = loaded.manifest.find_action(str(config.get("action") or "")) if loaded else None
        return action if action is not None and action.consent is not None else None


def step_agent_id(step: AutomationNode) -> str | None:
    """The agent an agent step asks: a native invoke_agent step, or the agent_invocation skill's `invoke`."""
    config = step.config
    if step.type != AutomationNodeType.ACTION:
        return None
    if config.get("action_type") == AutomationActionType.INVOKE_AGENT.value:
        return str(config.get("agent_id") or "") or None
    if config.get("action_type") == AutomationActionType.SKILL_ACTION.value and config.get("skill_id") == "agent_invocation":
        arguments = config.get("arguments")
        return str(arguments.get("agent_id") or "") or None if isinstance(arguments, dict) else None
    return None


def suggested_grants(candidates: list[ConsentAction], allow: list[str]) -> list[str]:
    """A blueprint's `skill.action` entries as the agent's consent keys: the install of that skill, when it has one."""
    keys = []
    for entry in allow:
        skill_id, _, action = entry.partition(".")
        matches = [candidate.key for candidate in candidates if (candidate.skill_id, candidate.action) == (skill_id, action)]
        if len(matches) == 1:
            keys.append(matches[0])
    return keys
