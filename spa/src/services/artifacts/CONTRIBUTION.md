# Artifacts Service Guide

`ArtifactApiService.ts` returns artifact metadata and view/download URL responses from `/artifacts`. Artifact kinds are `html_report`, `image` and `file`.

- List returns an `ArtifactListResponse`, not a bare array. Detail IDs are encoded in paths.
- `/view` and `/download` return `ArtifactUrlResponse`; they do not fetch bytes. Let the consumer handle opening/downloading the returned URL, preserving any expiry metadata rather than treating it as a permanent asset path.
- Keep source metadata distinct from the artifact's identity. Requests use the active dashboard account through `httpClient`; a returned URL is not a reason to bypass metadata authorization.

## KAN-21 deletion

- `ArtifactApiService.ts` implements `deleteArtifact(id): Promise<void>` via encoded `DELETE /artifacts/{id}` and the shared `httpClient`; bodyless 204 is success, including idempotent completion for missing or wrong-owner IDs. Those IDs are absent from the caller's partition and foreign artifacts remain untouched. Actual deletion failures return safe 502 and reject as shared HTTP errors.
- `bulkDeleteArtifacts(ids): Promise<BulkArtifactDeletionResponse>` deduplicates in first-seen order, rejects an empty or over-100 unique-ID selection before HTTP, and sends JSON `{ artifact_ids: ids }` in `DELETE /artifacts/bulk`. The API validates the input list before server-side deduplication: 1–100 strict strings of 1–128 characters, no extra fields (422 for invalid bodies).
- A 200 bulk result is not necessarily complete success: `deleted_ids` lists successfully completed IDs, including absent-ID no-ops, not necessarily removed stored rows; `failed` contains typed `ArtifactDeletionFailure` entries only for actual failures (`artifact_id`, `code: "DELETE_FAILED"`, safe `message`). These types are exported through `index.ts`. Keep HTTP/network failures distinct from per-ID failures and let the consumer reconcile only reported successes. Do not display arbitrary provider details in UI feedback.
- Use shared auth/active-account headers, not request-supplied owner fields or direct fetches. Deletion is private to authenticated `Owner.member_pk`; the service performs one member-partition-scoped GSI lookup, treats absence as success, and otherwise trusts the stored record to delete its exact S3 key then ordinarily delete metadata at `pk`/`sk`, without a conditional expression or atomic rollback. Stored record correctness is assumed at the write boundary, not revalidated during deletion. A metadata failure can occur after bytes are gone; retry is safe for missing bytes. It does not remove conversation references or conversations, and does not purge historical S3 versions.

## Testing

`ArtifactApiService.test.ts` should cover encoded single DELETE paths, shared auth/account headers, bodyless 204 including absent-ID idempotent completion, deduplicated/bounded bulk JSON, absent IDs in `deleted_ids`, real `DELETE_FAILED` partial results with safe messages, safe single 502 and bulk HTTP/network errors, plus existing list envelopes and detail/view/download paths. From `spa/`:

```bash
yarn test src/services/artifacts/ArtifactApiService.test.ts
yarn eslint src/services/artifacts/ArtifactApiService.ts src/services/artifacts/ArtifactApiService.test.ts src/services/artifacts/index.ts
```

For related page behavior, also run `yarn test src/pages/dashboard/artifactDeletion.test.ts src/pages/dashboard/ArtifactsPagePanel.test.tsx`. See [services guide](../CONTRIBUTION.md) for shared validation; for frontend code changes, run `yarn test`, `yarn lint`, and `yarn build`.
