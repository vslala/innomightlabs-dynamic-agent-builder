# LLD: Move HTTP API to Railway While Keeping AWS Services

Date: 2026-05-24

## Goal

Move the public FastAPI HTTP API from AWS Lambda + API Gateway to Railway, while keeping the existing AWS architecture for DynamoDB, Cognito, S3 buckets, Bedrock, SES/Mailjet-related configuration, CloudFront widget hosting, DynamoDB stream processing, and any remaining Lambda background handlers.

The recommended migration is a phased cutover:

1. Run the public HTTP API as a Railway web service.
2. Keep AWS resources managed by Terraform.
3. Keep Lambda only for non-HTTP background/event work until a separate worker architecture is introduced.
4. Point the existing API custom domain to Railway after validation.

## Current State

The backend is currently Lambda-first:

- [api/Dockerfile](../Dockerfile) uses `public.ecr.aws/lambda/python:3.13` and ends with `CMD ["main.handler"]`.
- [api/main.py](../main.py) creates a normal FastAPI `app`, but also creates a Mangum `_http_handler` and a Lambda `handler(event, context)`.
- [terraform/lambda.tf](../../terraform/lambda.tf) deploys `aws_lambda_function.api` from the ECR image and injects the API runtime environment.
- [terraform/api_gateway.tf](../../terraform/api_gateway.tf) exposes that Lambda through API Gateway and optionally an API Gateway custom domain.
- [terraform/dynamodb.tf](../../terraform/dynamodb.tf), [terraform/artifacts.tf](../../terraform/artifacts.tf), and [terraform/conversation_media.tf](../../terraform/conversation_media.tf) grant the Lambda role access to DynamoDB and S3.
- [terraform/lambda.tf](../../terraform/lambda.tf) also deploys `aws_lambda_function.usage_events` for DynamoDB stream usage accounting.

The FastAPI app itself is portable because `main.py` exposes `app = create_app()`, but the container and some runtime behavior are not portable yet.

## Railway Constraints That Matter

Railway web services are long-running processes, so the API must run `uvicorn main:app` rather than a Lambda handler. Railway injects a `PORT` variable and public services must listen on `0.0.0.0:$PORT` for routing and health checks.

Relevant Railway docs:

- Railway public networking requires listening on `0.0.0.0:$PORT`: <https://docs.railway.com/deploy/exposing-your-app>
- Railway can use a custom Dockerfile path through `RAILWAY_DOCKERFILE_PATH`: <https://docs.railway.com/builds/dockerfiles>
- Railway config-as-code supports `railway.toml`: <https://docs.railway.com/config-as-code>
- Railway health checks can target `/health`: <https://docs.railway.com/reference/healthchecks>
- Railway monorepo services should set root directory/watch paths: <https://docs.railway.com/guides/monorepo>
- Railway variables are runtime/build environment variables: <https://docs.railway.com/variables>
- Static outbound IPs are optional and Pro-plan gated; AWS SDK calls do not require them unless AWS resource policies are IP-restricted: <https://docs.railway.com/reference/static-outbound-ips>

## Key Finding

The basic HTTP API migration is small, but the Lambda-specific async paths are the main required design change.

Today these paths depend on `AWS_LAMBDA_FUNCTION_NAME` and self-invocation:

- Crawl jobs: [api/src/knowledge/router.py](../src/knowledge/router.py) calls `_invoke_crawl_async()` only when `is_lambda()` is true; otherwise it uses FastAPI `BackgroundTasks`.
- Crawl continuation: [api/src/crawler/worker.py](../src/crawler/worker.py) self-invokes the current Lambda for checkpoint continuation.
- Automation runs: [api/src/automations/router.py](../src/automations/router.py) invokes the current Lambda when in Lambda, otherwise starts an in-process task.
- Account deletion: [api/src/users/router.py](../src/users/router.py) invokes a separate `"{environment}-account-deletion-handler"` Lambda.

In Railway, `is_lambda()` will be false. That means crawl jobs and automation runs would run in-process as background work. This may work for short jobs, but it is not a production-equivalent replacement for Lambda async execution because Railway deploys/restarts can interrupt the web process.

## Recommended Target Architecture

### Railway

- One Railway service named `api`.
- Source root: `/api`.
- Build using a Railway-specific Dockerfile, not the existing Lambda Dockerfile.
- Start command inside the image: `uv run uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}`.
- Health check path: `/health`.
- Public custom domain: keep the current API domain, but repoint DNS from API Gateway to Railway during cutover.

### AWS Kept

- DynamoDB table and stream.
- `usage_events` Lambda and event source mapping.
- S3 artifacts bucket.
- S3 conversation media bucket.
- Cognito user pool and hosted UI.
- SES identity if still needed.
- CloudFront/S3 widget CDN.
- Optional: a renamed/re-scoped background worker Lambda that continues to process crawl and automation jobs.

### AWS Removed or Disabled After Cutover

- API Gateway public API and API Gateway custom domain mapping can be removed after Railway is live and verified.
- `aws_lambda_function.api` should not be deleted immediately if it is reused as the async worker. Rename it later to avoid confusion.
- ECR can remain as long as AWS Lambda workers still use the shared Lambda image.

## Required Code Changes

### 1. Add a Railway Runtime Dockerfile

Do not replace [api/Dockerfile](../Dockerfile) in the first migration because AWS Lambda still needs it. Add `api/Dockerfile.railway`:

```dockerfile
FROM python:3.13-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY main.py ./
COPY src ./src
COPY lambdas ./lambdas
COPY assets ./assets

ENV PYTHONPATH="/app/.venv/lib/python3.13/site-packages:/app"
ENV PYTHONUNBUFFERED=1

CMD ["sh", "-c", "uv run uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
```

Railway configuration options:

- Set `RAILWAY_DOCKERFILE_PATH=api/Dockerfile.railway` if the service root is repository root.
- Prefer setting Railway root directory to `/api`, then set `RAILWAY_DOCKERFILE_PATH=Dockerfile.railway`.

### 2. Add Railway Config as Code

Add `api/railway.toml`:

```toml
[build]
dockerfilePath = "Dockerfile.railway"

[deploy]
healthcheckPath = "/health"
healthcheckTimeout = 300
restartPolicyType = "ON_FAILURE"
```

If Railway does not infer the file because the service root is not `/api`, configure the Railway service to use `/api/railway.toml` as the config file path.

### 3. Introduce Explicit Async Worker Configuration

Replace “am I Lambda?” as the routing condition for production async work. Add settings:

```python
async_job_backend: str = "local"
async_job_lambda_name: str = ""
account_deletion_lambda_name: str = ""
```

Load from:

```python
ASYNC_JOB_BACKEND=local|lambda
ASYNC_JOB_LAMBDA_NAME=dynamic-agent-builder-api
ACCOUNT_DELETION_LAMBDA_NAME=prod-account-deletion-handler
```

Then update:

- [api/src/knowledge/router.py](../src/knowledge/router.py): if `ASYNC_JOB_BACKEND=lambda`, invoke `ASYNC_JOB_LAMBDA_NAME`; otherwise use `BackgroundTasks`.
- [api/src/automations/router.py](../src/automations/router.py): same pattern.
- [api/src/crawler/worker.py](../src/crawler/worker.py): continuation should use `ASYNC_JOB_LAMBDA_NAME`, not `AWS_LAMBDA_FUNCTION_NAME`.
- [api/src/users/router.py](../src/users/router.py): use `ACCOUNT_DELETION_LAMBDA_NAME` instead of constructing `"{environment}-account-deletion-handler"`.

This keeps Railway as the public web tier while allowing AWS Lambda to remain the job executor.

### 4. Keep Lambda Handler Compatibility

Do not remove Mangum or `handler()` from [api/main.py](../main.py) during phase 1. The same codebase can continue to support AWS worker invocation payloads:

```python
if "crawl_job" in event:
    return _handle_crawl_job(event["crawl_job"], context)
if "automation_run" in event:
    return _handle_automation_run(event["automation_run"], context)
```

The Railway container will ignore the Lambda handler and run `main:app`.

### 5. Add Tests for Backend Selection

Add focused tests that verify:

- `ASYNC_JOB_BACKEND=lambda` invokes Lambda for crawl jobs.
- `ASYNC_JOB_BACKEND=local` uses background tasks.
- Automation run dispatch follows the same backend selection.
- Account deletion uses `ACCOUNT_DELETION_LAMBDA_NAME`.

Existing tests use pytest and moto patterns; keep these tests small and mock `boto3.client`.

## Railway Environment Variables

Railway must receive almost all variables currently injected in `terraform/lambda.tf`, plus AWS static credentials for the new IAM user.

Required core:

```bash
ENVIRONMENT=prod
DYNAMODB_TABLE=<terraform output dynamodb_table_name>
AWS_REGION_NAME=<terraform aws_region>
AWS_DEFAULT_REGION=<same as AWS_REGION_NAME>
FRONTEND_URL=<current frontend URL>
API_BASE_URL=https://<api-domain-on-railway>
JWT_SECRET=<existing secret>
LOG_LEVEL=INFO
```

AWS credentials for the Railway IAM user:

```bash
AWS_ACCESS_KEY_ID=<new access key>
AWS_SECRET_ACCESS_KEY=<new secret key>
```

OAuth/auth:

```bash
GOOGLE_CLIENT_ID=<existing>
GOOGLE_CLIENT_SECRET=<existing>
GOOGLE_DRIVE_REDIRECT_URI=https://<api-domain>/auth/google-drive/callback
GOOGLE_MAIL_REDIRECT_URI=https://<api-domain>/auth/google-mail/callback
OPENAI_OAUTH_CLIENT_ID=<existing>
OPENAI_OAUTH_SCOPES=<existing>
OPENAI_OAUTH_REDIRECT_URI=https://<api-domain>/auth/openai
OPENAI_OAUTH_RESPONSES_URL=<existing>
COGNITO_DOMAIN=<terraform output cognito_domain_url>
COGNITO_CLIENT_ID=<terraform output cognito_user_pool_client_id>
COGNITO_CLIENT_SECRET=<terraform output cognito_user_pool_client_secret>
COGNITO_REDIRECT_URI=https://<api-domain>/auth/callback/cognito
```

Vector/model/storage:

```bash
PINECONE_API_KEY=<existing>
PINECONE_HOST=<existing>
PINECONE_INDEX=<existing>
BEDROCK_EMBEDDING_MODEL=amazon.titan-embed-text-v2:0
BEDROCK_EMBEDDING_DIMENSION=1024
DOWNLOADS_ARTIFACTS_BUCKET=<terraform output artifacts_s3_bucket>
DOWNLOADS_ARTIFACTS_REGION=us-east-1
DOWNLOADS_MANIFEST_KEY=artifacts/plugins/manifest.json
CONVERSATION_MEDIA_BUCKET=<terraform output conversation_media_s3_bucket>
CONVERSATION_MEDIA_PRESIGN_TTL_SECONDS=900
```

Billing/email:

```bash
STRIPE_SECRET_KEY=<existing>
STRIPE_PUBLISHABLE_KEY=<existing>
STRIPE_WEBHOOK_SECRET=<new or existing webhook secret for Railway endpoint>
MAILJET_API_KEY=<existing>
MAILJET_SECRET_KEY=<existing>
SUPERUSER_EMAILS=<existing>
```

Async worker:

```bash
ASYNC_JOB_BACKEND=lambda
ASYNC_JOB_LAMBDA_NAME=dynamic-agent-builder-api
ACCOUNT_DELETION_LAMBDA_NAME=prod-account-deletion-handler
```

The exact Lambda names should be confirmed from AWS before setting them. Terraform currently outputs `lambda_function_name` for the API Lambda, but it does not manage an account deletion Lambda in the checked files.

## IAM User Policy for Railway

The new Railway AWS user should not be an admin. It needs the same data-plane permissions that the public API uses, plus Lambda invoke permission for retained workers.

Minimum policy shape:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "dynamodb:DeleteItem",
        "dynamodb:Query",
        "dynamodb:Scan",
        "dynamodb:BatchGetItem",
        "dynamodb:BatchWriteItem"
      ],
      "Resource": [
        "arn:aws:dynamodb:<region>:<account-id>:table/<table-name>",
        "arn:aws:dynamodb:<region>:<account-id>:table/<table-name>/index/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": ["s3:ListBucket"],
      "Resource": [
        "arn:aws:s3:::<downloads-bucket>",
        "arn:aws:s3:::<conversation-media-bucket>"
      ]
    },
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject"],
      "Resource": "arn:aws:s3:::<downloads-bucket>/artifacts/plugins/*"
    },
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
      "Resource": "arn:aws:s3:::<conversation-media-bucket>/agents/*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "bedrock:ListFoundationModels",
        "bedrock:GetFoundationModel",
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": ["lambda:InvokeFunction"],
      "Resource": [
        "arn:aws:lambda:<region>:<account-id>:function:dynamic-agent-builder-api",
        "arn:aws:lambda:<region>:<account-id>:function:prod-account-deletion-handler"
      ]
    }
  ]
}
```

Do not grant DynamoDB stream read permissions to the Railway user unless the stream processor is also moved to Railway. `usage_events` can keep its existing Lambda role.

## Terraform Changes

Phase 1 should avoid destructive infrastructure changes:

- Keep [terraform/lambda.tf](../../terraform/lambda.tf) and [terraform/docker_build.tf](../../terraform/docker_build.tf) for worker Lambda image deployment.
- Keep [terraform/api_gateway.tf](../../terraform/api_gateway.tf) until Railway is verified.
- Add outputs that make Railway variable setup easier:
  - table name already exists as `dynamodb_table_name`
  - artifacts bucket already exists as `artifacts_s3_bucket`
  - conversation media bucket already exists as `conversation_media_s3_bucket`
  - Cognito outputs already exist
  - add worker Lambda output if the async worker is renamed
- Optionally add Terraform-managed `aws_iam_user`, `aws_iam_access_key`, and `aws_iam_user_policy` for Railway. If access keys are generated manually, document rotation outside Terraform.

Phase 2 cleanup after Railway has handled production traffic:

- Remove API Gateway custom domain mapping.
- Remove API Gateway routes/integration if no longer used.
- Rename `aws_lambda_function.api` to a dedicated worker resource, or split worker code from HTTP API entirely.
- Remove ECR only if no Lambda worker uses container images.

## External Service Cutover Checklist

Before DNS cutover:

1. Railway service deploys and `/health` returns `200`.
2. `railway logs` shows the app loaded settings without `ConfigValidationError`.
3. DynamoDB CRUD smoke tests pass through Railway.
4. S3 presigned downloads and generated media upload/read paths work.
5. Bedrock model listing and embedding generation work.
6. Crawl job creation invokes the AWS worker Lambda and updates job status.
7. Automation run creation invokes the AWS worker Lambda and updates run status.
8. Stripe checkout session creation works.
9. Stripe webhook endpoint is changed or duplicated to `https://<api-domain>/payments/stripe/webhook`.
10. Google OAuth redirect URIs include the Railway API domain.
11. Google Drive and Google Mail OAuth redirect URIs include the Railway API domain.
12. OpenAI OAuth redirect URI includes the Railway API domain.
13. Cognito callback/logout URLs include the Railway API/frontend domains.
14. SPA `VITE_API_BASE_URL` points to the final API domain.
15. WordPress and VS Code plugin API base URLs are checked if they hardcode the API domain.

Cutover:

1. Add Railway custom domain for the API.
2. Update DNS CNAME from the API Gateway target to the Railway target.
3. Keep API Gateway/Lambda deployed for rollback until traffic and webhooks are stable.
4. Rotate or remove old webhook secrets only after Stripe confirms delivery to Railway.

## Risks and Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Existing Lambda Dockerfile is used by Railway | Service boots as a Lambda image and does not serve HTTP | Use `Dockerfile.railway` and set `RAILWAY_DOCKERFILE_PATH` |
| API does not bind to Railway `PORT` | Railway health check/routing fails | Start uvicorn on `0.0.0.0:${PORT}` |
| Background jobs silently run inside Railway web process | Long jobs can be interrupted by deploy/restart | Use `ASYNC_JOB_BACKEND=lambda` for production |
| Railway IAM user over-permissioned | Larger blast radius if key leaks | Use resource-scoped IAM policy and rotate keys |
| OAuth callbacks still point at API Gateway | Login/connect flows fail after cutover | Update Google, OpenAI, Cognito redirect URLs before DNS switch |
| Stripe sends events to old endpoint | Subscription state becomes stale | Add Railway webhook endpoint and verify event delivery |
| API Gateway removed too early | No fast rollback | Keep API Gateway/Lambda until Railway has passed production smoke tests |

## Implementation Order

1. Add `Dockerfile.railway` and `railway.toml`.
2. Add explicit async worker settings and tests.
3. Configure Railway variables with existing Terraform outputs and the new IAM user credentials.
4. Deploy Railway service with temporary Railway domain.
5. Smoke-test API, AWS access, OAuth callback URLs, Stripe webhook, S3, Bedrock, crawl jobs, and automation runs.
6. Add final custom domain to Railway and update DNS.
7. Keep AWS API Gateway available for rollback.
8. Clean up API Gateway only after stable production operation.

## Open Questions

- What is the actual production API domain to preserve during cutover: `api.innomightlabs.com`, `api.innomight.com`, or another value from `terraform.tfvars`?
- Is `prod-account-deletion-handler` deployed outside this Terraform project? The code invokes it, but the checked Terraform does not define it.
- Should long-running crawl and automation jobs remain Lambda-based long term, or should a Railway worker/queue be introduced later?
- Should the Railway IAM user and access key be Terraform-managed, or generated manually as planned?
