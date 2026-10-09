"""Commands that undo themselves: the order is derived, what can't be undone runs after the commit point, each undo
is saved before its command runs, and an apply interrupted part-way is put back from what was saved."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import ClassVar

import pytest
from fastapi import BackgroundTasks

from src.agents.repository import AgentRepository
from src.apikeys.repository import ApiKeyRepository
from src.blueprints.catalog import example_yaml
from src.blueprints.commands import COMMIT, Command, OrderError, Reversibility, command_order
from src.blueprints.executor import apply_blueprint, recover_interrupted
from src.blueprints.kinds import knowledge_base as knowledge_base_kind
from src.blueprints.kinds.widget_key import CreateWidgetKey, SaveWidgetKey
from src.blueprints.models import DeploymentStatus, JournalState
from src.blueprints.planner import plan_blueprint
from src.blueprints.repository import DeploymentRepository
from src.blueprints.validator import validate_blueprint
from src.config import settings
from src.knowledge.models import KnowledgeBaseStatus
from src.knowledge.repository import KnowledgeBaseRepository
from src.scheduler.runtime import BLUEPRINT_APPLY_REAPER_ID, SchedulerRuntime
from src.settings.models import ProviderSettings
from src.settings.repository import ProviderSettingsRepository
from tests.mock_data import TEST_USER_EMAIL

SITE_AGENT = example_yaml("site-agent") or ""
PARAMS = {"site_url": "https://acme.example/about", "business_name": "Acme"}


# --- Order -------------------------------------------------------------------------------------------------


@dataclass(kw_only=True)
class Make(Command):
    establishes: ClassVar[bool] = True


@dataclass(kw_only=True)
class Touch(Command):
    pass


@dataclass(kw_only=True)
class Destroy(Command):
    reversibility: ClassVar[Reversibility] = Reversibility.IRREVERSIBLE
    deletes: ClassVar[bool] = True


@dataclass(kw_only=True)
class Spend(Command):
    reversibility: ClassVar[Reversibility] = Reversibility.IRREVERSIBLE


def names(order) -> list[str]:
    return ["COMMIT" if step is COMMIT else f"{type(step).__name__}:{step.resource}" for step in order]


def test_what_cant_be_undone_runs_after_the_commit_point_whatever_order_it_comes_in():
    order = command_order([Spend(resource="kb"), Make(resource="kb"), Touch(resource="agent", uses=frozenset({"kb"}))])
    assert names(order) == ["Make:kb", "Touch:agent", "COMMIT", "Spend:kb"]


def test_a_resource_exists_before_anything_uses_it():
    order = command_order([Touch(resource="agent", uses=frozenset({"kb"})), Make(resource="agent"), Make(resource="kb")])
    assert names(order) == ["Make:agent", "Make:kb", "Touch:agent", "COMMIT"]


def test_dependents_are_deleted_first():
    order = command_order([
        Destroy(resource="kb"),
        Destroy(resource="agent", uses=frozenset({"kb"})),
        Destroy(resource="widget", uses=frozenset({"agent"})),
    ])
    assert names(order) == ["COMMIT", "Destroy:widget", "Destroy:agent", "Destroy:kb"]


def test_ties_keep_the_order_given():
    order = command_order([Touch(resource="b"), Touch(resource="a"), Touch(resource="c")])
    assert names(order) == ["Touch:b", "Touch:a", "Touch:c", "COMMIT"]


def test_commands_that_must_each_come_first_are_refused():
    with pytest.raises(OrderError):
        command_order([Make(resource="a", uses=frozenset({"b"})), Make(resource="b", uses=frozenset({"a"}))])


# --- Apply -------------------------------------------------------------------------------------------------


@pytest.fixture
def account(monkeypatch, dynamodb_table) -> list[str]:
    launched: list[str] = []
    monkeypatch.setattr(knowledge_base_kind, "launch_crawl", lambda job_id, *_: launched.append(job_id))
    monkeypatch.setattr(settings, "require_pinecone", lambda: None)
    monkeypatch.setattr(settings, "is_superuser_email", lambda email: True)
    ProviderSettingsRepository().save(
        ProviderSettings(user_email=TEST_USER_EMAIL, provider_name="Bedrock", encrypted_credentials="{}")
    )
    return launched


def planned(text: str = SITE_AGENT, params: dict | None = None):
    validated = validate_blueprint(text, PARAMS if params is None else params)
    return validated, plan_blueprint(validated, TEST_USER_EMAIL)


def test_the_crawl_starts_after_the_commit_point(account):
    _, plan = planned()
    order = names(plan.commands)
    assert order.index("COMMIT") < order.index("StartCrawl:site_kb")
    assert order[-1] == "StartCrawl:site_kb"


def test_every_command_is_journalled_with_its_undo(account):
    validated, plan = planned()
    deployment = apply_blueprint(validated, plan, TEST_USER_EMAIL, BackgroundTasks())
    assert deployment.status == DeploymentStatus.APPLIED and deployment.committed
    assert {entry.state for entry in deployment.journal} == {JournalState.DONE}
    undos = {entry.command.split()[0]: entry.undo.action for entry in deployment.journal if entry.undo}
    assert undos["CreateAgent"] == "delete_new_agent"
    assert undos["CreateWidgetKey"] == "delete_widget_key"
    assert "StartCrawl" not in undos  # it can't be undone


class Interrupted(BaseException):
    """Stands in for the process stopping: not an Exception, so the apply can't catch it and undo."""


def test_an_interrupted_apply_is_put_back_by_the_reaper(account, monkeypatch):
    def stop(*args, **kwargs):
        raise Interrupted()

    monkeypatch.setattr(CreateWidgetKey, "run", stop)
    validated, plan = planned()
    with pytest.raises(Interrupted):
        apply_blueprint(validated, plan, TEST_USER_EMAIL, BackgroundTasks())

    [stuck] = DeploymentRepository().list_by_user(TEST_USER_EMAIL)
    assert stuck.status == DeploymentStatus.APPLYING
    assert stuck.journal[-1].state == JournalState.STARTED  # the widget key may or may not have been made
    agent_id = stuck.resources["assistant"].id

    assert recover_interrupted(now=datetime.now(timezone.utc)) == 0  # not stale yet
    later = datetime.now(timezone.utc) + timedelta(seconds=settings.blueprint_apply_stale_timeout_seconds + 1)
    assert recover_interrupted(now=later) == 1

    [recovered] = DeploymentRepository().list_by_user(TEST_USER_EMAIL)
    assert recovered.status == DeploymentStatus.FAILED
    assert "put back" in recovered.error
    assert recovered.resources == {}
    assert AgentRepository().find_agent_by_id(agent_id, TEST_USER_EMAIL) is None
    [kb] = KnowledgeBaseRepository().find_all_by_user(TEST_USER_EMAIL, include_deleted=True)
    assert kb.status == KnowledgeBaseStatus.DELETED
    assert account == []  # it never got as far as reading the site


def test_an_apply_interrupted_after_the_commit_point_says_what_is_left(account, monkeypatch):
    def stop(*args, **kwargs):
        raise Interrupted()

    monkeypatch.setattr(knowledge_base_kind, "launch_crawl", stop)
    validated, plan = planned()
    with pytest.raises(Interrupted):
        apply_blueprint(validated, plan, TEST_USER_EMAIL, BackgroundTasks())
    later = datetime.now(timezone.utc) + timedelta(seconds=settings.blueprint_apply_stale_timeout_seconds + 1)
    recover_interrupted(now=later)

    [recovered] = DeploymentRepository().list_by_user(TEST_USER_EMAIL)
    assert recovered.status == DeploymentStatus.FAILED_PARTIAL
    assert "Apply the same blueprint again" in recovered.error
    assert AgentRepository().find_agent_by_id(recovered.resources["assistant"].id, TEST_USER_EMAIL) is not None


def test_undo_puts_back_only_what_it_changed_as_it_was_when_it_ran(account, monkeypatch):
    """The before-state is read when the command runs, so a change made after the plan isn't overwritten."""
    validated, plan = planned()
    first = apply_blueprint(validated, plan, TEST_USER_EMAIL, BackgroundTasks())
    agent_id = first.resources["assistant"].id

    edited = SITE_AGENT.replace("keep answers short and friendly.", "be terse.").replace(
        "allow_guests: true", "allow_guests: false"
    )
    validated, plan = planned(edited)
    # Between the plan and the apply, the person edits the agent's description in the dashboard.
    agent = AgentRepository().find_agent_by_id(agent_id, TEST_USER_EMAIL)
    AgentRepository().save(agent.model_copy(update={"agent_description": "Edited in the dashboard"}))

    def fail(*args, **kwargs):
        raise RuntimeError("key service down")

    monkeypatch.setattr(SaveWidgetKey, "run", fail)
    failed = apply_blueprint(validated, plan, TEST_USER_EMAIL, BackgroundTasks())

    assert failed.status == DeploymentStatus.FAILED
    agent = AgentRepository().find_agent_by_id(agent_id, TEST_USER_EMAIL)
    assert "short and friendly" in agent.agent_persona
    assert agent.agent_description == "Edited in the dashboard"
    assert ApiKeyRepository().find_all_by_agent(agent_id)[0].allow_guests is True


async def test_the_reaper_runs_with_the_scheduler(dynamodb_table):
    runtime = SchedulerRuntime()
    await runtime.start()
    try:
        assert runtime.scheduler.get_job(BLUEPRINT_APPLY_REAPER_ID) is not None
    finally:
        await runtime.stop()
