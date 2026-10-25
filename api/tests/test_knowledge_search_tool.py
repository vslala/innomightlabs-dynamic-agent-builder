"""What `knowledge_base_search` shows the agent: whole chunks, and where a hit is a slice of an uploaded document."""

import pytest

# The order the app loads them in (vision.analysis imported first runs into an import cycle through the native tools)
from src.tools.native import handlers
from src.vectorstore.search import SearchResult

ROWS = "| FirstName | Surname | Score |\n| --- | --- | --- |\n" + "\n".join(f"| Madawa | P | {n} |" for n in range(120))


def result(source_url: str, content: str = ROWS) -> SearchResult:
    return SearchResult(chunk_id="c1", content=content, source_url=source_url, page_title="batting-2026.xlsx",
                        score=0.8, level=2, word_count=len(content.split()))


@pytest.fixture
def searching(dynamodb_table, monkeypatch):
    def answer(*results: SearchResult):
        class Search:
            async def search_multiple_kbs(self, **_):
                return list(results)

        monkeypatch.setattr(handlers, "get_search_service", lambda: Search())
        return handlers.NativeToolHandler()

    return answer


async def test_a_chunk_is_shown_whole_up_to_the_preview_cap(searching):
    tool = searching(result("file://kb-1/batting-2026.xlsx"))

    shown = await tool._handle_knowledge_base_search({"query": "Madawa runs"}, "agent-1", linked_kb_ids=["kb-1"])

    assert "| Madawa | P | 90 |" in shown, "well past the old 500-character cut"


async def test_a_hit_from_an_uploaded_file_points_to_the_documents_skill(searching):
    tool = searching(result("file://kb-1/batting-2026.xlsx"), result("https://example.com/fixtures", "Fixtures page"))

    shown = await tool._handle_knowledge_base_search({"query": "Madawa runs"}, "agent-1", linked_kb_ids=["kb-1"])

    assert "Document: a slice of the uploaded file 'batting-2026.xlsx' (knowledge_base_id kb-1)" in shown
    assert shown.count("Document:") == 1, "a crawled page isn't a document"
