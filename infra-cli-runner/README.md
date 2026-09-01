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
  "timeout_seconds": 60
}
```

The runner creates a private UUID directory beneath `/tmp/infra-cli-runner`, writes fixed `script.py` and `requirements.txt` paths there, and uses `uv` to create a fresh `.venv` before every execution. Requirements are installed into that environment and the script always runs with its Python interpreter. The run directory and environment are cleaned afterward.

Environment creation is returned as the non-agent-controllable first command result with `operation: "create_environment"`. The remaining ordered command list is fail-fast: after setup or a requested command fails or times out, later entries are returned with `status: "skipped"`. The 60-second default is a single deadline shared by environment creation, dependency installation, and script execution.

Requirements are limited to package-index requirement specifiers and binary wheels. Options, nested requirement files, local paths, direct URLs, and source distributions are rejected. Binary-extension packages such as NumPy are supported when a compatible wheel is available. Python receives a sanitized environment and a startup audit policy that rejects normal filesystem writes outside its run directory and prevents child-process execution. The production container also runs the service as an unprivileged user. This is controlled script execution, not unrestricted shell or host isolation.

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
