# Knowledge Service Guide

`KnowledgeApiService.ts` owns knowledge-base CRUD, schemas, content uploads, crawl jobs/audits, search and agent links. Contracts come from `src/types/knowledge`.

- Fetch backend create/crawl/upload forms as `FormSchema`; do not duplicate crawl or upload validation here.
- `uploadContentFile()` uses FormData field `attachment` plus optional `metadata`, then `postForm`. The public argument is named `file`, but that is not the multipart field name.
- Upload listing returns a paginated envelope with an encoded cursor. Crawl listing/steps/pages return arrays; preserve those differences and caller limits.
- Starting a crawl POSTs configuration with `auto_start` (default true); manual `/run` and DELETE cancellation are separate operations. Polling/UI lifecycle belongs to consumers.
- Search is POST with encoded `query` and `top_k` query parameters, not a JSON query body. Knowledge-base CRUD is separate from `/agents/{id}/knowledge-bases` linking and `/knowledge-search`.

No adjacent tests currently. Add multipart field/boundary, cursor, auto-start and query-path tests; from `spa/`, run `yarn test src/services/knowledge` once added. See [services guide](../CONTRIBUTION.md).
