# Contributing to `documents/`

Reading, storing and serving files for an **owner**: a knowledge base or a conversation. A caller hands over a file and
its owner; `documents` stores the original, reads it in the background, keeps what was read in S3 and records it in
DynamoDB. Design: [docs/LLD-documents.md](../../../docs/LLD-documents.md).

```text
documents/
  models.py      ParsedDocument / ParsedPage / ParsedTable (a reading), DocumentOwner, OwnerKind, Document (the row),
                 OutlineEntry, DocumentStatus, DocumentResponse, errors
  parsers.py     One strategy per way of reading: TextParser, HtmlParser, DoclingParser (the CLI runner),
                 PdfTextLayerParser; default_parsers(), accepted_extensions(), DOCUMENT_CONTENT_TYPES
  outline.py     outline_from_markdown (headings with offsets and pages), weak_pages, describe_reading (outline.json)
  tables.py      describe_table, page_table, query_table: bounded questions about a table's rows
  reader.py      read_document(data, filename) -> ParsedDocument: asks every parser that supports the file, picks one;
                 parsers_for(), PARSER_VERSION
  repository.py  Document rows: pk=DocumentOwner#{kind}#{owner_id}, sk=Document#{id}; claim (lease), save_in_flight
  storage.py     The documents bucket: {account}/{kind}/{owner_id}/{document_id}/ original/, document.md,
                 structured.json, outline.json, tables/{n}.csv, pages/{n}.md|png
  follow_ups.py  FOLLOW_UPS: what an owner kind does after a read and before a delete (knowledge/documents.py registers)
  service.py     DocumentService: submit, process, requeue_stale, retry, describe, read_markdown/read_section/read_pages/
                 describe_table/read_table/query_table/page_image, search, attach, unsent, sweep_unsent,
                 delete, delete_all
  worker.py      launch (BackgroundTasks or a task on the loop), run, requeue_stale (the scheduler's reaper)
  uploads.py     The HTTP side every owner's upload route shares: read_upload (size cap), take_upload_slot (rate limit)
```

## Conventions

- **Documents sent with a message** (a conversation's): `submit(..., sent_with_a_message=True)` records
  `attached_at = 0`; `attach` sets when it was sent; `sweep_unsent` removes those never sent. `None` means the owner
  doesn't attach documents (a knowledge base) or the document predates attaching: the sweep never touches it.
- **A worker saves only its own fields** (`save_in_flight` is an update without `attached_at`): the owner can change
  a document while it is being read.

- **A new kind of file is a new parser**: a class with `name`, `supports(filename)` and `async parse(data, filename)`,
  added to `default_parsers()` (and its extensions to `accepted_extensions()`). Don't branch on file type elsewhere.
- **The first reading wins, unless a later one holds more than `MORE_TEXT_FACTOR` times its text** (`text_chars`).
  Layout models can drop the text of a decorated page; the PDF's text layer shows it. Order parsers richest first.
- **Docling runs in the CLI runner**, not here: `DoclingParser` calls `POST /v1/documents/parse` with
  `CLI_RUNNER_BASE_URL` / `CLI_RUNNER_SHARED_TOKEN`. Without a runner it isn't in the list and a PDF is read from its
  text layer; Office files and images can't be read.
- **The owner is a resource, never a person.** Keys use the owner's id; `created_by` is audit only. Nothing here checks
  permissions: the caller resolves the owner with its own rules and passes it in.
- **An owner kind differs only in its follow-up** (`follow_ups.FOLLOW_UPS`). `documents` imports no owner module; the
  owner registers itself at import (`knowledge/documents.py`, imported by `knowledge/__init__.py`).
- **Deletion order: the owner's part, the bucket, the row.** The row records what the bucket holds, so it goes last; a
  failure stops and the delete can run again. `delete` runs the owner's `before_delete`; `delete_all` is for an owner
  that is going away and has already removed what it built (a KB's namespace).
- **Progress is saved with `save_in_flight`**, which refuses once the document is no longer in flight: a delete that
  happens while a worker reads the file wins.
- **A file no parser can read fails for good; anything else is retried** by the reaper up to `document_max_attempts`.
- Bump `PARSER_VERSION` when a parser change should re-read stored documents.
- Never log document text: ids, sizes, parser names and errors only.

## Testing

```bash
uv run pytest tests/test_documents_reader.py tests/test_documents_service.py tests/test_documents_skill.py tests/test_knowledge_documents.py tests/test_conversation_documents.py tests/crawler/test_fetch_outcomes.py -q
uv run ruff check src/documents && uv run mypy src/documents
```

S3 and DynamoDB are moto; `tests/documents_support.py` has `create_documents_bucket`, `bucket_keys` and `pdf_with_text`.
