"""Files in lead forms: a visitor uploads into the form's own file field, the capture keeps it, members download it."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import boto3
import jwt
import pytest
from botocore.exceptions import ClientError

from src.config import settings
from src.form_models import FormInput, FormInputType, FormInputValidation
from src.leads.errors import LeadsError
from src.leads.models import CreateLeadFormRequest
from src.leads.service import CaptureOrigin, LeadsService
from src.skills.models import ActorKind
from tests.mock_data import account_for
from tests.vision_support import create_media_bucket, create_memgpt_agent, png_bytes

PDF = b"%PDF-1.7\n1 0 obj << >> endobj\n%%EOF"
CLAIM_FORM = CreateLeadFormRequest(
    slug="claim",
    name="Damage claim",
    form_inputs=[
        FormInput(input_type=FormInputType.TEXT, name="name", label="Name"),
        FormInput(input_type=FormInputType.FILE_UPLOAD, name="evidence", label="Photo of the damage",
                  validation=FormInputValidation(max_items=2)),
    ],
)


def visitor_token(visitor_id: str, agent_id: str) -> str:
    return jwt.encode(
        {
            "aud": "widget_visitor", "sub": visitor_id, "email": f"{visitor_id}@example.com", "name": "Visitor",
            "picture": None, "agent_id": agent_id, "type": "widget_visitor", "kind": "google",
            "exp": datetime.now(timezone.utc) + timedelta(hours=4), "iat": datetime.now(timezone.utc),
        },
        "test-secret",
        algorithm="HS256",
    )


@pytest.fixture
def widget(test_client, auth_headers):
    create_media_bucket()
    agent_id = create_memgpt_agent(test_client, auth_headers)
    public_key = test_client.post(
        f"/agents/{agent_id}/api-keys", json={"name": "k", "allowed_origins": []}, headers=auth_headers
    ).json()["public_key"]
    LeadsService().create_form(account_for(), "owner-1", CLAIM_FORM)

    class Widget:
        account_id = account_for()

        def __init__(self) -> None:
            self.agent_id = agent_id

        def headers(self, visitor_id: str = "visitor-1") -> dict[str, str]:
            return {"X-API-Key": public_key, "Authorization": f"Bearer {visitor_token(visitor_id, agent_id)}"}

        def conversation(self, visitor_id: str = "visitor-1") -> str:
            return str(test_client.post("/widget/conversations", json={}, headers=self.headers(visitor_id)).json()[
                "conversation_id"])

        def upload(self, conversation_id: str, body: bytes = PDF, *, name: str = "report.pdf",
                   input_name: str = "evidence", visitor_id: str = "visitor-1"):
            return test_client.post(
                f"/widget/conversations/{conversation_id}/lead-files",
                data={"form": "claim", "input": input_name},
                files={"file": (name, body, "application/pdf")},
                headers=self.headers(visitor_id),
            )

        def origin(self, conversation_id: str, visitor_id: str = "visitor-1") -> CaptureOrigin:
            return CaptureOrigin(account_id=self.account_id, agent_id=agent_id, conversation_id=conversation_id,
                                 actor_kind=ActorKind.VISITOR, actor_id=visitor_id)

    return Widget()


def stored_keys() -> list[str]:
    listed = boto3.client("s3", region_name=settings.conversation_media_region).list_objects_v2(
        Bucket=settings.conversation_media_bucket
    )
    return sorted(item["Key"] for item in listed.get("Contents", []))


def test_an_upload_is_kept_with_the_capture_and_downloads_as_an_attachment(test_client, widget, auth_headers):
    conversation_id = widget.conversation()
    uploaded = widget.upload(conversation_id, name="../../My report.pdf")
    assert uploaded.status_code == 201, uploaded.text
    file_id = uploaded.json()["file_id"]
    assert uploaded.json()["filename"] == "My-report.pdf"

    capture = LeadsService().capture("claim", {"name": "Jane", "evidence": [file_id]}, widget.origin(conversation_id)).capture

    assert [file.file_id for file in capture.files] == [file_id]
    assert stored_keys() == [f"leads/{widget.account_id}/{capture.capture_id}/{file_id}.pdf"], "moved out of the chat"
    download = test_client.get(f"/leads/captures/{capture.capture_id}/files/{file_id}", headers=auth_headers)
    assert download.status_code == 200, download.text
    assert "attachment" in download.json()["url"]


def test_the_type_comes_from_the_bytes_not_the_name(widget):
    conversation_id = widget.conversation()

    refused = widget.upload(conversation_id, b"MZ\x90\x00 an executable", name="invoice.pdf")

    assert refused.status_code == 415
    assert refused.json()["detail"]["code"] == "FILE_TYPE"
    assert widget.upload(conversation_id, png_bytes(), name="photo.png").status_code == 201


def test_only_the_forms_file_fields_take_uploads(widget):
    conversation_id = widget.conversation()

    refused = widget.upload(conversation_id, input_name="name")

    assert refused.status_code == 422 and refused.json()["detail"]["code"] == "NOT_A_FILE_FIELD"


def test_files_are_limited_by_the_form(widget):
    conversation_id = widget.conversation()

    too_big = widget.upload(conversation_id, PDF + b"0" * (10 * 1024 * 1024))

    assert too_big.status_code == 413, "the form's default limit is 10 MB"
    assert too_big.json()["detail"]["code"] == "FILE_TOO_LARGE"


def test_a_visitor_cannot_capture_someone_elses_upload(widget):
    conversation_id = widget.conversation("visitor-1")
    file_id = widget.upload(conversation_id).json()["file_id"]

    with pytest.raises(LeadsError) as refused:
        LeadsService().capture("claim", {"name": "Mallory", "evidence": [file_id]},
                               widget.origin(conversation_id, visitor_id="visitor-2"))

    assert refused.value.code == "FILE_UNAVAILABLE"


def test_a_retried_capture_claims_its_files_once(widget):
    conversation_id = widget.conversation()
    file_id = widget.upload(conversation_id).json()["file_id"]
    answers = {"name": "Jane", "evidence": [file_id]}

    first = LeadsService().capture("claim", answers, widget.origin(conversation_id))
    again = LeadsService().capture("claim", answers, widget.origin(conversation_id))

    assert again.duplicate and again.capture.capture_id == first.capture.capture_id
    assert len(stored_keys()) == 1


def test_an_upload_already_used_by_another_capture_is_refused(widget):
    conversation_id = widget.conversation()
    file_id = widget.upload(conversation_id).json()["file_id"]
    LeadsService().capture("claim", {"name": "Jane", "evidence": [file_id]}, widget.origin(conversation_id))

    with pytest.raises(LeadsError) as refused:
        LeadsService().capture("claim", {"name": "Jane again", "evidence": [file_id]}, widget.origin(conversation_id))

    assert refused.value.code == "FILE_UNAVAILABLE"


def test_an_expired_upload_cannot_be_captured(widget, dynamodb_table):
    conversation_id = widget.conversation()
    file_id = widget.upload(conversation_id).json()["file_id"]
    dynamodb_table.update_item(Key={"pk": f"CONVERSATION#{conversation_id}", "sk": f"LEADFILE#{file_id}"},
                               UpdateExpression="SET #ttl = :past", ExpressionAttributeNames={"#ttl": "ttl"},
                               ExpressionAttributeValues={":past": 1})

    with pytest.raises(LeadsError) as refused:
        LeadsService().capture("claim", {"name": "Jane", "evidence": [file_id]}, widget.origin(conversation_id))

    assert refused.value.code == "FILE_UNAVAILABLE"


def test_deleting_a_capture_deletes_its_files(widget):
    conversation_id = widget.conversation()
    file_id = widget.upload(conversation_id).json()["file_id"]
    capture = LeadsService().capture("claim", {"name": "Jane", "evidence": [file_id]}, widget.origin(conversation_id)).capture

    LeadsService().delete_capture(widget.account_id, capture.capture_id)

    assert stored_keys() == []
    with pytest.raises(ClientError):
        boto3.client("s3", region_name=settings.conversation_media_region).head_object(
            Bucket=settings.conversation_media_bucket, Key=capture.files[0].storage_key(widget.account_id, capture.capture_id)
        )
