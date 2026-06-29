from __future__ import annotations

from src.artifacts.models import Artifact, ArtifactResponse, ArtifactSource, ArtifactType
from src.artifacts.repository import ArtifactRepository
from src.artifacts.storage import ArtifactStorage, sanitize_filename
from src.config import settings

VIEWABLE_ARTIFACT_TYPES = {"html_report", "csv", "markdown", "json", "text", "code"}


class ArtifactNotFoundError(Exception):
    pass


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
        owner_email: str,
        artifact_type: ArtifactType,
        title: str,
        filename: str,
        mime_type: str,
        body: bytes,
        source: ArtifactSource | None = None,
    ) -> ArtifactResponse:
        safe_filename = sanitize_filename(filename)
        artifact = Artifact(
            owner_email=owner_email,
            artifact_type=artifact_type,
            title=title.strip() or safe_filename,
            filename=safe_filename,
            mime_type=mime_type,
            s3_key="",
            size_bytes=len(body),
            source=source or ArtifactSource(),
        )
        artifact.s3_key = self.storage.build_key(
            owner_email=owner_email,
            artifact_id=artifact.artifact_id,
            filename=safe_filename,
        )
        self.storage.put_artifact(
            key=artifact.s3_key,
            body=body,
            content_type=mime_type,
        )
        return self.to_response(self.repository.save(artifact))

    def list_artifacts(self, owner_email: str, limit: int = 50) -> list[ArtifactResponse]:
        return [self.to_response(item) for item in self.repository.list_by_user(owner_email, limit=limit)]

    def get_artifact(self, owner_email: str, artifact_id: str) -> ArtifactResponse:
        artifact = self._require_artifact(owner_email, artifact_id)
        return self.to_response(artifact)

    def download_url(self, owner_email: str, artifact_id: str) -> str:
        artifact = self._require_artifact(owner_email, artifact_id)
        return self.storage.presign_get_url(artifact.s3_key, filename=artifact.filename)

    def view_url(self, owner_email: str, artifact_id: str) -> str:
        artifact = self._require_artifact(owner_email, artifact_id)
        if not is_browser_viewable_artifact(artifact):
            raise ArtifactNotViewableError(artifact_id)
        return self._view_url(artifact)

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

    def _require_artifact(self, owner_email: str, artifact_id: str) -> Artifact:
        artifact = self.repository.find_by_id(owner_email, artifact_id)
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


def is_browser_viewable_artifact(artifact: Artifact) -> bool:
    return artifact.artifact_type in VIEWABLE_ARTIFACT_TYPES
