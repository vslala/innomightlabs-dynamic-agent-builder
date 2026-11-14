"""Documents in social posts: which networks take them and why the others skip them, checking the file is what its name
says, LinkedIn's upload (register, send, wait until processed, post), and finding the document by id."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import boto3
import httpx
import pytest

from src.config import settings
from src.config.settings import SocialAppCredentials
from src.connectors.social import networks
from src.connectors.social.documents import SourceDocument, prepare_document
from src.connectors.social.models import SocialAccount
from src.connectors.social.networks import linkedin as linkedin_module
from src.connectors.social.networks.base import PublishError, PublishErrorKind
from src.connectors.social.networks.linkedin import DOCUMENT_LIMITS, LinkedInNetwork
from src.connectors.social.planning import plan_targets
from src.connectors.social.repository import SocialAccountRepository
from src.crypto import encrypt
from src.documents.models import Document, OwnerKind
from src.documents.repository import DocumentRepository
from src.documents.storage import DocumentStorage
from src.skills.social_media import actions
from tests.documents_support import create_documents_bucket, pdf_with_text
from tests.mock_data import TEST_USER_EMAIL, account_for, user_id_for

ACCOUNT_ID = account_for(TEST_USER_EMAIL)
OWNER_ID = user_id_for(TEST_USER_EMAIL)
BUCKET = "innomightlabs-conversations-documents"
CONVERSATION_ID = "conversation-1"
PDF = pdf_with_text("Quarterly results")


class Facts:
    def __init__(self, filename: str, size_bytes: int = 1000) -> None:
        self.filename, self.size_bytes = filename, size_bytes


def account(network: str) -> SocialAccount:
    return SocialAccount(account_id="acct-1", network=network, external_id="1", handle="@acme", display_name="Acme",
                         encrypted_credentials="sealed", connected_by="user-1")


def plan(network: str, document: Facts, images: int = 0) -> tuple[str | None, str]:
    [target] = plan_targets([account(network)], "Our results", image_count=images, document=document)
    return target.reason, target.detail


@pytest.fixture
def every_network(monkeypatch):
    monkeypatch.setattr(settings, "social_apps", {app: SocialAppCredentials("id", "secret") for app in
                                                  ("linked_in", "linked_in_pages", "facebook_pages", "threads")})


@pytest.mark.parametrize("network", ["linkedin", "linkedin_page"])
def test_linkedin_takes_a_pdf_or_slides(every_network, network):
    assert plan(network, Facts("results.pdf")) == (None, "")
    assert plan(network, Facts("deck.PPTX")) == (None, ""), "the extension's case doesn't matter"


@pytest.mark.parametrize(("network", "name"), [
    ("facebook_page", "Facebook Pages"), ("instagram", "Instagram"), ("threads", "Threads"),
])
def test_a_network_without_documents_tells_the_agent_so(every_network, network, name):
    assert plan(network, Facts("results.pdf")) == ("documents_not_supported", f"{name} can't post documents")


def test_a_document_is_checked_for_type_size_and_company(every_network):
    assert plan("linkedin", Facts("figures.xlsx")) == ("document_type_not_supported",
                                                       "LinkedIn takes PDF, PPTX, PPT, DOCX, DOC documents")
    assert plan("linkedin", Facts("huge.pdf", 101 * 1024 * 1024)) == ("document_too_large", "101.0 MB/100.0 MB")
    assert plan("linkedin", Facts("results.pdf"), images=1) == ("document_with_images",
                                                                "A post carries a document or images, not both")


def test_a_document_must_be_what_its_name_says():
    with pytest.raises(PublishError) as raised:
        prepare_document(SourceDocument(b"<html>not a pdf</html>", "results.pdf"), DOCUMENT_LIMITS)
    assert raised.value.kind == PublishErrorKind.REJECTED and "not a valid PDF" in str(raised.value)

    prepared = prepare_document(SourceDocument(PDF, "Q3 results.pdf"), DOCUMENT_LIMITS)
    assert (prepared.mime_type, prepared.title) == ("application/pdf", "Q3 results"), "the title defaults to the name"


class FakeLinkedIn:
    """LinkedIn's Documents and Posts APIs. The document reports PROCESSING once before it is AVAILABLE."""

    def __init__(self, final_status: str = "AVAILABLE") -> None:
        self.requests: list[httpx.Request] = []
        self.uploads: list[bytes] = []
        self.statuses = ["PROCESSING", final_status]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path == "/rest/documents" and request.method == "POST":
            return httpx.Response(200, json={"value": {"uploadUrl": "https://upload.linkedin.test/d/1",
                                                       "document": "urn:li:document:D1"}})
        if request.method == "PUT":
            self.uploads.append(request.content)
            return httpx.Response(201)
        if request.url.path.startswith("/rest/documents/"):
            return httpx.Response(200, json={"id": "urn:li:document:D1", "status": self.statuses.pop(0)})
        return httpx.Response(201, headers={"x-restli-id": "urn:li:share:1"})

    def posts(self) -> list[dict]:
        return [json.loads(r.content) for r in self.requests if r.url.path == "/rest/posts"]


@pytest.fixture
def linkedin(monkeypatch, dynamodb_table) -> FakeLinkedIn:
    fake = FakeLinkedIn()
    monkeypatch.setattr(networks, "NETWORKS", (LinkedInNetwork(transport=httpx.MockTransport(fake)),))
    monkeypatch.setattr(settings, "social_apps", {"linked_in": SocialAppCredentials("id", "secret")})
    monkeypatch.setattr(linkedin_module, "DOCUMENT_POLL_SECONDS", 0)
    SocialAccountRepository().connect(SocialAccount(
        account_id=ACCOUNT_ID, network="linkedin", external_id="member-1", handle="Ada", display_name="Ada",
        encrypted_credentials=encrypt(json.dumps({"access_token": "li-token", "person_urn": "urn:li:person:member-1"})),
        token_expires_at=datetime.now(timezone.utc) + timedelta(days=30), connected_by=OWNER_ID,
    ))
    return fake


@pytest.fixture
def media(dynamodb_table, monkeypatch):
    monkeypatch.setattr("src.artifacts.storage.settings.conversation_media_bucket", BUCKET)
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket=BUCKET)
    return s3


def context() -> dict:
    return {"account_id": ACCOUNT_ID, "owner_id": OWNER_ID, "owner_email": TEST_USER_EMAIL, "conversation_id": CONVERSATION_ID}


def saved_file(s3, filename: str, data: bytes) -> str:
    """A file the agent saved with upload_file."""
    from src.artifacts.models import Artifact
    from src.artifacts.repository import ArtifactRepository

    key = f"accounts/{ACCOUNT_ID}/members/{OWNER_ID}/artifacts/{filename}"
    s3.put_object(Bucket=BUCKET, Key=key, Body=data)
    artifact = Artifact(account_id=ACCOUNT_ID, user_id=OWNER_ID, artifact_type="file", title=filename,
                        filename=filename, mime_type="application/pdf", s3_key=key, size_bytes=len(data))
    ArtifactRepository().save(artifact)
    return artifact.artifact_id


@pytest.mark.asyncio
async def test_a_saved_pdf_is_uploaded_processed_and_posted_as_a_document(media, linkedin):
    document_id = saved_file(media, "q3-results.pdf", PDF)

    result = await actions.publish({"text": "Our Q3 results", "document": document_id,
                                    "document_title": "Q3 results"}, {}, context())

    assert result["status"] == "published"
    assert linkedin.uploads == [PDF], "sent as it is, never re-encoded"
    assert linkedin.posts()[0]["content"] == {"media": {"title": "Q3 results", "id": "urn:li:document:D1"}}
    status_checks = [r for r in linkedin.requests if r.method == "GET"]
    assert len(status_checks) == 2, "it waits until LinkedIn has processed the document before posting"


@pytest.mark.asyncio
async def test_a_document_linkedin_cannot_process_is_never_posted(media, linkedin):
    linkedin.statuses = ["PROCESSING_FAILED"]
    document_id = saved_file(media, "broken.pdf", PDF)

    result = await actions.publish({"text": "Broken", "document": document_id}, {}, context())

    [target] = result["targets"]
    assert (result["status"], target["reason"]) == ("failed", "rejected")
    assert "could not process the document" in target["detail"]
    assert linkedin.posts() == []


@pytest.mark.asyncio
async def test_a_document_attached_to_the_conversation_can_be_posted(linkedin):
    create_documents_bucket()
    document = Document(account_id=ACCOUNT_ID, owner_kind=OwnerKind.CONVERSATION, owner_id=CONVERSATION_ID,
                        filename="Pitch deck.pdf", size_bytes=len(PDF))
    DocumentRepository().save(document)
    DocumentStorage().put_original(document, PDF)

    result = await actions.publish({"text": "Our deck", "document": document.document_id}, {}, context())

    assert result["status"] == "published"
    assert linkedin.posts()[0]["content"]["media"]["title"] == "Pitch deck"


@pytest.mark.asyncio
async def test_a_document_from_another_conversation_is_not_found(linkedin):
    create_documents_bucket()
    theirs = Document(account_id=ACCOUNT_ID, owner_kind=OwnerKind.CONVERSATION, owner_id="someone-elses",
                      filename="secret.pdf", size_bytes=len(PDF))
    DocumentRepository().save(theirs)

    with pytest.raises(ValueError, match="No document"):
        await actions.publish({"text": "Stolen", "document": theirs.document_id}, {}, context())
    assert not linkedin.requests


@pytest.mark.asyncio
async def test_the_agent_sees_which_accounts_take_documents_and_the_person_sees_the_file(media, linkedin):
    document_id = saved_file(media, "q3-results.pdf", PDF)

    [described] = (await actions.accounts({}, {}, context()))["accounts"]
    assert described["document_formats"] == ["pdf", "pptx", "ppt", "docx", "doc"]

    checked = await actions.check({"text": "Ours", "document": document_id}, {}, context())
    assert checked["targets"][0]["can_post"] is True

    preview = await actions.publish_preview({"text": "Ours", "document": document_id, "document_title": "Q3"}, {}, context())
    [block] = [block for block in preview["blocks"] if block.get("label") == "Document"]
    assert [(item["label"], item["value"]) for item in block["items"]] == [("File", "q3-results.pdf"), ("Title", "Q3")]

