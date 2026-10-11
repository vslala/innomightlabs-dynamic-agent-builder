from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from src.accounts.owner import member_partition


ArtifactType = Literal["html_report", "image", "file", "csv", "markdown", "json", "text", "code", "canvas"]


class ArtifactSource(BaseModel):
    skill_id: str | None = None
    agent_id: str | None = None
    automation_id: str | None = None
    automation_run_id: str | None = None
    automation_node_id: str | None = None
    conversation_id: str | None = None
    message_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Artifact(BaseModel):
    """A file a run produced: private to the member it belongs to, in one account."""

    artifact_id: str = Field(default_factory=lambda: str(uuid4()))
    account_id: str
    #: The member it belongs to
    user_id: str
    artifact_type: ArtifactType
    title: str
    filename: str
    mime_type: str
    s3_key: str
    size_bytes: int
    source: ArtifactSource = Field(default_factory=ArtifactSource)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def pk(self) -> str:
        return member_partition(self.account_id, self.user_id)

    @property
    def sk(self) -> str:
        return f"Artifact#{self.created_at.isoformat()}#{self.artifact_id}"

    @property
    def gsi2_pk(self) -> str:
        return f"Artifact#{self.artifact_id}"

    @property
    def gsi2_sk(self) -> str:
        return self.pk

    def to_dynamo_item(self) -> dict[str, Any]:
        return {
            "pk": self.pk,
            "sk": self.sk,
            "gsi2_pk": self.gsi2_pk,
            "gsi2_sk": self.gsi2_sk,
            "entity_type": "Artifact",
            "artifact_id": self.artifact_id,
            "account_id": self.account_id,
            "user_id": self.user_id,
            "artifact_type": self.artifact_type,
            "title": self.title,
            "filename": self.filename,
            "mime_type": self.mime_type,
            "s3_key": self.s3_key,
            "size_bytes": self.size_bytes,
            "source": self.source.model_dump(mode="json"),
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "Artifact":
        return cls(
            artifact_id=item["artifact_id"],
            account_id=item["account_id"],
            user_id=item["user_id"],
            artifact_type=item["artifact_type"],
            title=item.get("title", item.get("filename", "Artifact")),
            filename=item["filename"],
            mime_type=item["mime_type"],
            s3_key=item["s3_key"],
            size_bytes=int(item.get("size_bytes", 0)),
            source=ArtifactSource.model_validate(item.get("source") or {}),
            created_at=datetime.fromisoformat(item["created_at"]),
        )


class ArtifactResponse(BaseModel):
    artifact_id: str
    artifact_type: ArtifactType
    title: str
    filename: str
    mime_type: str
    size_bytes: int
    source: ArtifactSource
    created_at: datetime
    url: str | None = None
    view_url: str | None = None


class ArtifactListResponse(BaseModel):
    items: list[ArtifactResponse]


class ArtifactBulkDeleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_ids: list[Annotated[str, StringConstraints(strict=True, min_length=1, max_length=128)]] = Field(
        min_length=1, max_length=100
    )


class ArtifactDeletionFailure(BaseModel):
    artifact_id: str
    code: Literal["DELETE_FAILED"]
    message: str


class ArtifactBulkDeleteResponse(BaseModel):
    deleted_ids: list[str] = Field(default_factory=list)
    failed: list[ArtifactDeletionFailure] = Field(default_factory=list)
