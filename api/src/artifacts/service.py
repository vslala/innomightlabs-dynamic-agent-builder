from __future__ import annotations

from typing import IO, Any

from src.artifacts.models import (
    Artifact,
    ArtifactBulkDeleteResponse,
    ArtifactDeletionFailure,
    ArtifactResponse,
    ArtifactSource,
    ArtifactType,
)
from src.artifacts.repository import ArtifactRepository
from src.artifacts.storage import ArtifactStorage, sanitize_filename
from src.config import settings
from src.conversations.repository import ConversationRepository
from src.skills.runtime_context import account_of, run_owner

VIEWABLE_ARTIFACT_TYPES = {"html_report", "video", "csv", "markdown", "json", "text", "code", "canvas"}
CONTENT_PROXY_ARTIFACT_TYPES = {"canvas", "html_report", "text", "markdown", "code", "json"}


class ArtifactNotFoundError(Exception):
    pass


class ArtifactDeletionError(Exception):
    def __init__(self) -> None:
        super().__init__("Artifact deletion failed")


class ArtifactNotViewableError(Exception):
    pass


class ArtifactService:
    def __init__(
        self,
        repository: ArtifactRepository | None = None,
        storage: ArtifactStorage | None = None,
    ):
        self.repository = repository or ArtifactRepository()
        self.storage = storage or ArtifactStorage()

    def create_artifact(
        self,
        *,
        account_id: str,
        user_id: str,
        artifact_type: ArtifactType,
        title: str,
        filename: str,
        mime_type: str,
        body: bytes | IO[bytes],
        source: ArtifactSource | None = None,
    ) -> ArtifactResponse:
        safe_filename = sanitize_filename(filename)
        size_bytes = len(body) if isinstance(body, bytes) else _file_size(body)
        artifact = Artifact(
            account_id=account_id,
            user_id=user_id,
            artifact_type=artifact_type,
            title=title.strip() or safe_filename,
            filename=safe_filename,
            mime_type=mime_type,
            s3_key="",
            size_bytes=size_bytes,
            source=source or ArtifactSource(),
        )
        artifact.s3_key = self.storage.build_key(
            account_id=account_id,
            user_id=user_id,
            artifact_id=artifact.artifact_id,
            filename=safe_filename,
        )
        self.storage.put_artifact(
            key=artifact.s3_key,
            body=body,
            content_type=mime_type,
        )
        return self.to_response(self.repository.save(artifact))

    def list_artifacts(self, partition: str, limit: int = 50) -> list[ArtifactResponse]:
        """A member's artifacts: `partition` is their member partition in the account."""
        return [self.to_response(item) for item in self.repository.list_in(partition, limit=limit)]

    def get_artifact(self, partition: str, artifact_id: str) -> ArtifactResponse:
        artifact = self._require_artifact(partition, artifact_id)
        return self.to_response(artifact)

    def delete_artifact(self, partition: str, artifact_id: str) -> None:
        try:
            artifact = self.repository.find_by_id(partition, artifact_id)
            if not artifact:
                return
            self.storage.delete_artifact(artifact.s3_key)
            self.repository.delete(artifact)
        except Exception as exc:
            raise ArtifactDeletionError() from exc

    def bulk_delete_artifacts(self, partition: str, artifact_ids: list[str]) -> ArtifactBulkDeleteResponse:
        result = ArtifactBulkDeleteResponse()
        for artifact_id in dict.fromkeys(artifact_ids):
            try:
                self.delete_artifact(partition, artifact_id)
                result.deleted_ids.append(artifact_id)
            except ArtifactDeletionError:
                result.failed.append(ArtifactDeletionFailure(
                    artifact_id=artifact_id, code="DELETE_FAILED", message="Artifact deletion failed"
                ))
        return result

    def download_url(self, partition: str, artifact_id: str) -> str:
        artifact = self._require_artifact(partition, artifact_id)
        return self.storage.presign_get_url(artifact.s3_key, filename=artifact.filename)

    def view_url(self, partition: str, artifact_id: str) -> str:
        artifact = self._require_artifact(partition, artifact_id)
        if not is_browser_viewable_artifact(artifact):
            raise ArtifactNotViewableError(artifact_id)
        return self._view_url(artifact)

    def get_content(self, partition: str, artifact_id: str) -> tuple[bytes, str]:
        artifact = self._require_artifact(partition, artifact_id)
        if artifact.artifact_type not in CONTENT_PROXY_ARTIFACT_TYPES:
            raise ArtifactNotViewableError(artifact_id)
        return self.storage.get_object_body(artifact.s3_key), artifact.mime_type

    def to_response(self, artifact: Artifact) -> ArtifactResponse:
        return ArtifactResponse(
            artifact_id=artifact.artifact_id,
            artifact_type=artifact.artifact_type,
            title=artifact.title,
            filename=artifact.filename,
            mime_type=artifact.mime_type,
            size_bytes=artifact.size_bytes,
            source=artifact.source,
            created_at=artifact.created_at,
            url=self.storage.presign_get_url(artifact.s3_key, filename=artifact.filename),
            view_url=self._artifact_page_url(artifact) if is_browser_viewable_artifact(artifact) else None,
        )

    def _require_artifact(self, partition: str, artifact_id: str) -> Artifact:
        artifact = self.repository.find_by_id(partition, artifact_id)
        if not artifact:
            raise ArtifactNotFoundError(artifact_id)
        return artifact

    def _view_url(self, artifact: Artifact) -> str:
        return self.storage.presign_get_url(
            artifact.s3_key,
            filename=artifact.filename,
            disposition="inline",
            content_type=artifact.mime_type,
        )

    def _artifact_page_url(self, artifact: Artifact) -> str:
        path = f"/dashboard/artifacts/{artifact.artifact_id}"
        if settings.frontend_url:
            return f"{settings.frontend_url.rstrip('/')}{path}"
        return path


def _file_size(file: IO[bytes]) -> int:
    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    return size


def is_browser_viewable_artifact(artifact: Artifact) -> bool:
    return artifact.artifact_type in VIEWABLE_ARTIFACT_TYPES


def run_artifact_holder(context: dict[str, Any]) -> tuple[str, str]:
    """(account_id, user_id) of the member whose artifact a skill run's file is: whoever's conversation it is (their
    own chat, even with a shared agent, or an automation's run). A key's, a visitor's or an A2A caller's run has no
    member of its own, so its files are the agent owner's."""
    account_id = account_of(context)
    conversation_id = str(context.get("conversation_id") or "").strip()
    conversation = ConversationRepository().get(conversation_id) if conversation_id else None
    if conversation and conversation.account_id == account_id and not conversation.created_by.startswith("secret-key:"):
        return account_id, conversation.created_by
    return account_id, run_owner(context).user_id
