# Artifacts Contribution Guide

`artifacts/` stores files and HTML canvases that agents, skills and automations produce. The bytes go to S3, the metadata to DynamoDB. An artifact is private to one member in one account.

## Layout

```text
src/artifacts/
  models.py      Artifact, source/type/response models; strict bulk delete request/results
  repository.py  save, find_by_id (member-partition-scoped GSI lookup), list_in, pk/sk delete
  storage.py     ArtifactStorage: S3 put/get/presign/exact-object delete; key/filename helpers
  service.py     ArtifactService: create, list, urls, content, single/bulk delete; run_artifact_holder
  router.py      /artifacts: list, get, download, view, content, single/bulk DELETE
```

## Conventions

- Keys: `pk=member_partition(account_id, user_id)` (from `accounts/owner.py`), `sk=Artifact#{created_at}#{artifact_id}` so a listing is newest-sortable. `gsi2_pk=Artifact#{artifact_id}`, `gsi2_sk={partition}` supports lookup by id within a partition.
- Access: routes use `Owner` (`get_owner`) and pass `owner.member_pk`; the service looks up only in that partition, so another member's or account's artifact is simply not found (reads: `ArtifactNotFoundError`, 404; deletion: successful no-op). There is no IAM action: artifacts are never shared.
- S3 keys: `accounts/{account_id}/members/{user_id}/artifacts/{yyyy/mm/dd}/{artifact_id}/{safe_filename}` in `settings.conversation_media_bucket`. Always build them with `build_key`; filenames go through `sanitize_filename`.
- Only `VIEWABLE_ARTIFACT_TYPES` open in the browser (`ArtifactNotViewableError` otherwise).
- Who owns a skill run's file: `run_artifact_holder` returns the member whose conversation it is, else the agent owner (keys, visitors and A2A callers have no member).
- Errors are domain exceptions raised by the service and mapped to `HTTPException` in the router.

## KAN-21 deletion

- `DELETE /artifacts/{id}` returns bodyless 204, including idempotent success for missing/wrong-owner IDs: they are absent from the caller's partition, and foreign artifacts remain untouched. Actual lookup, S3, or metadata deletion failures return safe 502 (`Artifact deletion failed`). Never expose provider errors or storage keys.
- `DELETE /artifacts/bulk` is registered before the parameterized route. `ArtifactBulkDeleteRequest` forbids extra fields and requires 1–100 input entries, each a strict string of 1–128 characters (invalid bodies: 422). `bulk_delete_artifacts` deduplicates in first-seen order and independently attempts each ID. A valid request returns 200 with `deleted_ids` and `failed` entries (`artifact_id`, `code`, safe `message`); `deleted_ids` means successfully completed IDs, including absent-ID no-ops, not necessarily removed stored rows. `failed` contains only actual failures with code `DELETE_FAILED`, including when every ID fails.
- Pass only authenticated `Owner.member_pk`. `find_by_id` is a simple member-partition-scoped GSI lookup, with no base-table reread or additional record-identity validation. The partition scope remains the authorization boundary.
- The service performs one lookup per unique ID; a missing record is a successful no-op. Stored record correctness is assumed at the write boundary. For an existing record, trust its stored `s3_key`, `pk`, and `sk`, without reconstructing or revalidating its key or identity.
- Delete the exact S3 object at the trusted stored key first, then perform an ordinary DynamoDB delete at `pk`/`sk`, without a conditional expression. S3 failure retains metadata; metadata failure can leave metadata after bytes are gone. Missing-object deletion makes retry safe, but there is no atomic rollback. Already-deleted metadata remains successful on later requests (single 204; bulk ID in `deleted_ids`).
- The conversation media bucket is currently unversioned; deletion does not purge historical versions or sweep prefixes. Conversation/message artifact references remain, deleted content is unavailable, and conversations are not deleted.

## Add an artifact type

1. Add the literal to `ArtifactType` in `models.py`; add it to the viewable set in `service.py` if browsers should render it.
2. Callers pass it to `ArtifactService.create_artifact(...)`; see `tests/test_artifacts.py` for the call shape.
3. Update the SPA's renderer if it displays that type.

## Testing

```bash
# From api/
uv run pytest tests/test_artifact_deletion.py tests/test_artifacts.py tests/test_artifact_access.py -q
uv run ruff check src/artifacts && uv run mypy src/artifacts
```

Fixtures: `dynamodb_table`, `test_client`, and boto3 S3 under moto (create the bucket in the test). `tests/test_artifacts.py` covers creation/list/view behavior; `tests/test_artifact_access.py` covers cross-member and cross-account read isolation. `tests/test_artifact_deletion.py` should cover single/bulk cleanup using the trusted stored S3 key, missing bytes, absent/repeated-delete idempotence, auth and cross-member/account isolation with foreign artifacts untouched, strict bounds, ordered deduplication, absent IDs in `deleted_ids`, and actual lookup/S3/DynamoDB failures with safe errors/retries. Deletion tests should not require stored-record integrity checks, malformed-key defenses, base-table rereads, or conditional-delete race defenses. Extend behavior regressions when changing deletion boundaries. For backend code changes, run the full suite from `api/` with `uv run pytest -q`.

## Do / Don't

- Do derive the partition from the `Owner`, never from a request parameter.
- Do keep S3 key construction in `ArtifactStorage`.
- Don't return S3 keys or raw bucket URLs; hand out presigned URLs (`conversation_media_presign_ttl_seconds`).
- Don't add sharing here; shared files would need an IAM resource type first.
