"""Knowledge Base module for storing and searching web content."""

from src.knowledge.models import (
    # Enums
    KnowledgeBaseStatus,
    CrawlJobStatus,
    CrawlSourceType,
    ChunkingStrategy,
    CrawlStepType,
    CrawledPageStatus,
    # Request/Response Models
    CreateKnowledgeBaseRequest,
    UpdateKnowledgeBaseRequest,
    KnowledgeBaseResponse,
    CrawlConfig,
    CrawlProgress,
    CrawlTiming,
    CrawlCheckpoint,
    StartCrawlJobRequest,
    CrawlJobResponse,
    PageTiming,
    PageMetadata,
    CrawledPageResponse,
    CrawlStepResponse,
    SearchRequest,
    SearchResult,
    SearchResponse,
    # Entity Models
    KnowledgeBase,
    CrawlJob,
    CrawlStep,
    CrawledPage,
    ContentChunk,
    AgentKnowledgeBase,
)

from src.knowledge.repository import (
    KnowledgeBaseRepository,
    CrawlJobRepository,
    CrawlStepRepository,
    CrawledPageRepository,
    ContentChunkRepository,
    AgentKnowledgeBaseRepository,
)

from src.knowledge.schemas import (
    get_crawl_config_form,
    get_create_knowledge_base_form,
    CRAWL_CONFIG_FORM,
    CREATE_KNOWLEDGE_BASE_FORM,
)

from src.knowledge.router import router, agent_kb_router

from src.knowledge.service import (
    KnowledgeBaseService,
    get_knowledge_base_service,
    DeleteResult,
)

__all__ = [
    # Enums
    "KnowledgeBaseStatus",
    "CrawlJobStatus",
    "CrawlSourceType",
    "ChunkingStrategy",
    "CrawlStepType",
    "CrawledPageStatus",
    # Request/Response Models
    "CreateKnowledgeBaseRequest",
    "UpdateKnowledgeBaseRequest",
    "KnowledgeBaseResponse",
    "CrawlConfig",
    "CrawlProgress",
    "CrawlTiming",
    "CrawlCheckpoint",
    "StartCrawlJobRequest",
    "CrawlJobResponse",
    "PageTiming",
    "PageMetadata",
    "CrawledPageResponse",
    "CrawlStepResponse",
    "SearchRequest",
    "SearchResult",
    "SearchResponse",
    # Entity Models
    "KnowledgeBase",
    "CrawlJob",
    "CrawlStep",
    "CrawledPage",
    "ContentChunk",
    "AgentKnowledgeBase",
    # Repositories
    "KnowledgeBaseRepository",
    "CrawlJobRepository",
    "CrawlStepRepository",
    "CrawledPageRepository",
    "ContentChunkRepository",
    "AgentKnowledgeBaseRepository",
    # Schemas
    "get_crawl_config_form",
    "get_create_knowledge_base_form",
    "CRAWL_CONFIG_FORM",
    "CREATE_KNOWLEDGE_BASE_FORM",
    # Routers
    "router",
    "agent_kb_router",
    # Service
    "KnowledgeBaseService",
    "get_knowledge_base_service",
    "DeleteResult",
]
