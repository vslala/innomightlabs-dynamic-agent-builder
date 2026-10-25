"""The Documents skill: an agent lists and reads stored documents in parts, from its conversation or a linked KB."""

import pytest

# The order the app loads them in: vision.analysis imported first runs into an import cycle through the native tools
import src.tools.native.handlers  # noqa: F401
from src.agents.models import Agent
from src.agents.repository import AgentRepository
from src.documents.models import DocumentOwner, OutlineEntry, OwnerKind, ParsedDocument, ParsedPage, ParsedTable
from src.documents.repository import DocumentRepository
from src.documents.service import DocumentService
from src.documents.storage import DocumentStorage
from src.knowledge.documents import owner_of
from src.knowledge.models import KnowledgeBase
from src.knowledge.repository import AgentKnowledgeBaseRepository, KnowledgeBaseRepository
from src.skills.documents import actions
from tests.documents_support import create_documents_bucket
from tests.mock_data import TEST_USER_EMAIL, agent_fields, kb_fields, user_id_for

READING = ParsedDocument(
    markdown="# Payslip\nEmployee: A. Person\nNet pay 5,608.87\nGross pay 9,391.67\n",
    parser="docling",
    page_count=2,
    tables=[ParsedTable(page=1, rows=[["Item", "Amount"], ["Net pay", "5,608.87"]])],
    pages=[ParsedPage(1, "Net pay 5,608.87", b"\x89PNG page one"), ParsedPage(2, "Gross pay 9,391.67")],
    outline=[OutlineEntry("Payslip", 1, 0, 1)],
)


class ReadsAsPayslip:
    name = "docling"

    def supports(self, filename: str) -> bool:
        return filename.endswith(".pdf")

    async def parse(self, data: bytes, filename: str) -> ParsedDocument:
        return READING


@pytest.fixture
def setting(dynamodb_table, monkeypatch):
    create_documents_bucket()
    service = DocumentService(DocumentRepository(), DocumentStorage(), parsers=[ReadsAsPayslip()])
    monkeypatch.setattr(actions, "get_document_service", lambda: service)
    agent = AgentRepository().save(Agent(agent_name="Reader", agent_architecture="krishna-memgpt", agent_provider="Bedrock",
                                         agent_persona="x", **agent_fields(TEST_USER_EMAIL)))
    context = {"account_id": agent.account_id, "agent_id": agent.agent_id, "conversation_id": "conv-1",
               "owner_id": agent.owner_id, "owner_email": TEST_USER_EMAIL}
    return service, agent, context


async def stored(service: DocumentService, owner: DocumentOwner, filename: str = "payslip.pdf") -> str:
    document = service.submit(owner, filename, b"%PDF-1", created_by="user-1")
    await service.process(owner, document.document_id)
    return document.document_id


async def test_the_agent_lists_and_reads_its_conversations_documents_in_parts(setting):
    service, agent, context = setting
    document_id = await stored(service, DocumentOwner(agent.account_id, OwnerKind.CONVERSATION, "conv-1"))

    listed = await actions.list_documents({}, {}, context)
    first = await actions.read_document({"document_id": document_id, "length": 20}, {}, context)
    rest = await actions.read_document({"document_id": document_id, "offset": first["next_offset"]}, {}, context)

    assert listed["documents"][0] | {"document_id": document_id} == {
        "document_id": document_id, "filename": "payslip.pdf", "status": "ready", "pages": 2, "tables": 1,
        "chars": len(READING.markdown),
    }
    assert first["text"] + rest["text"] == READING.markdown and rest["next_offset"] is None


async def test_pages_tables_and_search(setting):
    service, agent, context = setting
    document_id = await stored(service, DocumentOwner(agent.account_id, OwnerKind.CONVERSATION, "conv-1"))

    pages = await actions.read_pages({"document_id": document_id, "from_page": 1, "to_page": 5}, {}, context)
    table = await actions.read_table({"document_id": document_id, "table": 1}, {}, context)
    hits = await actions.search_document({"document_id": document_id, "query": "net pay"}, {}, context)
    overview = await actions.describe_document({"document_id": document_id}, {}, context)
    shape = await actions.describe_table({"document_id": document_id, "table": 1}, {}, context)
    answer = await actions.query_table(
        {"document_id": document_id, "table": 1, "where": [{"column": "Item", "op": "contains", "value": "net"}],
         "aggregate": [{"fn": "sum", "column": "Amount"}]}, {}, context)
    section = await actions.read_section({"document_id": document_id, "section": 1}, {}, context)

    assert [page["page"] for page in pages["pages"]] == [1, 2], "capped at the document's pages"
    assert table["rows"] == [["Net pay", "5,608.87"]] and table["next_row"] is None and table["total_rows"] == 1
    assert "Net pay 5,608.87" in hits["hits"][0]["snippet"]
    assert overview["tables"][0]["columns"] == ["Item", "Amount"] and shape["total_rows"] == 1
    assert answer["rows"] == [[5608.87]] and answer["matched_rows"] == 1
    assert section["text"].startswith("# Payslip")
    with pytest.raises(ValueError, match="1 table"):
        await actions.read_table({"document_id": document_id, "table": 2}, {}, context)


async def test_view_page_asks_the_vision_model_about_the_pages_image(setting, monkeypatch):
    service, agent, context = setting
    document_id = await stored(service, DocumentOwner(agent.account_id, OwnerKind.CONVERSATION, "conv-1"))
    seen = {}

    async def look_at(self, **kwargs):
        seen.update(kwargs)
        from src.vision.analysis import VisionReading

        return VisionReading("A payslip", "Net pay is 5,608.87")

    monkeypatch.setattr("src.vision.analysis.ImageReader.look_at", look_at)
    monkeypatch.setattr("src.vision.analysis.ImageReader.__init__", lambda self, **_: None)

    result = await actions.view_page({"document_id": document_id, "page": 1, "prompt": "Net pay?"}, {}, context)

    assert result["answer"] == "Net pay is 5,608.87" and seen["image"] == b"\x89PNG page one" and seen["prompt"] == "Net pay?"
    with pytest.raises(ValueError, match="no image of page 2"):
        await actions.view_page({"document_id": document_id, "page": 2}, {}, context)


async def test_a_linked_knowledge_bases_documents_are_readable(setting):
    service, agent, context = setting
    kb = KnowledgeBaseRepository().save(KnowledgeBase(name="Payslips", **kb_fields(TEST_USER_EMAIL)))
    await stored(service, owner_of(kb), "june.pdf")

    with pytest.raises(ValueError, match="isn't linked"):
        await actions.list_documents({"knowledge_base_id": kb.kb_id}, {}, context)
    AgentKnowledgeBaseRepository().link(agent.agent_id, kb.kb_id, user_id_for(TEST_USER_EMAIL))

    listed = await actions.list_documents({"knowledge_base_id": kb.kb_id}, {}, context)
    assert [d["filename"] for d in listed["documents"]] == ["june.pdf"]


async def test_another_conversations_documents_arent_found(setting):
    service, agent, context = setting
    document_id = await stored(service, DocumentOwner(agent.account_id, OwnerKind.CONVERSATION, "conv-2"))

    assert (await actions.list_documents({}, {}, context))["documents"] == []
    with pytest.raises(ValueError, match="No document"):
        await actions.read_document({"document_id": document_id}, {}, context)
