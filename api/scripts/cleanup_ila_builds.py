#!/usr/bin/env python3
"""
Removes everything building with Ila has left in the table, so kits start from nothing.

For each account it finds:
- Ila's conversations (agent_id = innomightlabs-ila) and their builder sessions, with every row in each
  conversation's partition (messages, tool audit, turns) and the canvases drawn in them;
- the agents and knowledge bases blueprints built (from deployment and kit records), deleted the way the dashboard
  deletes them (an agent takes its widget keys, secret keys and dream schedule; a knowledge base its content), plus
  every row left in each agent's partition (skills, links);
- the deployment and kit records.

MCP connections stay: they belong to the account, not to a build. So do Ila's token usage records (billing history).

Usage:
    uv run python scripts/cleanup_ila_builds.py                 # dry run: lists what would go
    uv run python scripts/cleanup_ila_builds.py --user a@b.com  # one account only
    uv run python scripts/cleanup_ila_builds.py --apply         # delete

Uses the API's own settings (DYNAMODB_TABLE, DYNAMODB_ENDPOINT, AWS credentials, Pinecone, the media bucket).
Against production, run it through `railway run` so they come from the service, never from a file.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from boto3.dynamodb.conditions import Attr, Key  # noqa: E402

from src.agents.repository import AgentRepository  # noqa: E402
from src.agents.service import AgentService  # noqa: E402
from src.artifacts.storage import ArtifactStorage  # noqa: E402
from src.builder.models import ILA_AGENT_ID  # noqa: E402
from src.config import settings  # noqa: E402
from src.db import get_dynamodb_resource  # noqa: E402
from src.knowledge.models import KnowledgeBaseStatus  # noqa: E402
from src.knowledge.repository import KnowledgeBaseRepository  # noqa: E402
from src.knowledge.service import get_knowledge_base_service  # noqa: E402


@dataclass
class AccountFindings:
    conversations: set[str] = field(default_factory=set)
    sessions: list[dict[str, Any]] = field(default_factory=list)
    deployments: list[dict[str, Any]] = field(default_factory=list)
    kits: list[dict[str, Any]] = field(default_factory=list)
    agents: set[str] = field(default_factory=set)
    knowledge_bases: set[str] = field(default_factory=set)
    artifacts: list[dict[str, Any]] = field(default_factory=list)


def scan(table, filter_expression) -> Iterator[dict[str, Any]]:
    kwargs: dict[str, Any] = {"FilterExpression": filter_expression}
    while True:
        response = table.scan(**kwargs)
        yield from response.get("Items", [])
        if "LastEvaluatedKey" not in response:
            return
        kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]


def partition(table, pk: str) -> list[dict[str, Any]]:
    kwargs: dict[str, Any] = {"KeyConditionExpression": Key("pk").eq(pk), "ProjectionExpression": "pk, sk"}
    rows: list[dict[str, Any]] = []
    while True:
        response = table.query(**kwargs)
        rows += response.get("Items", [])
        if "LastEvaluatedKey" not in response:
            return rows
        kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]


def owner_of(item: dict[str, Any]) -> str:
    return str(item["pk"]).split("#", 1)[1]


def find(table, only_user: str | None) -> dict[str, AccountFindings]:
    found: dict[str, AccountFindings] = defaultdict(AccountFindings)
    ila_conversation = Attr("entity_type").eq("Conversation") & Attr("agent_id").eq(ILA_AGENT_ID)
    for item in scan(table, Attr("entity_type").is_in(["BuilderSession", "BlueprintDeployment", "Kit"]) | ila_conversation):
        owner = owner_of(item)
        if only_user and owner != only_user:
            continue
        account = found[owner]
        entity = item.get("entity_type")
        if entity == "BuilderSession":
            account.sessions.append(item)
            account.conversations.add(item["conversation_id"])
        elif entity == "BlueprintDeployment":
            account.deployments.append(item)
            for resource in (item.get("resources") or {}).values():
                _built(account, resource)
        elif entity == "Kit":
            account.kits.append(item)
            for resource in (item.get("resources") or {}).values():
                _built(account, resource)
        else:
            account.conversations.add(item["conversation_id"])

    for owner, account in found.items():
        for item in scan(table, Attr("pk").eq(f"User#{owner}") & Attr("entity_type").eq("Artifact")):
            if (item.get("source") or {}).get("conversation_id") in account.conversations:
                account.artifacts.append(item)
    return dict(found)


def _built(account: AccountFindings, resource: dict[str, Any]) -> None:
    if resource.get("kind") == "Agent":
        account.agents.add(resource["id"])
    elif resource.get("kind") == "KnowledgeBase":
        account.knowledge_bases.add(resource["id"])


def report(owner: str, account: AccountFindings) -> None:
    agents = AgentRepository()
    kbs = KnowledgeBaseRepository()
    live_agents = [a for a in (agents.find_agent_by_id(i, owner) for i in sorted(account.agents)) if a]
    live_kbs = [k for k in (kbs.find_by_id(i, owner) for i in sorted(account.knowledge_bases))
                if k and k.status != KnowledgeBaseStatus.DELETED]
    print(f"\n{owner}")
    print(f"  Ila conversations: {len(account.conversations)} (builder sessions: {len(account.sessions)})")
    print(f"  canvases drawn in them: {len(account.artifacts)}")
    print(f"  agents built: {len(live_agents)} still there of {len(account.agents)}")
    for agent in live_agents:
        print(f"    - {agent.agent_name} ({agent.agent_id})")
    print(f"  knowledge bases built: {len(live_kbs)} still there of {len(account.knowledge_bases)}")
    for kb in live_kbs:
        print(f"    - {kb.name} ({kb.kb_id})")
    print(f"  deployment records: {len(account.deployments)}, kit records: {len(account.kits)}")


def delete(table, owner: str, account: AccountFindings) -> list[str]:
    """Deletes in dependency order. Returns what couldn't be deleted, so the run can say so."""
    problems: list[str] = []
    for agent_id in sorted(account.agents):
        try:
            if AgentRepository().find_agent_by_id(agent_id, owner):
                AgentService().delete(agent_id, owner)
            _delete_rows(table, partition(table, f"Agent#{agent_id}"))
        except Exception as e:  # keep going: report everything that failed at the end
            problems.append(f"agent {agent_id}: {e}")
    for kb_id in sorted(account.knowledge_bases):
        try:
            kb = KnowledgeBaseRepository().find_by_id(kb_id, owner)
            if kb and kb.status != KnowledgeBaseStatus.DELETED:
                result = get_knowledge_base_service().soft_delete(kb_id, owner)
                if not result.success:
                    problems.append(f"knowledge base {kb_id}: {result.error}")
        except Exception as e:
            problems.append(f"knowledge base {kb_id}: {e}")

    storage = ArtifactStorage() if settings.conversation_media_bucket else None
    for artifact in account.artifacts:
        try:
            if storage and artifact.get("s3_key"):
                storage.client.delete_object(Bucket=storage.bucket, Key=artifact["s3_key"])
        except Exception as e:
            problems.append(f"canvas file {artifact.get('artifact_id')}: {e}")
        _delete_rows(table, [artifact])

    for conversation_id in sorted(account.conversations):
        _delete_rows(table, partition(table, f"CONVERSATION#{conversation_id}"))
        _delete_rows(table, [{"pk": f"USER#{owner}", "sk": f"CONVERSATION#{conversation_id}"}])
    _delete_rows(table, [*account.sessions, *account.deployments, *account.kits])
    return problems


def _delete_rows(table, rows: list[dict[str, Any]]) -> None:
    with table.batch_writer() as batch:
        for row in rows:
            batch.delete_item(Key={"pk": row["pk"], "sk": row["sk"]})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--user", help="Only this account")
    parser.add_argument("--apply", action="store_true", help="Delete. Without it, only lists what would go.")
    args = parser.parse_args()

    table = get_dynamodb_resource().Table(settings.dynamodb_table)
    print(f"Table: {settings.dynamodb_table}{' at ' + settings.dynamodb_endpoint if settings.dynamodb_endpoint else ''}")
    found = find(table, args.user)
    if not found:
        print("Nothing to remove.")
        return 0
    for owner, account in sorted(found.items()):
        report(owner, account)
    if not args.apply:
        print("\nDry run: nothing was deleted. Run again with --apply to delete.")
        return 0

    failed = False
    for owner, account in sorted(found.items()):
        problems = delete(table, owner, account)
        for problem in problems:
            print(f"  could not delete {problem}")
        failed = failed or bool(problems)
    print("\nDone." if not failed else "\nDone, with the problems above; run again to retry them.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
