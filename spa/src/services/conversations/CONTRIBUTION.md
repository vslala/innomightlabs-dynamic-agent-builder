# Conversations Service Guide

`ConversationApiService.ts` owns dashboard conversation CRUD and persisted message retrieval. Conversation contracts come from `src/types/conversation`, messages from `src/types/message`.

- List/create currently use `/conversations/` with the trailing slash. List and message history return `PaginatedResponse`, not arrays; preserve URLSearchParams filters/cursors and caller pagination.
- Updates use PUT on `/conversations/{id}`; deletes return void. Keep metadata edits separate from message submission.
- `getMessages()` loads saved history. Sending, reattaching and stopping turns belong to `../chat`, not this CRUD service. Consumers reconcile live events with persisted records.
- Requests inherit active-account context; conversation IDs alone do not establish ownership/access.

No adjacent tests currently. Add list/history pagination and CRUD method/path tests; use `yarn test src/services/conversations` from `spa/` once added. Full checks: [services guide](../CONTRIBUTION.md).
