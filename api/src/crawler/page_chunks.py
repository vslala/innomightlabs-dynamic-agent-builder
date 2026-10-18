"""A page's chunks, named by what they say: only the ones that are new go through the embedding model.

A chunk's id comes from its page, its level, the page title and its text (`chunk_id`). The same text keeps its id
wherever it moves on the page, so reading a page again tells what changed by ids alone: a chunk whose id the page
already has is unchanged. An edit makes a new chunk rather than overwriting the old one, so a vector never sits beside
text it wasn't made from. Which chunks the page no longer has is the page ledger's to say (`page_index.py`).
"""

import hashlib
from dataclasses import dataclass

from src.crawler.chunking import ContentChunkData
from src.knowledge.models import ContentChunk
from src.vectorstore.embeddings import EmbeddingResult
from src.vectorstore.pinecone_client import VectorMetadata, VectorRecord


def chunk_id(kb_id: str, url: str, title: str, level: int, content: str, occurrence: int) -> str:
    """The same text at the same level of the same page keeps its id. `occurrence` tells apart identical chunks on one
    page (the second "Contact us" is 1). The title is in it because the vector's metadata carries it."""
    named = "\n".join((kb_id, url, title, str(level), str(occurrence), content))
    digest = hashlib.sha256(named.encode()).hexdigest()
    return f"{digest[:8]}-{digest[8:12]}-{digest[12:16]}-{digest[16:20]}-{digest[20:32]}"


def text_hash(title: str, text: str, chunking: str) -> str:
    """What a read of a page said, as chunked: two reads with the same hash make the same chunks."""
    return hashlib.sha256("\n".join((chunking, title, text)).encode()).hexdigest()


@dataclass(frozen=True)
class PageChunks:
    #: Every chunk of the page, named by what it says.
    chunks: list[ContentChunk]
    #: The ones the page didn't have: the only ones to embed, save and index.
    new: list[ContentChunk]

    @property
    def unchanged(self) -> int:
        return len(self.chunks) - len(self.new)


def prepare_page(
    kb_id: str, url: str, title: str, chunk_data_list: list[ContentChunkData], committed: set[str]
) -> PageChunks:
    """`committed` is the ids the page has (`KnowledgePage.chunk_ids`); empty for a page read for the first time."""
    seen: dict[tuple[int, str], int] = {}
    ids: dict[str, str] = {}  # the chunker's random id -> the chunk's id
    for data in chunk_data_list:
        occurrence = seen.get((data.level, data.content), 0)
        seen[(data.level, data.content)] = occurrence + 1
        ids[data.chunk_id] = chunk_id(kb_id, url, title, data.level, data.content, occurrence)
    chunks = [
        ContentChunk(
            chunk_id=ids[data.chunk_id],
            kb_id=kb_id,
            source_url=url,
            page_title=title,
            chunk_index=data.chunk_index,
            content=data.content,
            word_count=data.word_count,
            parent_chunk_id=ids.get(data.parent_chunk_id or ""),
            level=data.level,
        )
        for data in chunk_data_list
    ]
    return PageChunks(chunks=chunks, new=[chunk for chunk in chunks if chunk.chunk_id not in committed])


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
