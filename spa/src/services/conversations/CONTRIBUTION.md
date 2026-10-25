# Conversations Service Guide

`ConversationApiService.ts` owns dashboard conversation CRUD and persisted message retrieval. Conversation contracts come from `src/types/conversation`, messages from `src/types/message`.

- List/create currently use `/conversations/` with the trailing slash. List and message history return `PaginatedResponse`, not arrays; preserve URLSearchParams filters/cursors and caller pagination.
- Updates use PUT on `/conversations/{id}`; deletes return void. Keep metadata edits separate from message submission.
- `getMessages()` loads saved history. Sending, reattaching and stopping turns belong to `../chat`, not this CRUD service. Consumers reconcile live events with persisted records.
- Documents: `uploadDocument()` posts multipart field `file` to `/conversations/{id}/documents` and gets 202 with a `KnowledgeDocument` (read in the background); `listDocuments(id, { unsent: true })` returns a plain array, only uploads not yet sent when `unsent`; `deleteDocument()` returns 204. A document goes out with a message as a reference (`references: [{ kind: "document", id }]` in `OutgoingMessage`), which tells the agent it arrived; one never sent is removed after a day.
- Requests inherit active-account context; conversation IDs alone do not establish ownership/access.

No adjacent tests currently. Add list/history pagination and CRUD method/path tests; use `yarn test src/services/conversations` from `spa/` once added. Full checks: [services guide](../CONTRIBUTION.md).
