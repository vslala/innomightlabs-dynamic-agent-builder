import json
import logging
import re
from typing import Optional

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from .service import RateLimitService
from ..knowledge.repository import CrawlJobRepository
from ..agents.repository import AgentRepository

log = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app) -> None:
        super().__init__(app)
        self.rate_limits = RateLimitService()
        self.crawl_job_repo = CrawlJobRepository()
        self.agent_repo = AgentRepository()

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        user_email = getattr(request.state, "user_email", None)
        if not user_email:
            return await call_next(request)

        try:
            if request.method == "POST" and request.url.path == "/agents":
                agent_name = await self._extract_agent_name(request)
                if agent_name:
                    existing = self.agent_repo.find_by_name(agent_name, user_email)
                    if existing:
                        return await call_next(request)
                self.rate_limits.check_agent_limit(user_email)

            if request.method == "POST" and self._is_send_message(request.url.path):
                self.rate_limits.check_message_limit(user_email)

            if request.method == "POST" and self._is_start_crawl_job(request.url.path):
                auto_start = request.query_params.get("auto_start", "true").lower() != "false"
                if auto_start:
                    requested_pages = await self._extract_max_pages(request)
                    self.rate_limits.check_kb_pages_limit(user_email, requested_pages)

            if request.method == "POST" and self._is_run_crawl_job(request.url.path):
                kb_id, job_id = self._parse_crawl_job_path(request.url.path)
                if kb_id and job_id:
                    job = self.crawl_job_repo.find_by_id(job_id, kb_id)
                    if job:
                        self.rate_limits.check_kb_pages_limit(user_email, job.config.max_pages)
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

        return await call_next(request)

    @staticmethod
    def _is_send_message(path: str) -> bool:
        return re.match(r"^/agents/[^/]+/[^/]+/send-message$", path) is not None

    @staticmethod
    def _is_start_crawl_job(path: str) -> bool:
        return re.match(r"^/knowledge-bases/[^/]+/crawl-jobs$", path) is not None

    @staticmethod
    def _is_run_crawl_job(path: str) -> bool:
        return re.match(r"^/knowledge-bases/[^/]+/crawl-jobs/[^/]+/(run|run-stream)$", path) is not None

    @staticmethod
    def _parse_crawl_job_path(path: str) -> tuple[Optional[str], Optional[str]]:
        match = re.match(r"^/knowledge-bases/([^/]+)/crawl-jobs/([^/]+)/(run|run-stream)$", path)
        if not match:
            return None, None
        return match.group(1), match.group(2)

    @staticmethod
    async def _extract_max_pages(request: Request) -> int:
        default_max = 100
        try:
            try:
                payload = await request.json()
            except json.JSONDecodeError as exc:
                log.warning("Invalid JSON payload while extracting max_pages: %s", exc)
                raise HTTPException(
                    status_code=400,
                    detail={"message": "Invalid JSON payload."},
                ) from exc
            if payload:
                max_pages = payload.get("max_pages")
                if isinstance(max_pages, int):
                    return max_pages
        except HTTPException:
            raise
        except Exception:
            log.warning("Failed to extract max_pages from request body; using default.")
            return default_max
        return default_max

    @staticmethod
    async def _extract_agent_name(request: Request) -> Optional[str]:
        try:
            try:
                payload = await request.json()
            except json.JSONDecodeError as exc:
                log.warning("Invalid JSON payload while extracting agent_name: %s", exc)
                raise HTTPException(
                    status_code=400,
                    detail={"message": "Invalid JSON payload."},
                ) from exc
            if payload:
                agent_name = payload.get("agent_name")
                if isinstance(agent_name, str) and agent_name.strip():
                    return agent_name.strip()
        except HTTPException:
            raise
        except Exception:
            log.warning("Failed to extract agent_name from request body.")
            return None
        return None
