# Infra CLI Runner

Private Railway sidecar for running approved infrastructure CLIs behind the API skill runtime.

The service intentionally exposes only:

- `GET /health`
- `POST /v1/commands`

Requests must use bearer auth with `CLI_RUNNER_SHARED_TOKEN`. The runner accepts argv arrays only, never shell command strings.

The API remains responsible for user identity, skill installation, command policy validation, STS credential generation, large-output paging, and future analytics.

Run locally:

```bash
uv sync
CLI_RUNNER_SHARED_TOKEN=dev-token uv run uvicorn main:app --reload
```
