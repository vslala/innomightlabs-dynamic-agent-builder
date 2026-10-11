# Artifacts Contribution Guide

`artifacts/` stores files and HTML canvases that agents, skills and automations produce. The bytes go to S3, the metadata to DynamoDB. An artifact is private to one member in one account.

## Layout

```text
src/artifacts/
  models.py      Artifact, ArtifactSource, ArtifactType, response models
  repository.py  save, find_by_id (via gsi2), list_in
  storage.py     ArtifactStorage: S3 put/get/presign; member_prefix, sanitize_filename
  service.py     ArtifactService: create, list, urls, content; run_artifact_holder
  router.py      /artifacts: list, get, download-url, view-url, content
```

## Conventions

- Keys: `pk=member_partition(account_id, user_id)` (from `accounts/owner.py`), `sk=Artifact#{created_at}#{artifact_id}` so a listing is newest-sortable. `gsi2_pk=Artifact#{artifact_id}`, `gsi2_sk={partition}` supports lookup by id within a partition.
- Access: routes use `Owner` (`get_owner`) and pass `owner.member_pk`; the service looks up only in that partition, so another member's or account's artifact is simply not found (`ArtifactNotFoundError`, 404). There is no IAM action: artifacts are never shared.
- S3 keys: `accounts/{account_id}/members/{user_id}/artifacts/{yyyy/mm/dd}/{artifact_id}/{safe_filename}` in `settings.conversation_media_bucket`. Always build them with `build_key`; filenames go through `sanitize_filename`.
- Only `VIEWABLE_ARTIFACT_TYPES` open in the browser (`ArtifactNotViewableError` otherwise).
- Who owns a skill run's file: `run_artifact_holder` returns the member whose conversation it is, else the agent owner (keys, visitors and A2A callers have no member).
- Errors are domain exceptions raised by the service and mapped to `HTTPException` in the router.

## Add an artifact type

1. Add the literal to `ArtifactType` in `models.py`; add it to the viewable set in `service.py` if browsers should render it.
2. Callers pass it to `ArtifactService.create_artifact(...)`; see `tests/test_artifacts.py` for the call shape.
3. Update the SPA's renderer if it displays that type.

## Testing

```bash
uv run pytest tests/test_artifacts.py tests/test_artifact_access.py -q
uv run ruff check src/artifacts && uv run mypy src/artifacts
```

Fixtures: `dynamodb_table`, `test_client`, and boto3 S3 under moto (create the bucket in the test). `tests/test_artifact_access.py` covers cross-member and cross-account isolation; extend it for any new read path.

## Do / Don't

- Do derive the partition from the `Owner`, never from a request parameter.
- Do keep S3 key construction in `ArtifactStorage`.
- Don't return S3 keys or raw bucket URLs; hand out presigned URLs (`conversation_media_presign_ttl_seconds`).
- Don't add sharing here; shared files would need an IAM resource type first.
