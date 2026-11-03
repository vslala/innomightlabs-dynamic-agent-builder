"""Plan limits on the routes that spend them.

Each `QuotaRule` names a route, the quota it spends and how much one request asks for. `rule_for` is the only
selector; the middleware bills the owner of the account the request acts in and lets `RateLimitService.check`
decide. To limit another route, add a rule to `QUOTA_RULES`.
"""

import logging
import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

from fastapi import HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from ..agents.repository import AgentRepository
from ..iam.dependencies import get_principal
from ..iam.principal import Principal
from ..iam.service import IamError
from ..knowledge.repository import CrawlJobRepository
from .billing import account_billing_email
from .quotas import AGENTS, KB_PAGES, MESSAGES, Quota
from .service import RateLimitService

log = logging.getLogger(__name__)

#: Pages a crawl asks for when its request doesn't say (the crawl job's own default)
DEFAULT_CRAWL_PAGES = 100


@dataclass(frozen=True)
class QuotaRequest:
    request: Request
    path: re.Match[str]
    principal: Principal


@dataclass(frozen=True)
class QuotaRule:
    method: str
    path: re.Pattern[str]
    quota: Quota
    #: How much of the quota the request asks for; None when it spends nothing
    requested: Callable[[QuotaRequest], Awaitable[Optional[int]]]


async def _new_agent(ask: QuotaRequest) -> Optional[int]:
    name = (await _json_body(ask.request)).get("agent_name")
    if not isinstance(name, str) or not name.strip():
        return 1  # the route rejects it; counting it is harmless
    # Re-creating an agent by name returns the existing one, so it isn't counted again
    existing = AgentRepository().find_by_name(ask.principal.account_id, ask.principal.user_id, name.strip())
    return None if existing else 1


async def _one_message(_ask: QuotaRequest) -> Optional[int]:
    return 1


async def _crawl_started(ask: QuotaRequest) -> Optional[int]:
    if ask.request.query_params.get("auto_start", "true").lower() == "false":
        return None  # a job saved for later spends its pages when it's run
    max_pages = (await _json_body(ask.request)).get("max_pages")
    return max_pages if isinstance(max_pages, int) else DEFAULT_CRAWL_PAGES


async def _crawl_run(ask: QuotaRequest) -> Optional[int]:
    job = CrawlJobRepository().find_by_id(ask.path["job_id"], ask.path["kb_id"])
    return job.config.max_pages if job else None  # an unknown job is the route's 404


QUOTA_RULES: tuple[QuotaRule, ...] = (
    QuotaRule("POST", re.compile(r"/agents"), AGENTS, _new_agent),
    # Ila's turns (/builder/...) use the person's own provider too, so they count like any agent's
    QuotaRule("POST", re.compile(r"/(agents/[^/]+|builder)/[^/]+/send-message"), MESSAGES, _one_message),
    QuotaRule("POST", re.compile(r"/knowledge-bases/[^/]+/crawl-jobs"), KB_PAGES, _crawl_started),
    QuotaRule("POST", re.compile(r"/knowledge-bases/(?P<kb_id>[^/]+)/crawl-jobs/(?P<job_id>[^/]+)/(run|run-stream)"),
              KB_PAGES, _crawl_run),
)


def rule_for(request: Request) -> Optional[tuple[QuotaRule, re.Match[str]]]:
    """The rule for this request's route, with the path's match, or None when the route spends no quota."""
    for rule in QUOTA_RULES:
        match = rule.path.fullmatch(request.url.path)
        if match and request.method == rule.method:
            return rule, match
    return None


async def _json_body(request: Request) -> dict[str, Any]:
    try:
        payload = await request.json()
    except ValueError as exc:
        log.warning("Invalid JSON payload on a limited route: %s", exc)
        raise HTTPException(status_code=400, detail={"message": "Invalid JSON payload."}) from exc
    return payload if isinstance(payload, dict) else {}


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app) -> None:
        super().__init__(app)
        self.rate_limits = RateLimitService()

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        selected = rule_for(request) if getattr(request.state, "user_email", None) else None
        principal = self._principal(request) if selected else None
        # The account owner's plan pays for the work, whoever in the account does it
        billed_email = account_billing_email(principal.account_id) if principal else None
        if selected is None or principal is None or billed_email is None:
            return await call_next(request)

        rule, path = selected
        try:
            requested = await rule.requested(QuotaRequest(request, path, principal))
            if requested is not None:
                self.rate_limits.check(billed_email, rule.quota, requested)
        except HTTPException as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content=jsonable_encoder({"detail": exc.detail}),
                headers=exc.headers,
            )
        return await call_next(request)

    @staticmethod
    def _principal(request: Request) -> Optional[Principal]:
        """The caller in the account the request acts in; None when they aren't in it, which the route refuses."""
        try:
            return get_principal(request)
        except IamError:
            return None
