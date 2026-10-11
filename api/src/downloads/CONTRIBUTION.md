# Contributing to `downloads/`

Owns the public plugin download catalogue (`GET /downloads/plugins`, `GET /downloads/plugins/{plugin_id}`) for the
IDE, macOS and WordPress plugins. A manifest JSON in S3 describes the plugins; this module reads it and returns
short-lived presigned URLs. It has no auth and no DynamoDB.

```text
downloads/
  __init__.py   Exports `router`
  router.py     Routes and `get_downloads_service` dependency; maps service errors to 404 / 503
  service.py    DownloadsService (S3 manifest, README, presigning) and its two exception types
  models.py     PluginDownloadSummary, PluginDownloadDetail (adds readme_markdown), PluginDownloadsResponse
```

## Conventions

- Router stays thin: it depends on `DownloadsService` via `Depends(get_downloads_service)` and translates
  `PluginDownloadNotFoundError` to 404 and `DownloadsConfigurationError` to 503 with a generic detail (the real
  reason is logged, not returned).
- `DownloadsService(s3_client=None)` takes an injectable S3 client; the manifest is the source of truth, so there is
  no storage layer of our own. Manifest fields are read defensively (`str(...)`, `isinstance` checks).
- Settings: `downloads_artifacts_bucket`, `downloads_artifacts_region`, `downloads_manifest_key`,
  `downloads_presign_ttl_seconds` in `src/config/settings.py` (env `DOWNLOADS_*`). They are already wired in
  Terraform (`lambda.tf`), `scripts/deploy_prod_railway.sh`, `deploy_local.sh` and `generate_tfvars.sh`.

## How to add a field to the plugin metadata

1. Add it to `PluginDownloadSummary` (or `Detail`) in `models.py`.
2. Read it in `DownloadsService._build_summary` from the manifest entry, with the same defensive coercion.
3. Update the manifest the artifact publisher writes, and the SPA type that consumes the response.

Adding a plugin needs no code: add it to the manifest in S3.

## Testing

```bash
uv run pytest tests/test_downloads_router.py -q
uv run ruff check src/downloads && uv run mypy src/downloads
```

`tests/test_downloads_router.py` overrides `get_downloads_service` with a fake through `test_client`, so no S3 is
touched. For service-level tests use moto `mock_aws` with a real manifest object.

## Do / Don't

- Do raise `DownloadsConfigurationError` / `PluginDownloadNotFoundError` from the service, `HTTPException` only in the router.
- Do keep presigned URLs short-lived (`downloads_presign_ttl_seconds`); never return raw bucket URLs.
- Don't hard-code the bucket or manifest key; use `settings`.
- Don't leak S3 error text to clients.
