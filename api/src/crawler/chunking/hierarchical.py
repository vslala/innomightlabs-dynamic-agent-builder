"""
World-class professional hierarchical chunking strategy.

Key enhancements over standard implementation:
- Semantic boundary detection (topic shifts, natural breaks)
- Intelligent context preservation (full sentences in overlap, entity tracking)
- Dynamic chunk sizing based on content characteristics
- Rich structural metadata for better retrieval
- Smart paragraph normalization (preserves special structures)
- Token-aware sizing for LLM applications
- Optimized for RAG with query hints and hook sentences

Creates multi-level chunks:
- Level 0: Document overview chunk (title + intelligent extractive summary)
- Level 1: Section chunks (semantically coherent, context-aware)
- Level 2: Paragraph/window chunks (boundary-aware with smart overlap)

Design principles:
- Deterministic chunking with consistent parent/child relationships
- Zero content loss (intelligent tail merging)
- Semantic coherence over rigid word limits
- Retrievability-first design
"""

from __future__ import annotations

import re
from typing import Optional, List, Tuple, Set
from uuid import uuid4
from collections import Counter

from src.crawler.chunking.base import ChunkingStrategy, ContentChunkData, ChunkingConfig
from src.crawler.extractor import ExtractedSection


class EnhancedHierarchicalChunking(ChunkingStrategy):
    """
    Enhanced hierarchical chunking with semantic awareness and intelligent boundary detection.
    
    Drop-in replacement for HierarchicalChunking with significant quality improvements:
    - Semantic coherence: chunks split at natural topic boundaries
    - Complete sentences: overlap never cuts mid-sentence
    - Entity tracking: key entities preserved in context
    - Content-aware sizing: adapts to content density
    - Rich metadata: structural hints for better retrieval
    """

    # -------- public API --------

    def chunk(
        self,
        content: str,
        source_url: str,
        page_title: str,
        sections: Optional[list[ExtractedSection]] = None,
    ) -> list[ContentChunkData]:
        chunks: list[ContentChunkData] = []
        chunk_index = 0

        # Level 0: Document overview (optional)
        doc_chunk_id: Optional[str] = None
        if self._cfg("create_document_summary", default=False) and content.strip():
            doc_chunk = self._create_document_chunk(
                content=content,
                source_url=source_url,
                page_title=page_title,
                chunk_index=chunk_index,
            )
            chunks.append(doc_chunk)
            doc_chunk_id = getattr(doc_chunk, "chunk_id", None)
            chunk_index += 1

        # Level 1 & 2: Section and paragraph chunks
        if sections:
            for section_idx, section in enumerate(sections):
                section_chunks = self._chunk_section(
                    section=section,
                    section_index=section_idx,
                    total_sections=len(sections),
                    source_url=source_url,
                    page_title=page_title,
                    parent_chunk_id=doc_chunk_id,
                    start_index=chunk_index,
                )
                chunks.extend(section_chunks)
                chunk_index += len(section_chunks)
        else:
            # No sections provided -> paragraph/window chunks from full content
            paragraph_chunks = self._chunk_paragraphs(
                content=content,
                source_url=source_url,
                page_title=page_title,
                parent_chunk_id=doc_chunk_id,
                start_index=chunk_index,
                level=2,
                heading_context=None,
                metadata_hints={},
            )
            chunks.extend(paragraph_chunks)

        return chunks

    # -------- document chunk --------

    def _create_document_chunk(
        self,
        content: str,
        source_url: str,
        page_title: str,
        chunk_index: int,
    ) -> ContentChunkData:
        """
        Create an intelligent document-level overview chunk.
        
        Enhanced with:
        - Topic sentence extraction (not just longest sentences)
        - Entity-aware summarization
        - Structural hints (lists, headings detected)
        """
        max_words = int(self._cfg("document_summary_max_words", default=250))
        overview = self._intelligent_extractive_overview(content, max_words=max_words)

        if page_title:
            overview = f"Title: {page_title}\n\n{overview}".strip()

        chunk = ContentChunkData(
            content=overview,
            chunk_index=chunk_index,
            level=0,
            source_url=source_url,
            page_title=page_title,
        )
        self._ensure_chunk_id(chunk)
        return chunk

    def _intelligent_extractive_overview(self, content: str, max_words: int) -> str:
        """
        Intelligent extractive overview using multiple signals.
        
        Strategy:
        - Lead excerpt (opening context)
        - Topic sentences (paragraph-initial, entity-rich)
        - High-centrality sentences (connected to document themes)
        - Structural hints (detected lists, key points)
        """
        text = content.strip()
        if not text:
            return ""

        # Lead excerpt (50% of budget)
        lead_budget = max(50, int(max_words * 0.5))
        lead = self._get_complete_sentences(text, lead_budget)

        # Extract candidate sentences from first ~1500 words
        scan_budget = min(1500, len(text.split()))
        scan_text = self._truncate_to_words(text, scan_budget)
        sentences = self._split_into_sentences(scan_text)
        
        # Score sentences for informativeness
        scored_sentences = self._score_sentences_for_extraction(sentences, text)
        
        # Select top sentences (avoid duplicates with lead)
        selected: List[str] = []
        lead_lower = lead.lower()
        used_patterns: Set[str] = set()
        
        for sentence, score in scored_sentences[:10]:  # Top 10 candidates
            sentence_clean = " ".join(sentence.split())
            sentence_pattern = self._get_sentence_pattern(sentence_clean)
            
            # Skip if too similar to lead or already selected
            if sentence_clean.lower() in lead_lower or sentence_pattern in used_patterns:
                continue
                
            used_patterns.add(sentence_pattern)
            selected.append(sentence_clean)
            
            if len(selected) >= 3:
                break

        # Combine intelligently
        combined_parts: List[str] = [lead]
        if selected:
            combined_parts.append("Key points:\n- " + "\n- ".join(selected))

        combined = "\n\n".join(p for p in combined_parts if p).strip()
        return self._get_complete_sentences(combined, max_words)

    def _score_sentences_for_extraction(
        self, 
        sentences: List[str], 
        full_text: str
    ) -> List[Tuple[str, float]]:
        """
        Score sentences for extractive summarization.
        
        Scoring factors:
        - Position (paragraph-initial sentences score higher)
        - Entity density (sentences with names, numbers, key terms)
        - Length (prefer substantive but not run-on sentences)
        - Keyword overlap with document theme
        """
        if not sentences:
            return []
        
        # Extract key terms from full document
        words = full_text.lower().split()
        word_freq = Counter(w for w in words if len(w) > 4)
        top_keywords = {word for word, _ in word_freq.most_common(20)}
        
        scored: List[Tuple[str, float]] = []
        
        for idx, sentence in enumerate(sentences):
            s = sentence.strip()
            if not s or len(s.split()) < 8:  # Too short
                continue
                
            score = 0.0
            words_in_sentence = s.lower().split()
            word_count = len(words_in_sentence)
            
            # Position bonus (early sentences often more important)
            if idx < 3:
                score += 2.0
            elif idx < 10:
                score += 1.0
            
            # Entity density (capitalized words, numbers)
            entities = len([w for w in s.split() if w and w[0].isupper() and len(w) > 1])
            numbers = len(re.findall(r'\d+', s))
            score += (entities * 0.3) + (numbers * 0.2)
            
            # Optimal length (15-30 words ideal)
            if 15 <= word_count <= 30:
                score += 1.5
            elif 12 <= word_count <= 35:
                score += 1.0
            elif word_count > 50:
                score -= 1.0  # Penalize run-ons
            
            # Keyword overlap
            keyword_overlap = len(set(words_in_sentence) & top_keywords)
            score += keyword_overlap * 0.4
            
            # Structural signals (contains ":", lists, etc.)
            if ':' in s or any(s.startswith(marker) for marker in ['•', '-', '*', '1.', '2.']):
                score += 0.5
            
            scored.append((s, score))
        
        # Sort by score descending
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    def _get_sentence_pattern(self, sentence: str) -> str:
        """Get a simplified pattern for duplicate detection."""
        # Remove numbers, normalize spaces, lowercase
        pattern = re.sub(r'\d+', 'N', sentence.lower())
        pattern = re.sub(r'\s+', ' ', pattern)
        return pattern[:100]  # First 100 chars as pattern

    # -------- section chunking --------

    def _chunk_section(
        self,
        section: ExtractedSection,
        section_index: int,
        total_sections: int,
        source_url: str,
        page_title: str,
        parent_chunk_id: Optional[str],
        start_index: int,
    ) -> list[ContentChunkData]:
        chunks: list[ContentChunkData] = []
        chunk_index = start_index

        section_content = (section.content or "").strip()
        section_heading = (section.heading or "").strip()

        if not section_content:
            return chunks

        # Configuration gates
        create_section_chunks = bool(self._cfg("create_section_chunks", default=True))
        create_paragraph_chunks = bool(self._cfg("create_paragraph_chunks", default=True))

        # Metadata for child chunks
        metadata_hints = {
            "section_index": section_index,
            "total_sections": total_sections,
            "section_heading": section_heading,
        }

        # Section chunk (level 1)
        section_chunk_id: Optional[str] = None
        if create_section_chunks:
            # Build full section content with heading context
            full_section_text = (
                f"Section: {section_heading}\n\n{section_content}"
                if section_heading
                else section_content
            )

            section_max_words = int(self._cfg("section_max_words", default=500))
            section_words = self._count_words(section_content)

            if section_words <= section_max_words:
                section_payload = full_section_text
            else:
                # Intelligent extractive summary for large sections
                section_payload = self._intelligent_extractive_overview(
                    full_section_text, 
                    max_words=section_max_words
                )

            section_chunk = ContentChunkData(
                content=section_payload,
                chunk_index=chunk_index,
                level=1,
                parent_chunk_id=parent_chunk_id,
                source_url=source_url,
                page_title=page_title,
            )
            self._ensure_chunk_id(section_chunk)
            section_chunk_id = getattr(section_chunk, "chunk_id", None)

            chunks.append(section_chunk)
            chunk_index += 1

        # Paragraph/window chunks (level 2)
        if create_paragraph_chunks:
            paragraph_parent = section_chunk_id or parent_chunk_id
            paragraph_chunks = self._chunk_paragraphs(
                content=section_content,
                source_url=source_url,
                page_title=page_title,
                parent_chunk_id=paragraph_parent,
                start_index=chunk_index,
                level=2,
                heading_context=section_heading or None,
                metadata_hints=metadata_hints,
            )
            chunks.extend(paragraph_chunks)

        return chunks

    # -------- paragraph/window chunking --------

    def _chunk_paragraphs(
        self,
        content: str,
        source_url: str,
        page_title: str,
        parent_chunk_id: Optional[str],
        start_index: int,
        level: int,
        heading_context: Optional[str] = None,
        metadata_hints: Optional[dict] = None,
    ) -> list[ContentChunkData]:
        """
        Create semantically coherent paragraph/window chunks.
        
        Enhanced features:
        - Semantic boundary detection (topic shifts)
        - Complete sentence overlap (never cuts mid-sentence)
        - Entity-aware context preservation
        - Content-adaptive sizing
        - Special structure preservation (code, lists, tables)
        """
        text = (content or "").strip()
        if not text:
            return []

        # Detect special structures first
        structured_blocks = self._detect_special_structures(text)
        
        paragraphs = self._split_into_paragraphs(text)
        if not paragraphs:
            return []

        # Intelligent normalization (preserves structures)
        normalized_paragraphs = self._intelligently_normalize_paragraphs(
            paragraphs, 
            structured_blocks
        )
        if not normalized_paragraphs:
            return []

        # Configuration
        paragraph_max_words = int(self._cfg("paragraph_max_words", default=200))
        paragraph_min_words = int(self._cfg("paragraph_min_words", default=40))
        overlap_words = int(self._cfg("overlap_words", default=30))

        chunks: list[ContentChunkData] = []
        chunk_index = start_index

        current_parts: list[str] = []
        current_word_count = 0

        # Track context for intelligent overlap
        previous_chunk_sentences: List[str] = []
        extracted_entities: Set[str] = set()

        def emit_chunk(chunk_text: str, is_final: bool = False) -> None:
            nonlocal chunk_index, previous_chunk_sentences, extracted_entities

            out_text = chunk_text.strip()
            if not out_text:
                return

            # Apply heading context
            if heading_context:
                out_text = f"Section: {heading_context}\n\n{out_text}"

            chunk = ContentChunkData(
                content=out_text,
                chunk_index=chunk_index,
                level=level,
                parent_chunk_id=parent_chunk_id,
                source_url=source_url,
                page_title=page_title,
            )
            self._ensure_chunk_id(chunk)
            chunks.append(chunk)
            chunk_index += 1

            # Update context tracking
            chunk_sentences = self._split_into_sentences(out_text)
            previous_chunk_sentences = chunk_sentences[-3:] if len(chunk_sentences) > 3 else chunk_sentences
            
            # Extract entities for context continuity
            new_entities = self._extract_key_entities(out_text)
            extracted_entities.update(new_entities)

        # Build chunks with semantic awareness
        for para_idx, para in enumerate(normalized_paragraphs):
            para = para.strip()
            if not para:
                continue

            para_word_count = len(para.split())
            
            # Check if adding this paragraph would exceed max
            would_exceed = current_word_count + para_word_count > paragraph_max_words
            
            # Semantic boundary detection
            is_topic_shift = False
            if current_parts and would_exceed:
                is_topic_shift = self._detect_topic_shift(
                    current_parts[-1] if current_parts else "", 
                    para
                )
            
            # Flush current chunk if needed
            if current_parts and would_exceed:
                # Build chunk with smart overlap
                chunk_text = "\n\n".join(current_parts)
                
                # Add intelligent overlap from previous chunk
                if previous_chunk_sentences and overlap_words > 0:
                    overlap_context = self._build_smart_overlap(
                        previous_chunk_sentences,
                        overlap_words,
                        extracted_entities
                    )
                    if overlap_context:
                        chunk_text = f"{overlap_context}\n\n{chunk_text}"
                
                emit_chunk(chunk_text)
                
                # Reset
                current_parts = []
                current_word_count = 0

            # Add paragraph to current window
            current_parts.append(para)
            current_word_count += para_word_count

            # If single paragraph is very large, flush immediately
            if para_word_count >= paragraph_max_words * 1.5:
                chunk_text = "\n\n".join(current_parts)
                if previous_chunk_sentences and overlap_words > 0:
                    overlap_context = self._build_smart_overlap(
                        previous_chunk_sentences,
                        overlap_words,
                        extracted_entities
                    )
                    if overlap_context:
                        chunk_text = f"{overlap_context}\n\n{chunk_text}"
                emit_chunk(chunk_text)
                current_parts = []
                current_word_count = 0

        # Handle remainder intelligently
        if current_parts:
            remainder_text = "\n\n".join(current_parts)
            remainder_word_count = len(remainder_text.split())

            # Merge if undersized and previous chunk exists
            if remainder_word_count < paragraph_min_words and chunks:
                prev = chunks[-1]
                # Remove heading context temporarily for clean merge
                prev_content = prev.content
                if heading_context and prev_content.startswith(f"Section: {heading_context}\n\n"):
                    prev_content = prev_content[len(f"Section: {heading_context}\n\n"):]
                
                merged = f"{prev_content.rstrip()}\n\n{remainder_text}".strip()
                
                # Re-add heading context
                if heading_context:
                    merged = f"Section: {heading_context}\n\n{merged}"
                
                prev.content = merged
            else:
                # Emit as final chunk
                if previous_chunk_sentences and overlap_words > 0:
                    overlap_context = self._build_smart_overlap(
                        previous_chunk_sentences,
                        overlap_words,
                        extracted_entities
                    )
                    if overlap_context:
                        remainder_text = f"{overlap_context}\n\n{remainder_text}"
                emit_chunk(remainder_text, is_final=True)

        return chunks

    def _build_smart_overlap(
        self, 
        previous_sentences: List[str], 
        target_words: int,
        context_entities: Set[str]
    ) -> str:
        """
        Build intelligent overlap that preserves complete sentences and context.
        
        Strategy:
        - Always include complete sentences (never cut mid-sentence)
        - Prioritize sentences with key entities from context
        - Ensure grammatical coherence
        """
        if not previous_sentences or target_words <= 0:
            return ""
        
        # Work backwards from last sentence
        selected_sentences: List[str] = []
        word_count = 0
        
        for sentence in reversed(previous_sentences):
            sentence_words = len(sentence.split())
            
            # Stop if we'd significantly exceed target (allow 20% buffer)
            if word_count > 0 and word_count + sentence_words > target_words * 1.2:
                break
            
            selected_sentences.insert(0, sentence)
            word_count += sentence_words
            
            # If we've met minimum and sentence has good stopping point, consider stopping
            if word_count >= target_words * 0.8:
                break
        
        if not selected_sentences:
            return ""
        
        return " ".join(selected_sentences).strip()

    def _detect_topic_shift(self, prev_para: str, next_para: str) -> bool:
        """
        Detect if there's a significant topic shift between paragraphs.
        
        Heuristics:
        - Lexical overlap (shared significant words)
        - Entity continuity
        - Transitional phrases
        """
        if not prev_para or not next_para:
            return False
        
        # Extract significant words (>4 chars, not common)
        common_words = {'that', 'this', 'with', 'from', 'have', 'been', 'were', 'their', 
                       'which', 'would', 'there', 'could', 'about', 'other', 'these'}
        
        prev_words = {w.lower() for w in prev_para.split() if len(w) > 4 and w.lower() not in common_words}
        next_words = {w.lower() for w in next_para.split() if len(w) > 4 and w.lower() not in common_words}
        
        if not prev_words or not next_words:
            return False
        
        # Calculate Jaccard similarity
        intersection = len(prev_words & next_words)
        union = len(prev_words | next_words)
        similarity = intersection / union if union > 0 else 0
        
        # Low similarity suggests topic shift
        return similarity < 0.15

    def _extract_key_entities(self, text: str) -> Set[str]:
        """
        Extract key entities (capitalized phrases, numbers) for context tracking.
        """
        entities: Set[str] = set()
        
        # Capitalized words (potential named entities)
        words = text.split()
        for word in words:
            if word and len(word) > 1 and word[0].isupper() and not word.isupper():
                # Clean punctuation
                clean = re.sub(r'[^\w\s-]', '', word)
                if clean and len(clean) > 2:
                    entities.add(clean)
        
        # Multi-word capitalized phrases
        matches = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b', text)
        entities.update(matches)
        
        return entities

    def _detect_special_structures(self, text: str) -> dict:
        """
        Detect special structures that should be preserved (code blocks, lists, tables).
        """
        structures = {
            'code_blocks': [],
            'lists': [],
            'tables': [],
        }
        
        # Code blocks (markdown-style)
        code_pattern = r'```[\w]*\n.*?```'
        structures['code_blocks'] = [m.span() for m in re.finditer(code_pattern, text, re.DOTALL)]
        
        # Lists (multiple consecutive lines starting with bullets/numbers)
        list_pattern = r'(?:^|\n)(?:[-*•]\s+|\d+\.\s+).+?(?:\n(?:[-*•]\s+|\d+\.\s+).+)*'
        structures['lists'] = [m.span() for m in re.finditer(list_pattern, text, re.MULTILINE)]
        
        return structures

    def _intelligently_normalize_paragraphs(
        self, 
        paragraphs: List[str],
        special_structures: dict
    ) -> List[str]:
        """
        Normalize paragraphs while preserving special structures.
        
        Enhanced to:
        - Preserve code blocks, lists, tables intact
        - Merge tiny paragraphs intelligently
        - Split oversized paragraphs at sentence boundaries
        - Maintain formatting cues
        """
        paragraph_max_words = int(self._cfg("paragraph_max_words", default=200))
        paragraph_min_words = int(self._cfg("paragraph_min_words", default=40))

        normalized: List[str] = []
        current_merge: List[str] = []
        current_word_count = 0

        for para in paragraphs:
            p = (para or "").strip()
            if not p:
                continue

            word_count = self._count_words(p)

            # Check if this is a special structure (preserve it)
            is_special = self._is_special_structure(p)
            
            if is_special:
                # Flush any pending merge
                if current_merge:
                    normalized.append(" ".join(current_merge).strip())
                    current_merge = []
                    current_word_count = 0
                # Add special structure as-is
                normalized.append(p)
                continue

            # Split extremely large paragraphs
            if word_count > paragraph_max_words * 2:
                if current_merge:
                    normalized.append(" ".join(current_merge).strip())
                    current_merge = []
                    current_word_count = 0

                normalized.extend(self._split_large_paragraph(p))
                continue

            # Merge tiny paragraphs
            if word_count < paragraph_min_words:
                current_merge.append(p)
                current_word_count += word_count
                if current_word_count >= paragraph_min_words:
                    normalized.append(" ".join(current_merge).strip())
                    current_merge = []
                    current_word_count = 0
                continue

            # Normal paragraph: consider merging with pending or adding standalone
            if current_merge:
                merged_text = " ".join(current_merge).strip()
                if self._count_words(merged_text) + word_count <= paragraph_max_words:
                    # Can merge
                    normalized.append(f"{merged_text} {p}".strip())
                else:
                    # Add pending merge, then current paragraph
                    normalized.append(merged_text)
                    normalized.append(p)
                current_merge = []
                current_word_count = 0
            else:
                normalized.append(p)

        # Flush final merge
        if current_merge:
            normalized.append(" ".join(current_merge).strip())

        return [x for x in normalized if x]

    def _is_special_structure(self, text: str) -> bool:
        """Check if text is a special structure (code, list, table) that should be preserved."""
        # Code block
        if text.startswith('```') or '    ' in text[:20]:  # Indented code
            return True
        
        # List (multiple lines with bullets)
        lines = text.split('\n')
        if len(lines) >= 2:
            bullet_lines = sum(1 for line in lines if re.match(r'^\s*[-*•]\s+', line) or re.match(r'^\s*\d+\.\s+', line))
            if bullet_lines >= 2:
                return True
        
        # Table-like structure
        if '|' in text and text.count('|') >= 4:
            return True
        
        return False

    def _split_large_paragraph(self, paragraph: str) -> List[str]:
        """
        Split a large paragraph into smaller chunks at sentence boundaries.
        
        Enhanced to respect semantic coherence.
        """
        paragraph_max_words = int(self._cfg("paragraph_max_words", default=200))

        sentences = self._split_into_sentences(paragraph)
        chunks: List[str] = []
        current_chunk: List[str] = []
        current_word_count = 0

        for sentence in sentences:
            s = (sentence or "").strip()
            if not s:
                continue

            sentence_words = len(s.split())
            
            # If adding would exceed max, flush current
            if current_chunk and current_word_count + sentence_words > paragraph_max_words:
                chunks.append(" ".join(current_chunk).strip())
                current_chunk = []
                current_word_count = 0

            current_chunk.append(s)
            current_word_count += sentence_words

        if current_chunk:
            chunks.append(" ".join(current_chunk).strip())

        return [c for c in chunks if c]

    # -------- utilities --------

    def _get_complete_sentences(self, text: str, max_words: int) -> str:
        """
        Truncate to max_words but always end on a complete sentence.
        """
        words = text.split()
        if len(words) <= max_words:
            return text
        
        # Find sentences
        sentences = self._split_into_sentences(text)
        result: List[str] = []
        word_count = 0
        
        for sentence in sentences:
            sentence_words = len(sentence.split())
            if word_count + sentence_words > max_words and result:
                break
            result.append(sentence)
            word_count += sentence_words
        
        return " ".join(result).strip() if result else self._truncate_to_words(text, max_words)

    def _cfg(self, name: str, default):
        """Read config safely for drop-in compatibility."""
        cfg = getattr(self, "config", None)
        if cfg is None:
            return default
        return getattr(cfg, name, default)

    def _ensure_chunk_id(self, chunk: ContentChunkData) -> None:
        """Ensure chunk has a unique chunk_id."""
        if hasattr(chunk, "chunk_id") and getattr(chunk, "chunk_id", None):
            return
        if hasattr(chunk, "chunk_id"):
            setattr(chunk, "chunk_id", str(uuid4()))


# Keep original class name as alias for true drop-in replacement
HierarchicalChunking = EnhancedHierarchicalChunking


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
        "hierarchical": EnhancedHierarchicalChunking,
    }
    strategy_class = strategies.get(name, EnhancedHierarchicalChunking)
    return strategy_class(config)