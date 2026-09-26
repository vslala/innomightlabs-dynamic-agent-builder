# Infra CLI Runner

Private Railway sidecar for running approved infrastructure CLIs behind the API skill runtime.

The service intentionally exposes only:

- `GET /health`
- `POST /v1/commands`
- `POST /v1/python/executions`
- `POST /v1/filesystem/actions`
- `GET /v1/mcp/packages`, `PUT|GET|DELETE /v1/mcp/servers/{server_id}`, `POST /v1/mcp/servers/{server_id}/mcp`

Requests must use bearer auth with `CLI_RUNNER_SHARED_TOKEN`. The runner never accepts shell command strings.

## Hosted stdio MCP servers

The runner hosts stdio MCP servers as long-lived processes and exposes each one through a stateless Streamable HTTP
façade, so the API talks to them with its ordinary MCP client. It only runs packages baked into the image:

```
mcp_packages/<key>/
  package.toml       entrypoint = "<console script>"   (optional: args = [...])
  requirements.txt   pinned, reviewed install (a git dependency pins a commit, never a branch)
```

The `mcp-packages` build stage installs each package into `/opt/mcp/<key>`; `git` exists only in that stage. Adding or
upgrading a package is a code review plus a redeploy. Nothing is installed at runtime.

- `PUT /v1/mcp/servers/{server_id}` with `{spec: {package, args, env, files}, wait_seconds}` is idempotent: it keeps a
  running server whose spec fingerprint matches, drains and restarts it when the spec changes (for example rotated
  credentials), and starts it when missing (after a redeploy, idle reap, or crash).
- `files` maps an env name to file content. Each file is written `0600` under the server's private `secrets/`
  directory, the env var holds its path, and the directory is removed when the server stops.
- The façade answers `initialize` from the child's cached handshake (a stdio process accepts one), remaps request ids
  so concurrent callers cannot collide, and refuses server-to-client requests with `-32601`.
- Servers idle for 15 minutes are stopped; at 8 running servers the least recently used idle one is evicted.

The process pool lives in memory, so **run this service as one replica with one worker** (the `CMD` sets no
`--workers`). All hosted servers share the `runner` uid, which is why only reviewed, baked packages may run.

On Apple Silicon machines whose CPU reports SME (M4-class), the arm64 `cryptography` wheel used by some Python MCP
packages crashes with an illegal instruction inside Docker. Build or run the image with `--platform linux/amd64`
locally if a hosted server exits with code `-4`; Railway builds for amd64.

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

The runner creates a private UUID run directory, writes fixed `script.py` and `requirements.txt` paths there, and uses `uv` to create a fresh `.venv` before every execution. Requirements are installed into that environment and the script always runs with its Python interpreter. When the API supplies an opaque `workspace_id`, the script runs in that conversation workspace so generated reports remain available through the File System skill. The private run directory and environment are cleaned afterward.

Environment creation is returned as the non-agent-controllable first command result with `operation: "create_environment"`. The remaining ordered command list is fail-fast: after setup or a requested command fails or times out, later entries are returned with `status: "skipped"`. The 60-second default is a single deadline shared by environment creation, dependency installation, and script execution.

Requirements are limited to package-index requirement specifiers and binary wheels. Options, nested requirement files, local paths, direct URLs, and source distributions are rejected. Binary-extension packages such as NumPy are supported when a compatible wheel is available. Python receives a sanitized environment and a startup audit policy that rejects normal filesystem writes outside its run directory and prevents child-process execution. The production container also runs the service as an unprivileged user. This is controlled script execution, not unrestricted shell or host isolation.

The operation-to-argv mapping in `CliRunnerService._python_command_argv` is the policy extension point for future project-scoped `uv` support. Any future operations must remain typed and allowlisted; do not expose arbitrary `uv` argv or general shell execution.

The API remains responsible for user identity, skill installation, command policy validation, STS credential generation, large-output paging, and future analytics.

## Filesystem workspaces

`POST /v1/filesystem/actions` accepts typed action names and structured arguments. It never accepts host paths or shell commands. The sidecar canonicalizes every workspace-relative path, blocks traversal and symlink escapes, bounds reads/search/diffs, detects binary files, applies text writes atomically, enforces per-write and workspace quotas, and returns a compact structured result.

Workspaces default to `/tmp/infra-cli-runner/workspaces`. The root and limits can be configured with `FILE_SYSTEM_WORKSPACE_ROOT`, `FILE_SYSTEM_MAX_READ_BYTES`, `FILE_SYSTEM_MAX_WRITE_BYTES`, and `FILE_SYSTEM_WORKSPACE_QUOTA_BYTES`. The runner executes validated filesystem requests as received; authorization and approval policy belong to the API skill platform.

Run locally:

```bash
uv sync
CLI_RUNNER_SHARED_TOKEN=dev-token uv run uvicorn main:app --reload
```

Run tests:

```bash
uv run python -m unittest discover -s tests -v
```

`tests/test_mcp_servers.py` drives a real stdio process (`tests/fake_mcp_server.py`) through the pool and façade.
