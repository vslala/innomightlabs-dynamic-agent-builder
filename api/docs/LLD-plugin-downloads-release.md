# Plugin Downloads Release Pipeline

## Goal

Offer Innomight plugin downloads from the SPA:

- `/downloads`
- `/downloads/plugins/vscode`
- `/downloads/plugins/wordpress`

Artifacts are stored in a private S3 bucket named:

```text
innomightlabs-artifacts
```

The API reads a generated plugin manifest and README content from S3, then returns short-lived presigned download URLs when users open the downloads pages.

## Key Decisions

- Use private S3, not public S3 URLs.
- Generate presigned URLs at request time in the API.
- Use `manifest.json` as the listing source of truth.
- Use per-plugin `README.md` as the details-page content.
- Package VS Code and WordPress plugins in parallel in GitHub Actions.
- Use the existing GitHub-provided AWS role for artifact uploads.
- Keep logos/icons in the artifact bucket and expose them via API-returned presigned URLs or API proxy URLs.

## S3 Layout

```text
s3://innomightlabs-artifacts/artifacts/plugins/manifest.json

s3://innomightlabs-artifacts/artifacts/plugins/vscode/README.md
s3://innomightlabs-artifacts/artifacts/plugins/vscode/icon.svg
s3://innomightlabs-artifacts/artifacts/plugins/vscode/innomightlabs-code-assist-0.1.0.vsix

s3://innomightlabs-artifacts/artifacts/plugins/wordpress/README.md
s3://innomightlabs-artifacts/artifacts/plugins/wordpress/icon.svg
s3://innomightlabs-artifacts/artifacts/plugins/wordpress/innomightlabs-ai-connector-0.1.0.zip
```

## Manifest Contract

Path:

```text
artifacts/plugins/manifest.json
```

Shape:

```json
{
  "schema_version": 1,
  "generated_at": "2026-05-24T12:00:00Z",
  "plugins": [
    {
      "id": "vscode",
      "name": "Innomight VS Code Plugin",
      "version": "0.1.0",
      "summary": "Build and manage Innomight agents directly from VS Code.",
      "category": "Developer Tools",
      "icon_key": "artifacts/plugins/vscode/icon.svg",
      "readme_key": "artifacts/plugins/vscode/README.md",
      "artifact_key": "artifacts/plugins/vscode/innomightlabs-code-assist-0.1.0.vsix",
      "artifact_name": "innomightlabs-code-assist-0.1.0.vsix",
      "artifact_content_type": "application/octet-stream",
      "sha256": "<artifact sha256>",
      "source_hash": "<plugin source hash>",
      "updated_at": "2026-05-24T12:00:00Z"
    },
    {
      "id": "wordpress",
      "name": "Innomight WordPress Plugin",
      "version": "0.1.0",
      "summary": "Connect a WordPress site to Innomight agents, chat widgets, and automation workflows.",
      "category": "WordPress",
      "icon_key": "artifacts/plugins/wordpress/icon.svg",
      "readme_key": "artifacts/plugins/wordpress/README.md",
      "artifact_key": "artifacts/plugins/wordpress/innomightlabs-ai-connector-0.1.0.zip",
      "artifact_name": "innomightlabs-ai-connector-0.1.0.zip",
      "artifact_content_type": "application/zip",
      "sha256": "<artifact sha256>",
      "source_hash": "<plugin source hash>",
      "updated_at": "2026-05-24T12:00:00Z"
    }
  ]
}
```

## Backend API

### Settings

Add:

```python
downloads_artifacts_bucket: str = "innomightlabs-artifacts"
downloads_manifest_key: str = "artifacts/plugins/manifest.json"
downloads_presign_ttl_seconds: int = 900
```

### Endpoints

Add a downloads router:

```text
GET /downloads/plugins
GET /downloads/plugins/{plugin_id}
```

These can be public endpoints unless you want downloads to require login. If public, do not mount them behind dashboard auth.

`GET /downloads/plugins` response:

```json
{
  "plugins": [
    {
      "id": "vscode",
      "name": "Innomight VS Code Plugin",
      "version": "0.1.0",
      "summary": "Build and manage Innomight agents directly from VS Code.",
      "category": "Developer Tools",
      "icon_url": "https://s3-presigned-url",
      "download_url": "https://s3-presigned-url",
      "artifact_name": "innomightlabs-code-assist-0.1.0.vsix",
      "sha256": "...",
      "details_path": "/downloads/plugins/vscode"
    }
  ]
}
```

`GET /downloads/plugins/{plugin_id}` response:

```json
{
  "plugin": {
    "id": "vscode",
    "name": "Innomight VS Code Plugin",
    "version": "0.1.0",
    "summary": "...",
    "icon_url": "https://s3-presigned-url",
    "download_url": "https://s3-presigned-url",
    "artifact_name": "innomightlabs-code-assist-0.1.0.vsix",
    "sha256": "..."
  },
  "readme_markdown": "# Innomight VS Code Plugin\n..."
}
```

### API Implementation Notes

Create:

```text
api/src/downloads/models.py
api/src/downloads/service.py
api/src/downloads/router.py
```

Service responsibilities:

- Read and parse `manifest.json` from S3.
- Find plugin by `id`.
- Read README markdown from S3 for detail endpoint.
- Generate presigned URLs for `artifact_key`.
- Generate presigned URLs for `icon_key`, or alternatively expose icons through the API.

Presign call:

```python
s3.generate_presigned_url(
    "get_object",
    Params={
        "Bucket": settings.downloads_artifacts_bucket,
        "Key": artifact_key,
        "ResponseContentDisposition": f'attachment; filename="{artifact_name}"',
    },
    ExpiresIn=settings.downloads_presign_ttl_seconds,
)
```

For icons, do not force attachment:

```python
s3.generate_presigned_url(
    "get_object",
    Params={"Bucket": bucket, "Key": icon_key},
    ExpiresIn=settings.downloads_presign_ttl_seconds,
)
```

### API IAM

Lambda role needs read-only access:

```hcl
Action = [
  "s3:GetObject",
  "s3:ListBucket"
]
Resource = [
  "arn:aws:s3:::innomightlabs-artifacts",
  "arn:aws:s3:::innomightlabs-artifacts/artifacts/plugins/*"
]
```

## Terraform

Add a dedicated bucket:

```hcl
resource "aws_s3_bucket" "artifacts" {
  bucket = "innomightlabs-artifacts"
}

resource "aws_s3_bucket_public_access_block" "artifacts" {
  bucket                  = aws_s3_bucket.artifacts.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
```

Do not attach a public read policy.

Add API Lambda env vars:

```hcl
DOWNLOADS_ARTIFACTS_BUCKET = aws_s3_bucket.artifacts.id
DOWNLOADS_MANIFEST_KEY     = "artifacts/plugins/manifest.json"
```

Add an IAM policy for Lambda read access.

For GitHub upload access, use the existing GitHub-provided AWS role in the workflow. If that role does not already have S3 write access, add only this scoped permission to that existing role:

```hcl
Action = [
  "s3:GetObject",
  "s3:PutObject",
  "s3:DeleteObject",
  "s3:ListBucket"
]
Resource = [
  "arn:aws:s3:::innomightlabs-artifacts",
  "arn:aws:s3:::innomightlabs-artifacts/artifacts/plugins/*"
]
```

## Packaging Scripts

Add dedicated scripts:

```text
scripts/downloads/package_vscode_plugin.sh
scripts/downloads/package_wordpress_plugin.sh
scripts/downloads/generate_plugins_manifest.py
scripts/downloads/publish_plugins.sh
```

### VS Code Packaging

Input:

```text
plugins/ide/vscode/innomightlabs-code-assist
```

Output directory:

```text
dist/downloads/vscode
```

Script behavior:

- install dependencies
- run lint/build/test if available
- package `.vsix`
- copy `README.md`
- copy or generate `icon.svg`
- compute artifact SHA256
- compute source hash from plugin source files
- write a plugin build metadata JSON:

```text
dist/downloads/vscode/plugin-build.json
```

### WordPress Packaging

Input:

```text
plugins/wordpress/innomightlabs-ai-connector
```

Output directory:

```text
dist/downloads/wordpress
```

Script behavior:

- validate main plugin PHP file exists
- exclude development docs/build files if needed
- zip the plugin folder
- convert/copy `readme.txt` or write `README.md`
- copy `assets/logo.svg` as `icon.svg`
- compute artifact SHA256
- compute source hash from plugin source files
- write `dist/downloads/wordpress/plugin-build.json`

### Version Increment

Use current S3 manifest as the deployed-state source of truth:

1. Download existing `artifacts/plugins/manifest.json` if it exists.
2. Compare each plugin's new `source_hash` to previous `source_hash`.
3. If unchanged, reuse previous version and artifact key.
4. If changed, bump patch version by default.
5. Allow explicit override:

```bash
VSCODE_PLUGIN_VERSION=0.2.0 WORDPRESS_PLUGIN_VERSION=0.3.0 scripts/downloads/publish_plugins.sh
```

This avoids committing a lock file just to bump versions, while still making deploys deterministic from the previous published manifest.

## GitHub Actions Plan

Existing workflow:

```text
.github/workflows/deploy.yml
```

It already has:

```yaml
permissions:
  contents: read
  pages: write
  id-token: write
```

Add AWS auth with the existing GitHub-provided role:

```yaml
- name: Configure AWS credentials
  uses: aws-actions/configure-aws-credentials@v4
  with:
    role-to-assume: ${{ vars.AWS_ROLE_TO_ASSUME }}
    aws-region: us-east-1
```

If the role is stored as a secret instead, use:

```yaml
role-to-assume: ${{ secrets.AWS_ROLE_TO_ASSUME }}
```

### Parallel Plugin Build Job

Use a matrix so VS Code and WordPress package in parallel under the same release stage:

```yaml
package_plugins:
  runs-on: ubuntu-latest
  strategy:
    fail-fast: false
    matrix:
      plugin: [vscode, wordpress]
  steps:
    - uses: actions/checkout@v4

    - name: Setup Node
      if: matrix.plugin == 'vscode'
      uses: actions/setup-node@v4
      with:
        node-version: '20'
        cache: 'yarn'
        cache-dependency-path: plugins/ide/vscode/innomightlabs-code-assist/yarn.lock

    - name: Package VS Code plugin
      if: matrix.plugin == 'vscode'
      run: scripts/downloads/package_vscode_plugin.sh

    - name: Package WordPress plugin
      if: matrix.plugin == 'wordpress'
      run: scripts/downloads/package_wordpress_plugin.sh

    - name: Upload packaged plugin as workflow artifact
      uses: actions/upload-artifact@v4
      with:
        name: plugin-${{ matrix.plugin }}
        path: dist/downloads/${{ matrix.plugin }}
```

These GitHub artifacts are only internal handoff artifacts between workflow jobs, not customer-facing downloads.

### Publish Job

One publish job gathers both plugin outputs and uploads to S3:

```yaml
publish_plugins:
  runs-on: ubuntu-latest
  needs: package_plugins
  steps:
    - uses: actions/checkout@v4

    - uses: actions/download-artifact@v4
      with:
        pattern: plugin-*
        path: dist/downloads
        merge-multiple: true

    - name: Configure AWS credentials
      uses: aws-actions/configure-aws-credentials@v4
      with:
        role-to-assume: ${{ vars.AWS_ROLE_TO_ASSUME }}
        aws-region: us-east-1

    - name: Publish plugin artifacts
      run: scripts/downloads/publish_plugins.sh
      env:
        ARTIFACTS_BUCKET: innomightlabs-artifacts
        PLUGINS_PREFIX: artifacts/plugins
```

`publish_plugins.sh` should:

- fetch existing manifest from S3 if present
- run `generate_plugins_manifest.py`
- upload each plugin artifact, README, icon
- upload final `manifest.json`

## SPA Plan

Add:

```text
spa/src/pages/DownloadsPage.tsx
spa/src/pages/PluginDetailsPage.tsx
spa/src/services/downloads/DownloadsApiService.ts
spa/src/types/downloads.ts
```

Routes:

```tsx
<Route path="/downloads" element={<DownloadsPage />} />
<Route path="/downloads/plugins/:pluginId" element={<PluginDetailsPage />} />
```

Use existing markdown renderer:

```text
spa/src/components/ui/markdown-renderer.tsx
```

`/downloads` UX:

- full page with two polished plugin cards
- icon
- name
- version
- summary
- "Download" button
- "Details" button

`/downloads/plugins/:pluginId` UX:

- icon + plugin name + version
- primary download button
- SHA256 copy/display
- markdown-rendered README
- back link to `/downloads`

## Implementation Order

1. Terraform bucket and IAM.
2. API settings, service, models, router.
3. Packaging scripts for each plugin.
4. Manifest generation and S3 publish script.
5. GitHub Actions matrix packaging and publish job.
6. SPA `/downloads` and plugin details pages.
7. End-to-end release test.

## Release Test

After deploy:

```bash
curl https://api.innomightlabs.com/downloads/plugins
```

Expected:

- two plugins
- presigned `download_url`
- icon URL
- details path

Then:

```bash
curl https://api.innomightlabs.com/downloads/plugins/vscode
```

Expected:

- README markdown
- presigned VSIX download URL
- SHA256

Open:

```text
https://innomightlabs.com/downloads
https://innomightlabs.com/downloads/plugins/vscode
https://innomightlabs.com/downloads/plugins/wordpress
```

Download buttons should trigger short-lived S3 presigned downloads.

