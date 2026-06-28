from __future__ import annotations

import asyncio
from typing import Any

import httpx
from pydantic import ValidationError

from src.artifacts.models import ArtifactSource
from src.artifacts.service import ArtifactService
from src.skills.league_insights_report.html_safety import (
    extract_html_document,
    validate_safe_report_html,
)
from src.skills.league_insights_report.models import (
    LeagueReportConfig,
    GenerateMatchReportRequest,
)
from src.skills.league_insights_report.report_agent import (
    build_report_prompt,
    generate_report_html_with_agent,
)
from src.skills.league_insights_report.report_data import build_report_payload
from src.skills.league_insights_report.riot_client import RiotApiError, RiotClient

MATCH_FETCH_CONCURRENCY = 3


async def generate_match_report(
    arguments: dict[str, Any],
    config: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    skill_config = _validate_config(config)
    request = _validate_request(arguments)
    owner_email = _required_context(context, "owner_email")
    actor_email = str(context.get("actor_email") or owner_email)
    actor_id = str(context.get("actor_id") or actor_email)
    routing_region = request.routing_region or skill_config.default_routing_region
    client = RiotClient(skill_config.riot_api_key)

    try:
        account = await client.get_account_by_riot_id(
            routing_region=routing_region,
            game_name=request.game_name,
            tag_line=request.tag_line,
        )
        match_ids = await _resolve_match_ids(
            client=client,
            request=request,
            routing_region=routing_region,
            puuid=account.puuid,
        )
        if not match_ids:
            return _branchable_error("No Riot matches were found for the requested player and filters.")

        matches = await _fetch_matches(client, routing_region, match_ids)
    except RiotApiError as exc:
        return _branchable_error(str(exc), status_code=exc.status_code)
    except httpx.TimeoutException:
        return _branchable_error("Riot API request timed out. Try again later or reduce the match count.")
    except httpx.RequestError:
        return _branchable_error("Could not connect to Riot API. Try again later.")

    report_data = build_report_payload(
        account=account,
        matches=matches,
        report_scope=request.normalized_scope,
        routing_region=routing_region,
    )
    prompt = build_report_prompt(report_data=report_data)
    html = extract_html_document(
        await generate_report_html_with_agent(
            agent_id=skill_config.report_agent_id,
            owner_email=owner_email,
            actor_email=actor_email,
            actor_id=actor_id,
            prompt=prompt,
        )
    )
    validate_safe_report_html(html)

    artifact = ArtifactService().create_artifact(
        owner_email=owner_email,
        artifact_type="html_report",
        title=_report_title(request),
        filename=_report_filename(request),
        mime_type="text/html; charset=utf-8",
        body=html.encode("utf-8"),
        source=ArtifactSource(
            skill_id="league_insights_report",
            agent_id=skill_config.report_agent_id,
            automation_id=_context_value(context, "automation_id"),
            automation_run_id=_context_value(context, "automation_run_id"),
            automation_node_id=_context_value(context, "automation_node_id"),
            conversation_id=_context_value(context, "conversation_id"),
            metadata={
                "game": "league_of_legends",
                "routing_region": routing_region,
                "report_scope": request.normalized_scope,
                "match_ids": match_ids,
                "riot_id": f"{request.game_name}#{request.tag_line}",
            },
        ),
    )
    return {
        "ok": True,
        "artifact_id": artifact.artifact_id,
        "title": artifact.title,
        "filename": artifact.filename,
        "url": artifact.view_url,
        "view_url": artifact.view_url,
        "download_url": artifact.url,
        "report_scope": request.normalized_scope,
        "match_ids": match_ids,
        "routing_region": routing_region,
    }


def _validate_config(config: dict[str, Any]) -> LeagueReportConfig:
    try:
        return LeagueReportConfig.model_validate(config)
    except ValidationError as exc:
        raise ValueError(f"Invalid League Insights Report skill configuration: {exc}") from exc


def _validate_request(arguments: dict[str, Any]) -> GenerateMatchReportRequest:
    try:
        return GenerateMatchReportRequest.model_validate(arguments)
    except ValidationError as exc:
        raise ValueError(f"Invalid League Insights Report arguments: {exc}") from exc


async def _resolve_match_ids(
    *,
    client: RiotClient,
    request: GenerateMatchReportRequest,
    routing_region: str,
    puuid: str,
) -> list[str]:
    if request.match_ids:
        return request.match_ids
    if request.match_id:
        return [request.match_id]

    count = 1 if request.normalized_scope == "single_match" else request.match_count
    return await client.get_match_ids(
        routing_region=routing_region,
        puuid=puuid,
        queue=request.queue,
        count=count,
    )


async def _fetch_matches(
    client: RiotClient,
    routing_region: str,
    match_ids: list[str],
) -> list[dict[str, Any]]:
    semaphore = asyncio.Semaphore(MATCH_FETCH_CONCURRENCY)

    async def fetch(match_id: str) -> dict[str, Any]:
        async with semaphore:
            return await client.get_match(routing_region=routing_region, match_id=match_id)

    return await asyncio.gather(*(fetch(match_id) for match_id in match_ids))


def _branchable_error(error: str, *, status_code: int | None = None) -> dict[str, Any]:
    return {
        "ok": False,
        "status_code": status_code,
        "error": error,
    }


def _report_title(request: GenerateMatchReportRequest) -> str:
    if request.report_title:
        return request.report_title
    report_type = "Multi-Match Report" if request.normalized_scope == "multi_match" else "Match Report"
    return f"League {report_type} - {request.game_name}#{request.tag_line}"


def _report_filename(request: GenerateMatchReportRequest) -> str:
    scope = "multi-match" if request.normalized_scope == "multi_match" else "match"
    riot_id = f"{request.game_name}-{request.tag_line}".replace("#", "-")
    return f"league-{scope}-report-{riot_id}.html"


def _required_context(context: dict[str, Any], key: str) -> str:
    value = str(context.get(key) or "").strip()
    if not value:
        raise ValueError(f"Missing skill runtime context: {key}")
    return value


def _context_value(context: dict[str, Any], key: str) -> str | None:
    value = str(context.get(key) or "").strip()
    return value or None
