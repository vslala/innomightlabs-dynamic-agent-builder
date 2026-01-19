"""
Hierarchical chunking strategy.

Creates multi-level chunks:
- Level 0: Document summary (captures overall context)
- Level 1: Section chunks (organized by headings)
- Level 2: Paragraph chunks (fine-grained retrieval)

This approach enables both broad context retrieval and precise
answer extraction during RAG queries.
"""

from typing import Optional
from uuid import uuid4

from src.crawler.chunking.base import ChunkingStrategy, ContentChunkData, ChunkingConfig
from src.crawler.extractor import ExtractedSection


class HierarchicalChunking(ChunkingStrategy):
    """
    Hierarchical chunking that creates document, section, and paragraph level chunks.

    Benefits:
    - Document-level chunks provide broad context
    - Section-level chunks maintain topical coherence
    - Paragraph-level chunks enable precise retrieval
    - Parent-child relationships allow context expansion during retrieval
    """

    def chunk(
        self,
        content: str,
        source_url: str,
        page_title: str,
        sections: Optional[list[ExtractedSection]] = None,
    ) -> list[ContentChunkData]:
        """
        Create hierarchical chunks from content.

        Args:
            content: The full text content
            source_url: Source URL for the content
            page_title: Title of the page
            sections: Optional list of ExtractedSection objects with structure

        Returns:
            List of ContentChunkData objects at multiple levels
        """
        chunks: list[ContentChunkData] = []
        chunk_index = 0

        # Level 0: Document summary
        doc_chunk_id = None
        if self.config.create_document_summary:
            doc_chunk = self._create_document_chunk(
                content=content,
                source_url=source_url,
                page_title=page_title,
                chunk_index=chunk_index,
            )
            chunks.append(doc_chunk)
            doc_chunk_id = doc_chunk.chunk_id
            chunk_index += 1

        # Level 1 & 2: Section and paragraph chunks
        if sections:
            # Use provided sections (preserves heading structure)
            for section in sections:
                section_chunks = self._chunk_section(
                    section=section,
                    source_url=source_url,
                    page_title=page_title,
                    parent_chunk_id=doc_chunk_id,
                    start_index=chunk_index,
                )
                chunks.extend(section_chunks)
                chunk_index += len(section_chunks)
        else:
            # No sections provided, create from raw content
            paragraph_chunks = self._chunk_paragraphs(
                content=content,
                source_url=source_url,
                page_title=page_title,
                parent_chunk_id=doc_chunk_id,
                start_index=chunk_index,
                level=2,
            )
            chunks.extend(paragraph_chunks)

        return chunks

    def _create_document_chunk(
        self,
        content: str,
        source_url: str,
        page_title: str,
        chunk_index: int,
    ) -> ContentChunkData:
        """Create a document-level summary chunk."""
        # Create a summary by taking the beginning of the content
        # In a production system, you might use an LLM to generate a proper summary
        summary = self._truncate_to_words(content, self.config.document_summary_max_words)

        # Add title context
        if page_title:
            summary = f"Title: {page_title}\n\n{summary}"

        return ContentChunkData(
            content=summary,
            chunk_index=chunk_index,
            level=0,  # Document level
            source_url=source_url,
            page_title=page_title,
        )

    def _chunk_section(
        self,
        section: ExtractedSection,
        source_url: str,
        page_title: str,
        parent_chunk_id: Optional[str],
        start_index: int,
    ) -> list[ContentChunkData]:
        """Create chunks for a section."""
        chunks: list[ContentChunkData] = []
        chunk_index = start_index

        section_content = section.content
        section_heading = section.heading

        # Add heading to content for context
        if section_heading:
            full_section_content = f"## {section_heading}\n\n{section_content}"
        else:
            full_section_content = section_content

        word_count = self._count_words(section_content)

        # If section is small enough, create single section chunk
        if word_count <= self.config.section_max_words:
            section_chunk = ContentChunkData(
                content=full_section_content,
                chunk_index=chunk_index,
                level=1,  # Section level
                parent_chunk_id=parent_chunk_id,
                source_url=source_url,
                page_title=page_title,
            )
            chunks.append(section_chunk)
            chunk_index += 1

            # Also create paragraph-level chunks if section has multiple paragraphs
            if self.config.create_section_chunks and "\n\n" in section_content:
                paragraph_chunks = self._chunk_paragraphs(
                    content=section_content,
                    source_url=source_url,
                    page_title=page_title,
                    parent_chunk_id=section_chunk.chunk_id,
                    start_index=chunk_index,
                    level=2,
                    heading_context=section_heading,
                )
                chunks.extend(paragraph_chunks)
        else:
            # Section is too large, create section chunk with summary
            # and multiple paragraph chunks
            section_summary = self._truncate_to_words(
                full_section_content, self.config.section_max_words
            )
            section_chunk = ContentChunkData(
                content=section_summary,
                chunk_index=chunk_index,
                level=1,
                parent_chunk_id=parent_chunk_id,
                source_url=source_url,
                page_title=page_title,
            )
            chunks.append(section_chunk)
            chunk_index += 1

            # Create paragraph chunks
            paragraph_chunks = self._chunk_paragraphs(
                content=section_content,
                source_url=source_url,
                page_title=page_title,
                parent_chunk_id=section_chunk.chunk_id,
                start_index=chunk_index,
                level=2,
                heading_context=section_heading,
            )
            chunks.extend(paragraph_chunks)

        return chunks

    def _chunk_paragraphs(
        self,
        content: str,
        source_url: str,
        page_title: str,
        parent_chunk_id: Optional[str],
        start_index: int,
        level: int,
        heading_context: Optional[str] = None,
    ) -> list[ContentChunkData]:
        """Create paragraph-level chunks with overlap."""
        chunks: list[ContentChunkData] = []
        chunk_index = start_index

        # Split into paragraphs
        paragraphs = self._split_into_paragraphs(content)

        if not paragraphs:
            return chunks

        # Merge small paragraphs and split large ones
        normalized_paragraphs = self._normalize_paragraphs(paragraphs)

        # Create chunks with sliding window overlap
        current_chunk_words: list[str] = []
        current_chunk_text: list[str] = []

        for para in normalized_paragraphs:
            para_words = para.split()
            para_word_count = len(para_words)

            # Check if adding this paragraph exceeds max
            if (
                current_chunk_words
                and len(current_chunk_words) + para_word_count > self.config.paragraph_max_words
            ):
                # Flush current chunk
                chunk_content = " ".join(current_chunk_text)

                # Add heading context if available
                if heading_context:
                    chunk_content = f"[{heading_context}]\n{chunk_content}"

                chunk = ContentChunkData(
                    content=chunk_content,
                    chunk_index=chunk_index,
                    level=level,
                    parent_chunk_id=parent_chunk_id,
                    source_url=source_url,
                    page_title=page_title,
                )
                chunks.append(chunk)
                chunk_index += 1

                # Keep overlap words for next chunk
                overlap_words = current_chunk_words[-self.config.overlap_words:]
                current_chunk_words = overlap_words
                current_chunk_text = [" ".join(overlap_words)] if overlap_words else []

            # Add paragraph to current chunk
            current_chunk_words.extend(para_words)
            current_chunk_text.append(para)

        # Flush remaining content
        if current_chunk_text and len(current_chunk_words) >= self.config.paragraph_min_words:
            chunk_content = " ".join(current_chunk_text)
            if heading_context:
                chunk_content = f"[{heading_context}]\n{chunk_content}"

            chunk = ContentChunkData(
                content=chunk_content,
                chunk_index=chunk_index,
                level=level,
                parent_chunk_id=parent_chunk_id,
                source_url=source_url,
                page_title=page_title,
            )
            chunks.append(chunk)

        return chunks

    def _normalize_paragraphs(self, paragraphs: list[str]) -> list[str]:
        """
        Normalize paragraphs by merging very small ones and splitting very large ones.
        """
        normalized: list[str] = []
        current_merge: list[str] = []
        current_word_count = 0

        for para in paragraphs:
            word_count = self._count_words(para)

            # If paragraph is very large, split it
            if word_count > self.config.paragraph_max_words * 2:
                # Flush any merged content first
                if current_merge:
                    normalized.append(" ".join(current_merge))
                    current_merge = []
                    current_word_count = 0

                # Split large paragraph by sentences
                split_paras = self._split_large_paragraph(para)
                normalized.extend(split_paras)
                continue

            # If paragraph is small, try to merge
            if word_count < self.config.paragraph_min_words:
                current_merge.append(para)
                current_word_count += word_count

                # If merged content is large enough, flush
                if current_word_count >= self.config.paragraph_min_words:
                    normalized.append(" ".join(current_merge))
                    current_merge = []
                    current_word_count = 0
            else:
                # Flush any merged content
                if current_merge:
                    # Add to this paragraph if combined is reasonable
                    if current_word_count + word_count <= self.config.paragraph_max_words:
                        current_merge.append(para)
                        normalized.append(" ".join(current_merge))
                    else:
                        normalized.append(" ".join(current_merge))
                        normalized.append(para)
                    current_merge = []
                    current_word_count = 0
                else:
                    normalized.append(para)

        # Flush remaining merged content
        if current_merge:
            normalized.append(" ".join(current_merge))

        return normalized

    def _split_large_paragraph(self, paragraph: str) -> list[str]:
        """Split a large paragraph into smaller chunks by sentences."""
        sentences = self._split_into_sentences(paragraph)
        chunks: list[str] = []
        current_chunk: list[str] = []
        current_word_count = 0

        for sentence in sentences:
            sentence_words = len(sentence.split())

            if (
                current_chunk
                and current_word_count + sentence_words > self.config.paragraph_max_words
            ):
                chunks.append(" ".join(current_chunk))
                current_chunk = []
                current_word_count = 0

            current_chunk.append(sentence)
            current_word_count += sentence_words

        if current_chunk:
            chunks.append(" ".join(current_chunk))

        return chunks


def get_chunking_strategy(name: str, config: Optional[ChunkingConfig] = None) -> ChunkingStrategy:
    """
    Factory function to get a chunking strategy by name.

    Args:
        name: Name of the strategy ("hierarchical")
        config: Optional configuration

    Returns:
        ChunkingStrategy instance
    """
    strategies = {
        "hierarchical": HierarchicalChunking,
    }

    strategy_class = strategies.get(name, HierarchicalChunking)
    return strategy_class(config)
