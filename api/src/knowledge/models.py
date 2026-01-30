"""
Knowledge Base and Crawl Job models for DynamoDB single table design.

Key Structure:
    KnowledgeBase:
        pk: User#{user_email}
        sk: KnowledgeBase#{kb_id}

    CrawlJob:
        pk: KnowledgeBase#{kb_id}
        sk: CrawlJob#{job_id}

    CrawlStep (Audit Log):
        pk: CrawlJob#{job_id}
        sk: Step#{timestamp}#{step_id}

    CrawledPage:
        pk: CrawlJob#{job_id}
        sk: Page#{url_hash}

    ContentChunk:
        pk: KnowledgeBase#{kb_id}
        sk: Chunk#{chunk_id}

    AgentKnowledgeBase (Link Table):
        pk: Agent#{agent_id}
        sk: KnowledgeBase#{kb_id}
        gsi2_pk: KnowledgeBase#{kb_id}
        gsi2_sk: Agent#{agent_id}
"""

from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4
from enum import Enum
from decimal import Decimal
import hashlib


def to_decimal(value: Optional[float]) -> Optional[Decimal]:
    """Convert float to Decimal for DynamoDB compatibility."""
    if value is None:
        return None
    return Decimal(str(value))


def convert_floats_to_decimals(obj: Any) -> Any:
    """
    Recursively convert all float values to Decimal for DynamoDB compatibility.
    DynamoDB doesn't support Python float type, requires Decimal instead.
    """
    if isinstance(obj, float):
        return Decimal(str(obj))
    elif isinstance(obj, dict):
        return {k: convert_floats_to_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_floats_to_decimals(item) for item in obj]
    return obj


# =============================================================================
# Enums
# =============================================================================

class KnowledgeBaseStatus(str, Enum):
    ACTIVE = "active"
    DELETED = "deleted"


class CrawlJobStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CrawlSourceType(str, Enum):
    SITEMAP = "sitemap"
    URL = "url"


class ChunkingStrategy(str, Enum):
    HIERARCHICAL = "hierarchical"


class CrawlStepType(str, Enum):
    # Job lifecycle
    JOB_STARTED = "JOB_STARTED"
    JOB_COMPLETED = "JOB_COMPLETED"
    JOB_FAILED = "JOB_FAILED"
    JOB_CHECKPOINT = "JOB_CHECKPOINT"

    # URL discovery
    URL_DISCOVERED = "URL_DISCOVERED"
    URL_SKIPPED = "URL_SKIPPED"

    # Page processing
    PAGE_FETCH_START = "PAGE_FETCH_START"
    PAGE_FETCH_COMPLETE = "PAGE_FETCH_COMPLETE"
    PAGE_FETCH_ERROR = "PAGE_FETCH_ERROR"
    PAGE_PARSE_START = "PAGE_PARSE_START"
    PAGE_PARSE_COMPLETE = "PAGE_PARSE_COMPLETE"
    PAGE_CHUNK_START = "PAGE_CHUNK_START"
    PAGE_CHUNK_COMPLETE = "PAGE_CHUNK_COMPLETE"
    PAGE_EMBED_START = "PAGE_EMBED_START"
    PAGE_EMBED_COMPLETE = "PAGE_EMBED_COMPLETE"
    PAGE_INGEST_START = "PAGE_INGEST_START"
    PAGE_INGEST_COMPLETE = "PAGE_INGEST_COMPLETE"


class CrawledPageStatus(str, Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


# =============================================================================
# Request/Response Models
# =============================================================================

class CreateKnowledgeBaseRequest(BaseModel):
    """Request model for creating a knowledge base."""
    name: str
    description: Optional[str] = None


class UpdateKnowledgeBaseRequest(BaseModel):
    """Request model for updating a knowledge base."""
    name: Optional[str] = None
    description: Optional[str] = None


class KnowledgeBaseResponse(BaseModel):
    """Response model for knowledge base."""
    kb_id: str
    name: str
    description: Optional[str] = None
    pinecone_namespace: str
    total_pages: int = 0
    total_chunks: int = 0
    total_vectors: int = 0
    status: KnowledgeBaseStatus
    created_by: str
    created_at: datetime
    updated_at: Optional[datetime] = None


class CrawlConfig(BaseModel):
    """Configuration for a crawl job."""
    source_type: CrawlSourceType = CrawlSourceType.SITEMAP
    source_url: str
    max_pages: int = 100
    max_depth: int = 3
    rate_limit_ms: int = 1000
    respect_robots_txt: bool = True
    chunking_strategy: ChunkingStrategy = ChunkingStrategy.HIERARCHICAL


class CrawlProgress(BaseModel):
    """Progress tracking for a crawl job."""
    discovered_urls: int = 0
    processed_urls: int = 0
    successful_urls: int = 0
    failed_urls: int = 0
    total_chunks: int = 0
    total_embeddings: int = 0


class CrawlTiming(BaseModel):
    """Timing information for a crawl job."""
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    total_duration_ms: Optional[int] = None
    avg_page_duration_ms: Optional[float] = None


class CrawlCheckpoint(BaseModel):
    """Checkpoint for Lambda continuation."""
    current_url_index: int = 0
    pending_urls: list[str] = Field(default_factory=list)


class StartCrawlJobRequest(BaseModel):
    """Request model for starting a crawl job."""
    source_type: CrawlSourceType = CrawlSourceType.SITEMAP
    source_url: str
    max_pages: int = 100
    max_depth: int = 3
    rate_limit_ms: int = 1000
    chunking_strategy: ChunkingStrategy = ChunkingStrategy.HIERARCHICAL


class CrawlJobResponse(BaseModel):
    """Response model for crawl job."""
    job_id: str
    kb_id: str
    status: CrawlJobStatus
    config: CrawlConfig
    progress: CrawlProgress
    timing: CrawlTiming
    error_message: Optional[str] = None
    created_by: str
    created_at: datetime


class ContentUploadResponse(BaseModel):
    """Response model for content upload."""

    kb_id: str
    filename: str
    chunk_count: int
    vector_count: int
    total_pages: int
    total_chunks: int
    total_vectors: int


class ContentUploadItemResponse(BaseModel):
    """Response model for content upload list item."""

    upload_id: str
    kb_id: str
    filename: str
    content_type: Optional[str] = None
    size_bytes: int
    metadata: Optional[str] = None
    chunk_count: int
    vector_count: int
    created_by: str
    created_at: datetime


class PageTiming(BaseModel):
    """Timing information for a crawled page."""
    fetch_duration_ms: Optional[int] = None
    parse_duration_ms: Optional[int] = None
    chunk_duration_ms: Optional[int] = None
    embed_duration_ms: Optional[int] = None
    ingest_duration_ms: Optional[int] = None
    total_duration_ms: Optional[int] = None


class PageMetadata(BaseModel):
    """Metadata extracted from a crawled page."""
    title: Optional[str] = None
    description: Optional[str] = None
    content_length: int = 0
    word_count: int = 0


class CrawledPageResponse(BaseModel):
    """Response model for crawled page."""
    url: str
    status: CrawledPageStatus
    page_metadata: PageMetadata
    chunk_count: int = 0
    timing: PageTiming
    error: Optional[str] = None
    crawled_at: datetime


class CrawlStepResponse(BaseModel):
    """Response model for crawl step (audit log entry)."""
    step_id: str
    step_type: CrawlStepType
    url: Optional[str] = None
    details: Optional[dict[str, Any]] = None
    duration_ms: Optional[int] = None
    timestamp: datetime


class SearchRequest(BaseModel):
    """Request model for searching a knowledge base."""
    query: str
    top_k: int = 5


class SearchResult(BaseModel):
    """A single search result."""
    chunk_id: str
    content: str
    source_url: str
    page_title: Optional[str] = None
    score: float


class SearchResponse(BaseModel):
    """Response model for search results."""
    results: list[SearchResult]
    query: str


# =============================================================================
# DynamoDB Entity Models
# =============================================================================

class KnowledgeBase(BaseModel):
    """Knowledge base entity for storing web content as vectors."""

    kb_id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    description: Optional[str] = None
    pinecone_namespace: str = ""  # Set in __init__ based on kb_id
    total_pages: int = 0
    total_chunks: int = 0
    total_vectors: int = 0
    status: KnowledgeBaseStatus = KnowledgeBaseStatus.ACTIVE
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None
    ttl: Optional[int] = None  # Unix timestamp for DynamoDB TTL auto-expiration

    def model_post_init(self, __context: Any) -> None:
        """Set pinecone_namespace after init if not already set."""
        if not self.pinecone_namespace:
            self.pinecone_namespace = f"kb_{self.kb_id}"

    @property
    def pk(self) -> str:
        return f"User#{self.created_by}"

    @property
    def sk(self) -> str:
        return f"KnowledgeBase#{self.kb_id}"

    def to_dynamo_item(self) -> dict[str, Any]:
        item: dict[str, Any] = {
            "pk": self.pk,
            "sk": self.sk,
            "kb_id": self.kb_id,
            "name": self.name,
            "description": self.description,
            "pinecone_namespace": self.pinecone_namespace,
            "total_pages": self.total_pages,
            "total_chunks": self.total_chunks,
            "total_vectors": self.total_vectors,
            "status": self.status.value,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None,
            "entity_type": "KnowledgeBase",
        }
        if self.ttl is not None:
            item["ttl"] = self.ttl
        return item

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "KnowledgeBase":
        return cls(
            kb_id=item["kb_id"],
            name=item["name"],
            description=item.get("description"),
            pinecone_namespace=item.get("pinecone_namespace", f"kb_{item['kb_id']}"),
            total_pages=item.get("total_pages", 0),
            total_chunks=item.get("total_chunks", 0),
            total_vectors=item.get("total_vectors", 0),
            status=KnowledgeBaseStatus(item.get("status", "active")),
            created_by=item["created_by"],
            created_at=datetime.fromisoformat(item["created_at"]),
            updated_at=datetime.fromisoformat(item["updated_at"]) if item.get("updated_at") else None,
            deleted_at=datetime.fromisoformat(item["deleted_at"]) if item.get("deleted_at") else None,
            ttl=item.get("ttl"),
        )

    def to_response(self) -> KnowledgeBaseResponse:
        return KnowledgeBaseResponse(
            kb_id=self.kb_id,
            name=self.name,
            description=self.description,
            pinecone_namespace=self.pinecone_namespace,
            total_pages=self.total_pages,
            total_chunks=self.total_chunks,
            total_vectors=self.total_vectors,
            status=self.status,
            created_by=self.created_by,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


class CrawlJob(BaseModel):
    """Crawl job entity for tracking web crawling progress."""

    job_id: str = Field(default_factory=lambda: str(uuid4()))
    kb_id: str
    status: CrawlJobStatus = CrawlJobStatus.PENDING
    config: CrawlConfig
    progress: CrawlProgress = Field(default_factory=CrawlProgress)
    timing: CrawlTiming = Field(default_factory=CrawlTiming)
    embedding_model: str = "amazon.titan-embed-text-v2:0"
    checkpoint: Optional[CrawlCheckpoint] = None
    error_message: Optional[str] = None
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def pk(self) -> str:
        return f"KnowledgeBase#{self.kb_id}"

    @property
    def sk(self) -> str:
        return f"CrawlJob#{self.job_id}"

    def to_dynamo_item(self) -> dict[str, Any]:
        return convert_floats_to_decimals({
            "pk": self.pk,
            "sk": self.sk,
            "job_id": self.job_id,
            "kb_id": self.kb_id,
            "status": self.status.value,
            "config": self.config.model_dump(),
            "progress": self.progress.model_dump(),
            "timing": {
                "started_at": self.timing.started_at.isoformat() if self.timing.started_at else None,
                "completed_at": self.timing.completed_at.isoformat() if self.timing.completed_at else None,
                "total_duration_ms": self.timing.total_duration_ms,
                "avg_page_duration_ms": self.timing.avg_page_duration_ms,
            },
            "embedding_model": self.embedding_model,
            "checkpoint": self.checkpoint.model_dump() if self.checkpoint else None,
            "error_message": self.error_message,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat(),
            "entity_type": "CrawlJob",
        })

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "CrawlJob":
        timing_data = item.get("timing", {})
        return cls(
            job_id=item["job_id"],
            kb_id=item["kb_id"],
            status=CrawlJobStatus(item["status"]),
            config=CrawlConfig(**item["config"]),
            progress=CrawlProgress(**item.get("progress", {})),
            timing=CrawlTiming(
                started_at=datetime.fromisoformat(timing_data["started_at"]) if timing_data.get("started_at") else None,
                completed_at=datetime.fromisoformat(timing_data["completed_at"]) if timing_data.get("completed_at") else None,
                total_duration_ms=timing_data.get("total_duration_ms"),
                avg_page_duration_ms=timing_data.get("avg_page_duration_ms"),
            ),
            embedding_model=item.get("embedding_model", "amazon.titan-embed-text-v2:0"),
            checkpoint=CrawlCheckpoint(**item["checkpoint"]) if item.get("checkpoint") else None,
            error_message=item.get("error_message"),
            created_by=item["created_by"],
            created_at=datetime.fromisoformat(item["created_at"]),
        )

    def to_response(self) -> CrawlJobResponse:
        return CrawlJobResponse(
            job_id=self.job_id,
            kb_id=self.kb_id,
            status=self.status,
            config=self.config,
            progress=self.progress,
            timing=self.timing,
            error_message=self.error_message,
            created_by=self.created_by,
            created_at=self.created_at,
        )


class CrawlStep(BaseModel):
    """Audit log entry for crawl job steps."""

    step_id: str = Field(default_factory=lambda: str(uuid4()))
    job_id: str
    step_type: CrawlStepType
    url: Optional[str] = None
    details: Optional[dict[str, Any]] = None
    duration_ms: Optional[int] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def pk(self) -> str:
        return f"CrawlJob#{self.job_id}"

    @property
    def sk(self) -> str:
        # Use timestamp + step_id for chronological ordering
        return f"Step#{self.timestamp.isoformat()}#{self.step_id}"

    def to_dynamo_item(self) -> dict[str, Any]:
        return {
            "pk": self.pk,
            "sk": self.sk,
            "step_id": self.step_id,
            "job_id": self.job_id,
            "step_type": self.step_type.value,
            "url": self.url,
            "details": self.details,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp.isoformat(),
            "entity_type": "CrawlStep",
        }

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "CrawlStep":
        return cls(
            step_id=item["step_id"],
            job_id=item["job_id"],
            step_type=CrawlStepType(item["step_type"]),
            url=item.get("url"),
            details=item.get("details"),
            duration_ms=item.get("duration_ms"),
            timestamp=datetime.fromisoformat(item["timestamp"]),
        )

    def to_response(self) -> CrawlStepResponse:
        return CrawlStepResponse(
            step_id=self.step_id,
            step_type=self.step_type,
            url=self.url,
            details=self.details,
            duration_ms=self.duration_ms,
            timestamp=self.timestamp,
        )


class CrawledPage(BaseModel):
    """Record of a crawled page with analytics."""

    job_id: str
    created_by: str
    url: str
    url_hash: str = ""  # Set from URL if not provided
    status: CrawledPageStatus = CrawledPageStatus.PENDING
    page_metadata: PageMetadata = Field(default_factory=PageMetadata)
    chunk_count: int = 0
    timing: PageTiming = Field(default_factory=PageTiming)
    error: Optional[str] = None
    crawled_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def model_post_init(self, __context: Any) -> None:
        """Set url_hash from URL if not already set."""
        if not self.url_hash:
            self.url_hash = hashlib.md5(self.url.encode()).hexdigest()

    @property
    def pk(self) -> str:
        return f"CrawlJob#{self.job_id}"

    @property
    def sk(self) -> str:
        return f"Page#{self.url_hash}"

    def to_dynamo_item(self) -> dict[str, Any]:
        return convert_floats_to_decimals({
            "pk": self.pk,
            "sk": self.sk,
            "job_id": self.job_id,
            "created_by": self.created_by,
            "url": self.url,
            "url_hash": self.url_hash,
            "status": self.status.value,
            "page_metadata": self.page_metadata.model_dump(),
            "chunk_count": self.chunk_count,
            "timing": self.timing.model_dump(),
            "error": self.error,
            "crawled_at": self.crawled_at.isoformat(),
            "entity_type": "CrawledPage",
        })

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "CrawledPage":
        return cls(
            job_id=item["job_id"],
            created_by=item.get("created_by", ""),
            url=item["url"],
            url_hash=item["url_hash"],
            status=CrawledPageStatus(item["status"]),
            page_metadata=PageMetadata(**item.get("page_metadata", {})),
            chunk_count=item.get("chunk_count", 0),
            timing=PageTiming(**item.get("timing", {})),
            error=item.get("error"),
            crawled_at=datetime.fromisoformat(item["crawled_at"]),
        )

    def to_response(self) -> CrawledPageResponse:
        return CrawledPageResponse(
            url=self.url,
            status=self.status,
            page_metadata=self.page_metadata,
            chunk_count=self.chunk_count,
            timing=self.timing,
            error=self.error,
            crawled_at=self.crawled_at,
        )


class ContentChunk(BaseModel):
    """A chunk of content stored for vector search."""

    chunk_id: str = Field(default_factory=lambda: str(uuid4()))
    kb_id: str
    source_url: str
    page_title: Optional[str] = None
    chunk_index: int
    content: str
    word_count: int = 0
    parent_chunk_id: Optional[str] = None
    level: int = 0  # 0=document, 1=section, 2=paragraph
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def model_post_init(self, __context: Any) -> None:
        """Calculate word count if not set."""
        if self.word_count == 0 and self.content:
            self.word_count = len(self.content.split())

    @property
    def pk(self) -> str:
        return f"KnowledgeBase#{self.kb_id}"

    @property
    def sk(self) -> str:
        return f"Chunk#{self.chunk_id}"

    def to_dynamo_item(self) -> dict[str, Any]:
        return {
            "pk": self.pk,
            "sk": self.sk,
            "chunk_id": self.chunk_id,
            "kb_id": self.kb_id,
            "source_url": self.source_url,
            "page_title": self.page_title,
            "chunk_index": self.chunk_index,
            "content": self.content,
            "word_count": self.word_count,
            "parent_chunk_id": self.parent_chunk_id,
            "level": self.level,
            "created_at": self.created_at.isoformat(),
            "entity_type": "ContentChunk",
        }

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "ContentChunk":
        return cls(
            chunk_id=item["chunk_id"],
            kb_id=item["kb_id"],
            source_url=item["source_url"],
            page_title=item.get("page_title"),
            chunk_index=item["chunk_index"],
            content=item["content"],
            word_count=item.get("word_count", 0),
            parent_chunk_id=item.get("parent_chunk_id"),
            level=item.get("level", 0),
            created_at=datetime.fromisoformat(item["created_at"]),
        )

    def to_pinecone_metadata(self) -> dict[str, Any]:
        """Generate metadata for Pinecone vector."""
        return {
            "kb_id": self.kb_id,
            "chunk_id": self.chunk_id,
            "source_url": self.source_url,
            "page_title": self.page_title or "",
            "chunk_index": self.chunk_index,
            "level": self.level,
            "word_count": self.word_count,
        }


class ContentUpload(BaseModel):
    """Represents a content upload for a knowledge base."""

    upload_id: str = Field(default_factory=lambda: str(uuid4()))
    kb_id: str
    created_by: str
    filename: str
    content_type: Optional[str] = None
    size_bytes: int = 0
    metadata: Optional[str] = None
    chunk_count: int = 0
    vector_count: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def pk(self) -> str:
        return f"KnowledgeBase#{self.kb_id}"

    @property
    def sk(self) -> str:
        return f"Upload#{self.created_at.isoformat()}#{self.upload_id}"

    def to_dynamo_item(self) -> dict[str, Any]:
        return {
            "pk": self.pk,
            "sk": self.sk,
            "upload_id": self.upload_id,
            "kb_id": self.kb_id,
            "created_by": self.created_by,
            "filename": self.filename,
            "content_type": self.content_type,
            "size_bytes": self.size_bytes,
            "metadata": self.metadata,
            "chunk_count": self.chunk_count,
            "vector_count": self.vector_count,
            "created_at": self.created_at.isoformat(),
            "entity_type": "ContentUpload",
        }

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "ContentUpload":
        return cls(
            upload_id=item["upload_id"],
            kb_id=item["kb_id"],
            created_by=item.get("created_by", ""),
            filename=item.get("filename", ""),
            content_type=item.get("content_type"),
            size_bytes=item.get("size_bytes", 0),
            metadata=item.get("metadata"),
            chunk_count=item.get("chunk_count", 0),
            vector_count=item.get("vector_count", 0),
            created_at=datetime.fromisoformat(item["created_at"]),
        )

    def to_response(self) -> ContentUploadItemResponse:
        return ContentUploadItemResponse(
            upload_id=self.upload_id,
            kb_id=self.kb_id,
            filename=self.filename,
            content_type=self.content_type,
            size_bytes=self.size_bytes,
            metadata=self.metadata,
            chunk_count=self.chunk_count,
            vector_count=self.vector_count,
            created_by=self.created_by,
            created_at=self.created_at,
        )


class AgentKnowledgeBase(BaseModel):
    """Link table for many-to-many relationship between Agent and KnowledgeBase."""

    agent_id: str
    kb_id: str
    linked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    linked_by: str  # User email

    @property
    def pk(self) -> str:
        return f"Agent#{self.agent_id}"

    @property
    def sk(self) -> str:
        return f"KnowledgeBase#{self.kb_id}"

    @property
    def gsi2_pk(self) -> str:
        """GSI2 partition key for reverse lookup (KB -> Agents)."""
        return f"KnowledgeBase#{self.kb_id}"

    @property
    def gsi2_sk(self) -> str:
        """GSI2 sort key for reverse lookup."""
        return f"Agent#{self.agent_id}"

    def to_dynamo_item(self) -> dict[str, Any]:
        return {
            "pk": self.pk,
            "sk": self.sk,
            "gsi2_pk": self.gsi2_pk,
            "gsi2_sk": self.gsi2_sk,
            "agent_id": self.agent_id,
            "kb_id": self.kb_id,
            "linked_at": self.linked_at.isoformat(),
            "linked_by": self.linked_by,
            "entity_type": "AgentKnowledgeBase",
        }

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "AgentKnowledgeBase":
        return cls(
            agent_id=item["agent_id"],
            kb_id=item["kb_id"],
            linked_at=datetime.fromisoformat(item["linked_at"]),
            linked_by=item["linked_by"],
        )
