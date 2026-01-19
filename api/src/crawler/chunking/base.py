"""
Base chunking strategy interface.

Chunking strategies break down extracted content into smaller pieces
suitable for embedding and vector search.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
from uuid import uuid4


@dataclass
class ContentChunkData:
    """
    A chunk of content ready for embedding.

    This is a data transfer object separate from the database model,
    containing just the essential information for processing.
    """
    chunk_id: str = field(default_factory=lambda: str(uuid4()))
    content: str = ""
    chunk_index: int = 0
    level: int = 0  # 0=document, 1=section, 2=paragraph
    parent_chunk_id: Optional[str] = None
    source_url: str = ""
    page_title: str = ""
    word_count: int = 0

    def __post_init__(self):
        if not self.word_count and self.content:
            self.word_count = len(self.content.split())


@dataclass
class ChunkingConfig:
    """Configuration for chunking strategies."""
    # Target chunk sizes (in words)
    document_summary_max_words: int = 300
    section_max_words: int = 500
    paragraph_max_words: int = 300
    paragraph_min_words: int = 50

    # Overlap between chunks (in words)
    overlap_words: int = 50

    # Whether to create document-level summary
    create_document_summary: bool = True

    # Whether to create section-level chunks
    create_section_chunks: bool = True


class ChunkingStrategy(ABC):
    """
    Abstract base class for chunking strategies.

    Implementations should break down ExtractedContent into
    smaller ContentChunkData objects suitable for embedding.
    """

    def __init__(self, config: Optional[ChunkingConfig] = None):
        self.config = config or ChunkingConfig()

    @abstractmethod
    def chunk(
        self,
        content: str,
        source_url: str,
        page_title: str,
        sections: Optional[list] = None,
    ) -> list[ContentChunkData]:
        """
        Break content into chunks.

        Args:
            content: The full text content
            source_url: Source URL for the content
            page_title: Title of the page
            sections: Optional list of ExtractedSection objects

        Returns:
            List of ContentChunkData objects
        """
        pass

    def _split_into_sentences(self, text: str) -> list[str]:
        """Split text into sentences."""
        import re

        # Simple sentence splitting on common endings
        # This handles most cases while being fast
        sentences = re.split(r'(?<=[.!?])\s+', text)
        return [s.strip() for s in sentences if s.strip()]

    def _split_into_paragraphs(self, text: str) -> list[str]:
        """Split text into paragraphs."""
        paragraphs = text.split("\n\n")
        return [p.strip() for p in paragraphs if p.strip()]

    def _count_words(self, text: str) -> int:
        """Count words in text."""
        return len(text.split())

    def _truncate_to_words(self, text: str, max_words: int) -> str:
        """Truncate text to a maximum number of words."""
        words = text.split()
        if len(words) <= max_words:
            return text
        return " ".join(words[:max_words]) + "..."
