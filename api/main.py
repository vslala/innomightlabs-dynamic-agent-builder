import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum

from src.auth import auth_router, middleware
from src.agents.router import router as agent_router
from src.apikeys.router import router as apikeys_router
from src.conversations.router import router as conversation_router
from src.settings.router import router as settings_router
from src.memory.router import router as memory_router
from src.llm.router import router as llm_router
from src.knowledge.router import router as knowledge_router, agent_kb_router, sse_router as knowledge_sse_router
from src.payments.stripe.router import router as stripe_payments_router
from src.widget import widget_router, WidgetAuthMiddleware
from src.exceptions import register_exception_handlers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logging.getLogger("botocore").setLevel(logging.WARNING)
logging.getLogger("boto3").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

app = FastAPI(
    title="Dynamic Agent Builder API",
    description="API for building dynamic agents with long-term memory",
    version="0.1.0",
)

# Register global exception handlers
register_exception_handlers(app)

# Dashboard origins (with credentials)
dashboard_origins = [
    "http://localhost:5173",
    "https://vslala.github.io",
]

# Middleware order matters! Last added = first to run.
# Order of execution: CORSMiddleware -> WidgetAuthMiddleware -> AuthMiddleware -> Route

# Dashboard auth middleware (JWT validation) - added first, runs last
app.add_middleware(middleware.AuthMiddleware)

# Widget auth middleware (API key validation) - runs second
app.add_middleware(WidgetAuthMiddleware)

# CORS middleware - added last, runs FIRST (must handle OPTIONS preflight before auth)
# Note: Widget endpoints allow any origin (validated by WidgetAuthMiddleware against API key's allowed_origins)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins; widget validates via API key, dashboard via auth
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
    Lambda handler that routes between HTTP requests and async crawl jobs.

    For async crawl job invocations, the event looks like:
    {
        "crawl_job": {
            "job_id": "...",
            "kb_id": "...",
            "user_email": "..."
        }
    }

    For HTTP requests (via API Gateway), the event is passed to Mangum.
    """
    # Check if this is an async crawl job invocation
    if "crawl_job" in event:
        return _handle_crawl_job(event["crawl_job"], context)

    # Otherwise, handle as HTTP request
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

    if not all([job_id, kb_id, user_email]):
        log.error(f"Invalid crawl_job payload: {crawl_job}")
        return {"statusCode": 400, "body": "Invalid crawl_job payload"}

    log.info(f"Processing async crawl job {job_id} for KB {kb_id}")

    try:
        from src.crawler import get_crawler_worker
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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
