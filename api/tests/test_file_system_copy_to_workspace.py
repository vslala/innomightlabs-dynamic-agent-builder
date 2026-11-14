"""Copying a conversation's files into the workspace by id, so a script can use them (stitch generated images into a
PDF): found only in the caller's scope, numbered in the order given, and sent to the runner with its token."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import boto3
import httpx
import pytest

from src.config import settings
from src.documents.models import Document, OwnerKind
from src.documents.repository import DocumentRepository
from src.documents.storage import DocumentStorage
from src.messages.models import Message, MessageImage
from src.messages.repositories.factory import get_message_repository
from src.skills.file_system import actions
from src.skills.workspaces import workspace_id_from_context
from tests.documents_support import create_documents_bucket, pdf_with_text
from tests.mock_data import TEST_USER_EMAIL, account_for, user_id_for

ACCOUNT_ID = account_for(TEST_USER_EMAIL)
OWNER_ID = user_id_for(TEST_USER_EMAIL)
BUCKET = "innomightlabs-conversations-copy"
CONVERSATION_ID = "conversation-1"


def context(conversation_id: str = CONVERSATION_ID) -> dict:
    return {"account_id": ACCOUNT_ID, "owner_id": OWNER_ID, "owner_email": TEST_USER_EMAIL,
            "conversation_id": conversation_id, "agent_id": "agent-1"}


class FakeRunner:
    def __init__(self, status: int = 200) -> None:
        self.puts: list[tuple[dict, bytes, str]] = []
        self.status = status

    def __call__(self, request: httpx.Request) -> httpx.Response:
        query = {key: values[0] for key, values in parse_qs(urlparse(str(request.url)).query).items()}
        self.puts.append((query, request.content, request.headers["Authorization"]))
        if self.status != 200:
            return httpx.Response(self.status, json={"detail": "workspace_quota_exceeded"})
        return httpx.Response(200, json={"path": query["path"], "size_bytes": len(request.content)})


@pytest.fixture
def runner(monkeypatch) -> FakeRunner:
    fake = FakeRunner()
    monkeypatch.setattr(settings, "cli_runner_base_url", "https://runner.test")
    monkeypatch.setattr(settings, "cli_runner_shared_token", "runner-token")
    real = httpx.AsyncClient
    monkeypatch.setattr("src.skills.file_system.client.httpx.AsyncClient",
                        lambda **kwargs: real(**{**kwargs, "transport": httpx.MockTransport(fake)}))
    return fake


@pytest.fixture
def media(dynamodb_table, monkeypatch):
    monkeypatch.setattr("src.artifacts.storage.settings.conversation_media_bucket", BUCKET)
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket=BUCKET)
    return s3


def generated_image(s3, key: str, data: bytes, conversation_id: str = CONVERSATION_ID) -> str:
    s3.put_object(Bucket=BUCKET, Key=key, Body=data)
    image = MessageImage(s3_key=key, filename="generated.png", mime_type="image/png", size_bytes=len(data))
    get_message_repository().save(Message(conversation_id=conversation_id, created_by=TEST_USER_EMAIL,
                                          role="assistant", content="Generated image", images=[image]))
    return image.image_id


@pytest.mark.asyncio
async def test_generated_images_are_copied_in_the_order_given(media, runner):
    first = generated_image(media, "agents/a/c/1.png", b"\x89PNG one")
    second = generated_image(media, "agents/a/c/2.png", b"\x89PNG two")

    result = await actions.copy_to_workspace({"files": [second, first], "directory": "slides"}, {}, context())

    assert [item["path"] for item in result["copied"]] == ["slides/01.png", "slides/02.png"]
    assert [item["id"] for item in result["copied"]] == [second, first]
    assert [body for _, body, _ in runner.puts] == [b"\x89PNG two", b"\x89PNG one"]
    query, _, authorization = runner.puts[0]
    assert query["workspace_id"] == workspace_id_from_context(context()), "into this conversation's workspace only"
    assert authorization == "Bearer runner-token"


@pytest.mark.asyncio
async def test_an_attached_document_and_a_saved_file_can_be_copied(media, runner):
    from src.artifacts.models import Artifact
    from src.artifacts.repository import ArtifactRepository

    create_documents_bucket()
    document = Document(account_id=ACCOUNT_ID, owner_kind=OwnerKind.CONVERSATION, owner_id=CONVERSATION_ID,
                        filename="Brief.PDF", size_bytes=10)
    DocumentRepository().save(document)
    DocumentStorage().put_original(document, pdf_with_text("Brief"))
    key = f"accounts/{ACCOUNT_ID}/members/{OWNER_ID}/artifacts/data.csv"
    media.put_object(Bucket=BUCKET, Key=key, Body=b"a,b\n1,2\n")
    artifact = Artifact(account_id=ACCOUNT_ID, user_id=OWNER_ID, artifact_type="csv", title="data", filename="data.csv",
                        mime_type="text/csv", s3_key=key, size_bytes=8)
    ArtifactRepository().save(artifact)

    result = await actions.copy_to_workspace({"files": [document.document_id, artifact.artifact_id]}, {}, context())

    assert [item["path"] for item in result["copied"]] == ["files/01.pdf", "files/02.csv"]
    assert runner.puts[1][1] == b"a,b\n1,2\n"


@pytest.mark.asyncio
async def test_an_image_from_another_conversation_is_not_found_and_nothing_is_copied(media, runner):
    theirs = generated_image(media, "agents/a/other/1.png", b"\x89PNG theirs", conversation_id="someone-elses")

    with pytest.raises(ValueError, match="No file"):
        await actions.copy_to_workspace({"files": [theirs]}, {}, context())
    assert runner.puts == []


@pytest.mark.asyncio
async def test_a_full_workspace_is_explained(media, runner):
    runner.status = 413
    image = generated_image(media, "agents/a/c/big.png", b"\x89PNG big")

    with pytest.raises(ValueError, match="workspace is full"):
        await actions.copy_to_workspace({"files": [image]}, {}, context())


@pytest.mark.asyncio
async def test_files_are_required_and_bounded(media, runner):
    with pytest.raises(ValueError, match="at least one"):
        await actions.copy_to_workspace({"files": []}, {}, context())
    with pytest.raises(ValueError, match="at most 50"):
        await actions.copy_to_workspace({"files": [f"id-{n}" for n in range(51)]}, {}, context())
