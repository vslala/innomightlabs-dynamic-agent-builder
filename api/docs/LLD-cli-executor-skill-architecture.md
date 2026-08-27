# Low Level Design: CLI Executor Skill Architecture

Date: 2026-08-27
Status: Draft
Owner: InnomightLabs API

## Summary

Create a generic CLI execution service that runs approved infrastructure CLIs, starting with AWS CLI, behind the existing manifest-backed skill system.

The core idea is feasible and directionally good: official CLIs reduce SDK wrapper maintenance, keep behavior aligned with provider tooling, and let new infrastructure capabilities be added mostly through command policy and container image updates. The unsafe version of this idea is "agent passes an arbitrary shell command to a container." The maintainable version is a brokered command runner:

```text
Agent / Automation
  -> execute_skill_action(cli_executor.run_aws)
  -> api/src/skills/cli_executor/actions.py
  -> private Railway service: infra-cli-runner
  -> approved executable + approved argv + scoped env credentials
  -> bounded stdout/stderr/result JSON
```

The agent still experiences this as a normal skill action. The API owns command policy, credential lookup, audit metadata, and result shaping. The runner service owns process execution isolation and installed CLI versions.

## Feasibility Decision

Recommended: build this as a separate private Railway service plus a thin skill wrapper.

Do not run provider CLIs inside the main API container. A separate runner service gives a better blast-radius boundary, independent dependency updates, separate resource limits, clearer logs, and a future path to queue-backed jobs.

Do not expose a generic `shell` action. Expose provider-specific actions such as `run_aws` and validate a structured command model. The first implementation can still be generic internally, but the public skill contract should be constrained.

## Current System Fit

The existing skills module already has most of the required extension points:

- `api/src/skills/registry.py` loads `api/src/skills/*/manifest.yml` and dispatches action handlers through `handler(arguments, config, context)`.
- `api/src/skills/service.py` installs skills, separates secret form fields, checks connectors, resolves installed skill ids, and invokes actions for agents.
- `api/src/automations/runner.py` can execute manifest skill actions from automation nodes with rendered smart values.
- `api/src/agents/tool_runtime/jobs/service.py` supports async skill action jobs, which is important for slow CLI operations.
- `api/src/connectors/service.py` already models user-level connector status on top of provider settings.

This means the first version should not require changing the skill registry contract. It can be added as a normal skill package under:

```text
api/src/skills/cli_executor/
  __init__.py
  manifest.yml
  actions.py
  models.py
```

Shared platform changes should be small:

- Add an internal HTTP client helper only if more than one skill needs service-to-service calls.
- Add settings for the runner URL/token in `api/src/config/settings.py`.
- Store AWS credential seeds and the editable command policy as encrypted skill install config for v1.

## External Platform Facts

Railway supports private service-to-service communication through private domains under `railway.internal`; services in the same project/environment can communicate over HTTP without public exposure, while client browsers cannot reach those internal domains. Source: <https://docs.railway.com/networking/domains/working-with-domains>

Railway variables are available to service builds and running deployments, and reference variables can point one service at another service's private domain. Source: <https://docs.railway.com/variables>

Railway health checks require the service to listen on the configured `PORT` and return HTTP `200` on the health path during deployment activation. Source: <https://docs.railway.com/deployments/healthchecks>

AWS CLI supports credentials and config through environment variables such as `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`, and `AWS_DEFAULT_REGION`; environment variables override profile files. Source: <https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-envvars.html>

## Architecture

### Services

```text
Railway project/environment

api
  FastAPI backend.
  Public service.
  Calls infra-cli-runner over private networking.

infra-cli-runner
  Private HTTP service.
  No public domain.
  Ubuntu or Debian slim image with approved CLIs installed.
  Executes commands without shell interpolation.
```

The API should call the runner through a Railway reference variable:

```text
CLI_RUNNER_BASE_URL=http://${{infra-cli-runner.RAILWAY_PRIVATE_DOMAIN}}:${{infra-cli-runner.PORT}}
CLI_RUNNER_SHARED_TOKEN=<sealed secret>
```

The runner should also hold the same shared token:

```text
CLI_RUNNER_SHARED_TOKEN=<sealed secret>
PORT=8080
```

### Runner API

Keep the runner HTTP API narrow:

```http
POST /v1/commands
Authorization: Bearer <CLI_RUNNER_SHARED_TOKEN>
Content-Type: application/json
```

Request:

```json
{
  "request_id": "tooljob_or_run_node_id",
  "tool": "aws",
  "argv": ["s3", "ls", "s3://example-bucket", "--region", "us-east-1"],
  "env": {
    "AWS_ACCESS_KEY_ID": "...",
    "AWS_SECRET_ACCESS_KEY": "...",
    "AWS_SESSION_TOKEN": "...",
    "AWS_DEFAULT_REGION": "us-east-1"
  },
  "timeout_seconds": 30,
  "max_stdout_bytes": 65536,
  "max_stderr_bytes": 16384
}
```

Response:

```json
{
  "ok": true,
  "request_id": "tooljob_or_run_node_id",
  "tool": "aws",
  "exit_code": 0,
  "stdout": "...",
  "stderr": "",
  "duration_ms": 842,
  "stdout_truncated": false,
  "stderr_truncated": false
}
```

The runner must call process APIs directly:

```python
await asyncio.create_subprocess_exec(
    executable,
    *argv,
    env=sanitized_env,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
)
```

Do not use `shell=True`. Do not accept a single command string in the runner API.

### Skill Contract

The skill should expose provider-specific actions, not a global shell.

Manifest sketch:

```yaml
id: cli_executor
namespace: infrastructure.cli
name: CLI Executor
description: Run approved infrastructure CLI commands through the private CLI runner.
system_prompt: |
  Use this skill for approved infrastructure CLI operations.
  Pass command arguments as an argv array. Do not pass shell syntax, pipes, redirects, subshells, or command separators.
  Prefer read-only actions unless the user explicitly asks for a mutation.
  For slow commands, call execute_skill_action with async: true.
connectors:
  - connector_id: aws_cli
    required: true
actions:
  - name: run_aws
    description: Run an approved AWS CLI command with scoped AWS credentials.
    input_schema:
      type: object
      required: [argv]
      properties:
        argv:
          type: array
          items:
            type: string
          description: AWS CLI arguments after the aws executable.
        timeout_seconds:
          type: integer
        max_output_chars:
          type: integer
        dry_run:
          type: boolean
    handler: actions:run_aws
```

Action argument example:

```json
{
  "argv": ["s3api", "list-objects-v2", "--bucket", "innomightlabs-artifacts", "--max-items", "10"],
  "timeout_seconds": 30
}
```

The handler converts that into a runner request with `tool="aws"` and injects AWS credentials from connector/provider settings.
The implementation should pass temporary STS session credentials to the runner, not the user-provided long-lived access key.

## Credential Model

### V1: Skill Install Credentials Plus STS Runtime Credentials

The user provides AWS credential seeds when installing the skill:

```yaml
form:
  - input_type: password
    name: aws_access_key_id
    label: AWS access key id
    attr:
      secret: "true"
  - input_type: password
    name: aws_secret_access_key
    label: AWS secret access key
    attr:
      secret: "true"
  - input_type: password
    name: aws_session_token
    label: AWS session token
    attr:
      secret: "true"
      optional: "true"
  - input_type: text
    name: aws_region
    label: AWS region
    value: us-east-1
  - input_type: text_area
    name: command_policy_yaml
    label: Command policy
    value: |
      aws:
        default_timeout_seconds: 30
        max_timeout_seconds: 120
        max_stdout_bytes: 65536
        services:
          s3:
            read:
              - ["s3api", "list-buckets"]
              - ["s3api", "list-objects-v2"]
          dynamodb:
            read:
              - ["dynamodb", "list-tables"]
              - ["dynamodb", "describe-table"]
```

The install UI should prefill `command_policy_yaml` from the skill's default policy and allow the user to edit it before saving. The persisted installed skill config becomes the runtime source of truth. On every action call, `actions.py` reads the persisted policy from decrypted runtime config, validates the requested argv against that policy, and only then calls the runner.

The skill action should use the installed AWS credential seeds only inside the API process to call AWS STS and create a short-lived session. The runner receives only these temporary values:

```text
AWS_ACCESS_KEY_ID=<temporary STS access key>
AWS_SECRET_ACCESS_KEY=<temporary STS secret>
AWS_SESSION_TOKEN=<temporary STS session token>
AWS_DEFAULT_REGION=<installed skill region>
```

The runner must never receive the user's long-lived secret key. Secret fields should stay encrypted in skill config and should not be exposed in catalog/install responses.

### Future Credential Upgrade: AssumeRole

The initial STS call can use `GetSessionToken` with the installed user-provided key. A stronger production model is to let the user provide an IAM role ARN during install, then use `AssumeRole` to mint the runner credentials.

Advantages:

- Short-lived credentials limit exposure.
- IAM role policies remain the real permission boundary.
- CloudTrail shows assumed role sessions.
- Users can revoke role trust without rotating static keys in InnomightLabs.

## Command Policy

The maintenance savings only hold if command validation is policy-driven.

Recommended policy shape:

```yaml
aws:
  default_timeout_seconds: 30
  max_timeout_seconds: 120
  max_stdout_bytes: 65536
  services:
    s3:
      read:
        - ["s3", "ls"]
        - ["s3api", "list-buckets"]
        - ["s3api", "list-objects-v2"]
        - ["s3api", "head-object"]
        - ["s3api", "get-object"]
      write:
        - ["s3", "cp"]
        - ["s3api", "put-object"]
        - ["s3api", "delete-object"]
    dynamodb:
      read:
        - ["dynamodb", "list-tables"]
        - ["dynamodb", "describe-table"]
        - ["dynamodb", "query"]
        - ["dynamodb", "scan"]
        - ["dynamodb", "get-item"]
      write:
        - ["dynamodb", "put-item"]
        - ["dynamodb", "update-item"]
        - ["dynamodb", "delete-item"]
```

Validation rules:

- Reject shell metacharacters because argv has no need for them: `|`, `&&`, `;`, `>`, `<`, `$(`, backticks.
- Reject commands not matching an allowlisted prefix.
- Treat write/delete/update/create commands as mutations and require `allow_mutation: true` in arguments or separate action names.
- Add resource constraints for production accounts, for example allowed bucket names, table prefixes, and regions.
- Clamp `--page-size`, `--max-items`, output bytes, and timeout.
- Disable interactive behavior with environment variables and arguments where available.
- Redact secrets from logs and runner responses.

The default policy should live in the skill package:

```text
api/src/skills/cli_executor/default_policy.yml
```

At install time, that default YAML is copied into the skill install form as `command_policy_yaml`. The user can edit it before persisting. Runtime always validates against the persisted policy from DB, not the packaged default. That keeps maintenance low while allowing per-agent/per-tenant scoping without a new policy service.

## Runner Container

Dockerfile sketch:

```dockerfile
FROM python:3.13-slim

RUN apt-get update \
  && apt-get install -y --no-install-recommends curl unzip ca-certificates groff less \
  && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "/tmp/awscliv2.zip" \
  && unzip /tmp/awscliv2.zip -d /tmp \
  && /tmp/aws/install \
  && rm -rf /tmp/aws /tmp/awscliv2.zip

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY main.py ./
COPY src ./src
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app"
ENV PYTHONUNBUFFERED=1
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
```

Pin CLI versions where practical. The goal is low maintenance, not uncontrolled drift. Use a scheduled rebuild cadence and smoke tests to update CLI versions deliberately.

## Security Boundary

This architecture must be treated as remote code execution over a narrow protocol.

Required controls:

- `infra-cli-runner` has no public domain.
- API authenticates every runner request with a shared secret or signed HMAC.
- Runner accepts only known `tool` values.
- Runner executes only argv arrays, never shell strings.
- API validates command policy before calling the runner.
- Runner repeats minimal executable allowlisting as defense in depth.
- Each command runs with a minimal environment.
- No credentials are stored on disk; pass credentials through child process env only.
- Use temp directories per request and clean them after execution.
- Enforce CPU/memory limits through Railway service sizing where possible.
- Enforce process timeout and kill the whole process group on timeout.
- Keep all user-facing interactions in the API. The runner should not know about users, agents, automations, approvals, or analytics.
- Store skill execution analytics/audit records in a separate follow-up feature; do not block the first runner implementation on analytics.

## Read vs Mutate Actions

Use separate actions when the UX and safety differ:

```text
run_aws_read
run_aws_mutation
```

or keep one action with explicit fields:

```json
{
  "argv": ["s3api", "delete-object", "--bucket", "x", "--key", "y"],
  "allow_mutation": true,
  "mutation_reason": "Delete stale generated artifact requested by the user"
}
```

For v1, avoid mutating commands. When mutating commands are introduced, add a separate runtime feature that lets a manifest action declare whether execution requires explicit user permission before the agent runtime dispatches it. That permission gate should be platform-level metadata on skill actions, not bespoke logic inside only the CLI skill.

## Result Shaping

Return structured output rather than raw terminal text whenever practical:

- If stdout is JSON, parse it and return both `json` and a bounded `stdout_preview`.
- If stdout is text, return bounded text plus truncation metadata.
- Always include `exit_code`, `duration_ms`, and command category.
- On non-zero exit, raise `RuntimeError` from the skill action with bounded stderr.

Recommended skill return:

```json
{
  "ok": true,
  "tool": "aws",
  "command": "aws s3api list-objects-v2 ...",
  "exit_code": 0,
  "json": {"Contents": []},
  "stdout_preview": "{\"Contents\":[]}",
  "stderr_preview": "",
  "duration_ms": 842,
  "truncated": false
}
```

## Async Behavior

Most read commands can run synchronously with a 20-30 second timeout.

Slow commands should use the existing async skill job path:

```json
{
  "skill_id": "cli_executor",
  "action": "run_aws",
  "arguments": {
    "argv": ["s3", "sync", "s3://source", "s3://dest"],
    "timeout_seconds": 120
  },
  "async": true
}
```

For long-running infrastructure operations, the future target should be queue-backed:

```text
API creates ToolJob
Worker/runner claims job
Runner updates job status/progress
Agent/automation polls check_tool_job
```

The current in-process async path is enough for a prototype but is not a durable job system if the API process restarts.

## Large Output Paging

Large command outputs and large file reads should be owned by the skill, not by the agent reasoning loop.

Add a read-style action that stores or reuses a bounded output artifact and returns one page at a time:

```json
{
  "action": "read_output_page",
  "arguments": {
    "output_id": "cliout_...",
    "page": 1,
    "page_size_chars": 12000
  }
}
```

The agent should receive page content plus navigation metadata:

```json
{
  "ok": true,
  "output_id": "cliout_...",
  "page": 1,
  "total_pages": 8,
  "content": "...",
  "has_next": true,
  "next_page": 2,
  "message": "More output is available. Call read_output_page with page=2 to continue."
}
```

This behaves like a controlled `more` command: the skill can hold the large stdout, stderr, or file output in DynamoDB/S3 with TTL and the agent asks for additional pages only when needed. The runner still returns bounded process output to the API; durable large-output storage belongs in the API skill layer.

## Automation Compatibility

The action can be automation-compatible if:

- It does not depend on live chat-only context.
- It receives all command arguments from `arguments`.
- It uses connector credentials by `owner_email`.
- It has an `action_form` with `smart_values: "true"` for argv or command parameters.

For v1, expose only read commands to automations by default. Mutation automation should wait until command policy, audit logs, and review UI are proven.

## Minimal Implementation Plan

### Phase 0: Prototype Locally

1. Build a tiny `infra-cli-runner` FastAPI app in a top-level repo folder next to `api`.
2. Install AWS CLI in its Dockerfile.
3. Add `/health` and `/v1/commands`.
4. Implement shared-token auth, argv execution, timeout, output truncation, and basic logging.
5. Run local smoke tests with fake/stub commands before real AWS.

### Phase 1: Add The Skill

1. Add `api/src/skills/cli_executor/manifest.yml`.
2. Add `models.py` with `AwsCliRequest`.
3. Add `default_policy.yml` with a small AWS read-only allowlist.
4. Add install fields for AWS credential seeds, region, and editable `command_policy_yaml`.
5. Add `actions.py` that validates arguments, loads decrypted install config, mints temporary STS credentials, checks the persisted policy, calls `CLI_RUNNER_BASE_URL`, and shapes the response.
6. Add `read_output_page` for paged large output once the first command execution path is proven.
7. Add settings:
   - `cli_runner_base_url`
   - `cli_runner_shared_token`
   - `cli_runner_timeout_seconds`
8. Add tests for manifest loading, policy allow/reject behavior, STS credential generation, redaction, runner HTTP failures, and successful result shaping.

### Phase 2: Deploy Private Runner On Railway

1. Add the runner as a second Railway service in the same project/environment as `api`.
2. Do not generate a public domain for the runner.
3. Configure `/health` health check.
4. Set `CLI_RUNNER_BASE_URL` in `api` using the runner private domain reference variable.
5. Set sealed `CLI_RUNNER_SHARED_TOKEN` on both services.
6. Verify `api -> infra-cli-runner` over private networking.

### Local Development Wiring

`docker-compose.local.yml` should run `infra-cli-runner` next to DynamoDB Local and expose it on `${LOCAL_CLI_RUNNER_PORT:-8002}`. The local API normally runs on the host, so `.envrc` and `scripts/deploy_local.sh` should set:

```text
CLI_RUNNER_BASE_URL=http://localhost:${LOCAL_CLI_RUNNER_PORT}
CLI_RUNNER_SHARED_TOKEN=${LOCAL_CLI_RUNNER_SHARED_TOKEN}
CLI_RUNNER_TIMEOUT_SECONDS=30
```

If the API is later moved into the same Compose network, its internal URL should be `http://infra-cli-runner:8080` instead of the host-mapped URL.

### Phase 3: Output Paging And Runtime Policy Hardening

1. Persist large command outputs with TTL.
2. Add `read_output_page`.
3. Validate editable policy YAML at install/update time.
4. Revalidate persisted policy on every action call.
5. Add least-privilege IAM policy examples for S3 and DynamoDB read-only access.

### Phase 4: Expand Carefully

Add providers one at a time:

- Railway CLI for controlled project/service introspection.
- GitHub CLI only if GitHub connector credentials are available and scoped.
- Terraform CLI only for plan/read workflows first; `apply` should need a stronger approval and state-lock design.
- kubectl only with very strict namespace and verb policy.

## Testing Strategy

API tests:

- Manifest loads and action schema is exposed.
- Valid read-only AWS command is accepted.
- Shell syntax is rejected.
- Unknown AWS service/subcommand is rejected.
- Mutating AWS command is rejected unless explicitly allowed.
- Skill install config encrypts AWS credential seeds.
- Skill mints STS temporary credentials before calling the runner.
- Runner receives temporary STS credentials, not long-lived installed keys.
- Editable policy YAML is validated at install/update and execution time.
- Secret values are redacted from logs/errors.
- `read_output_page` returns stable pages and refuses output owned by another user/agent.
- Runner non-zero exit maps to `RuntimeError`.
- Runner timeout maps to bounded user-safe error.
- Parsed JSON stdout returns structured JSON.

Runner tests:

- Missing/invalid auth returns `401`.
- Unknown tool returns `400`.
- Command timeout kills process.
- Output truncation works.
- Environment allowlist strips unexpected env vars.
- No shell interpolation occurs.

Integration smoke tests:

- `aws sts get-caller-identity`
- `aws s3api list-buckets`
- `aws dynamodb list-tables`

## Main Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Arbitrary command execution | Credential or infrastructure compromise | No shell strings, allowlisted argv prefixes, private runner, auth, audit |
| Over-broad AWS credentials | Agent can access too much | Use least-privilege IAM, persisted editable policy, resource allowlists, STS session credentials |
| CLI output too large | Memory/cost/user experience issues | Byte caps, pagination constraints, truncation metadata |
| Long-running commands interrupted | Failed agent/automation work | Use existing async jobs first, add durable worker/queue later |
| CLI version drift | Behavior changes unexpectedly | Pin versions and update through scheduled rebuilds/tests |
| Maintenance moves from wrappers to policy | Policy can become complex | Start with few read-only command families; add patterns only after real use |
| Automation misuse | Saved workflow mutates resources repeatedly | Read-only automation v1; require explicit mutation action and audit |

## Alternatives Considered

### Continue Writing Native SDK Wrappers

Pros:

- Stronger typing.
- Easier domain-specific UX.
- Better control over pagination and response shape.

Cons:

- Higher maintenance for broad provider surfaces.
- Every new operation requires code.
- Duplicates behavior already implemented by official CLIs.

Use this for polished, high-volume product workflows. Use CLI executor for low-frequency infrastructure operations and broad admin surfaces.

### Run CLIs Inside The Main API Container

Pros:

- Fewer services.
- Simpler local development.

Cons:

- Larger API image.
- More package/dependency churn in the main service.
- CLI execution shares process/container blast radius with customer API traffic.

Not recommended beyond a quick local spike.

### Expose A Generic Shell Skill

Pros:

- Maximum flexibility.

Cons:

- Too risky for production.
- Hard to audit and validate.
- Encourages command strings, pipes, redirection, and filesystem side effects.

Not recommended.

## Recommended V1 Scope

Build a read-only AWS CLI executor first:

- `aws sts get-caller-identity`
- `aws s3api list-buckets`
- `aws s3api list-objects-v2`
- `aws s3api head-object`
- `aws dynamodb list-tables`
- `aws dynamodb describe-table`
- `aws dynamodb query`
- `aws dynamodb get-item`

Keep write commands out of v1. This gives enough value to validate the architecture without opening the highest-risk path. The runtime permission prompt for mutating skill actions should be a separate platform feature after the read-only executor is stable.

## Open Questions

- Should v1 use `GetSessionToken` only, or should install support optional `role_arn` and `AssumeRole` immediately?
- Should editable policy YAML be stored only in installed skill config, or should automations eventually get their own override policy?
- What TTL should large command output pages use?
- Which storage backend should hold large command output: DynamoDB for small pages, S3 for larger artifacts, or both?
- Which future action metadata shape should express "requires explicit user permission" for mutating skill actions?

## Conclusion

This is a good idea if framed as a constrained CLI broker, not a shell proxy. It should reduce wrapper maintenance for infrastructure-style skills while fitting the current manifest/action/runtime model. The essential design work is security and policy, not process execution. Start narrow with read-only AWS CLI commands, deploy `infra-cli-runner` privately on Railway, mint temporary STS credentials inside the API for every call, validate against the persisted install-time policy, and expand only after paging, credential scoping, and the future mutation-permission feature are proven.
