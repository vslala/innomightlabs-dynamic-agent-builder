"""The one-off reconcile: vectors with no chunk are deleted, chunks with no vector are indexed."""

import importlib.util
import sys
from pathlib import Path

import pytest

from src.knowledge.models import ContentChunk
from src.knowledge.repository import ContentChunkRepository
from tests.crawler.fakes import CountingEmbeddings, FakeIndex

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "reconcile_kb_vectors.py"


@pytest.fixture
def script():
    spec = importlib.util.spec_from_file_location("reconcile_kb_vectors", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # its dataclasses look their module up
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def knowledge_base(dynamodb_table):
    """kb-1 with a chunk that has its vector, one whose vector write failed, and an orphan vector."""
    ContentChunkRepository().batch_save([
        ContentChunk(chunk_id=chunk_id, kb_id="kb-1", source_url="https://example.com", chunk_index=0, content=text)
        for chunk_id, text in (("indexed", "Seats cost ten pounds."), ("unindexed", "Refunds take five days."))
    ])
    index = FakeIndex()
    index.vectors = {"indexed": [1.0], "orphan": [2.0]}
    return index


async def test_a_dry_run_counts_and_changes_nothing(script, knowledge_base):
    result = await script.reconcile(
        "kb-1", vectors=knowledge_base, embeddings=CountingEmbeddings(), chunks=ContentChunkRepository(), apply=False
    )

    assert (result.orphans, result.unindexed) == (1, 1)
    assert set(knowledge_base.vectors) == {"indexed", "orphan"}


async def test_applying_deletes_orphans_and_indexes_what_had_no_vector(script, knowledge_base):
    embeddings = CountingEmbeddings()

    result = await script.reconcile(
        "kb-1", vectors=knowledge_base, embeddings=embeddings, chunks=ContentChunkRepository(), apply=True
    )

    assert set(knowledge_base.vectors) == {"indexed", "unindexed"}
    assert embeddings.texts == ["Refunds take five days."] and result.not_deleted == 0


def test_a_deleted_knowledge_bases_left_vectors_are_found_and_only_those_deleted(script):
    class Namespaces(FakeIndex):
        def __init__(self):
            super().__init__()
            self.namespaces = {"gone-1": 3, "gone-2": 0, "someone-elses": 9}

        def list_ids(self, kb_id):
            return iter(range(self.namespaces[kb_id]))

        def delete_namespace(self, kb_id):
            self.namespaces[kb_id] = 0
            return True

    index = Namespaces()

    dry = script.leaked_vectors(["gone-1", "gone-2"], vectors=index, apply=False)
    assert dry == {"gone-1": 3} and index.namespaces["gone-1"] == 3, "a dry run changes nothing"

    script.leaked_vectors(["gone-1", "gone-2"], vectors=index, apply=True)
    assert index.namespaces == {"gone-1": 0, "gone-2": 0, "someone-elses": 9}, "a namespace not asked about is never touched"
