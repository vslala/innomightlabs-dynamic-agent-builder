"""Ila builds an automation whose steps act for the person: it is left off, she asks on a card, approving turns it on.

See docs/LLD-action-consent.md ("Ila: the same consent, asked in her chat").
"""

from __future__ import annotations

import asyncio
import json

import pytest

from src.agents.runtime_state import AgentTurnState
from src.automations.models import AutomationStatus
from src.automations.repository import AutomationRepository
from src.blueprints import service as blueprints_service
from src.blueprints.kinds.base import Action
from src.builder.step_consent import step_consent_card
from src.consent.continuation import ConsentContinuation
from src.consent.models import ConsentStatus, skill_key
from src.consent.repository import ConsentRepository
from src.settings.models import ProviderSettings
from src.settings.repository import ProviderSettingsRepository
from src.skills.models import ActorKind
from tests.mock_data import TEST_USER_EMAIL, account_for, user_id_for
from tests.mock_data import test_owner as _test_owner

OWNER = _test_owner()

BLUEPRINT = """
apiVersion: innomight/v2
kind: Blueprint
metadata: {name: weekly-post, title: Weekly post}
resources:
  writer:
    kind: Agent
    name: Writer
    provider: Bedrock
    instructions: Write the week's summary.
    skills:
      - id: social_media
  weekly:
    kind: Automation
    title: Weekly post
    enabled: true
    trigger:
      manual: {}
    skills:
      - id: social_media
    steps:
      - name: write
        agent: writer
        prompt: "Write this week's summary and post it"
        allow: [social_media.publish]
      - name: post
        skill: social_media
        action: publish
        arguments:
          text: "{{ steps.write.output.response_text }}"
"""


@pytest.fixture(autouse=True)
def bedrock(dynamodb_table) -> None:
    ProviderSettingsRepository().save(
        ProviderSettings(account_id=account_for(TEST_USER_EMAIL), provider_name="Bedrock", encrypted_credentials="{}")
    )


def _automation():
    [found] = [item for item in AutomationRepository().list_in_account(OWNER.account_id) if item.title == "Weekly post"]
    return found


def _ila_state() -> AgentTurnState:
    return AgentTurnState(
        owner_email=TEST_USER_EMAIL, actor_email=TEST_USER_EMAIL, actor_id=TEST_USER_EMAIL, actor_kind=ActorKind.OWNER,
        conversation_id="build-1", agent_id="ila", model_name="m", user_message="build it",
        account_id=account_for(TEST_USER_EMAIL), owner_id=user_id_for(TEST_USER_EMAIL),
    )


class _Ila:
    agent_model = "m"


def test_an_automation_whose_steps_act_for_the_person_is_built_but_left_off():
    deployed = blueprints_service.deploy_blueprint(BLUEPRINT, {}, OWNER)

    assert deployed.deployment.status.value == "applied"
    assert _automation().status != AutomationStatus.ACTIVE
    assert deployed.deployment.awaiting_consent == [_automation().automation_id]


def test_ila_asks_on_one_card_and_approving_it_turns_the_automation_on():
    deployed = blueprints_service.deploy_blueprint(BLUEPRINT, {}, OWNER)
    card = step_consent_card(deployed.validated, deployed.deployment, _ila_state())

    assert card is not None and card.subject.kind == "automation_steps"
    agent_step, post_step = card.subject.steps
    assert (agent_step.agent_step, post_step.agent_step) == (True, False)
    assert agent_step.activate and post_step.activate
    # The blueprint's `allow`, as the agent's own install, ticked for the person to see and keep or untick
    publish = skill_key("social_media", "publish")
    assert card.arguments == {f"grants:{agent_step.node_id}": [publish]}
    assert card.editable == [f"grants:{agent_step.node_id}"]

    repository = ConsentRepository()
    decided = repository.decide(card, approve=True, by=OWNER.user_id)
    turn_input = asyncio.run(ConsentContinuation(decided.consent_id, _Ila(), repository=repository).run(lambda event: None))

    assert repository.get(card.consent_id).status is ConsentStatus.SUCCEEDED
    assert _automation().status == AutomationStatus.ACTIVE
    consent = AutomationRepository().find_consent(_automation().automation_id, agent_step.node_id)
    assert consent is not None and consent.granted_actions == [publish] and consent.via == "chat"
    assert json.loads(repository.get(card.consent_id).result)["turned_on"] == [_automation().automation_id]
    assert 'decision="approved"' in turn_input.user_message


def test_once_approved_building_again_asks_nothing_and_changes_nothing():
    deployed = blueprints_service.deploy_blueprint(BLUEPRINT, {}, OWNER)
    card = step_consent_card(deployed.validated, deployed.deployment, _ila_state())
    repository = ConsentRepository()
    asyncio.run(ConsentContinuation(repository.decide(card, approve=True, by=OWNER.user_id).consent_id, _Ila(),
                                    repository=repository).run(lambda event: None))

    again = blueprints_service.deploy_blueprint(BLUEPRINT, {}, OWNER)
    # `allow` is what the card offered, not what the step stores: it is never a difference to apply
    assert {step.resource: step.action for step in again.plan.steps}["weekly"] == Action.UNCHANGED
    assert step_consent_card(again.validated, again.deployment, _ila_state()) is None
    assert _automation().status == AutomationStatus.ACTIVE


def _issues(text: str) -> list[str]:
    outcome = blueprints_service.deploy_blueprint(text, {}, OWNER)
    assert isinstance(outcome, blueprints_service.Invalid)
    return [issue.message for issue in outcome.issues]


def test_allow_names_only_actions_that_ask_first():
    issues = _issues(BLUEPRINT.replace("allow: [social_media.publish]", "allow: [social_media.check]"))
    assert any("'social_media.check' isn't one" in issue for issue in issues)


def test_only_an_agent_step_can_allow_actions():
    text = BLUEPRINT.replace(
        '          text: "{{ steps.write.output.response_text }}"',
        '          text: "{{ steps.write.output.response_text }}"\n        allow: [social_media.publish]',
    )
    assert any("Only a step that asks an agent" in issue for issue in _issues(text))
