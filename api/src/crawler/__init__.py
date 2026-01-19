"""Web crawler module for discovering and processing web pages."""

from src.crawler.events import (
    CrawlEventType,
    CrawlEvent,
    # Event factory functions
    job_started_event,
    job_progress_event,
    job_checkpoint_event,
    job_completed_event,
    job_failed_event,
    url_discovered_event,
    url_skipped_event,
    page_fetch_start_event,
    page_fetch_complete_event,
    page_parse_complete_event,
    page_chunk_complete_event,
    page_embed_complete_event,
    page_ingest_complete_event,
    page_error_event,
)

from src.crawler.robots import RobotsParser, RobotsTxt, RobotsRule

from src.crawler.discovery import (
    UrlDiscovery,
    DiscoveryConfig,
    DiscoveredUrl,
    SitemapParser,
    UrlCrawler,
)

from src.crawler.extractor import (
    ContentExtractor,
    ExtractedContent,
    ExtractedSection,
)

from src.crawler.chunking import (
    ChunkingStrategy,
    ChunkingConfig,
    ContentChunkData,
    HierarchicalChunking,
    get_chunking_strategy,
)

from src.crawler.worker import (
    CrawlerWorker,
    CrawlContext,
    get_crawler_worker,
)

__all__ = [
    # Events
    "CrawlEventType",
    "CrawlEvent",
    "job_started_event",
    "job_progress_event",
    "job_checkpoint_event",
    "job_completed_event",
    "job_failed_event",
    "url_discovered_event",
    "url_skipped_event",
    "page_fetch_start_event",
    "page_fetch_complete_event",
    "page_parse_complete_event",
    "page_chunk_complete_event",
    "page_embed_complete_event",
    "page_ingest_complete_event",
    "page_error_event",
    # Robots
    "RobotsParser",
    "RobotsTxt",
    "RobotsRule",
    # Discovery
    "UrlDiscovery",
    "DiscoveryConfig",
    "DiscoveredUrl",
    "SitemapParser",
    "UrlCrawler",
    # Extractor
    "ContentExtractor",
    "ExtractedContent",
    "ExtractedSection",
    # Chunking
    "ChunkingStrategy",
    "ChunkingConfig",
    "ContentChunkData",
    "HierarchicalChunking",
    "get_chunking_strategy",
    # Worker
    "CrawlerWorker",
    "CrawlContext",
    "get_crawler_worker",
]
