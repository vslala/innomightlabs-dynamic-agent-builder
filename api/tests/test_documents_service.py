"""Keeping documents for an owner: submit, background reading, reading back, the reaper, deletion order."""

import time

import boto3
import pytest

from src.config import settings
from src.documents import follow_ups
from src.documents.models import (
    Document,
    DocumentOwner,
    DocumentReadError,
    DocumentStatus,
    OutlineEntry,
    OwnerKind,
    ParsedDocument,
    ParsedPage,
    ParsedTable,
    UnsupportedDocument,
)
from src.documents.repository import DocumentRepository
from src.documents.service import DocumentNotReady, DocumentService, DocumentTooLarge
from src.documents.storage import DocumentStorage

KB = DocumentOwner(account_id="acct-1", kind=OwnerKind.KNOWLEDGE_BASE, owner_id="kb-1")
CHAT = DocumentOwner(account_id="acct-1", kind=OwnerKind.CONVERSATION, owner_id="conv-1")
PAYSLIP = ParsedDocument(
    markdown="# Payslip\nGross pay 9,391.67\nNet pay 5,608.87\n",
    parser="fake",
    page_count=1,
    tables=[ParsedTable(page=1, rows=[["Item", "Amount"], ["Net pay", "5,608.87"]])],
    pages=[ParsedPage(number=1, markdown="Net pay 5,608.87", image=b"\x89PNG page")],
    outline=[OutlineEntry(title="Payslip", level=1, offset=0, page=1)],
)


class FakeParser:
    name = "fake"

    def __init__(self, reading: ParsedDocument = PAYSLIP, error: Exception | None = None):
        self.reading, self.error, self.calls = reading, error, 0

    def supports(self, filename: str) -> bool:
        return filename.endswith(".pdf")

    async def parse(self, data: bytes, filename: str) -> ParsedDocument:
        self.calls += 1
        if self.error:
            raise self.error
        return self.reading


class RecordingFollowUp:
    def __init__(self, fail_parse: bool = False, fail_delete: bool = False):
        self.fail_parse, self.fail_delete = fail_parse, fail_delete
        self.parsed: list[str] = []
        self.deleted: list[str] = []

    async def after_parse(self, document: Document, reading: ParsedDocument) -> None:
        if self.fail_parse:
            raise RuntimeError("pinecone is down")
        self.parsed.append(document.document_id)

    def before_delete(self, document: Document) -> None:
        if self.fail_delete:
            raise RuntimeError("pinecone is down")
        self.deleted.append(document.document_id)


@pytest.fixture(autouse=True)
def no_owner_follow_ups(monkeypatch):
    """Owners register follow-ups when their module is imported (`knowledge`); these tests register their own."""
    monkeypatch.setattr(follow_ups, "FOLLOW_UPS", {})
    monkeypatch.setattr("src.documents.service.FOLLOW_UPS", follow_ups.FOLLOW_UPS)


@pytest.fixture
def bucket(dynamodb_table):
    s3 = boto3.client("s3", region_name=settings.documents_region)
    s3.create_bucket(Bucket=settings.documents_bucket)
    return s3


@pytest.fixture
def follow_up(monkeypatch):
    recording = RecordingFollowUp()
    follow_ups.FOLLOW_UPS[OwnerKind.KNOWLEDGE_BASE] = recording
    return recording


def service(parser: FakeParser | None = None) -> DocumentService:
    return DocumentService(DocumentRepository(), DocumentStorage(), parsers=[parser or FakeParser()])


def keys(s3, prefix: str) -> set[str]:
    return {obj["Key"].removeprefix(prefix) for obj in s3.list_objects_v2(Bucket=settings.documents_bucket, Prefix=prefix).get("Contents", [])}


def test_submit_stores_the_original_and_records_it_pending(bucket):
    document = service().submit(KB, "payslip.pdf", b"%PDF-1", created_by="user-1", content_type="application/pdf")

    assert document.status is DocumentStatus.PENDING and document.size_bytes == 6
    assert document.prefix == f"acct-1/knowledge_base/kb-1/{document.document_id}/"
    assert keys(bucket, document.prefix) == {"original/payslip.pdf"}


def test_a_file_nothing_reads_or_too_large_is_refused(bucket, monkeypatch):
    with pytest.raises(UnsupportedDocument):
        service().submit(KB, "setup.exe", b"MZ", created_by="user-1")
    monkeypatch.setattr(settings, "document_max_bytes", 4)
    with pytest.raises(DocumentTooLarge):
        service().submit(KB, "big.pdf", b"%PDF-1", created_by="user-1")


async def test_processing_keeps_the_reading_and_runs_the_owners_follow_up(bucket, follow_up):
    docs = service()
    document = docs.submit(KB, "payslip.pdf", b"%PDF-1", created_by="user-1")

    done = await docs.process(KB, document.document_id)

    assert done is not None and done.status is DocumentStatus.READY and follow_up.parsed == [document.document_id]
    assert (done.parser, done.page_count, done.table_count) == ("fake", 1, 1) and done.lease_expires_at == 0
    assert keys(bucket, document.prefix) == {"original/payslip.pdf", "document.md", "outline.json", "tables/1.csv", "pages/1.md", "pages/1.png"}
    assert docs.read_table(done, 1)["rows"] == [["Net pay", "5,608.87"]]
    assert docs.read_page(done, 1) == "Net pay 5,608.87" and docs.page_image(done, 1) == b"\x89PNG page"


async def test_a_conversation_document_is_ready_once_parsed(bucket, follow_up):
    docs = service()
    document = docs.submit(CHAT, "payslip.pdf", b"%PDF-1", created_by="user-1")

    assert (await docs.process(CHAT, document.document_id)).status is DocumentStatus.READY
    assert follow_up.parsed == []


async def test_the_same_file_again_is_the_same_document_and_a_changed_one_is_read_again(bucket, follow_up):
    docs = service()
    first = docs.submit(KB, "payslip.pdf", b"%PDF-1", created_by="user-1")
    await docs.process(KB, first.document_id)

    again = docs.submit(KB, "payslip.pdf", b"%PDF-1", created_by="user-1")
    changed = docs.submit(KB, "payslip.pdf", b"%PDF-2", created_by="user-1")

    assert again.status is DocumentStatus.READY
    assert changed.document_id == first.document_id and changed.status is DocumentStatus.PENDING
    assert len(docs.documents(KB)) == 1


async def test_a_file_no_parser_can_read_fails_for_good(bucket):
    docs = service(FakeParser(error=DocumentReadError("the PDF is password protected")))
    document = docs.submit(KB, "locked.pdf", b"%PDF-1", created_by="user-1")

    failed = await docs.process(KB, document.document_id)

    assert failed.status is DocumentStatus.FAILED and "password protected" in failed.error
    with pytest.raises(DocumentNotReady):
        docs.read_markdown(failed)


async def test_an_unexpected_failure_is_tried_again_until_attempts_run_out(bucket, monkeypatch):
    monkeypatch.setattr(settings, "document_max_attempts", 2)
    follow = RecordingFollowUp(fail_parse=True)
    monkeypatch.setitem(follow_ups.FOLLOW_UPS, OwnerKind.KNOWLEDGE_BASE, follow)
    docs = service()
    document = docs.submit(KB, "payslip.pdf", b"%PDF-1", created_by="user-1")

    first = await docs.process(KB, document.document_id)
    second = await docs.process(KB, document.document_id)

    assert first.status is DocumentStatus.PENDING and "pinecone is down" in first.error
    assert second.status is DocumentStatus.FAILED and second.attempts == 2


async def test_a_document_a_worker_holds_is_not_taken_again(bucket):
    docs = service()
    document = docs.submit(KB, "payslip.pdf", b"%PDF-1", created_by="user-1")
    DocumentRepository().claim(KB, document.document_id, lease_seconds=600, now=int(time.time()))

    assert await docs.process(KB, document.document_id) is None


async def test_a_document_deleted_while_it_is_read_stays_deleted(bucket, monkeypatch):
    docs = service()
    document = docs.submit(KB, "payslip.pdf", b"%PDF-1", created_by="user-1")

    class DeletesMidway(RecordingFollowUp):
        async def after_parse(self, document: Document, reading: ParsedDocument) -> None:
            DocumentRepository().delete(document)

    monkeypatch.setitem(follow_ups.FOLLOW_UPS, OwnerKind.KNOWLEDGE_BASE, DeletesMidway())

    assert await docs.process(KB, document.document_id) is None
    assert DocumentRepository().get(KB, document.document_id) is None


async def test_reading_in_parts_and_searching(bucket):
    docs = service()
    document = await docs.process(KB, docs.submit(KB, "payslip.pdf", b"%PDF-1", created_by="user-1").document_id)

    first = docs.read_markdown(document, offset=0, length=10)
    rest = docs.read_markdown(document, offset=first.next_offset)

    assert first.text + rest.text == PAYSLIP.markdown and rest.next_offset is None
    hits = docs.search(document, "net PAY")
    assert len(hits) == 1 and "Net pay 5,608.87" in hits[0].snippet and hits[0].section == "Payslip"
    assert PAYSLIP.markdown.startswith(hits[0].snippet.splitlines()[0], hits[0].offset)


async def test_delete_runs_the_owners_part_then_the_bucket_then_the_row(bucket, follow_up):
    docs = service()
    document = await docs.process(KB, docs.submit(KB, "payslip.pdf", b"%PDF-1", created_by="user-1").document_id)

    docs.delete(document)

    assert follow_up.deleted == [document.document_id]
    assert keys(bucket, document.prefix) == set() and DocumentRepository().get(KB, document.document_id) is None


async def test_a_delete_the_owner_cant_do_removes_nothing_and_can_run_again(bucket, monkeypatch):
    docs = service()
    document = await docs.process(CHAT, docs.submit(CHAT, "payslip.pdf", b"%PDF-1", created_by="user-1").document_id)
    monkeypatch.setitem(follow_ups.FOLLOW_UPS, OwnerKind.CONVERSATION, RecordingFollowUp(fail_delete=True))

    with pytest.raises(RuntimeError):
        docs.delete(document)

    assert "original/payslip.pdf" in keys(bucket, document.prefix)
    assert DocumentRepository().get(CHAT, document.document_id).status is DocumentStatus.DELETING
    assert docs.documents(CHAT) == []  # hidden while half deleted
    monkeypatch.setitem(follow_ups.FOLLOW_UPS, OwnerKind.CONVERSATION, RecordingFollowUp())
    docs.delete(DocumentRepository().get(CHAT, document.document_id))
    assert keys(bucket, document.prefix) == set()


def test_delete_all_removes_every_document_of_the_owner_only(bucket):
    docs = service()
    docs.submit(CHAT, "a.pdf", b"%PDF-a", created_by="user-1")
    docs.submit(CHAT, "b.pdf", b"%PDF-b", created_by="user-1")
    kept = docs.submit(KB, "c.pdf", b"%PDF-c", created_by="user-1")

    assert docs.delete_all(CHAT) == 2

    assert docs.documents(CHAT) == [] and keys(bucket, "acct-1/conversation/") == set()
    assert [d.document_id for d in docs.documents(KB)] == [kept.document_id]


def test_the_reaper_relaunches_lapsed_documents_and_fails_exhausted_ones(bucket, monkeypatch):
    monkeypatch.setattr(settings, "document_max_attempts", 2)
    docs = service()
    lapsed = docs.submit(CHAT, "a.pdf", b"%PDF-a", created_by="user-1")
    held = docs.submit(CHAT, "b.pdf", b"%PDF-b", created_by="user-1")
    exhausted = docs.submit(CHAT, "c.pdf", b"%PDF-c", created_by="user-1")
    repo = DocumentRepository()
    repo.claim(CHAT, held.document_id, lease_seconds=600, now=int(time.time()))
    repo.save(exhausted.model_copy(update={"attempts": 2, "status": DocumentStatus.PARSING}))
    launched: list[str] = []

    failed = docs.requeue_stale(lambda document: launched.append(document.document_id))

    assert launched == [lapsed.document_id] and failed == 1
    assert repo.get(CHAT, exhausted.document_id).status is DocumentStatus.FAILED


def test_an_owner_is_found_only_in_its_account(bucket):
    document = service().submit(KB, "a.pdf", b"%PDF-a", created_by="user-1")

    other_account = DocumentOwner(account_id="acct-2", kind=KB.kind, owner_id=KB.owner_id)
    assert DocumentRepository().get(other_account, document.document_id) is None
    assert DocumentRepository().list_by_owner(other_account) == []


async def test_a_retry_after_the_follow_up_failed_doesnt_read_the_file_again(bucket, monkeypatch):
    parser = FakeParser()
    docs = service(parser)
    flaky = RecordingFollowUp(fail_parse=True)
    follow_ups.FOLLOW_UPS[OwnerKind.KNOWLEDGE_BASE] = flaky
    document = docs.submit(KB, "payslip.pdf", b"%PDF-1", created_by="user-1")
    assert (await docs.process(KB, document.document_id)).status is DocumentStatus.PENDING

    flaky.fail_parse = False
    done = await docs.process(KB, document.document_id)

    assert done.status is DocumentStatus.READY and parser.calls == 1 and flaky.parsed == [document.document_id]


async def test_a_changed_file_is_read_from_scratch(bucket):
    parser = FakeParser()
    docs = service(parser)
    first = docs.submit(KB, "payslip.pdf", b"%PDF-1", created_by="user-1")
    await docs.process(KB, first.document_id)

    changed = docs.submit(KB, "payslip.pdf", b"%PDF-2", created_by="user-1")
    assert (changed.parser, changed.page_count) == ("", 0)
    await docs.process(KB, changed.document_id)

    assert parser.calls == 2


async def test_the_reaper_scans_off_the_loop_and_launches_on_it(bucket, monkeypatch):
    from src.documents import worker

    docs = service()
    document = docs.submit(CHAT, "a.pdf", b"%PDF-a", created_by="user-1")
    monkeypatch.setattr("src.documents.service.get_document_service", lambda: docs)
    launched: list[str] = []
    monkeypatch.setattr(worker, "launch", lambda d, background_tasks=None: launched.append(d.document_id))

    assert await worker.requeue_stale() == 0
    assert launched == [document.document_id]


async def test_a_worker_renews_its_lease_while_it_works_and_a_ready_document_has_no_error(bucket, monkeypatch):
    monkeypatch.setattr(settings, "document_lease_seconds", 3)
    renewed: list[int] = []
    real_renew = DocumentRepository.renew

    def counting_renew(self, document, *, lease_seconds, now):
        renewed.append(now)
        return real_renew(self, document, lease_seconds=lease_seconds, now=now)

    monkeypatch.setattr(DocumentRepository, "renew", counting_renew)

    class SlowFollowUp(RecordingFollowUp):
        async def after_parse(self, document: Document, reading: ParsedDocument) -> None:
            import asyncio

            await asyncio.sleep(2.5)

    follow_ups.FOLLOW_UPS[OwnerKind.KNOWLEDGE_BASE] = SlowFollowUp()
    docs = service()
    document = docs.submit(KB, "payslip.pdf", b"%PDF-1", created_by="user-1")
    DocumentRepository().save(document.model_copy(update={"error": "ReadTimeout"}))

    done = await docs.process(KB, document.document_id)

    assert len(renewed) >= 2, "renewed every third of the lease while the follow-up ran"
    assert done.status is DocumentStatus.READY and done.error == ""


BOOK_MARKDOWN = "# Contract\nIntro text\n## Payment\nPay within 30 days\nLate fees apply\n## Term\nOne year\n# Annex\nSchedule of fees\n"
BOOK = ParsedDocument(
    markdown=BOOK_MARKDOWN,
    parser="fake",
    page_count=3,
    pages=[ParsedPage(1, "# Contract\nIntro text\n## Payment\nPay within 30 days " + "x" * 60), ParsedPage(2, ""), ParsedPage(3, "# Annex\nSchedule of fees " + "x" * 60)],
    outline=[
        OutlineEntry("Contract", 1, BOOK_MARKDOWN.index("# Contract"), 1),
        OutlineEntry("Payment", 2, BOOK_MARKDOWN.index("## Payment"), 1),
        OutlineEntry("Term", 2, BOOK_MARKDOWN.index("## Term"), 2),
        OutlineEntry("Annex", 1, BOOK_MARKDOWN.index("# Annex"), 3),
    ],
)


async def ready_book(bucket):
    docs = service(FakeParser(BOOK))
    document = await docs.process(KB, docs.submit(KB, "book.pdf", b"%PDF-1", created_by="user-1").document_id)
    return docs, document


async def test_describe_lists_sections_with_their_extent_and_the_pages_with_little_text(bucket):
    docs, document = await ready_book(bucket)

    description = docs.describe(document)

    assert [(s.title, s.page) for s in description.sections] == [("Contract", 1), ("Payment", 1), ("Term", 2), ("Annex", 3)]
    contract, payment = description.sections[0], description.sections[1]
    assert contract.end == description.sections[3].offset, "a level-1 section runs to the next level-1 heading"
    assert payment.end == description.sections[2].offset, "a level-2 section stops at the next heading of its level"
    assert description.weak_pages == [2]


async def test_a_document_read_before_outlines_were_kept_still_has_its_headings(bucket):
    docs, document = await ready_book(bucket)
    bucket.delete_object(Bucket=settings.documents_bucket, Key=f"{document.prefix}outline.json")

    description = docs.describe(document)

    assert [s.title for s in description.sections] == ["Contract", "Payment", "Term", "Annex"]
    assert description.weak_pages == [] and description.tables == []


async def test_a_section_is_read_in_parts_from_its_own_start(bucket):
    docs, document = await ready_book(bucket)

    first = docs.read_section(document, 2, length=10)
    rest = docs.read_section(document, 2, offset=first.next_offset)

    assert first.text + rest.text == "## Payment\nPay within 30 days\nLate fees apply\n" and rest.next_offset is None
    with pytest.raises(DocumentReadError, match="4 section"):
        docs.read_section(document, 5)


async def test_search_ranks_passages_with_every_word_first_and_names_their_section(bucket):
    docs, document = await ready_book(bucket)

    hits = docs.search(document, "fees late")

    assert hits[0].section == "Payment" and "Late fees apply" in hits[0].snippet
    assert any(hit.section == "Annex" for hit in hits), "a line with only one of the words still shows, after"
    assert docs.search(document, "   ") == []


async def test_read_pages_stops_before_the_characters_allowed_run_out(bucket, monkeypatch):
    monkeypatch.setattr("src.documents.service.MAX_PAGES_CHARS", 100)
    docs, document = await ready_book(bucket)

    part = docs.read_pages(document, 1, 3)

    assert [number for number, _ in part.pages] == [1] and part.next_page == 2
    assert docs.read_pages(document, 2, 3).next_page is None


SALES = ParsedDocument(
    markdown="Sales",
    parser="fake",
    tables=[ParsedTable(page=1, rows=[["Name", "Runs"], ["Madawa", "1,200"], ["Kasun", "(5)"], ["Madawa", "30"]])],
)


async def test_table_operations_work_on_every_row_and_say_what_is_missing(bucket):
    from src.documents.tables import Condition, TableQuery, TableQueryError

    docs = service(FakeParser(SALES))
    document = await docs.process(KB, docs.submit(KB, "sales.pdf", b"%PDF-1", created_by="user-1").document_id)

    query = TableQuery(where=[Condition(column="name", value="madawa")], aggregate=[{"fn": "sum", "column": "Runs"}])
    assert docs.query_table(document, 1, query)["rows"] == [[1230]]
    assert docs.describe_table(document, 1)["total_rows"] == 3
    with pytest.raises(TableQueryError, match="1 table"):
        docs.read_table(document, 2)
