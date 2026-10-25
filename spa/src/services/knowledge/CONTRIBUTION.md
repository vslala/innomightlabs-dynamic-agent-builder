# Knowledge Service Guide

`KnowledgeApiService.ts` owns knowledge-base CRUD, schemas, content uploads and documents, crawl jobs/audits, search and agent links. Contracts come from `src/types/knowledge`.

- Fetch backend create/crawl/upload forms as `FormSchema`; do not duplicate crawl or upload validation here.
- `uploadContentFile()` uses FormData field `attachment` plus optional `metadata`, then `postForm`. The public argument is named `file`, but that is not the multipart field name. It returns 202 with a `KnowledgeDocument` (usually `pending`): the file is read and indexed in the background, so callers poll `listDocuments()`/`getDocument()` for status. Errors: 400 unsupported type, 413 too large, 429 rate limited, 503 no vector store.
- Documents: `listDocuments()` returns a paginated envelope (newest first, opaque cursor); `retryDocument()` POSTs `/retry` (only for `failed`, 409 otherwise); `deleteDocument()` returns 204 (503 means try again). The legacy `/uploads` history is not used by the UI any more.
- Crawl steps/pages return arrays; preserve those differences and caller limits.
- Starting a crawl POSTs configuration with `auto_start` (default true); manual `/run` and DELETE cancellation are separate operations. Polling/UI lifecycle belongs to consumers.
- Search is POST with encoded `query` and `top_k` query parameters, not a JSON query body. Knowledge-base CRUD is separate from `/agents/{id}/knowledge-bases` linking and `/knowledge-search`.

No adjacent tests currently. Add multipart field/boundary, cursor, auto-start and query-path tests; from `spa/`, run `yarn test src/services/knowledge` once added. See [services guide](../CONTRIBUTION.md).
