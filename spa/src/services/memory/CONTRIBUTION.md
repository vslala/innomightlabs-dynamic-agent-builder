# Memory Service Guide

`MemoryApiService.ts` owns agent memory-block metadata and content operations under `/agents/{id}/memory-blocks`.

- List/create return `MemoryBlockResponse`; content GET/PUT return `MemoryBlockContentResponse`. Keep metadata separate from editable content.
- The block path key is `blockName`, not a generated block ID. Existing paths interpolate it directly; if changing supported names, check URL encoding and the backend contract together rather than silently changing identity.
- Content replacement uses PUT on `/{blockName}/content`; deletion targets the block itself. Submit `UpdateMemoryBlockContentRequest` without frontend persistence or a parallel local-memory cache.
- This REST service is distinct from the legacy local agent service's memory helpers. All calls use dashboard bearer/account context.

No adjacent tests currently. Add name/path and metadata-versus-content payload tests; use `yarn test src/services/memory` from `spa/` after adding them. See [services guide](../CONTRIBUTION.md).
