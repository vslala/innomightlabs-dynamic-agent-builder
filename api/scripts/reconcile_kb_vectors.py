#!/usr/bin/env python3
"""
Makes a knowledge base's vectors and chunks match, for knowledge bases written before pages were kept.

Search finds vectors in Pinecone and returns the text of their chunks in DynamoDB, so the two must match:

- a vector with no chunk (an orphan) can't be returned, but takes a place in every search's top results;
- a chunk with no vector (left by a vector write that failed before it was checked) can never be found.

Crawls keep them matched now (crawler/page_index.py). This cleans up what older crawls left: orphans are deleted,
and chunks with no vector are embedded and indexed.

It also finds the vectors of deleted knowledge bases. Deleting used to carry on when Pinecone couldn't be reached, so a
deleted KB could leave its namespace behind (and nothing recorded that it did). Only the namespaces of knowledge bases
this table marks deleted are touched, never any other namespace of the index.

Usage:
    uv run python scripts/reconcile_kb_vectors.py --kb <kb_id>     # dry run: counts what's off
    uv run python scripts/reconcile_kb_vectors.py --all            # every live knowledge base
    uv run python scripts/reconcile_kb_vectors.py --all --apply    # fix it
    uv run python scripts/reconcile_kb_vectors.py --deleted        # dry run: deleted KBs that still have vectors
    uv run python scripts/reconcile_kb_vectors.py --deleted --apply

Needs a serverless Pinecone index (only those can be listed). Uses the API's own settings; against production, run
it through `railway run` so they come from the service, never from a file.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from boto3.dynamodb.conditions import Attr  # noqa: E402

from src.config import settings  # noqa: E402
from src.crawler.page_chunks import vectors_for  # noqa: E402
from src.db import get_dynamodb_resource  # noqa: E402
from src.knowledge.repository import ContentChunkRepository  # noqa: E402
from src.vectorstore import get_embeddings_service, get_pinecone_client  # noqa: E402
from src.vectorstore.embeddings import EmbeddingProvider  # noqa: E402
from src.vectorstore.pinecone_client import PineconeClient  # noqa: E402


@dataclass(frozen=True)
class Reconciled:
    kb_id: str
    orphans: int
    unindexed: int
    #: Orphans whose delete failed (only with --apply).
    not_deleted: int = 0


async def reconcile(
    kb_id: str, *, vectors: PineconeClient, embeddings: EmbeddingProvider, chunks: ContentChunkRepository, apply: bool
) -> Reconciled:
    stored = {chunk.chunk_id: chunk for chunk in chunks.find_all_by_kb(kb_id)}
    indexed = set(vectors.list_ids(kb_id))
    orphans = sorted(indexed - set(stored))
    unindexed = [chunk for chunk_id, chunk in stored.items() if chunk_id not in indexed]
    if not apply:
        return Reconciled(kb_id, len(orphans), len(unindexed))
    not_deleted = vectors.delete_by_ids(orphans, kb_id) if orphans else []
    if unindexed:
        vectors.upsert(vectors_for(unindexed, await embeddings.embed_texts_async([c.content for c in unindexed])), kb_id)
    return Reconciled(kb_id, len(orphans), len(unindexed), len(not_deleted))


def leaked_vectors(kb_ids: list[str], *, vectors: PineconeClient, apply: bool) -> dict[str, int]:
    """The deleted knowledge bases that still have vectors, with how many; deletes their namespaces when applying."""
    leaked = {kb_id: count for kb_id in kb_ids if (count := len(list(vectors.list_ids(kb_id))))}
    if apply:
        for kb_id in leaked:
            if not vectors.delete_namespace(kb_id):
                print(f"  {kb_id}: the namespace couldn't be deleted; run again")
    return leaked


def knowledge_bases(*, deleted: bool) -> list[str]:
    table = get_dynamodb_resource().Table(settings.dynamodb_table)
    status = Attr("status").eq("deleted") if deleted else Attr("status").ne("deleted")
    scan = {"FilterExpression": Attr("entity_type").eq("KnowledgeBase") & status}
    kb_ids: list[str] = []
    while True:
        response = table.scan(**scan)
        kb_ids += [item["kb_id"] for item in response.get("Items", [])]
        if "LastEvaluatedKey" not in response:
            return kb_ids
        scan["ExclusiveStartKey"] = response["LastEvaluatedKey"]


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    which = parser.add_mutually_exclusive_group(required=True)
    which.add_argument("--kb", action="append", help="a knowledge base id (repeatable)")
    which.add_argument("--all", action="store_true", help="every live knowledge base")
    which.add_argument("--deleted", action="store_true", help="knowledge bases deleted, whose vectors may be left")
    parser.add_argument("--apply", action="store_true", help="fix what's off: delete orphans, index unindexed chunks")
    args = parser.parse_args()

    vectors = get_pinecone_client(validate=True)
    if args.deleted:
        leaked = leaked_vectors(knowledge_bases(deleted=True), vectors=vectors, apply=args.apply)
        for kb_id, count in leaked.items():
            print(f"  {kb_id}: {count} vectors of a deleted knowledge base")
        print(f"{len(leaked)} deleted knowledge base(s) had vectors left" + ("" if args.apply else "; run with --apply to delete them"))
        return 0

    embeddings, chunks = get_embeddings_service(), ContentChunkRepository()
    kb_ids = args.kb or knowledge_bases(deleted=False)
    print(f"{'Fixing' if args.apply else 'Checking'} {len(kb_ids)} knowledge base(s)")
    off = 0
    for kb_id in kb_ids:
        result = await reconcile(kb_id, vectors=vectors, embeddings=embeddings, chunks=chunks, apply=args.apply)
        if result.orphans or result.unindexed:
            off += 1
            failed = f", {result.not_deleted} orphans not deleted" if result.not_deleted else ""
            print(f"  {kb_id}: {result.orphans} orphan vectors, {result.unindexed} chunks without a vector{failed}")
    print(f"{off} of {len(kb_ids)} were off" + ("" if args.apply else "; run with --apply to fix them"))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
