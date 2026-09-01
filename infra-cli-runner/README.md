# Infra CLI Runner

Private Railway sidecar for running approved infrastructure CLIs behind the API skill runtime.

The service intentionally exposes only:

- `GET /health`
- `POST /v1/commands`
- `POST /v1/python/executions`

Requests must use bearer auth with `CLI_RUNNER_SHARED_TOKEN`. The runner never accepts shell command strings.

## Python executions

Python executions accept script and `requirements.txt` content directly. Callers select from fixed operations rather than supplying executable paths or a working directory:

```json
{
  "request_id": "tooljob_or_run_node_id",
  "script": "import httpx\nprint(httpx.__version__)",
  "requirements": "httpx==0.28.1",
  "commands": [
    {"operation": "install_requirements"},
    {"operation": "run_script", "args": []}
  ],
  "timeout_seconds": 30
}
```

The runner creates a private UUID directory beneath `/tmp/infra-cli-runner`, writes fixed `script.py` and `requirements.txt` paths there, and cleans the run directory afterward. The ordered command list is fail-fast: after a failed or timed-out command, remaining entries are returned with `status: "skipped"`. The 30-second default is a single deadline shared by the whole sequence.

Requirements are limited to package-index requirement specifiers. Options, nested requirement files, local paths, direct URLs, and source distributions are rejected. Python receives a sanitized environment and a startup audit policy that rejects normal filesystem writes outside its run directory and prevents child-process and native-library escape routes. The production container also runs the service as an unprivileged user. This is controlled script execution, not unrestricted shell or host isolation.

The operation-to-argv mapping in `CliRunnerService._python_command_argv` is the policy extension point for future project-scoped `uv` support. Any future operations must remain typed and allowlisted; do not expose arbitrary `uv` argv or general shell execution.

The API remains responsible for user identity, skill installation, command policy validation, STS credential generation, large-output paging, and future analytics.

Run locally:

```bash
uv sync
CLI_RUNNER_SHARED_TOKEN=dev-token uv run uvicorn main:app --reload
```

Run tests:

```bash
uv run python -m unittest discover -s tests -v
```
