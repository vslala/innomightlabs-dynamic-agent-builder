from __future__ import annotations

import base64
import json
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from src.config import settings
from src.skills.agent2agent_client.credentials import A2ACredentialResolver
from src.skills.agent2agent_client.client import A2AHttpClient
from src.skills.agent2agent_client.models import (
    A2AAgentCardView,
    A2ARegistryConfig,
    A2ASkillSummary,
    AgentRef,
    DiscoverAgentsRequest,
    DiscoverAgentsResponse,
    DiscoveredAgent,
    RegistryAgentCandidate,
)
from src.skills.agent2agent_client.references import encode_agent_ref


class A2ADiscoveryClient:
    def __init__(self, http_client: A2AHttpClient | None = None) -> None:
        self.http_client = http_client or A2AHttpClient()
        self.credential_resolver = A2ACredentialResolver()

    async def search(self, *, request: DiscoverAgentsRequest, config: A2ARegistryConfig) -> DiscoverAgentsResponse:
        candidates = await self._load_candidates(config)
        matches = [candidate for candidate in candidates if self._matches(candidate, request.keyword)]
        start = _decode_cursor(request.cursor)
        selected = matches[start : start + request.limit]
        next_cursor = _encode_cursor(start + request.limit) if start + request.limit < len(matches) else None

        return DiscoverAgentsResponse(
            keyword=request.keyword,
            items=[
                self._to_discovered_agent(candidate, include_card=request.include_cards)
                for candidate in selected
            ],
            next_cursor=next_cursor,
            searched_registries=config.registry_urls,
        )

    async def get_card(self, agent_ref: AgentRef) -> A2AAgentCardView:
        if not agent_ref.card_url:
            raise ValueError("Discovered A2A agent is missing an Agent Card URL")
        card_url = agent_ref.card_url
        payload = await self.http_client.get_agent_card(card_url)
        return A2AAgentCardView.model_validate(payload)

    async def _load_candidates(self, config: A2ARegistryConfig) -> list[RegistryAgentCandidate]:
        candidates: list[RegistryAgentCandidate] = []
        for registry_url in config.registry_urls:
            candidates.extend(await self._load_registry(registry_url, config=config))
        return candidates

    async def _load_registry(self, registry_url: str, *, config: A2ARegistryConfig) -> list[RegistryAgentCandidate]:
        payload = await self.http_client.get_json(
            _list_url(registry_url),
            headers=self.credential_resolver.headers_for_url(target_url=registry_url, config=config),
        )
        if _looks_like_agent_list(payload):
            return await self._from_agent_list(registry_url, payload, config=config)
        return await self._from_agent_card(registry_url, payload)

    async def _from_agent_card(self, registry_url: str, payload: dict[str, Any]) -> list[RegistryAgentCandidate]:
        card = A2AAgentCardView.model_validate(self.http_client.normalize_agent_card(payload))

        service_url = card.service_url(_preferred_protocols())
        return [
            RegistryAgentCandidate(
                registry_url=registry_url,
                service_url=service_url,
                card_url=registry_url,
                name=card.name,
                description=card.description,
                skills=card.skills,
                card=card,
                protocol_binding=card.protocol_binding(_preferred_protocols()),
            )
        ]

    async def _from_agent_list(
        self,
        registry_url: str,
        payload: dict[str, Any],
        *,
        config: A2ARegistryConfig,
    ) -> list[RegistryAgentCandidate]:
        items = payload.get("items")
        return await self._from_agent_summaries(registry_url, items if isinstance(items, list) else [], config=config)

    async def _from_agent_summaries(
        self,
        registry_url: str,
        summaries: list[Any],
        *,
        config: A2ARegistryConfig,
    ) -> list[RegistryAgentCandidate]:
        candidates: list[RegistryAgentCandidate] = []
        for summary in summaries:
            if not isinstance(summary, dict):
                continue
            candidate = _candidate_from_summary(
                registry_url,
                summary,
                normalize_agent_card=self.http_client.normalize_agent_card,
            )
            if not candidate.service_url and not candidate.card and not candidate.card_url:
                continue
            enriched = await self._enrich_candidate(candidate, config=config)
            candidates.append(enriched)
        return candidates

    async def _enrich_candidate(
        self,
        candidate: RegistryAgentCandidate,
        *,
        config: A2ARegistryConfig,
    ) -> RegistryAgentCandidate:
        if candidate.card:
            card = candidate.card
            return candidate.model_copy(
                update={
                    "name": card.name or candidate.name,
                    "description": card.description or candidate.description,
                    "skills": card.skills,
                    "service_url": card.service_url(_preferred_protocols()) or candidate.service_url,
                    "protocol_binding": card.protocol_binding(_preferred_protocols()),
                }
            )
        if not candidate.card_url:
            return candidate
        try:
            card = A2AAgentCardView.model_validate(
                await self.http_client.get_agent_card(
                    candidate.card_url,
                    headers=self.credential_resolver.headers_for_url(
                        target_url=candidate.card_url,
                        config=config,
                    ),
                )
            )
        except Exception:
            return candidate
        return candidate.model_copy(
            update={
                "name": card.name or candidate.name,
                "description": card.description or candidate.description,
                "skills": card.skills,
                "card": card,
                "service_url": card.service_url(_preferred_protocols()) or candidate.service_url,
                "protocol_binding": card.protocol_binding(_preferred_protocols()),
            }
        )

    def _matches(self, candidate: RegistryAgentCandidate, keyword: str) -> bool:
        needle = keyword.strip().casefold()
        if not needle:
            return True
        haystack = " ".join(
            [
                candidate.name,
                candidate.description or "",
                *[
                    " ".join([skill.id, skill.name, skill.description, *skill.tags])
                    for skill in candidate.skills
                ],
            ]
        ).casefold()
        return needle in haystack

    def _to_discovered_agent(self, candidate: RegistryAgentCandidate, *, include_card: bool) -> DiscoveredAgent:
        return DiscoveredAgent(
            agent_ref=encode_agent_ref(
                AgentRef(
                    registry_url=candidate.registry_url,
                    service_url=candidate.service_url,
                    card_url=candidate.card_url,
                    name=candidate.name,
                    protocol_binding=candidate.protocol_binding,
                )
            ),
            registry_url=candidate.registry_url,
            card_url=candidate.card_url,
            service_url=candidate.service_url,
            name=candidate.name,
            description=candidate.description,
            skills=candidate.skills if include_card else candidate.skills[:5],
        )


def _candidate_from_summary(
    registry_url: str,
    summary: dict[str, Any],
    *,
    normalize_agent_card,
) -> RegistryAgentCandidate:
    raw_card = summary.get("agentCard") or summary.get("agent_card")
    card = None
    if isinstance(raw_card, dict):
        card = A2AAgentCardView.model_validate(normalize_agent_card(raw_card))
    service_url = str(
        summary.get("serviceUrl")
        or summary.get("service_url")
        or summary.get("url")
        or (card.service_url(_preferred_protocols()) if card else "")
        or ""
    ).strip()
    card_url = str(
        summary.get("agentCardUrl")
        or summary.get("agent_card_url")
        or summary.get("cardUrl")
        or summary.get("card_url")
        or ""
    ).strip() or None
    return RegistryAgentCandidate(
        registry_url=registry_url,
        service_url=service_url,
        card_url=card_url,
        name=str(summary.get("name") or "Agent").strip() or "Agent",
        description=str(summary.get("description") or "").strip() or None,
        skills=[
            A2ASkillSummary.model_validate(skill)
            for skill in summary.get("skills", [])
            if isinstance(skill, dict)
        ],
        card=card,
    )


def _looks_like_agent_list(payload: dict[str, Any]) -> bool:
    return isinstance(payload.get("items"), list)


def _list_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.path.rstrip("/").endswith("/a2a/agents"):
        return url
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.setdefault("limit", "100")
    return urlunparse(parsed._replace(query=urlencode(query)))


def _preferred_protocols() -> list[str]:
    supported = [
        protocol
        for protocol in settings.a2a_supported_protocols
        if protocol in {"JSONRPC", "HTTP+JSON"}
    ]
    primary = settings.a2a_primary_protocol
    if primary in supported:
        return [primary, *[protocol for protocol in supported if protocol != primary]]
    return supported or ["JSONRPC"]


def _encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(json.dumps({"offset": offset}).encode("utf-8")).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str | None) -> int:
    if not cursor:
        return 0
    padded = cursor + ("=" * (-len(cursor) % 4))
    try:
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
        return max(0, int(payload.get("offset", 0)))
    except Exception:
        return 0
