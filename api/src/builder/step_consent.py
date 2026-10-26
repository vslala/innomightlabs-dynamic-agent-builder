"""When Ila builds an automation whose steps act for the person, she asks for their consent there and then.

It is the editor's consent, asked in her chat: one card for the steps a deploy left waiting. Approving it records each
step's consent and turns on the automations the blueprint wanted on. See docs/LLD-action-consent.md.
"""

from __future__ import annotations

from src.agents.runtime_state import AgentTurnState
from src.agents.tool_runtime.current_call import current_tool_call_id
from src.blueprints.kinds.automation import steps_awaiting_consent
from src.blueprints.models import Deployment
from src.blueprints.validator import ValidatedBlueprint
from src.consent.models import AutomationStepsSubject, ConsentRequest
from src.consent.preview import ConsentBlock, ConsentPreview, GrantsBlock, TextBlock
from src.consent.repository import ConsentRepository

CARD_TITLE = "Approve what your automation does on its own"


def step_consent_card(validated: ValidatedBlueprint, deployment: Deployment, state: AgentTurnState) -> ConsentRequest | None:
    """The card for the steps this deploy built that wait on the person, or None when nothing does."""
    waiting = steps_awaiting_consent(validated, deployment)
    if not waiting:
        return None
    blocks: list[ConsentBlock] = []
    grants: dict[str, list[str]] = {}
    for step in waiting:
        blocks.append(TextBlock(label=step.automation_title, value=f"{step.step_name}: {step.preview.title}"))
        blocks.extend(step.preview.blocks)
        for block in step.preview.blocks:
            if isinstance(block, GrantsBlock):
                grants[block.argument] = [item.key for item in block.items if item.checked]

    return ConsentRepository().open(
        ConsentRequest(
            conversation_id=state.conversation_id,
            agent_id=state.agent_id,
            account_id=state.account_id,
            owner_id=state.owner_id,
            owner_email=state.owner_email,
            actor_email=state.actor_email,
            actor_id=state.actor_id,
            user_message_id=state.user_message_id,
            tool_use_id=current_tool_call_id.get() or "",
            subject=AutomationStepsSubject(steps=[step.ref for step in waiting]),
            key="automation_steps:" + ",".join(sorted({step.ref.automation_id for step in waiting})),
            title=CARD_TITLE,
            # What the person ticks for each agent step, edited on the card
            arguments=grants,
            preview=ConsentPreview(title=CARD_TITLE, blocks=blocks),
            editable=sorted(grants),
        )
    )
