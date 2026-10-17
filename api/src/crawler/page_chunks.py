"""What to embed when a page is read again: only the chunks whose text changed.

Chunk ids are fixed by the page and the chunk's place on it (`generate_chunk_id`), so a page read twice names the same
chunks. Comparing each with the one stored under its id tells which ones changed, and only those go through the
embedding model and into the vector index. Chunks the page no longer has are removed.
"""

import hashlib
from dataclasses import dataclass

from src.crawler.chunking import ContentChunkData
from src.knowledge.models import ContentChunk
from src.vectorstore.embeddings import EmbeddingResult
from src.vectorstore.pinecone_client import VectorMetadata, VectorRecord


def generate_chunk_id(kb_id: str, source_url: str, chunk_index: int, level: int) -> str:
    """The same id for the same place on the same page, so reading a page again finds its chunks and overwrites
    them instead of adding copies. `level` is 0 for the document, 1 for a section, 2 for a paragraph."""
    digest = hashlib.md5(f"{kb_id}:{source_url}:{chunk_index}:{level}".encode()).hexdigest()
    return f"{digest[:8]}-{digest[8:12]}-{digest[12:16]}-{digest[16:20]}-{digest[20:32]}"


@dataclass(frozen=True)
class PageChunks:
    #: Every chunk of the page, with its stable id.
    chunks: list[ContentChunk]
    #: The ones with no identical chunk stored: the only ones to embed, save and index.
    changed: list[ContentChunk]
    #: Ids stored for this page that it no longer has (it got shorter).
    stale: list[str]

    @property
    def reused(self) -> int:
        return len(self.chunks) - len(self.changed)


def prepare_page(
    kb_id: str,
    url: str,
    title: str,
    chunk_data_list: list[ContentChunkData],
    stored: dict[str, ContentChunk],
) -> PageChunks:
    """`stored` is the page's chunks as saved by an earlier read, by id; empty for a page read for the first time."""
    def stable_id(index: int, level: int) -> str:
        return generate_chunk_id(kb_id=kb_id, source_url=url, chunk_index=index, level=level)

    # The chunker gives each chunk a random id and points children at their parent's; ids that last come from the place.
    place = {data.chunk_id: (data.chunk_index, data.level) for data in chunk_data_list}
    chunks = [
        ContentChunk(
            chunk_id=stable_id(data.chunk_index, data.level),
            kb_id=kb_id,
            source_url=url,
            page_title=title,
            chunk_index=data.chunk_index,
            content=data.content,
            word_count=data.word_count,
            parent_chunk_id=stable_id(*place[data.parent_chunk_id]) if data.parent_chunk_id in place else None,
            level=data.level,
        )
        for data in chunk_data_list
    ]
    changed = [chunk for chunk in chunks if not _same(chunk, stored.get(chunk.chunk_id))]
    kept = {chunk.chunk_id for chunk in chunks}
    return PageChunks(chunks=chunks, changed=changed, stale=[chunk_id for chunk_id in stored if chunk_id not in kept])


def _same(chunk: ContentChunk, stored: ContentChunk | None) -> bool:
    """Everything the vector and its search metadata are made from."""
    return stored is not None and (
        (stored.content, stored.page_title or "", stored.parent_chunk_id, stored.level)
        == (chunk.content, chunk.page_title or "", chunk.parent_chunk_id, chunk.level)
    )


def vectors_for(chunks: list[ContentChunk], embeddings: list[EmbeddingResult]) -> list[VectorRecord]:
    return [
        VectorRecord(
            id=chunk.chunk_id,
            values=result.embedding,
            metadata=VectorMetadata(
                kb_id=chunk.kb_id,
                chunk_id=chunk.chunk_id,
                source_url=chunk.source_url,
                page_title=chunk.page_title or "",
                chunk_index=chunk.chunk_index,
                level=chunk.level,
                word_count=chunk.word_count,
            ),
        )
        for chunk, result in zip(chunks, embeddings)
    ]
