"""Core skills: the Documents manifest served as tools of the DOCUMENT family, never installed."""

import json
from datetime import datetime, timezone

import src.tools.native.handlers  # noqa: F401  # the app's import order (vision.analysis has a cycle through the tools)
from src.agents.architectures.krishna_memgpt_families import TOOL_FAMILIES
from src.agents.runtime_state import AgentTurnState
from src.agents.tool_runtime.core_skills import core_skill_tools, run_core_skill_tool
from src.agents.tool_runtime.families import active_families, prompt_sections
from src.agents.tool_runtime.specs import ToolCategory
from src.documents.models import DocumentOwner, OwnerKind
from src.documents.repository import DocumentRepository
from src.documents.service import DocumentService
from src.documents.storage import DocumentStorage
from src.messages.models import MessageReference
from src.skills import service as skills_service
from src.skills.documents import actions
from src.skills.models import ActorKind, AgentSkill
from src.skills.registry import get_skill_registry
from tests.documents_support import create_documents_bucket


def _state(**changes) -> AgentTurnState:
    state = AgentTurnState(
        owner_email="o@example.com", actor_email="o@example.com", actor_id="o", actor_kind=ActorKind.OWNER,
        conversation_id="conv-1", agent_id="agent-1", model_name="m", user_message="hi", account_id="acct-1",
        owner_id="owner-1",
    )
    for name, value in changes.items():
        setattr(state, name, value)
    return state


def _offered(state: AgentTurnState) -> set[ToolCategory]:
    return {family.category for family in active_families(TOOL_FAMILIES, state)}


def test_every_documents_action_is_a_tool_of_the_document_family():
    tools = core_skill_tools()
    manifest = get_skill_registry().core("documents").manifest

    assert [tool.name for tool in tools] == [action.name for action in manifest.actions]
    assert {tool.spec.category for tool in tools} == {ToolCategory.DOCUMENT}
    read_table = next(tool for tool in tools if tool.name == "read_table")
    assert read_table.spec.definition["parameters"]["required"] == ["document_id", "table"]


def test_a_core_skill_is_neither_in_the_catalog_nor_installable():
    registry = get_skill_registry()

    assert registry.get("documents") is None and "documents" not in {s.manifest.id for s in registry.list()}
    assert registry.core("documents") is not None


def test_an_old_install_of_the_documents_skill_is_not_offered(monkeypatch):
    install = AgentSkill(skill_id="documents", agent_id="agent-1", namespace="core.documents", skill_name="Documents",
                         skill_description="", installed_by="u", installed_at=datetime.now(timezone.utc))
    runtime = skills_service.SkillRuntimeService()
    monkeypatch.setattr(runtime, "list_enabled", lambda agent_id: [install])

    assert runtime.list_usable("agent-1", ActorKind.OWNER) == []


def test_documents_tools_come_with_an_attached_document_or_a_linked_knowledge_base():
    document = MessageReference(kind="document", id="d-1", label="payslip.pdf")

    assert ToolCategory.DOCUMENT not in _offered(_state())
    assert ToolCategory.DOCUMENT in _offered(_state(references={"document": [document]}))
    assert ToolCategory.DOCUMENT in _offered(_state(linked_kb_ids=["kb-1"]))
    sections = prompt_sections(TOOL_FAMILIES, _state(references={"document": [document]}))
    assert any(section.startswith("<documents>") and "describe_document" in section for section in sections)


async def test_a_core_tool_runs_the_manifests_action_with_the_turns_context(dynamodb_table, monkeypatch):
    create_documents_bucket()
    service = DocumentService(DocumentRepository(), DocumentStorage())
    monkeypatch.setattr(actions, "get_document_service", lambda: service)
    owner = DocumentOwner("acct-1", OwnerKind.CONVERSATION, "conv-1")
    service.submit(owner, "notes.md", b"# Notes\nhello", created_by="u")

    result = await run_core_skill_tool(get_skill_registry(), "documents", "list_documents", {}, _state())

    assert [d["filename"] for d in json.loads(result)["documents"]] == ["notes.md"]
