"""
Unit tests for the chunking module.
"""

import pytest
from src.crawler.chunking import (
    ChunkingStrategy,
    ChunkingConfig,
    ContentChunkData,
    HierarchicalChunking,
    get_chunking_strategy,
)
from src.crawler.extractor import ExtractedSection


class TestContentChunkData:
    """Tests for ContentChunkData dataclass."""

    def test_auto_word_count(self):
        """Test that word count is automatically calculated."""
        chunk = ContentChunkData(
            content="This is a test sentence with eight words.",
            source_url="https://example.com",
            page_title="Test",
        )
        assert chunk.word_count == 8

    def test_explicit_word_count_preserved(self):
        """Test that explicit word count is preserved."""
        chunk = ContentChunkData(
            content="Short content",
            word_count=100,  # Override
            source_url="https://example.com",
            page_title="Test",
        )
        assert chunk.word_count == 100

    def test_chunk_id_auto_generated(self):
        """Test that chunk_id is auto-generated."""
        chunk1 = ContentChunkData(content="Test", source_url="", page_title="")
        chunk2 = ContentChunkData(content="Test", source_url="", page_title="")
        assert chunk1.chunk_id != chunk2.chunk_id


class TestChunkingConfig:
    """Tests for ChunkingConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = ChunkingConfig()
        assert config.document_summary_max_words == 300
        assert config.section_max_words == 500
        assert config.paragraph_max_words == 300
        assert config.paragraph_min_words == 50
        assert config.overlap_words == 50
        assert config.create_document_summary is True
        assert config.create_section_chunks is True

    def test_custom_config(self):
        """Test custom configuration."""
        config = ChunkingConfig(
            document_summary_max_words=500,
            paragraph_max_words=200,
            overlap_words=25,
        )
        assert config.document_summary_max_words == 500
        assert config.paragraph_max_words == 200
        assert config.overlap_words == 25


class TestHierarchicalChunking:
    """Tests for HierarchicalChunking strategy."""

    @pytest.fixture
    def strategy(self):
        """Create a default strategy."""
        return HierarchicalChunking()

    @pytest.fixture
    def small_config_strategy(self):
        """Create a strategy with small chunk sizes for testing."""
        config = ChunkingConfig(
            document_summary_max_words=50,
            section_max_words=50,
            paragraph_max_words=30,
            paragraph_min_words=5,
            overlap_words=5,
        )
        return HierarchicalChunking(config)

    def test_chunk_empty_content(self, strategy):
        """Test chunking empty content."""
        chunks = strategy.chunk(
            content="",
            source_url="https://example.com",
            page_title="Test",
        )
        # Should create document chunk even for empty content
        assert len(chunks) >= 1
        assert chunks[0].level == 0  # Document level

    def test_chunk_simple_content(self, strategy):
        """Test chunking simple content."""
        content = "This is a simple paragraph. It has a few sentences."
        chunks = strategy.chunk(
            content=content,
            source_url="https://example.com",
            page_title="Test Page",
        )
        assert len(chunks) >= 1
        # First chunk should be document summary
        assert chunks[0].level == 0
        assert "Test Page" in chunks[0].content

    def test_chunk_with_sections(self, strategy):
        """Test chunking content with sections."""
        content = "Introduction content.\n\nMain body content."
        sections = [
            ExtractedSection(heading="Introduction", content="Introduction content."),
            ExtractedSection(heading="Main Body", content="Main body content."),
        ]
        chunks = strategy.chunk(
            content=content,
            source_url="https://example.com",
            page_title="Test",
            sections=sections,
        )
        assert len(chunks) >= 1
        # Should have document chunk + section chunks
        levels = [c.level for c in chunks]
        assert 0 in levels  # Document level
        assert 1 in levels  # Section level

    def test_chunk_preserves_source_metadata(self, strategy):
        """Test that source metadata is preserved in all chunks."""
        content = "Test content with multiple paragraphs.\n\nSecond paragraph here."
        chunks = strategy.chunk(
            content=content,
            source_url="https://example.com/page",
            page_title="Test Title",
        )
        for chunk in chunks:
            assert chunk.source_url == "https://example.com/page"
            assert chunk.page_title == "Test Title"

    def test_chunk_creates_document_summary(self, strategy):
        """Test that document summary is created."""
        content = "A " * 100  # 100 words
        chunks = strategy.chunk(
            content=content,
            source_url="https://example.com",
            page_title="Test",
        )
        doc_chunks = [c for c in chunks if c.level == 0]
        assert len(doc_chunks) == 1
        assert doc_chunks[0].word_count <= strategy.config.document_summary_max_words + 10

    def test_chunk_without_document_summary(self):
        """Test chunking without document summary."""
        config = ChunkingConfig(create_document_summary=False)
        strategy = HierarchicalChunking(config)
        content = "Test content"
        chunks = strategy.chunk(
            content=content,
            source_url="https://example.com",
            page_title="Test",
        )
        doc_chunks = [c for c in chunks if c.level == 0]
        assert len(doc_chunks) == 0

    def test_chunk_large_content_creates_multiple_chunks(self, small_config_strategy):
        """Test that large content creates multiple paragraph chunks."""
        # Create content larger than max paragraph size with multiple paragraphs
        content = "\n\n".join([" ".join(["word"] * 50) for _ in range(5)])  # 5 paragraphs x 50 words
        chunks = small_config_strategy.chunk(
            content=content,
            source_url="https://example.com",
            page_title="Test",
        )
        # Should have document chunk + paragraph chunks
        assert len(chunks) >= 2
        # Check that paragraph level chunks exist
        paragraph_chunks = [c for c in chunks if c.level == 2]
        assert len(paragraph_chunks) >= 1

    def test_chunk_parent_child_relationships(self, strategy):
        """Test that parent-child relationships are set correctly."""
        sections = [
            ExtractedSection(heading="Section 1", content="Content " * 50),
        ]
        chunks = strategy.chunk(
            content="Content " * 50,
            source_url="https://example.com",
            page_title="Test",
            sections=sections,
        )
        # Find document chunk
        doc_chunk = next((c for c in chunks if c.level == 0), None)
        # Find section chunks
        section_chunks = [c for c in chunks if c.level == 1]
        
        if doc_chunk and section_chunks:
            # Section chunks should reference document as parent
            for section_chunk in section_chunks:
                assert section_chunk.parent_chunk_id == doc_chunk.chunk_id


class TestChunkingStrategyHelpers:
    """Tests for helper methods in ChunkingStrategy."""

    @pytest.fixture
    def strategy(self):
        return HierarchicalChunking()

    def test_split_into_sentences(self, strategy):
        """Test sentence splitting."""
        text = "First sentence. Second sentence! Third sentence?"
        sentences = strategy._split_into_sentences(text)
        assert len(sentences) == 3
        assert sentences[0] == "First sentence."
        assert sentences[1] == "Second sentence!"
        assert sentences[2] == "Third sentence?"

    def test_split_into_paragraphs(self, strategy):
        """Test paragraph splitting."""
        text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        paragraphs = strategy._split_into_paragraphs(text)
        assert len(paragraphs) == 3

    def test_count_words(self, strategy):
        """Test word counting."""
        assert strategy._count_words("one two three") == 3
        assert strategy._count_words("") == 0
        assert strategy._count_words("single") == 1

    def test_truncate_to_words(self, strategy):
        """Test word truncation."""
        text = "one two three four five"
        truncated = strategy._truncate_to_words(text, 3)
        assert truncated == "one two three..."

    def test_truncate_short_text(self, strategy):
        """Test truncation of short text."""
        text = "short text"
        truncated = strategy._truncate_to_words(text, 10)
        assert truncated == "short text"  # No truncation needed


class TestGetChunkingStrategy:
    """Tests for the factory function."""

    def test_get_hierarchical_strategy(self):
        """Test getting hierarchical strategy."""
        strategy = get_chunking_strategy("hierarchical")
        assert isinstance(strategy, HierarchicalChunking)

    def test_get_unknown_strategy_returns_default(self):
        """Test that unknown strategy name returns default."""
        strategy = get_chunking_strategy("unknown")
        assert isinstance(strategy, HierarchicalChunking)

    def test_get_strategy_with_config(self):
        """Test getting strategy with custom config."""
        config = ChunkingConfig(paragraph_max_words=100)
        strategy = get_chunking_strategy("hierarchical", config)
        assert strategy.config.paragraph_max_words == 100
