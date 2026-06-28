import os
import logging
from contextlib import asynccontextmanager
from decimal import Decimal

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum

from src.auth import auth_router, middleware
from src.rate_limits.middleware import RateLimitMiddleware
from src.agents.router import router as agent_router
from src.apikeys.router import router as apikeys_router
from src.conversations.router import router as conversation_router
from src.settings.router import router as settings_router
from src.memory.router import router as memory_router
from src.llm.router import router as llm_router
from src.knowledge.router import router as knowledge_router, agent_kb_router, sse_router as knowledge_sse_router
from src.payments.stripe.router import router as stripe_payments_router
from src.users import users_router
from src.widget import widget_router, WidgetAuthMiddleware
from src.contact.router import router as contact_router
from src.connectors.router import router as connectors_router
from src.connectors.mcp.router import public_router as mcp_connectors_public_router
from src.connectors.mcp.router import router as mcp_connectors_router
from src.skills import skills_router
from src.skills.api_registry import build_skill_api_routers
from src.skills.registry import get_skill_registry
from src.analytics import analytics_router
from src.automations.router import router as automations_router
from src.downloads import router as downloads_router
from src.artifacts import artifacts_router
from src.scheduler.router import router as scheduler_router
from src.smart_suggestions.router import router as smart_suggestions_router
from src.scheduler.runtime import get_scheduler_runtime
from src.exceptions import register_exception_handlers
from src.middleware.request_id import RequestIdMiddleware
from src.runtime.env import is_lambda
from src.logging_config import configure_cloudwatch_logging
from src.logging.config import configure_logging
from src.config import settings


# Custom JSON encoder for DynamoDB Decimal types
def decimal_default(obj):
    """Convert Decimal to int or float for JSON serialization."""
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    raise TypeError

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Configure logging once at import time (Lambda cold start / local startup)
if is_lambda():
    configure_cloudwatch_logging(LOG_LEVEL)
else:
    configure_logging()
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("boto3").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

# Override JSONResponse to handle Decimal serialization from DynamoDB
import json as stdlib_json
from starlette.responses import JSONResponse as StarletteJSONResponse

original_render = StarletteJSONResponse.render

def patched_render(self, content):
    return stdlib_json.dumps(
        content,
        ensure_ascii=False,
        allow_nan=False,
        indent=None,
        separators=(",", ":"),
        default=decimal_default,
    ).encode("utf-8")

    setattr(StarletteJSONResponse, "render", patched_render)


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    await get_scheduler_runtime().start()
    try:
        yield
    finally:
        await get_scheduler_runtime().stop()


def create_app() -> FastAPI:
    """Create the FastAPI app.

    Waterfall design goal:
    - validate core config once
    - configure middleware in a single block
    - register routers
    """

    # Fail-fast if core runtime config is missing.
    settings.validate_core()

    app = FastAPI(
        title="Dynamic Agent Builder API",
        description="API for building dynamic agents with long-term memory",
        version="0.1.0",
        lifespan=app_lifespan,
    )

    register_exception_handlers(app)

    # Middleware order matters! Last added = first to run.
    # Order of execution: CORSMiddleware -> RequestId -> WidgetAuth -> Auth -> RateLimit -> Route

    # Rate limit middleware - runs after auth (added first)
    app.add_middleware(RateLimitMiddleware)

    # Dashboard auth middleware (JWT validation) - added first, runs last
    app.add_middleware(middleware.AuthMiddleware)

    # Widget auth middleware (API key validation) - runs second
    app.add_middleware(WidgetAuthMiddleware)

    # Request id middleware - runs early so request_id is available in downstream logs
    app.add_middleware(RequestIdMiddleware)

    # CORS middleware - added last, runs FIRST (must handle OPTIONS preflight before auth)
    # Note: Widget endpoints allow any origin (validated by WidgetAuthMiddleware against API key's allowed_origins)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )

    app.include_router(auth_router)
    app.include_router(router=agent_router)
    app.include_router(router=apikeys_router)
    app.include_router(router=conversation_router)
    app.include_router(router=settings_router)
    app.include_router(router=memory_router)
    app.include_router(router=llm_router)
    app.include_router(router=knowledge_sse_router)
    app.include_router(router=knowledge_router)
    app.include_router(router=agent_kb_router)
    app.include_router(router=widget_router)
    app.include_router(router=stripe_payments_router)
    app.include_router(router=users_router)
    app.include_router(router=contact_router)
    app.include_router(router=connectors_router)
    app.include_router(router=mcp_connectors_public_router)
    app.include_router(router=mcp_connectors_router)
    app.include_router(router=skills_router)
    app.include_router(router=automations_router)
    app.include_router(router=downloads_router)
    app.include_router(router=artifacts_router)
    app.include_router(router=scheduler_router)
    app.include_router(router=smart_suggestions_router)

    # Skill-owned API routers (optional, mounted under /skills/{skill_id}/...)
    # If a skill folder (and its manifest) is removed, it simply won't be loaded.
    try:
        loaded_skills = get_skill_registry().list()
        for prefix, router in build_skill_api_routers(loaded_skills):
            app.include_router(router, prefix=prefix, tags=["skills"])
    except Exception as e:
        log.warning("Failed to mount skill API routers: %s", e)
    app.include_router(router=analytics_router)

    @app.get("/health")
    def health_check():
        return {"status": "healthy"}

    @app.get("/")
    def root():
        return {"message": "Dynamic Agent Builder API"}

    return app


app = create_app()


@app.get("/health")
def health_check():
    return {"status": "healthy"}


@app.get("/")
def root():
    return {"message": "Dynamic Agent Builder API"}


# Mangum handler for HTTP API requests
_http_handler = Mangum(app, lifespan="off")

log = logging.getLogger(__name__)


def handler(event, context):
    """
    Lambda handler that routes between HTTP requests and async jobs.

    For async crawl job invocations, the event looks like:
    {
        "crawl_job": {
            "job_id": "...",
            "kb_id": "...",
            "user_email": "..."
        }
    }

    For async automation run invocations, the event looks like:
    {
        "automation_run": {
            "run_id": "...",
            "automation_id": "...",
            "user_email": "..."
        }
    }

    For HTTP requests (via API Gateway), the event is passed to Mangum.
    """
    if "crawl_job" in event:
        return _handle_crawl_job(event["crawl_job"], context)
    if "automation_run" in event:
        return _handle_automation_run(event["automation_run"], context)

    return _http_handler(event, context)


def _handle_crawl_job(crawl_job: dict, context):
    """
    Handle async crawl job invocation.

    Runs the crawler synchronously since Lambda async invocations
    can run for up to 15 minutes.
    """
    import asyncio

    job_id = crawl_job.get("job_id")
    kb_id = crawl_job.get("kb_id")
    user_email = crawl_job.get("user_email")

    if (
        not isinstance(job_id, str)
        or not isinstance(kb_id, str)
        or not isinstance(user_email, str)
        or not job_id
        or not kb_id
        or not user_email
    ):
        log.error(f"Invalid crawl_job payload: {crawl_job}")
        return {"statusCode": 400, "body": "Invalid crawl_job payload"}

    log.info(f"Processing async crawl job {job_id} for KB {kb_id}")

    try:
        from src.crawler.worker import get_crawler_worker
        crawler = get_crawler_worker()

        # Calculate timeout based on Lambda remaining time
        # Leave 30 seconds buffer for cleanup
        remaining_ms = context.get_remaining_time_in_millis() - 30000
        timeout_ms = max(remaining_ms, 60000)  # At least 60 seconds

        # Run crawler synchronously
        asyncio.run(crawler.run(
            job_id=job_id,
            kb_id=kb_id,
            user_email=user_email,
            timeout_ms=timeout_ms,
        ))

        log.info(f"Completed crawl job {job_id}")
        return {"statusCode": 200, "body": f"Crawl job {job_id} completed"}

    except Exception as e:
        log.error(f"Crawl job {job_id} failed: {e}")
        return {"statusCode": 500, "body": f"Crawl job {job_id} failed: {str(e)}"}


def _handle_automation_run(automation_run: dict, context):  # noqa: ARG001
    """Handle async automation run invocation."""
    import asyncio

    run_id = automation_run.get("run_id")
    user_email = automation_run.get("user_email")

    if not isinstance(run_id, str) or not isinstance(user_email, str) or not run_id or not user_email:
        log.error("Invalid automation_run payload: %s", automation_run)
        return {"statusCode": 400, "body": "Invalid automation_run payload"}

    log.info("Processing async automation run %s", run_id)

    try:
        from src.automations.runner import AutomationRunner

        run = asyncio.run(AutomationRunner().execute_run(run_id, user_email))

        log.info("Completed automation run %s with status %s", run_id, run.status.value)
        return {
            "statusCode": 200,
            "body": f"Automation run {run_id} completed with status {run.status.value}",
        }
    except Exception as e:
        log.error("Automation run %s failed: %s", run_id, e)
        return {"statusCode": 500, "body": f"Automation run {run_id} failed: {str(e)}"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
