"""The one-off cleanup removes what building with Ila left behind, and nothing else."""

import importlib.util
import sys
from pathlib import Path

from fastapi import BackgroundTasks

from src.agents.models import Agent
from src.agents.repository import AgentRepository
from src.blueprints.catalog import example_yaml
from src.blueprints.kinds import knowledge_base as knowledge_base_kind
from src.blueprints.kits import KitRepository
from src.blueprints.repository import DeploymentRepository
from src.blueprints.service import Deployed, deploy_blueprint
from src.builder.models import ILA_AGENT_ID, BuilderSession
from src.builder.repository import BuilderSessionRepository
from src.config import settings
from src.conversations.models import Conversation
from src.conversations.repository import ConversationRepository
from src.db import get_dynamodb_resource
from src.knowledge.models import KnowledgeBaseStatus
from src.knowledge.repository import KnowledgeBaseRepository
from src.knowledge.service import KnowledgeBaseService
from src.settings.models import ProviderSettings
from src.settings.repository import ProviderSettingsRepository
from tests.mock_data import account_for, TEST_USER_EMAIL, agent_fields, conversation_fields, conversations_of, owner_ids, session_fields
from tests.mock_data import test_owner as _test_owner

TEST_OWNER = _test_owner()


SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "cleanup_ila_builds.py"


def load_script():
    spec = importlib.util.spec_from_file_location("cleanup_ila_builds", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # its dataclasses look their module up
    spec.loader.exec_module(module)
    return module


def test_ila_builds_are_removed_and_the_persons_own_things_stay(dynamodb_table, monkeypatch):
    monkeypatch.setattr(knowledge_base_kind, "launch_crawl", lambda *_: None)
    monkeypatch.setattr(settings, "require_pinecone", lambda: None)
    monkeypatch.setattr(KnowledgeBaseService, "_delete_pinecone_namespace", lambda self, kb_id: 0)
    monkeypatch.setattr(settings, "conversation_media_bucket", "")
    ProviderSettingsRepository().save(
        ProviderSettings(account_id=account_for(TEST_USER_EMAIL), provider_name="Bedrock", encrypted_credentials="{}")
    )
    built = deploy_blueprint(example_yaml("site-agent") or "", {"site_url": "https://acme.example", "business_name": "Acme"},
                             TEST_OWNER, BackgroundTasks())
    assert isinstance(built, Deployed)
    ila_chat = ConversationRepository().save(Conversation(title="Build", agent_id=ILA_AGENT_ID, **conversation_fields(TEST_USER_EMAIL)))
    BuilderSessionRepository().save(BuilderSession(
        conversation_id=ila_chat.conversation_id, **session_fields(TEST_USER_EMAIL), provider="Bedrock",
    ))
    mine = AgentRepository().save(Agent(
        agent_name="Mine", agent_architecture="krishna-memgpt", agent_provider="Bedrock", agent_persona="Hi",
        **agent_fields(TEST_USER_EMAIL),
    ))
    my_chat = ConversationRepository().save(Conversation(title="Chat", agent_id=mine.agent_id, **conversation_fields(TEST_USER_EMAIL)))

    script = load_script()
    table = get_dynamodb_resource().Table(settings.dynamodb_table)
    found = script.find(table, None)
    account = found[TEST_OWNER]
    assert account.conversations == {ila_chat.conversation_id}
    assert account.agents == {built.deployment.resources["assistant"].id}
    assert script.delete(table, TEST_OWNER, account) == []

    assert AgentRepository().get(built.deployment.resources["assistant"].id) is None
    kb = KnowledgeBaseRepository().find_in_account(owner_ids(TEST_USER_EMAIL)[0], built.deployment.resources["site_kb"].id)
    assert kb.status == KnowledgeBaseStatus.DELETED
    assert ConversationRepository().find_by_id(ila_chat.conversation_id, conversations_of(TEST_USER_EMAIL)) is None
    assert BuilderSessionRepository().find(TEST_OWNER.member_pk, ila_chat.conversation_id) is None
    assert DeploymentRepository().list_owned(TEST_OWNER.account_id, TEST_OWNER.user_id) == []
    assert KitRepository().list_owned(TEST_OWNER.account_id, TEST_OWNER.user_id) == []
    # The person's own agent and chat stay.
    assert AgentRepository().get(mine.agent_id) is not None
    assert ConversationRepository().find_by_id(my_chat.conversation_id, conversations_of(TEST_USER_EMAIL)) is not None
    assert script.find(table, None) == {}
